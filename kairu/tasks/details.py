"""My details (ADR-054 proposed, BAR.md "My details"): your name, email, phone and the like, on this PC only, for the screen
agent's forms ("sign me up for the Buildathon newsletter", "apply for this internship on Internshala", "log in to my GitHub").

    data/my-details.json    {"name": "...", "email": "...", "username:github.com": "...", ...} in Guardian's data folder

What it is for, and what never happens:
  - Kept or changed only by you: the owner command `kairu details set email you@example.com` (typed in PowerShell, never a
    Kairu action), or "save my email as you@example.com" in the bar (details.keep, High: your yes and PIN).
  - A secret (a password, PIN, OTP or code, card, Aadhaar or other ID number) is never kept: the privacy filter reads every
    value here, and a value it calls a secret is refused, whoever asks. No file here uses the network.
  - Never sent: Gemini sees only the name of a detail ("{email}"), never its value. screen.fill reads the value here, inside
    Guardian's own action, and types it on this PC; its reply names the detail, never the value. The audit log keeps only
    hashes (policy.yaml: private).
  - Shown only in the Kairu bar at this PC (details.show): never said aloud, never told to Kairu Live.
"""

import json
import os
import re
import sys
from pathlib import Path

from kairu.brain import privacy

FILE = "my-details.json"
KEYS = ("name", "email", "phone", "city", "college", "linkedin", "resume")
USERNAME = "username"  # "username:github.com": your username on one site
LONGEST = 200
MOST_SITES = 50
SITE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}")
JOB = re.compile(r"[0-9a-f]{16}")
SAID = {  # what you may call a detail -> its key
    "name": "name", "my name": "name", "full name": "name", "first and last name": "name",
    "email": "email", "e-mail": "email", "email address": "email", "e-mail address": "email", "mail": "email",
    "mail id": "email", "email id": "email", "gmail": "email",
    "phone": "phone", "phone number": "phone", "mobile": "phone", "mobile number": "phone", "number": "phone",
    "contact number": "phone", "whatsapp number": "phone",
    "city": "city", "town": "city", "location": "city", "current city": "city",
    "college": "college", "college name": "college", "university": "college", "school": "college", "institute": "college",
    "linkedin": "linkedin", "linkedin profile": "linkedin", "linkedin url": "linkedin", "linkedin link": "linkedin",
    "resume": "resume", "résumé": "resume", "cv": "resume", "resume file": "resume", "resume file name": "resume",
    "username": USERNAME, "user name": USERNAME, "user id": USERNAME, "login": USERNAME, "login id": USERNAME,
}
LABELS = {"name": "your name", "email": "your email", "phone": "your phone number", "city": "your city",
          "college": "your college", "linkedin": "your LinkedIn", "resume": "your résumé's file name", USERNAME: "your username"}
EMAIL = re.compile(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
PHONE = re.compile(r"\+?[0-9][0-9 ()-]{6,18}[0-9]")


class DetailProblem(Exception):
    """Why a detail can't be kept. Its text is what to tell you."""


def path(data_dir) -> Path:
    return Path(data_dir) / FILE


def key_of(words: str) -> str | None:
    """What you called a detail ("e-mail", "mobile number", "CV") as its key; None if it isn't one Kairu keeps."""
    said = " ".join((words or "").lower().replace("my ", " ").split()).strip(" .:'\"")
    return SAID.get(said) or SAID.get(said.removesuffix(" id")) or (said if said in KEYS else None)


def site_of(address: str) -> str:
    """"https://www.github.com/login" -> "github.com", "internshala.com" -> itself; "" if it isn't a site's name."""
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", (address or "").strip().lower()).split("/")[0].split("?")[0].split("#")[0]
    host = host.rsplit("@", 1)[-1].split(":")[0].strip(".")
    if not SITE.fullmatch(host or ""):
        return ""
    parts = host.split(".")
    # the name you registered: the last two parts, or three for "co.in", "ac.uk", "com.au" ...
    keep = 3 if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov", "edu", "nic", "res") and \
        len(parts[-1]) == 2 else 2
    return ".".join(parts[-keep:])


def full_key(key: str, site: str = "") -> str:
    if key == USERNAME:
        site = site_of(site)
        if not site:
            raise DetailProblem("Say which site the username is for, such as: save my username for github.com as sungjenwoo.")
        return f"{USERNAME}:{site}"
    if key not in KEYS:
        raise DetailProblem(f"Kairu keeps only these details: {', '.join(KEYS)}, and a username per site.")
    return key


def problem(key: str, value: str) -> str:
    """Why this value can't be kept as this detail ("" if it can). A secret never is, whoever asks."""
    value = " ".join((value or "").split())
    if not value or len(value) > LONGEST or re.search(r"[\x00-\x1f\x7f]", value):
        return f"A detail is one line of 1 to {LONGEST} characters."
    verdict = privacy.classify(value)
    if verdict.secret:
        return f"Not kept: it has {verdict.why()}. Kairu never keeps a secret, not even with your PIN."
    base = key.split(":")[0]
    if base == "email" and not EMAIL.fullmatch(value):
        return "That doesn't look like an email address."
    if base == "phone" and not PHONE.fullmatch(value):
        return "That doesn't look like a phone number."
    if base == "phone" and len(re.sub(r"\D", "", value)) > 13:
        return "That's too long for a phone number (an ID or card number is never kept)."
    if base != "phone" and re.search(r"\d{9,}", value.replace(" ", "")) and base not in ("linkedin", USERNAME):
        return "That has a long number in it, and Kairu never keeps an ID or card number."
    return ""


def load(data_dir) -> dict[str, str]:
    """Your saved details; {} when there are none. A line that isn't a detail Kairu keeps, or that now reads as a secret, is
    left out (fails closed)."""
    try:
        raw = json.loads(path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    kept = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        base, _, site = key.partition(":")
        known = (base in KEYS and not site) or (base == USERNAME and bool(site) and site_of(site) == site)
        if known and not problem(key, value):
            kept[key] = value
    return kept


def value(data_dir, key: str, site: str = "") -> str:
    """One detail's value, "" if it isn't kept. A username falls back to your email when there is none for that site."""
    details = load(data_dir)
    if key == USERNAME:
        return details.get(f"{USERNAME}:{site_of(site)}", "") or details.get("email", "")
    return details.get(key, "")


def _write(data_dir, details: dict[str, str]) -> None:
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / (FILE + ".new")
    temporary.write_text(json.dumps(details, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path(data_dir))


def keep(data_dir, key: str, value: str, site: str = "") -> str:
    """Keep one detail; what to tell you. Raises DetailProblem."""
    full = full_key(key, site)
    value = " ".join((value or "").split())
    why = problem(full, value)
    if why:
        raise DetailProblem(why)
    details = load(data_dir)
    if full not in details and len([k for k in details if k.startswith(USERNAME + ":")]) >= MOST_SITES \
            and full.startswith(USERNAME + ":"):
        raise DetailProblem(f"Kairu keeps usernames for at most {MOST_SITES} sites.")
    details[full] = value
    _write(data_dir, details)
    return f"Kept {LABELS[key]}{' for ' + full.split(':', 1)[1] if ':' in full else ''}, on this PC only."


def forget(data_dir, key: str, site: str = "") -> str:
    full = full_key(key, site)
    details = load(data_dir)
    if full not in details:
        return f"I don't have {LABELS[key]}{' for ' + full.split(':', 1)[1] if ':' in full else ''} saved."
    del details[full]
    _write(data_dir, details)
    return f"Forgotten: {LABELS[key]}{' for ' + full.split(':', 1)[1] if ':' in full else ''}."


def shown(data_dir) -> str:
    details = load(data_dir)
    if not details:
        return 'You have no details saved. Say "save my email as you@example.com", or type `kairu details set email ...`.'
    lines = [f"{key.split(':')[0]}{' (' + key.split(':', 1)[1] + ')' if ':' in key else ''}: {value}"
             for key, value in sorted(details.items())]
    return "Your details, on this PC only: " + "; ".join(lines) + "."


# --- the Guardian actions (policy.yaml: details.keep High, details.forget Medium, details.show Low; all private) ----------

def _say(data_dir: str, job: str, ok: bool, text: str) -> None:
    from kairu.tasks.store import TaskStore
    TaskStore(data_dir).put_reply(job, ok, text)


def _checked(job: str) -> None:
    if not JOB.fullmatch(job or ""):
        print("details: a job id is 16 hex digits", file=sys.stderr)
        raise SystemExit(1)


def keep_action(data_dir: str, job: str, key: str, value: str, site: str = "") -> None:
    _checked(job)
    try:
        _say(data_dir, job, True, keep(data_dir, key_of(key) or key, value, site))
    except DetailProblem as why:
        _say(data_dir, job, False, str(why))


def forget_action(data_dir: str, job: str, key: str, site: str = "") -> None:
    _checked(job)
    try:
        _say(data_dir, job, True, forget(data_dir, key_of(key) or key, site))
    except DetailProblem as why:
        _say(data_dir, job, False, str(why))


def show_action(data_dir: str, job: str) -> None:
    _checked(job)
    _say(data_dir, job, True, shown(data_dir))
