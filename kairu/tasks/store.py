"""data/tasks.db: what each skill answered, until read, and the undo log.

    replies   each step's short answer, under a random job id, deleted as it is read. Guardian runs a skill in its own
              process, so this is how its answer comes back. What nobody read goes with the next reply after KEEP_MINUTES.
    plans     every free-form plan that ran (Sprint Day 4): when, from where, how you approved it, its steps' skill names, and
              the same hash of its details that Guardian's audit log keeps for its task.plan run. Never the words of the plan.
    undo      the newest MOST_UNDO changes that can be reversed. A rename is kept as two names inside your work folder;
              task.undo checks them again with the same fence, so this file cannot point Kairu outside it.

Nothing in it is a permission: Guardian never reads it to decide anything. On Linux the file is readable by you only.
"""

import json
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

DB_NAME = "tasks.db"
KEEP_MINUTES = 10
MOST_UNDO = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS replies (
    job  TEXT PRIMARY KEY,
    at   REAL NOT NULL,
    ok   INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       REAL NOT NULL,
    source   TEXT NOT NULL,   -- pc, a paired device's id
    approved TEXT NOT NULL,   -- yes, or yes+PIN
    request  TEXT NOT NULL,   -- Guardian's approval request for the High step, or ''
    steps    TEXT NOT NULL,   -- JSON: the skills' names, in order
    sha256   TEXT NOT NULL    -- as Guardian's audit log keeps it for this plan's task.plan run
);
CREATE TABLE IF NOT EXISTS undo (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     REAL NOT NULL,
    kind   TEXT NOT NULL,   -- rename
    detail TEXT NOT NULL    -- JSON
);
"""


@dataclass(frozen=True)
class SkillReply:
    ok: bool
    text: str


@dataclass(frozen=True)
class UndoEntry:
    id: int
    kind: str
    detail: dict


class TaskStore:
    def __init__(self, data_dir):
        # realpath on the text (the same as Path.resolve): a test that stands in for os.path.normpath with text in, text out
        # broke Path.resolve on Windows, which hands normpath a Path (laptop check, 16 Nov 2026)
        self.data_dir = Path(os.path.realpath(os.fspath(data_dir)))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DB_NAME
        new = not self.path.exists()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as db:
            yield db

    def put_reply(self, job: str, ok: bool, text: str) -> None:
        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM replies WHERE at < ?", (now - KEEP_MINUTES * 60,))
            db.execute("INSERT OR REPLACE INTO replies (job, at, ok, text) VALUES (?, ?, ?, ?)", (job, now, int(ok), text))

    def take_reply(self, job: str) -> SkillReply | None:
        with self.connect() as db:
            row = db.execute("DELETE FROM replies WHERE job = ? RETURNING ok, text", (job,)).fetchone()
        return SkillReply(bool(row[0]), row[1]) if row else None

    def keep_plan(self, source: str, approved: str, request: str, steps: list[str], sha256: str) -> int:
        with self.connect() as db:
            return db.execute("INSERT INTO plans (at, source, approved, request, steps, sha256) VALUES (?, ?, ?, ?, ?, ?)",
                              (time.time(), source, approved, request, json.dumps(steps), sha256)).lastrowid

    def plans(self, most: int = 20) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id, at, source, approved, request, steps, sha256 FROM plans ORDER BY id DESC LIMIT ?",
                              (most,)).fetchall()
        return [{"id": row[0], "at": row[1], "source": row[2], "approved": row[3], "request": row[4],
                 "steps": json.loads(row[5]), "sha256": row[6]} for row in rows]

    def remember(self, kind: str, detail: dict) -> None:
        """One more change that can be undone; only the newest MOST_UNDO are kept."""
        with self.connect() as db:
            db.execute("INSERT INTO undo (at, kind, detail) VALUES (?, ?, ?)", (time.time(), kind, json.dumps(detail)))
            db.execute("DELETE FROM undo WHERE id NOT IN (SELECT id FROM undo ORDER BY id DESC LIMIT ?)", (MOST_UNDO,))

    def newest_undo(self) -> UndoEntry | None:
        with self.connect() as db:
            row = db.execute("SELECT id, kind, detail FROM undo ORDER BY id DESC LIMIT 1").fetchone()
        return UndoEntry(row[0], row[1], json.loads(row[2])) if row else None

    def forget_undo(self, entry_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM undo WHERE id = ?", (entry_id,))

    def undo_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM undo").fetchone()[0]
