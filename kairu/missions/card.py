"""Reading a Mission Card file you wrote (YAML), and the practice card for the gate test.

    goal: Learn about two rivers          what the mission is for (up to 200 characters)
    done:                                 your "100% done" checklist (optional, up to 10 lines)
      - every question answered
    steps:                                1 to 20 steps, done in order. Phase B has two kinds:
      - ask: How long is the Godavari?      a question for Kairu's brain (it goes through the privacy filter)
      - wait: 20                            practice: count 20 seconds (1 to 600), to try Stop and restart
    deadline: 2026-11-01 18:00            optional, your local time
    report: phone                         pc (the tray and `kairu mission show`), phone, or both

Anything else is refused rather than guessed at. Reading files, writing, sending and anything High come
with later phases (D, G, I); a step a card cannot have in Phase B is refused here, and Guardian decides
every step anyway.
"""

from datetime import datetime
from pathlib import Path

import yaml

MOST_STEPS = 20
LONGEST_GOAL = 200
LONGEST_QUESTION = 500
MOST_CHECKS = 10
MOST_WAIT = 600
REPORTS = ("pc", "phone", "both")
EXAMPLE = """\
# A Mission Card for Kairu (BRAIN.md). Save it as card.yaml, then: kairu mission new card.yaml
goal: Learn about two rivers
done:                       # what "100% done" means to you
  - every question answered
  - the report is on my phone
steps:                      # ask: a question for Kairu's brain; wait: count seconds (practice)
  - ask: How long is the Godavari river?
  - wait: 20
  - ask: How long is the Krishna river?
deadline: 2026-11-30 18:00  # optional
report: both                # pc, phone or both
"""
PRACTICE = {
    "goal": "Practice mission: count, then answer one question",
    "done": ["every step finished once, none twice"],
    "steps": [{"wait": 20}, {"wait": 20}, {"wait": 20}, {"wait": 20}, {"wait": 20},
              {"ask": "What is the capital of India?"}],
    "report": "both",
}


class CardProblem(Exception):
    pass


def read(path: str) -> dict:
    try:
        raw = Path(path).read_bytes()
        # Windows PowerShell's `>` writes UTF-16; Notepad may add a byte-order mark: both are read as they are
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise CardProblem(f"the card file could not be read ({error})") from None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise CardProblem(f"the card file is not YAML ({str(error).splitlines()[0]})") from None
    return check(raw)


def check(raw) -> dict:
    """The card as {"goal", "done", "steps": [(kind, text)], "deadline", "report"}. Raises CardProblem."""
    if not isinstance(raw, dict):
        raise CardProblem("a card has goal, steps and optionally done, deadline and report")
    extra = set(raw) - {"goal", "done", "steps", "deadline", "report"}
    if extra:
        raise CardProblem(f"a card does not take {', '.join(sorted(map(str, extra)))}")
    goal = raw.get("goal")
    if not isinstance(goal, str) or not goal.strip() or len(goal) > LONGEST_GOAL:
        raise CardProblem(f"goal must be text of 1 to {LONGEST_GOAL} characters")
    done = raw.get("done") or []
    if not isinstance(done, list) or len(done) > MOST_CHECKS or not all(isinstance(item, str) and 0 < len(item) <= 200
                                                                        for item in done):
        raise CardProblem(f"done must be a list of up to {MOST_CHECKS} short lines")
    steps = raw.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MOST_STEPS:
        raise CardProblem(f"steps must be a list of 1 to {MOST_STEPS} steps")
    checked = [_step(number, step) for number, step in enumerate(steps, 1)]
    report = raw.get("report", "pc")
    if report not in REPORTS:
        raise CardProblem("report must be pc, phone or both")
    return {"goal": " ".join(goal.split()), "done": [" ".join(item.split()) for item in done], "steps": checked,
            "deadline": _deadline(raw.get("deadline")), "report": report}


def _step(number: int, step) -> tuple[str, str]:
    if not isinstance(step, dict) or len(step) != 1:
        raise CardProblem(f"step {number} must be one of: ask: QUESTION, or wait: SECONDS")
    (kind, value), = step.items()
    if kind == "ask":
        if not isinstance(value, str) or not value.strip() or len(value) > LONGEST_QUESTION:
            raise CardProblem(f"step {number}: a question is 1 to {LONGEST_QUESTION} characters")
        return "ask", value.strip()
    if kind == "wait":
        if type(value) not in (int, float) or not 1 <= value <= MOST_WAIT:
            raise CardProblem(f"step {number}: wait takes 1 to {MOST_WAIT} seconds")
        return "wait", f"{float(value):g}"
    raise CardProblem(f"step {number}: Phase B steps are ask and wait; {str(kind)[:30]!r} comes with a later phase")


def _deadline(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).strip())
        except ValueError:
            raise CardProblem("deadline must look like 2026-11-30 18:00") from None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.isoformat(timespec="minutes")
