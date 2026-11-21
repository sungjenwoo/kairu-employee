"""Your talk history (MEMORY.md "Talk history"): what you asked Kairu at the PC, and the start of each answer.

Kairu keeps it by itself, on this PC only (data/brain.db, the brain's own file), for 30 days and at most 300 talks:

    kept(question, result)     whether this talk is kept: an answer at the PC, with no secret in it, and not a question
                               about the memory or the history itself
    told(data_dir, when, about) "what did I ask yesterday", "what did we talk about today", "what did I ask about tea":
                               the talks, read by rules; nothing is sent

It never leaves this PC: no file here uses the network, no talk is added to anything sent to a cloud AI, a search or the
phone, and none goes into Guardian's audit log. "forget our talks" deletes all of it (memory.forget, Medium).
"""

import time
from datetime import datetime, timedelta

from kairu.brain import privacy
from kairu.memory.store import words

TALKS = "*talks"  # memory.forget's word for "the whole talk history" (no line has it: words() drops the "*")
MOST_SHOWN = 8
LONGEST_ANSWER = 90
WHEN = ("today", "yesterday", "recent")
NONE = {"today": "We haven't talked yet today.", "yesterday": "We didn't talk yesterday.",
        "recent": "We haven't talked yet. Ask me anything."}


def kept(question: str, answer: str, level: str, kind: str) -> bool:
    if kind == "memory" or not question.strip() or not answer.strip():
        return False
    return not privacy.secrets_in(question) and not privacy.secrets_in(answer)


def window(when: str, now: float | None = None) -> tuple[float, float]:
    """(from, to) for today, yesterday, or the whole history (recent)."""
    now = time.time() if now is None else now
    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    if when == "today":
        return midnight.timestamp(), now + 1
    if when == "yesterday":
        return (midnight - timedelta(days=1)).timestamp(), midnight.timestamp()
    return 0, now + 1


def _short(answer: str) -> str:
    first = answer.split("\n", 1)[0].strip()
    return first if len(first) <= LONGEST_ANSWER else first[:LONGEST_ANSWER].rsplit(" ", 1)[0] + " …"


def told(data_dir, when: str = "recent", about: str = "", now: float | None = None) -> str:
    from kairu.brain.store import BrainStore
    start, end = window(when if when in WHEN else "recent", now)
    talks = BrainStore(data_dir).talks(start, end)
    if about:
        wanted = words(about)
        talks = [talk for talk in talks if wanted and wanted <= words(talk["question"] + " " + talk["answer"])]
        if not talks:
            return f"I don't find a talk about {about}."
    if not talks:
        return NONE[when if when in WHEN else "recent"]
    shown = talks[-MOST_SHOWN:]
    lead = {"today": "Today you asked:", "yesterday": "Yesterday you asked:"}.get(when, "Lately you asked:")
    if about:
        lead = f"About {about}, you asked:"
    lines = [lead]
    for talk in shown:
        stamp = datetime.fromtimestamp(talk["at"])
        day = "" if when in ("today", "yesterday") else stamp.strftime("%d %b ")
        lines.append(f"- {day}{stamp.strftime('%H:%M')} {talk['question']} → {_short(talk['answer'])}")
    if len(talks) > len(shown):
        lines.append(f"... and {len(talks) - len(shown)} before that.")
    return "\n".join(lines)
