"""The meeting actions (HACKATHON.md stage 1, ADR-055 proposed), each a Guardian action run in its own program.

    meeting.read    (High)    read one meeting file from your work folder - a recording Gemini writes down, or a transcript
                              (Teams/Zoom/Meet .vtt, .srt, .txt) - and pull out its decisions, owners, deadlines and open
                              questions with Gemini; only the file you approved (its sha256), only to Gemini
    meeting.record  (High)    record a meeting from the mic, in memory only, until you say "end the meeting" (or after
                              `minutes`); then the same as meeting.read on that recording. No sound is written to disk
    meeting.stop    (Low)     end the recording: meeting.record hands what it heard to Gemini
    meeting.show    (Low)     what came out of a meeting, in a few lines (read only)
    meeting.forget  (Medium)  delete a meeting, its transcript and its items from data/meetings.db

None of them runs anything that came out of a meeting: decisions and actions are data, kept in data/meetings.db for you to
see. Splitting them into work (stage 3) is its own action, shown first and decided by Guardian.
"""

import hashlib
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from kairu.meeting import hear, read
from kairu.meeting.store import MeetingStore, exists
from kairu.tasks import fence
from kairu.tasks.actions import _say
from kairu.worker import FAILED, REFUSED

STOP_FILE = "meeting.stop"  # in the data folder: meeting.stop asks meeting.record to end
LIVE_FILE = "meeting-live.json"  # in the data folder: how long the recording has run (numbers only, never sound or words)
MOST_RECORD_MINUTES = 120
LEAST_RECORD_SECONDS = 5
SHOWN = 4  # items of each kind in the spoken or typed answer; the workspace's Meetings page shows them all


class Stop(Exception):
    """Why the action ends without a meeting; its words are what to tell you."""

    def __init__(self, words: str, failed: bool = False):
        super().__init__(words)
        self.failed = failed


def _held(held: str) -> date:
    try:
        return datetime.strptime(held.strip(), "%Y-%m-%d").date() if held.strip() else date.today()
    except ValueError:
        raise Stop("A meeting's day looks like 2026-11-21.") from None


def _guarded(data_dir: str, job: str, work) -> int | None:
    try:
        _say(data_dir, job, True, work())
    except Stop as stop:
        _say(data_dir, job, False, str(stop))
        return FAILED if stop.failed else REFUSED
    except (read.NotAMeeting, read.NoReading, hear.HearingProblem) as problem:
        _say(data_dir, job, False, f"Not read: {problem}.")
        return FAILED
    return None


def _gateway(data_dir: str, brain: dict | None):
    from kairu.brain.gateway import Gateway
    return Gateway(data_dir, brain)


def _ask(gateway, instructions: str, text: str, media: dict | None = None, json_answer: bool = False) -> tuple[str, str]:
    from kairu.brain.gateway import ANSWERED
    result = gateway.meeting(instructions, text, media=media, json_answer=json_answer)
    if result.status != ANSWERED:
        raise Stop(f"Not read: {result.text}", failed=True)
    return result.text, result.provider


def understand(data_dir: str, brain: dict | None, lines: list[str], held: date, title: str, file: str, sha: str, heard: str,
               minutes: float | None, started: float, gateway=None) -> int:
    """The transcript's lines (secrets are left out here) -> Gemini's decisions, actions and questions -> data/meetings.db."""
    lines, count = read.left_out(lines)
    text = read.joined(lines)
    gateway = gateway or _gateway(data_dir, brain)
    answer, provider = _ask(gateway, read.instructions(held, title), f"Meeting transcript:\n{text}", json_answer=True)
    reading = read.parse(answer, text, held)
    name = title or reading["title"] or (Path(file).stem.replace("_", " ").replace("-", " ") if file else "Meeting")
    return MeetingStore(data_dir).add(name[:read.LONGEST_TITLE], held.isoformat(), file, sha, heard, lines, reading,
                                      minutes, count, provider, round(time.time() - started, 1))


def _hear(data_dir: str, brain: dict | None, data: bytes, mime: str, gateway=None) -> list[str]:
    """A recording -> Gemini's transcript lines. The upload, if there was one, is deleted from Google right after."""
    gateway = gateway or _gateway(data_dir, brain)
    part = hear.media_part(data_dir, data, mime)
    try:
        text, _ = _ask(gateway, read.HEAR, "Transcribe this meeting recording.", media=part)
    finally:
        hear.forget_upload(data_dir, part)
    return read.transcript_answer(text)


# --- meeting.read ------------------------------------------------------------------------------------------------

def file_of(work_folder: str, file: str) -> tuple[Path, bytes]:
    try:
        place = fence.inside(fence.work_folder(work_folder), file)
    except fence.OutsideFolder as problem:
        raise Stop(f"Refused: {problem}.") from None
    if not place.is_file():
        raise Stop(f"Not read: there's no file {file[:80]} in your work folder.")
    kind = read.kind_of(place.name)
    most = read.MOST_AUDIO_BYTES if kind == "audio" else read.MOST_TEXT_BYTES
    if place.stat().st_size > most:
        raise Stop(f"Not read: {place.name} is over {most // (1024 * 1024)} MB.")
    return place, place.read_bytes()


def sha_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_meeting(data_dir: str, job: str, file: str, sha: str, title: str, held: str, brain: dict | None = None,
                 work_folder: str = "") -> int | None:
    """meeting.read: exactly the file you approved (its sha256 is in the approval), heard and read by Gemini only."""
    def work() -> str:
        started = time.time()
        day = _held(held)
        place, data = file_of(work_folder, file)
        if sha_of(data) != sha:
            raise Stop(f"Not read: {place.name} changed after you approved it. Ask again.")
        if read.kind_of(place.name) == "audio":
            lines, heard, minutes = _hear(data_dir, brain, data, read.mime_of(place.name)), "gemini", hear.minutes_of(place.name, data)
        else:
            lines, heard, minutes = read.transcript_of(place.name, data), "transcript", None
        number = understand(data_dir, brain, lines, day, title.strip(), file, sha, heard, minutes, started)
        return told(MeetingStore(data_dir).meeting(number))
    return _guarded(data_dir, job, work)


# --- meeting.record / meeting.stop ----------------------------------------------------------------------------------

def _live(data_dir: str, state: dict | None) -> None:
    path = Path(data_dir) / LIVE_FILE
    try:
        if state is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def live(data_dir) -> dict | None:
    """{"started", "seconds", "level", "title"} while meeting.record is listening, else None (the bar and the workspace)."""
    try:
        found = json.loads((Path(data_dir) / LIVE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or time.time() - float(found.get("now", 0)) > 10:
        return None  # a recording that ended without tidying up (an emergency stop ends its program)
    return found


def _level(chunk: bytes) -> int:
    """How loud this tenth of a second was, 0 to 100 (for the moving dot only)."""
    if len(chunk) < 2:
        return 0
    samples = memoryview(chunk[: len(chunk) // 2 * 2]).cast("h")
    peak = max(abs(value) for value in samples[::8]) if len(samples) else 0
    return min(100, int(peak * 100 / 12000))


def record(data_dir: str, job: str, title: str, minutes: float, held: str = "", brain: dict | None = None,
           open_mic=None, clock=time.time) -> int | None:
    """meeting.record: the mic, in memory only, until meeting.stop (or `minutes`, at most MOST_RECORD_MINUTES); then Gemini
    writes it down and pulls out the items. An emergency stop ends it at once, and what was heard is gone with it."""
    def work() -> str:
        day = _held(held)
        longest = max(1.0, min(float(minutes or 60), MOST_RECORD_MINUTES)) * 60
        stop = Path(data_dir) / STOP_FILE
        stop.unlink(missing_ok=True)
        from kairu.voice import mic as mics
        try:
            source = (open_mic or mics.open_mic)()
        except mics.MicProblem as problem:
            raise Stop(f"Not recorded: {problem}") from None
        started, sound, level = clock(), bytearray(), 0
        try:
            while clock() - started < longest and not stop.exists():
                chunk = source.read()
                if not chunk:
                    break
                sound += chunk
                level = max(int(level * 0.6), _level(chunk))
                if len(sound) % (mics.CHUNK_BYTES * 5) < mics.CHUNK_BYTES:  # about twice a second
                    _live(data_dir, {"started": started, "now": time.time(), "seconds": round(clock() - started, 1),
                                     "level": level, "title": title[:read.LONGEST_TITLE]})
        finally:
            source.close()
            stop.unlink(missing_ok=True)
            _live(data_dir, None)
        seconds = len(sound) / (hear.RATE * 2)
        if seconds < LEAST_RECORD_SECONDS:
            raise Stop(f"Not read: the recording was only {seconds:.0f} seconds long.")
        data = hear.wav(bytes(sound))
        del sound
        lines = _hear(data_dir, brain, data, "audio/wav")
        number = understand(data_dir, brain, lines, day, title.strip(), "", sha_of(data), "mic", round(seconds / 60, 1),
                            started)
        return told(MeetingStore(data_dir).meeting(number))
    return _guarded(data_dir, job, work)


def stop_recording(data_dir: str, job: str) -> int | None:
    def work() -> str:
        if live(data_dir) is None:
            return "No meeting is being recorded."
        (Path(data_dir) / STOP_FILE).write_text("stop", encoding="utf-8")
        return "Ending the recording: Gemini is writing it down now."
    return _guarded(data_dir, job, work)


# --- meeting.show / meeting.forget ----------------------------------------------------------------------------------

def _due(item: dict) -> str:
    if item["due"]:
        day = datetime.strptime(item["due"], "%Y-%m-%d")
        return f"by {day.strftime('%a')} {day.day} {day.strftime('%b')}"
    return f"({item['due_said']})" if item["due_said"] else ""


def line_of(item: dict) -> str:
    who = item["owner"] or ("nobody yet" if item["kind"] == "action" else "")
    bits = [item["what"].rstrip(".")]
    if who:
        bits.append(f"→ {who}")
    if _due(item):
        bits.append(_due(item))
    return " ".join(bits)


def told(meeting: dict | None) -> str:
    """A meeting in a few lines: the counts first (Tenmin: answer first), then the decisions, actions and questions."""
    if meeting is None:
        return "There's no meeting with that number."
    items = meeting["items"]
    kinds = {kind: [item for item in items if item["kind"] == kind] for kind in ("decision", "action", "question")}
    nobody = [item for item in kinds["action"] if not item["owner"]]
    undated = [item for item in kinds["action"] if not item["due"] and not item["due_said"]]
    day = datetime.strptime(meeting["held"], "%Y-%m-%d")
    counts = (f"{len(kinds['decision'])} decision{'s' if len(kinds['decision']) != 1 else ''}, "
              f"{len(kinds['action'])} action{'s' if len(kinds['action']) != 1 else ''}, "
              f"{len(kinds['question'])} open question{'s' if len(kinds['question']) != 1 else ''}")
    out = [f"Meeting {meeting['number']} read: {meeting['title']} ({day.day} {day.strftime('%b')}). {counts}."]
    if nobody:
        out.append(f"{len(nobody)} action{' has' if len(nobody) == 1 else 's have'} no owner yet.")
    if undated:
        out.append(f"{len(undated)} action{' has' if len(undated) == 1 else 's have'} no deadline.")
    for kind, label in (("decision", "Decided"), ("action", "To do"), ("question", "Open")):
        if kinds[kind]:
            shown = "; ".join(line_of(item) for item in kinds[kind][:SHOWN])
            more = len(kinds[kind]) - SHOWN
            out.append(f"{label}: {shown}{f'; and {more} more' if more > 0 else ''}.")
    if meeting.get("left_out"):
        out.append(f"({meeting['left_out']} line{'s' if meeting['left_out'] != 1 else ''} with a secret left out on this PC.)")
    out.append("All of it is on the Meetings page of the workspace (kairu workspace), with the words that show each one.")
    return "\n".join(out)


def show(data_dir: str, job: str, meeting: float = 0) -> int | None:
    def work() -> str:
        if not exists(data_dir):
            return "No meetings yet. Put a recording or transcript in your work folder and say: read the meeting NAME."
        store = MeetingStore(data_dir)
        number = int(meeting) or store.latest()
        if not number:
            return "No meetings yet. Put a recording or transcript in your work folder and say: read the meeting NAME."
        return told(store.meeting(number)).replace(" read:", ":", 1)
    return _guarded(data_dir, job, work)


def forget(data_dir: str, job: str, meeting: float) -> int | None:
    def work() -> str:
        if not exists(data_dir) or not MeetingStore(data_dir).forget(int(meeting)):
            raise Stop(f"There's no meeting {int(meeting)}.")
        return f"Forgot meeting {int(meeting)}: its transcript and everything that came out of it."
    return _guarded(data_dir, job, work)


if __name__ == "__main__":  # pragma: no cover
    print("Run through Guardian: kairu meeting ...", file=sys.stderr)
    raise SystemExit(2)
