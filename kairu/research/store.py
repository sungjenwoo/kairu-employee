"""data/research.db: what one search or one page read found, until the question that asked for it has read it.

Guardian runs each search and page read in its own process, so what they find comes back through this file, under
a random job id. It is deleted as it is read; what nobody read (a stop came first) goes with the next search after
KEEP_MINUTES.

    found    a job's search results or page text. Page text stays quarantined data (kairu/research/quarantine.py):
             the only reader is the question that asked for it. A search's words are never written here.
    passes   one mark per search you approved with "yes" and your PIN, kept as a hash and spent by that one search
    state    until when DuckDuckGo is left alone, after it asked Kairu to slow down

Nothing in it is a permission for Guardian: Guardian never reads it to decide anything. Passes only tell the search
action (kairu/research/search.py) that a personal search came through your approval, not around it. On Linux the
file is readable by you only (mode 600).
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

DB_NAME = "research.db"
KEEP_MINUTES = 10
PASS_MINUTES = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS found (
    job  TEXT NOT NULL,
    kind TEXT NOT NULL,   -- search or pages
    at   REAL NOT NULL,
    body TEXT NOT NULL,   -- JSON
    PRIMARY KEY (job, kind)
);
CREATE TABLE IF NOT EXISTS passes (
    digest TEXT PRIMARY KEY,
    at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);
"""


def _digest(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


class ResearchStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
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

    def put(self, job: str, kind: str, body: dict) -> None:
        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM found WHERE at < ?", (now - KEEP_MINUTES * 60,))
            db.execute("INSERT OR REPLACE INTO found (job, kind, at, body) VALUES (?, ?, ?, ?)",
                       (job, kind, now, json.dumps(body)))

    def take(self, job: str, kind: str) -> dict | None:
        """What a job found, deleted as it is read."""
        with self.connect() as db:
            row = db.execute("DELETE FROM found WHERE job = ? AND kind = ? RETURNING body", (job, kind)).fetchone()
        return json.loads(row[0]) if row else None

    def allow(self, query: str) -> None:
        """You approved this search: one mark for the search action to spend."""
        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM passes WHERE at < ?", (now - PASS_MINUTES * 60,))
            db.execute("INSERT OR REPLACE INTO passes (digest, at) VALUES (?, ?)", (_digest(query), now))

    def spend(self, query: str) -> bool:
        """True once for a search you approved, within PASS_MINUTES; False otherwise."""
        with self.connect() as db:
            row = db.execute("DELETE FROM passes WHERE digest = ? RETURNING at", (_digest(query),)).fetchone()
        return bool(row) and row[0] >= time.time() - PASS_MINUTES * 60

    def rest_until(self, moment: float) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO state (key, value) VALUES ('rest_until', ?)", (moment,))

    def resting_until(self) -> float | None:
        """Until when DuckDuckGo is left alone, or None."""
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key = 'rest_until'").fetchone()
        return row[0] if row and row[0] > time.time() else None
