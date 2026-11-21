"""data/brain.db: the brain's notes. Nothing in it is a permission: Guardian never reads it to decide anything.

    answers   each question's answer, kept only until it is read (by `kairu ask`, by Guardian for your
              phone, by a mission) and never more than ANSWER_MINUTES; refused questions keep only why
    context   the last public question and its answer for each place you ask from (this PC, your phone, a
              mission), for CONTEXT_MINUTES, so "yes, tell me more" can follow an answer. A personal
              question is never kept here.
    sources   the web pages the last answer used, for each place you ask from, so "sources?" can list them:
              titles and links, for SOURCES_MINUTES (CONTEXT_MINUTES after a search you approved)
    usage     questions and tokens per provider per day (your local day): what `kairu usage` shows
    limits    what each provider said about its free limit, and until when Kairu leaves it alone
              (at its limit, refused the key, or paused by you)
    events    switches, limits, refused keys, pauses: the "every switch" list of `kairu usage`
    state     small settings

Questions themselves are never written here, except the last public one in `context`; Guardian's audit
log keeps only their hashes (BRAIN.md). On Linux the file is readable by you only (mode 600).
"""

import json
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DB_NAME = "brain.db"
ANSWER_MINUTES = 10
CONTEXT_MINUTES = 10
SOURCES_MINUTES = 60
EVENT_DAYS = 30
USAGE_DAYS = 90
TALK_DAYS = 30  # your talks are kept this long ...
MOST_TALKS = 300  # ... and at most this many, the oldest going first
LONGEST_TALK = 400  # characters of an answer kept

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    ask      TEXT PRIMARY KEY,
    at       REAL NOT NULL,
    source   TEXT NOT NULL,
    status   TEXT NOT NULL,           -- answered, needs_approval, refused, not_sent
    level    TEXT NOT NULL,           -- L0, L3, L4
    provider TEXT NOT NULL DEFAULT '',
    text     TEXT NOT NULL DEFAULT '',
    note     TEXT NOT NULL DEFAULT '',
    reasons  TEXT NOT NULL DEFAULT '[]',
    seconds  REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS context (
    source   TEXT PRIMARY KEY,
    at       REAL NOT NULL,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    source TEXT PRIMARY KEY,
    until  REAL NOT NULL,
    items  TEXT NOT NULL              -- JSON: {"title", "url"} of each page
);
CREATE TABLE IF NOT EXISTS usage (
    day        TEXT NOT NULL,
    provider   TEXT NOT NULL,
    questions  INTEGER NOT NULL DEFAULT 0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, provider)
);
CREATE TABLE IF NOT EXISTS limits (
    provider  TEXT PRIMARY KEY,
    until     REAL NOT NULL DEFAULT 0,  -- leave it alone until then
    why       TEXT NOT NULL DEFAULT '',
    day_limit INTEGER,
    day_left  INTEGER,
    day_reset REAL,
    seen      REAL
);
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY,
    at       REAL NOT NULL,
    provider TEXT NOT NULL,
    kind     TEXT NOT NULL,             -- answered_after_switch, limit, key, unreachable, refused, pause, resume
    note     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS talks (     -- your talks with Kairu at the PC (MEMORY.md "Talk history"): on this PC only
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       REAL NOT NULL,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Answer:
    ask: str
    at: float
    source: str
    status: str
    level: str
    provider: str
    text: str
    note: str
    reasons: tuple[str, ...]
    seconds: float
    search: str = ""  # needs_approval: the words that would go to the search engine if you approve


@dataclass(frozen=True)
class Limit:
    provider: str
    until: float
    why: str
    day_limit: int | None
    day_left: int | None
    day_reset: float | None
    seen: float | None


def today(moment: float | None = None) -> str:
    return date.fromtimestamp(time.time() if moment is None else moment).isoformat()


class BrainStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DB_NAME
        new = not self.path.exists()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            self._add_search_column(db)
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)  # your questions' answers are yours alone

    @staticmethod
    def _add_search_column(db) -> None:
        """A brain.db from before stage R1. An answer lives 10 minutes at most, and older code ignores the column."""
        if "search" not in {row[1] for row in db.execute("PRAGMA table_info(answers)")}:
            try:
                db.execute("ALTER TABLE answers ADD COLUMN search TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError as error:  # another of Kairu's processes added it just now
                if "duplicate column" not in str(error):
                    raise

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as db:
            yield db

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    # --- answers -------------------------------------------------------------------------------

    def put_answer(self, answer: Answer) -> None:
        with self.transaction() as db:
            db.execute("DELETE FROM answers WHERE at < ?", (time.time() - ANSWER_MINUTES * 60,))
            db.execute("INSERT OR REPLACE INTO answers (ask, at, source, status, level, provider, text, note, reasons, "
                       "seconds, search) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (answer.ask, answer.at, answer.source, answer.status, answer.level, answer.provider, answer.text,
                        answer.note, json.dumps(list(answer.reasons)), answer.seconds, answer.search))

    def has_answer(self, ask: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM answers WHERE ask = ? AND at >= ?",
                              (ask, time.time() - ANSWER_MINUTES * 60)).fetchone() is not None

    def take_answer(self, ask: str) -> Answer | None:
        """The answer, deleted as it is read: an answer is read once."""
        with self.transaction() as db:
            row = db.execute("SELECT ask, at, source, status, level, provider, text, note, reasons, seconds, search "
                             "FROM answers WHERE ask = ?", (ask,)).fetchone()
            db.execute("DELETE FROM answers WHERE ask = ? OR at < ?", (ask, time.time() - ANSWER_MINUTES * 60))
        if row is None:
            return None
        return Answer(*row[:8], tuple(json.loads(row[8])), row[9], row[10])

    # --- the last public exchange ----------------------------------------------------------------

    def context(self, source: str, now: float | None = None) -> tuple[str, str] | None:
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("DELETE FROM context WHERE at < ?", (now - CONTEXT_MINUTES * 60,))
            row = db.execute("SELECT question, answer FROM context WHERE source = ?", (source,)).fetchone()
        return (row[0], row[1]) if row else None

    def keep_context(self, source: str, question: str, answer: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO context (source, at, question, answer) VALUES (?, ?, ?, ?)",
                       (source, time.time(), question, answer))

    def forget_context(self, source: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM context WHERE source = ?", (source,))

    # --- your talks (MEMORY.md "Talk history"): kept on this PC, sent nowhere, never in the audit log --------------

    def keep_talk(self, question: str, answer: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("INSERT INTO talks (at, question, answer) VALUES (?, ?, ?)",
                       (now, " ".join(question.split())[:300], " ".join(answer.split())[:LONGEST_TALK]))
            db.execute("DELETE FROM talks WHERE at < ? OR id NOT IN (SELECT id FROM talks ORDER BY id DESC LIMIT ?)",
                       (now - TALK_DAYS * 86400, MOST_TALKS))

    def talks(self, since: float = 0, until: float | None = None) -> list[dict]:
        """Your talks between these times, oldest first."""
        until = time.time() + 1 if until is None else until
        with self.connect() as db:
            db.execute("DELETE FROM talks WHERE at < ?", (time.time() - TALK_DAYS * 86400,))
            rows = db.execute("SELECT at, question, answer FROM talks WHERE at >= ? AND at < ? ORDER BY id",
                              (since, until)).fetchall()
        return [{"at": row[0], "question": row[1], "answer": row[2]} for row in rows]

    def forget_talks(self) -> int:
        with self.connect() as db:
            return db.execute("DELETE FROM talks").rowcount

    # --- the pages the last answer used -----------------------------------------------------------

    def keep_sources(self, source: str, items: list[dict], personal: bool = False) -> None:
        minutes = CONTEXT_MINUTES if personal else SOURCES_MINUTES
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO sources (source, until, items) VALUES (?, ?, ?)",
                       (source, time.time() + minutes * 60, json.dumps(items)))

    def sources(self, source: str) -> list[dict]:
        with self.connect() as db:
            db.execute("DELETE FROM sources WHERE until < ?", (time.time(),))
            row = db.execute("SELECT items FROM sources WHERE source = ?", (source,)).fetchone()
        return json.loads(row[0]) if row else []

    def forget_sources(self, source: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sources WHERE source = ?", (source,))

    # --- usage and limits ----------------------------------------------------------------------

    def count(self, provider: str, tokens_in: int, tokens_out: int, when: float | None = None) -> None:
        day = today(when)
        with self.transaction() as db:
            db.execute("INSERT INTO usage (day, provider, questions, tokens_in, tokens_out) VALUES (?, ?, 1, ?, ?) "
                       "ON CONFLICT(day, provider) DO UPDATE SET questions = questions + 1, "
                       "tokens_in = tokens_in + excluded.tokens_in, tokens_out = tokens_out + excluded.tokens_out",
                       (day, provider, tokens_in, tokens_out))
            db.execute("DELETE FROM usage WHERE day < ?", (today((when or time.time()) - USAGE_DAYS * 86400),))

    def usage(self, day: str | None = None) -> dict[str, tuple[int, int, int]]:
        """provider -> (questions, tokens in, tokens out) on that day (today by default)."""
        with self.connect() as db:
            rows = db.execute("SELECT provider, questions, tokens_in, tokens_out FROM usage WHERE day = ?",
                              (day or today(),)).fetchall()
        return {row[0]: (row[1], row[2], row[3]) for row in rows}

    def questions_today(self) -> int:
        return sum(questions for questions, _, _ in self.usage().values())

    def limit(self, provider: str) -> Limit | None:
        with self.connect() as db:
            row = db.execute("SELECT provider, until, why, day_limit, day_left, day_reset, seen FROM limits "
                             "WHERE provider = ?", (provider,)).fetchone()
        return Limit(*row) if row else None

    def leave_alone(self, provider: str, until: float, why: str) -> None:
        """Do not use this provider until then (at its limit, its key refused, or paused by you)."""
        with self.connect() as db:
            db.execute("INSERT INTO limits (provider, until, why) VALUES (?, ?, ?) ON CONFLICT(provider) DO UPDATE SET "
                       "until = excluded.until, why = excluded.why", (provider, until, why))

    def free_again(self, provider: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE limits SET until = 0, why = '' WHERE provider = ?", (provider,))

    def note_day(self, provider: str, day_limit: int | None, day_left: int | None, day_reset: float | None) -> None:
        """What the provider just said about its free day."""
        with self.connect() as db:
            db.execute("INSERT INTO limits (provider, day_limit, day_left, day_reset, seen) VALUES (?, ?, ?, ?, ?) "
                       "ON CONFLICT(provider) DO UPDATE SET day_limit = COALESCE(excluded.day_limit, day_limit), "
                       "day_left = COALESCE(excluded.day_left, day_left), "
                       "day_reset = COALESCE(excluded.day_reset, day_reset), seen = excluded.seen",
                       (provider, day_limit, day_left, day_reset, time.time()))

    # --- events --------------------------------------------------------------------------------

    def event(self, provider: str, kind: str, note: str, when: float | None = None) -> None:
        when = time.time() if when is None else when
        with self.connect() as db:
            db.execute("INSERT INTO events (at, provider, kind, note) VALUES (?, ?, ?, ?)", (when, provider, kind, note))
            db.execute("DELETE FROM events WHERE at < ?", (when - EVENT_DAYS * 86400,))

    def events(self, since: float) -> list[tuple[float, str, str, str]]:
        with self.connect() as db:
            return db.execute("SELECT at, provider, kind, note FROM events WHERE at >= ? ORDER BY at, id",
                              (since,)).fetchall()


def start_of_today() -> float:
    return datetime.combine(date.today(), datetime.min.time()).timestamp()


def exists(data_dir) -> bool:
    return (Path(data_dir) / DB_NAME).exists()
