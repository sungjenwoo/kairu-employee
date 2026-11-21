"""The meeting orders, said or typed in the bar, the workspace or to Kairu Live (HACKATHON.md stage 1, ADR-055 proposed).

    "read the meeting kickoff.txt"        meeting.read (High): the card shows the file and its sha256; Gemini hears or reads it
    "transcribe the meeting standup.mp3"  (the same; a name without its ending is looked for in the work folder and its
                                           meetings folder)
    "record the meeting [called X]"       meeting.record (High): the mic, in memory only; it runs on after the answer
    "end the meeting"                     meeting.stop (Low)
    "show the last meeting" / "what did we decide in the meeting" / "show meeting 2"   meeting.show (Low)

Like the team orders, at Main Kairu's own PC only: a phone or another Kairu never reads or records a meeting here. This file
holds no authority: each order is a Guardian action through the task core, and High waits for "yes" and your PIN.
"""

import re
import secrets
from pathlib import Path

from kairu import channel
from kairu.guardian import Action, Refused, Verdict

READ = re.compile(r"(?:read|transcribe|process|go through|summari[sz]e|take notes (?:of|from|on)|pull (?:out )?(?:the )?"
                  r"(?:decisions|tasks|actions) (?:from|of|in))(?: the| my| our| this| that)? (?:meeting|call|standup|stand-up|"
                  r"sync)(?: (?:file|recording|transcript|notes|audio|video))?(?: called| named| in| from)?[: ]+(?P<file>\S.{0,199})",
                  re.I)
RECORD = re.compile(r"(?:record|start recording|listen to|join)(?: the| this| our| my| a)? (?:meeting|call|standup|stand-up)"
                    r"(?: (?:called|named|about|for) (?P<title>.{1,80}))?", re.I)
END = re.compile(r"(?:end|stop|finish|wrap up)(?: the| this| our)? (?:meeting|call|recording|meeting recording|standup)"
                 r"(?: recording)?", re.I)
SHOW = re.compile(r"(?:show|open|tell me|what came out of|what (?:was|did we) decide(?:d)? in|summary of|recap)(?: me)?"
                  r"(?: the| our)? (?:(?:last|latest|previous|newest) )?(?:meeting|call)(?: (?P<number>\d{1,6}))?\??", re.I)
SECONDS = 420  # a long recording: the upload, Gemini writing it down, and Gemini reading it


def find(work_folder, said: str) -> str:
    """The meeting file this name means, as a name inside the work folder: exactly it, or in the meetings folder, or a
    recording or transcript whose name without its ending is this. "" if none (or more than one) fits."""
    from kairu.meeting import read
    from kairu.tasks import fence
    said = said.strip().strip("\"'“”")
    folder = fence.work_folder(work_folder)
    for name in (said, f"meetings/{said}"):
        try:
            place = fence.inside(folder, name)
        except fence.OutsideFolder:
            return ""
        if place.is_file():
            return name
    stem = Path(said).stem.lower()
    found = []
    for where in (folder, folder / "meetings"):
        if where.is_dir():
            for place in where.iterdir():
                try:
                    read.kind_of(place.name)
                except read.NotAMeeting:
                    continue
                if place.is_file() and place.stem.lower() == stem:
                    found.append(place.relative_to(folder).as_posix())
    return found[0] if len(found) == 1 else ""


def handle(core, text: str) -> str | None:
    read_it, record, end, show = READ.fullmatch(text), RECORD.fullmatch(text), END.fullmatch(text), SHOW.fullmatch(text)
    if not (read_it or record or end or show):
        return None
    if core.source != "pc":
        return "Meetings are read and recorded at Main Kairu's own PC."
    from kairu.tasks.core import Step
    if end:
        return core._run_step(Step("meeting.stop", {}))[1]
    if show:
        number = float(show.group("number") or 0)
        return core._run_step(Step("meeting.show", {"meeting": number}))[1]
    if record:
        return _record(core, (record.group("title") or "").strip(" .,"))
    from kairu.meeting import conduct, read
    name = find(core.cfg.work_folder, read_it.group("file"))
    if not name:
        return (f"I couldn't find the meeting {read_it.group('file')[:60]} in your work folder ({core.cfg.work_folder}). "
                "Put the recording or transcript there (or in its meetings folder) and say its name.")
    try:
        place, data = conduct.file_of(str(core.cfg.work_folder), name)
    except (conduct.Stop, read.NotAMeeting) as problem:
        return str(problem)
    core._tell({"kind": "thinking"})
    details = {"file": name, "sha": conduct.sha_of(data), "title": "", "held": ""}
    return core._run_step(Step("meeting.read", details))[1]


def _record(core, title: str) -> str:
    """meeting.record runs on after this answer (like "start the project"): its card first, then it listens until "end the
    meeting"."""
    action = Action("meeting.record", {"job": secrets.token_hex(8), "title": title, "minutes": 60.0, "held": ""})
    try:
        decision = core.client.check(action)
        if decision.verdict is Verdict.DENY:
            return f"Guardian refused meeting.record: {decision.reason.rstrip('.')}."
        granted = None
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            try:
                granted = core.approver(decision)
            except Refused as refusal:
                return f"Not recording: {str(refusal).rstrip('.')}."
            if granted is None:
                return "Not recording: you refused it. The mic stayed off."
        core.client.run(action, granted)
    except Refused as refusal:
        return f"Not recording: {str(refusal).rstrip('.')}."
    except channel.ChannelError:
        return "Guardian is not running."
    return "Recording the meeting, in memory only. Say \"end the meeting\" when it's over, and I'll pull out the decisions."
