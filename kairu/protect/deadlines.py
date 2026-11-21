"""Deadlines: the ones you add, the ones found in emails, and the reminders before each.

Reminders come 3 days, 1 day and 3 hours before a deadline, each once; then one note when it has
passed. If the PC was off at a reminder's time, the next check gives the one that applies now.

Dates in emails are read with fixed patterns (no AI model): "submit by 30/10/2026 6 pm",
"deadline: Nov 5", "registrations close tomorrow at 11:59 PM". Numbers such as 05/11 are read
day first, as in India; when both readings are possible, the alert says which one was taken. Only
dates up to MAX_AHEAD days ahead are taken, and never from an email flagged as phishing, or from
Gmail's Promotions and Social tabs (sales and offers are full of "ends tomorrow").
"""

import re
from datetime import datetime, time, timedelta, timezone

from kairu.protect.store import Finding, ProtectStore

MAX_AHEAD = timedelta(days=120)
STAGES = ((timedelta(hours=72), 1), (timedelta(hours=24), 2), (timedelta(hours=3), 3))  # (before the deadline, stage)
PASSED = 4
SKIPPED_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "SPAM", "TRASH"}

MONTHS = {name: number for number, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")], start=1) for name in names}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|" \
         r"nov(?:ember)?|dec(?:ember)?)\.?"
TRIGGER = re.compile(r"\b(deadline|due (date|on|by)|is due|last date|submit(ted)? (by|before|on or before)|"
                     r"submissions? (close|closes|ends?|due)|closes? (on|at|by)|registrations? (close|closes|ends?)|"
                     r"apply (by|before)|no later than|ends? on|until)\b", re.I)
ISO_DATE = re.compile(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b")
NUMERIC = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\b")
DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH},?\s*(20\d\d)?\b", re.I)
MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b,?\s*(20\d\d)?", re.I)
RELATIVE = re.compile(r"\b(today|tonight|tomorrow)\b", re.I)
CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|\b([01]?\d|2[0-3]):([0-5]\d)\b(?:\s*(?:hrs|hours))?|"
                   r"\b(midnight|noon)\b", re.I)
UTC_NAMED = re.compile(r"\b(utc|gmt)\b", re.I)


class DateNotUnderstood(ValueError):
    pass


def local_now() -> datetime:
    return datetime.now().astimezone()


# --- reading a date -------------------------------------------------------------------------------

def find_date(text: str, sent: datetime, zone=None) -> tuple[datetime, bool] | None:
    """The first date (and time) in text, as an aware datetime in your time zone, and whether it was ambiguous.

    sent: when the text was written; "tomorrow" and dates without a year count from it.
    zone: your time zone (default: this PC's); a time written without a zone is taken as yours.
    """
    zone = zone or local_now().tzinfo
    local = sent.astimezone(zone)
    day, ambiguous, end = None, False, None
    candidates = []
    for match in ISO_DATE.finditer(text):
        candidates.append((match.start(), match.end(), lambda m=match: (_date(int(m[1]), int(m[2]), int(m[3])), False)))
    for match in NUMERIC.finditer(text):
        candidates.append((match.start(), match.end(), lambda m=match: _numeric(m, local)))
    for match in DAY_MONTH.finditer(text):
        candidates.append((match.start(), match.end(),
                           lambda m=match: (_with_year(int(m[1]), MONTHS[m[2].lower()], m[3], local), False)))
    for match in MONTH_DAY.finditer(text):
        candidates.append((match.start(), match.end(),
                           lambda m=match: (_with_year(int(m[2]), MONTHS[m[1].lower()], m[3], local), False)))
    for match in RELATIVE.finditer(text):
        word = match[1].lower()
        candidates.append((match.start(), match.end(),
                           lambda w=word: (local.date() + timedelta(days=1 if w == "tomorrow" else 0), False)))
    for start, end_at, read in sorted(candidates, key=lambda c: c[0]):
        try:
            day, ambiguous = read()
        except ValueError:
            continue
        if day is not None:
            end = end_at
            break
    if day is None:
        return None
    clock = _clock(text[end:end + 40]) or _clock(text) or time(23, 59)
    written = timezone.utc if UTC_NAMED.search(text) else zone
    return datetime.combine(day, clock, written).astimezone(zone), ambiguous


def _date(year: int, month: int, day: int):
    return datetime(year, month, day).date()


def _numeric(match, local: datetime):
    first, second, year = int(match[1]), int(match[2]), int(match[3])
    year += 2000 if year < 100 else 0
    if first > 12:  # 30/10: day first
        return _date(year, second, first), False
    if second > 12:  # 10/30: month first, as some senders write it
        return _date(year, first, second), False
    return _date(year, second, first), first != second  # 05/11: read day first, and say so


def _with_year(day: int, month: int, year: str | None, local: datetime):
    if year:
        return _date(int(year), month, day)
    candidate = _date(local.year, month, day)
    if candidate < local.date() - timedelta(days=1):  # "Jan 5" written in December means next year
        candidate = _date(local.year + 1, month, day)
    return candidate


def _clock(text: str) -> time | None:
    match = CLOCK.search(text)
    if not match:
        return None
    if match[6]:
        return time(23, 59) if match[6].lower() == "midnight" else time(12, 0)
    if match[3]:
        hour, minute = int(match[1]) % 12, int(match[2] or 0)
        if hour > 11 or minute > 59:
            return None
        return time(hour + (12 if match[3].lower().startswith("p") else 0), minute)
    return time(int(match[4]), int(match[5]))


def parse_when(date_text: str, time_text: str = "", now: datetime | None = None) -> datetime:
    """A deadline you typed: `2026-11-05`, `05/11/2026`, `5 Nov`, `tomorrow`, with an optional time (`18:00`, `6pm`)."""
    now = now or local_now()
    found = find_date(date_text.strip(), now, now.tzinfo)
    if found is None:
        raise DateNotUnderstood(f"could not read the date {date_text!r}; write it like 2026-11-05, 05/11/2026, "
                                "5 Nov or tomorrow")
    due, _ = found
    if time_text.strip():
        clock = _clock(time_text)
        if clock is None:
            raise DateNotUnderstood(f"could not read the time {time_text!r}; write it like 18:00 or 6pm")
        due = datetime.combine(due.date(), clock, due.tzinfo)
    return due


# --- deadlines found in emails --------------------------------------------------------------------

def from_email(mail, now: datetime | None = None) -> tuple[datetime, str, bool] | None:
    """(due, the sentence it was read from, ambiguous) for the first future deadline an email states, or None."""
    if SKIPPED_LABELS & set(mail.labels):
        return None
    now = now or local_now()
    sent = mail.received or now
    best = None
    for sentence in _sentences(f"{mail.subject}.\n{mail.text}"):
        if not TRIGGER.search(sentence):
            continue
        found = find_date(sentence, sent, now.tzinfo)
        if found is None:
            continue
        due, ambiguous = found
        if now < due <= now + MAX_AHEAD and (best is None or due < best[0]):
            best = (due, sentence.strip()[:200], ambiguous)
    return best


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", text or "") if part.strip()]


def email_finding(mail, due: datetime, sentence: str, ambiguous: bool, number: int) -> Finding:
    when = describe_due(due)
    note = [f"read from the email: \"{sentence}\""]
    if ambiguous:
        note.append(f"the date could be read two ways; Kairu read it day first ({due.strftime('%d %b %Y')})")
    return Finding(key=f"deadline-found:{mail.id}", source="gmail", kind="deadline_found", severity="info",
                   classification="Unknown", title=f"Deadline {when}: {_short(mail.subject)}",
                   lines=[("From", f"{mail.sender_name} <{mail.sender}>".strip()), ("Due", _full(due)),
                          ("Deadline", f"number {number} in `kairu deadline list`")],
                   why=note, not_checked=["whether Kairu read the date right: check it in the email"],
                   you_can="Check the date in the email. `kairu deadline remove " + str(number) + "` if it is not a "
                           "deadline for you. Reminders come 3 days, 1 day and 3 hours before.")


# --- reminders ------------------------------------------------------------------------------------

def reminders(store: ProtectStore, now: datetime | None = None) -> list[Finding]:
    """The reminders due now for every open deadline. Each is given once; the stage is saved with it."""
    now = now or local_now()
    findings = []
    for deadline in store.deadlines():
        remaining = deadline["due"] - now
        number, title = deadline["id"], deadline["title"]
        if remaining <= timedelta(0):
            store.set_deadline_stage(number, PASSED, close=True)
            findings.append(_reminder(deadline, "deadline_passed", "info", f"Deadline passed: {title}", now, PASSED))
            continue
        stage = max((s for before, s in STAGES if remaining <= before), default=0)
        if stage > deadline["stage"]:
            store.set_deadline_stage(number, stage)
            findings.append(_reminder(deadline, "deadline_soon", "warning",
                                      f"Due {describe_due(deadline['due'], now)}: {title}", now, stage))
    return findings


def _reminder(deadline: dict, kind: str, severity: str, title: str, now: datetime, stage: int) -> Finding:
    yours = deadline["origin"] == "you"
    return Finding(key=f"deadline:{deadline['id']}:{stage}", source="deadlines", kind=kind, severity=severity,
                   classification="Confirmed fact" if yours else "Unknown", title=title,
                   lines=[("Due", _full(deadline["due"])), ("Left", _left(deadline["due"] - now)),
                          ("Added", "by you" if yours else "found in an email")] + (
                             [("Note", deadline["note"])] if deadline["note"] else []),
                   why=["you added this deadline" if yours else "Kairu read this date from an email"],
                   not_checked=[] if yours else ["whether Kairu read the date right: check it in the email"],
                   you_can=f"`kairu deadline remove {deadline['id']}` once it is done, so no more reminders come.")


def describe_due(due: datetime, now: datetime | None = None) -> str:
    """"today at 6:00 pm", "tomorrow at 11:59 pm", "on Fri 30 Oct at 6:00 pm"."""
    now = (now or local_now()).astimezone(due.tzinfo)
    at = f"at {_clock_words(due)}"
    if due.date() == now.date():
        return f"today {at}"
    if due.date() == now.date() + timedelta(days=1):
        return f"tomorrow {at}"
    return f"on {due.strftime('%a')} {due.day} {due.strftime('%b')} {at}"


def _clock_words(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"


def _full(due: datetime) -> str:
    return f"{due.strftime('%a')} {due.day} {due.strftime('%b %Y')}, {_clock_words(due)}"


def _left(remaining: timedelta) -> str:
    hours = int(remaining.total_seconds() // 3600)
    if hours >= 48:
        return f"about {round(hours / 24)} days"
    if hours >= 1:
        return f"about {hours} hour{'s' if hours != 1 else ''}"
    return f"{max(1, int(remaining.total_seconds() // 60))} minutes"


def _short(text: str, most: int = 80) -> str:
    text = " ".join((text or "(no subject)").split())
    return text if len(text) <= most else text[:most - 1] + "…"
