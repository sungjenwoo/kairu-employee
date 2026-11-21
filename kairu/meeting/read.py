"""Meeting in (HACKATHON.md stage 1): what a meeting file is, what Gemini is told, and how its answers are read.

    kind_of(name)                    "audio" (a recording: mp3, wav, m4a, ogg, flac, aac, mp4, webm, mov) or "text" (a
                                     transcript: txt, md, vtt, srt), from the file's ending; anything else is not a meeting
    transcript_of(name, raw)         a transcript file as tidy lines "[mm:ss] Name: words" (Teams/Zoom/Meet .vtt, .srt, text)
    left_out(lines)                  each line with a secret replaced by a marker, so a secret is never kept or sent
    HEAR                             what Gemini is told when it writes a recording down
    instructions(held, title)        what Gemini is told when it pulls out decisions, actions and open questions
    parse(text, transcript, held)    Gemini's answer, read strictly: JSON only, each item short text, a deadline only as a
                                     real date, every quote checked against the transcript (a quote that isn't there is
                                     marked "not heard", never shown as evidence)

The answer is only data: nothing in it runs. The items go to data/meetings.db (kairu/meeting/store.py) for you to see;
the next stages (the decision ledger, the conflict check, the split to Clones) read them from there.
"""

import json
import re
from datetime import date, datetime, timedelta

from kairu.brain import privacy

AUDIO = {".mp3": "audio/mp3", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg",
         ".oga": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".aiff": "audio/aiff", ".mp4": "video/mp4",
         ".webm": "video/webm", ".mov": "video/quicktime", ".mpeg": "video/mpeg", ".mpg": "video/mpeg"}
TEXT = (".txt", ".md", ".vtt", ".srt")
MOST_AUDIO_BYTES = 300 * 1024 * 1024  # about 5 hours of a phone's recording; Gemini's Files API takes up to 2 GB
MOST_TEXT_BYTES = 2 * 1024 * 1024
MOST_TRANSCRIPT = 400_000  # characters kept and sent (about 4 hours of talk)
MOST_ITEMS = 40  # of each kind
LONGEST_ITEM = 300
LONGEST_QUOTE = 300
LONGEST_NAME = 40
LONGEST_SUMMARY = 900
LONGEST_TITLE = 80
SECRET_LINE = "[a line with a secret was left out on this PC]"
SURE = ("high", "medium", "low")
MERGE_UNDER = 160  # one speaker's short cues become one line until it is this long (a quote's time stays close)


class NotAMeeting(Exception):
    pass


class NoReading(Exception):
    pass


def kind_of(name: str) -> str:
    lower = name.lower()
    for ending in AUDIO:
        if lower.endswith(ending):
            return "audio"
    if lower.endswith(TEXT):
        return "text"
    raise NotAMeeting(f"{name[-40:]} isn't a meeting file: a recording (mp3, wav, m4a, ogg, mp4, webm ...) or a transcript "
                      "(txt, md, vtt, srt)")


def mime_of(name: str) -> str:
    lower = name.lower()
    for ending, mime in AUDIO.items():
        if lower.endswith(ending):
            return mime
    raise NotAMeeting(f"{name[-40:]} isn't a recording Gemini can hear")


# --- a transcript file ----------------------------------------------------------------------------------------

STAMP = re.compile(r"^(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\s*-->\s*(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?.*$")
VOICE = re.compile(r"^<v(?:\.[^ >]*)?\s+([^>]{1,60})>(.*?)(?:</v>)?$")
TAG = re.compile(r"</?[a-z][^>]{0,40}>", re.I)


def _clock(stamp: str) -> str:
    """'00:01:05.120' or '01:05,120' -> '01:05' (an hour or more: '1:01:05')."""
    parts = [float(part.replace(",", ".")) for part in stamp.split(":")]
    seconds = int(sum(part * 60 ** index for index, part in enumerate(reversed(parts))))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60:02d}:{rest % 60:02d}"


def _cues(lines: list[str]) -> list[tuple[str, str]]:
    """(when, words) for each cue of a .vtt or .srt file; the cue numbers, the header and notes are dropped."""
    out, when, words = [], "", []

    def close():
        if words:
            out.append((when, " ".join(words)))
    for line in lines:
        line = line.strip("﻿ \t")
        if STAMP.match(line):
            close()
            when, words = _clock(line.split("-->")[0].strip()), []
        elif not line:
            close()
            words = []
        elif line.isdigit() and not words:
            continue
        elif line.startswith(("WEBVTT", "NOTE", "STYLE", "Kind:", "Language:")) and not words:
            continue
        else:
            words.append(line)
    close()
    return out


def transcript_of(name: str, raw: bytes) -> list[str]:
    """The transcript as lines "[mm:ss] Name: words" (or as written, for a plain text). Consecutive cues of one speaker are
    joined into one line, so a Teams file of 2-second cues reads like a conversation."""
    if len(raw) > MOST_TEXT_BYTES:
        raise NotAMeeting(f"that transcript is over {MOST_TEXT_BYTES // (1024 * 1024)} MB")
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lower = name.lower()
    if lower.endswith((".vtt", ".srt")):
        lines, speaker = [], None
        for when, words in _cues(text.split("\n")):
            found = VOICE.match(words)
            who = found.group(1).strip() if found else ""
            words = TAG.sub("", found.group(2) if found else words).strip()
            if not who:
                said = re.match(r"^([A-Z][\w.' -]{0,38}):\s+(.+)$", words)
                if said:
                    who, words = said.group(1).strip(), said.group(2).strip()
            if not words:
                continue
            if lines and who and who == speaker and len(lines[-1]) < MERGE_UNDER:
                lines[-1] += " " + words
                continue
            speaker = who or speaker
            lines.append(f"[{when}] {who}: {words}" if who else f"[{when}] {words}")
    else:
        lines = [" ".join(line.split()) for line in text.split("\n")]
        lines = [line for line in lines if line]
    if not lines:
        raise NotAMeeting("that transcript has no words")
    return lines


def left_out(lines: list[str]) -> tuple[list[str], int]:
    """Each line with a secret (a password, a key, a card number ...) replaced by SECRET_LINE: a secret is never kept in
    data/meetings.db and never sent. Returns the lines and how many were left out."""
    out, count = [], 0
    for line in lines:
        if privacy.secrets_in(line):
            out.append(SECRET_LINE)
            count += 1
        else:
            out.append(line)
    return out, count


def joined(lines: list[str]) -> str:
    text = "\n".join(lines)
    if len(text) > MOST_TRANSCRIPT:
        raise NotAMeeting(f"that meeting is longer than Kairu reads at once ({MOST_TRANSCRIPT // 1000}k characters)")
    return text


# --- what Gemini is told --------------------------------------------------------------------------------------

HEAR = (
    "You are Kairu's meeting scribe. Transcribe this meeting recording word for word. Keep each speaker's own words; do not "
    "summarise, correct or add anything. Start a new line at each change of speaker, written exactly as: "
    "[mm:ss] Name: words\n"
    "mm:ss is when that turn starts in the recording. Use a person's real name only when the meeting makes it clear (they "
    "say their name, or someone calls them by it); otherwise write Speaker 1, Speaker 2 and so on, the same label for the same "
    "voice all the way through. Write English words in English; keep Hindi or Telugu words as they were said, in Latin "
    "letters. Mark words you can't make out as [unclear]. If there is no speech at all, answer with exactly: NO SPEECH. "
    "Answer with the transcript lines only: no title, notes or summary.")


def instructions(held: date, title: str = "") -> str:
    day = held.strftime("%A %d %B %Y")
    named = f' The meeting is called "{title}".' if title else ""
    return (
        "You are Kairu, an AI teammate that turns meetings into finished work. Read the meeting transcript you are given and "
        f"pull out what the team decided, who does what by when, and what is still open. The meeting was held on {day}.{named}\n"
        "Rules:\n"
        "- decisions: things the team agreed or settled (a choice, a scope, a date, something dropped). Not suggestions that "
        "nobody agreed to.\n"
        "- actions: work someone will do. owner is the person who will do it, exactly as named in the transcript (a first name "
        "is fine). If nobody took it, owner is \"\" - never guess an owner.\n"
        f"- due: a real date as YYYY-MM-DD, worked out from the meeting date ({held.isoformat()}): \"Friday\" is the next "
        "Friday after the meeting, \"end of the week\" is that Friday, \"tomorrow\" is the next day. If no deadline was said, due "
        "is \"\". due_said is the deadline in the words that were said, such as \"by Friday\".\n"
        "- questions: things raised and not settled, or that need someone's answer.\n"
        "- quote: the exact words from the transcript that show it, copied character for character, at most 25 words; at is the "
        "[mm:ss] of that line if there is one.\n"
        "- sure: high when it was said plainly, medium when you read it from context, low when you are unsure.\n"
        "- If a later part of the meeting changes an earlier decision, keep only the final one and say what it replaced in "
        "replaces.\n"
        "Answer with JSON only, no other words:\n"
        '{"title": "a short name for this meeting", "summary": "2 or 3 sentences: the purpose and the outcome", '
        '"people": ["each person who spoke or was given work"], '
        '"decisions": [{"what": "...", "owner": "", "due": "", "due_said": "", "replaces": "", "quote": "...", "at": "", "sure": "high"}], '
        '"actions": [{"what": "...", "owner": "", "due": "", "due_said": "", "quote": "...", "at": "", "sure": "high"}], '
        '"questions": [{"what": "...", "owner": "", "quote": "...", "at": "", "sure": "high"}]}\n'
        f"At most {MOST_ITEMS} of each kind; every what under {LONGEST_ITEM} characters, written as a short plain sentence. "
        "Use empty lists when there are none. Never invent anything that is not in the transcript.")


# --- Gemini's answer, read strictly ---------------------------------------------------------------------------

WORD = re.compile(r"[\w']+")


def _words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def heard(quote: str, transcript: str) -> bool:
    """Is this quote really in the transcript? Words in order, case, punctuation and spacing aside; a quote of 4 words or
    more may differ by one word at either end (Gemini sometimes trims a "so" or adds the speaker's name)."""
    words, said = _words(quote), " ".join(_words(transcript))
    if not words:
        return False
    if " ".join(words) in said:
        return True
    return len(words) >= 4 and any(" ".join(part) in said for part in (words[1:], words[:-1], words[1:-1]) if len(part) >= 3)


def _text(value, longest: int, what: str, empty: bool = False) -> str:
    if value is None and empty:
        return ""
    if not isinstance(value, str):
        raise NoReading(f"{what} is not text")
    value = " ".join(value.split())
    if len(value) > longest:
        value = value[:longest - 1].rstrip() + "…"
    if not value and not empty:
        raise NoReading(f"{what} is empty")
    return value


def due_date(value, held: date) -> str:
    """A deadline as YYYY-MM-DD, or "" if it isn't a real date within two years of the meeting (an AI's slip is dropped,
    never guessed at)."""
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        day = datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""
    return day.isoformat() if held - timedelta(days=31) <= day <= held + timedelta(days=730) else ""


def _items(data: dict, kind: str, transcript: str, held: date, people: set[str]) -> list[dict]:
    found = data.get(kind, [])
    if found is None:
        return []
    if not isinstance(found, list):
        raise NoReading(f"{kind} is not a list")
    out = []
    for number, item in enumerate(found[:MOST_ITEMS], 1):
        if not isinstance(item, dict):
            raise NoReading(f"{kind} {number} is not an item")
        what = _text(item.get("what"), LONGEST_ITEM, f"{kind} {number}'s what")
        owner = _text(item.get("owner", ""), LONGEST_NAME, f"{kind} {number}'s owner", empty=True)
        quote = _text(item.get("quote", ""), LONGEST_QUOTE, f"{kind} {number}'s quote", empty=True)
        at = str(item.get("at") or "").strip().strip("[]")
        sure = str(item.get("sure") or "medium").lower()
        entry = {"kind": kind[:-1], "what": what, "owner": owner,
                 "due": due_date(item.get("due"), held) if kind != "questions" else "",
                 "due_said": _text(item.get("due_said", ""), 80, f"{kind} {number}'s due_said", empty=True),
                 "replaces": _text(item.get("replaces", ""), LONGEST_ITEM, f"{kind} {number}'s replaces", empty=True),
                 "quote": quote, "at": at if re.fullmatch(r"(?:\d+:)?\d{1,2}:\d{2}", at) else "",
                 "sure": sure if sure in SURE else "medium",
                 "heard": heard(quote, transcript) if quote else False,
                 "owner_heard": bool(owner) and (owner.lower() in transcript.lower() or owner.lower() in people)}
        if privacy.secrets_in(" ".join((what, owner, quote, entry["replaces"]))):
            continue  # never kept
        out.append(entry)
    return out


def parse(text: str, transcript: str, held: date) -> dict:
    """{"title", "summary", "people", "items": [...]} or NoReading. Each item: kind (decision, action, question), what,
    owner, due (YYYY-MM-DD or ""), due_said, replaces, quote, at, sure, heard (the quote is really in the transcript) and
    owner_heard (the owner's name is in the transcript)."""
    found = re.search(r"\{.*\}", text or "", re.S)
    if not found:
        raise NoReading("the answer was not JSON")
    try:
        data = json.loads(found.group(0))
    except ValueError:
        raise NoReading("the answer was not JSON") from None
    if not isinstance(data, dict):
        raise NoReading("the answer was not a JSON object")
    people = data.get("people") or []
    if not isinstance(people, list):
        raise NoReading("people is not a list")
    people = [_text(name, LONGEST_NAME, "a person's name", empty=True) for name in people[:30] if isinstance(name, str)]
    people = list(dict.fromkeys(name for name in people if name))
    known = {name.lower() for name in people if name.lower() in transcript.lower()}
    items = []
    for kind in ("decisions", "actions", "questions"):
        items += _items(data, kind, transcript, held, known)
    summary = _text(data.get("summary", ""), LONGEST_SUMMARY, "the summary", empty=True)
    if privacy.secrets_in(summary):
        summary = ""
    return {"title": _text(data.get("title", ""), LONGEST_TITLE, "the title", empty=True), "summary": summary,
            "people": people, "items": items}


def transcript_answer(text: str) -> list[str]:
    """Gemini's transcript, as lines; NO SPEECH (or nothing) is NotAMeeting."""
    lines = [" ".join(line.split()) for line in (text or "").replace("\r", "").split("\n")]
    lines = [line.strip("`") for line in lines if line.strip("` ")]
    if not lines or (len(lines) == 1 and lines[0].upper().strip(".") == "NO SPEECH"):
        raise NotAMeeting("there's no speech in that recording")
    return lines
