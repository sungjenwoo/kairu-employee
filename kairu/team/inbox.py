"""A Clone's team inbox (TEAM.md "Talk and sync"): Main Kairu's notes to this laptop, kept in data/team-inbox.json.

    note(data_dir, text, device)   team.note (Low): keep one note that came with an order from Main Kairu (kairu/tasks/
                                   remote.py takes it off the order first, so the task core never sees it)
    read(data_dir)                 the notes, oldest first, for `kairu team inbox` and the workspace's Clones page

A note is words to show the person at this laptop, nothing more: it is never an order, never handed to the brain, and
never moves anything. It is built by Main Kairu from its own data (the project, the task titles, the times), never from
another Clone's words. It stays on this PC; Guardian's audit log keeps only its hash (team.note is private).
"""

import json
import os
import sys
import time
from pathlib import Path

FILE = "team-inbox.json"
MOST = 50
LONGEST = 600


def _path(data_dir) -> Path:
    return Path(data_dir) / FILE


def read(data_dir) -> list[dict]:
    try:
        notes = json.loads(_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    if not isinstance(notes, list):
        return []
    return [{"time": float(n.get("time", 0)), "words": str(n.get("words", ""))[:LONGEST]}
            for n in notes if isinstance(n, dict)][-MOST:]


def keep(data_dir, words: str, when: float | None = None) -> None:
    words = " ".join(str(words or "").split())[:LONGEST]
    if not words:
        return
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    notes = (read(data_dir) + [{"time": when or time.time(), "words": words}])[-MOST:]
    temp = path.with_name(f"{FILE}.{os.getpid()}.tmp")
    with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as out:
        json.dump(notes, out)
    os.replace(temp, path)


def note(data_dir: str, text: str, device: str = "") -> None:
    """team.note: Guardian runs it for kairu/tasks/remote.py, with a note that came with Main Kairu's order."""
    keep(data_dir, text)
    print("team.note: kept", file=sys.stderr, flush=True)
