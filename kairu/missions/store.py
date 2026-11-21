"""data/missions.db: the Mission Cards, and a checkpoint after every step.

A card holds the goal, your "100% done" checklist, the steps and how each went, an optional deadline and
how to report (pc, phone or both). Each step's start and end is its own small SQLite transaction, written
to disk before the next thing happens (synchronous=FULL): that is the checkpoint. After a restart, a crash
or a stop, the mission goes on from there: a step that finished is never run again, and a step that was
cut off half-way runs again from its start (safe, because Phase B steps only ask and count), at most
MOST_TRIES times.

Card states:  queued -> running -> done | waiting (for your approval) | failed;  stopped (by you, or a stop)
Step states:  todo -> running -> done | waiting | failed | skipped

Written by the mission actions Guardian runs (kairu/missions/actions.py, run.py), and by Guardian itself
for two things only: a card that was running when a stop halted it becomes "stopped", and a finished card
is marked as reported once you were told. Nothing in it is a permission: Guardian decides every step.
On Linux the file is readable by you only (mode 600).
"""

import json
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

DB_NAME = "missions.db"
MOST_TRIES = 3  # a step cut off this many times is not tried again (ADR-006: bounded retries)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id       INTEGER PRIMARY KEY,
    created  REAL NOT NULL,
    goal     TEXT NOT NULL,
    done     TEXT NOT NULL,                 -- JSON list: your "100% done" checklist
    deadline TEXT,                          -- ISO date and time with its zone, or NULL
    report   TEXT NOT NULL,                 -- pc, phone or both
    status   TEXT NOT NULL,                 -- queued, running, done, waiting, failed, stopped
    reason   TEXT NOT NULL DEFAULT '',
    updated  REAL NOT NULL,
    finished REAL,
    reported INTEGER NOT NULL DEFAULT 1     -- 0: you have not been told how it ended yet
);
CREATE TABLE IF NOT EXISTS steps (
    card    INTEGER NOT NULL,
    number  INTEGER NOT NULL,
    kind    TEXT NOT NULL,                  -- ask or wait
    text    TEXT NOT NULL,                  -- the question, or the seconds to count
    status  TEXT NOT NULL,                  -- todo, running, done, waiting, failed, skipped
    tries   INTEGER NOT NULL DEFAULT 0,
    ask     TEXT,                           -- the answer id of an ask step's latest try
    result  TEXT NOT NULL DEFAULT '',
    note    TEXT NOT NULL DEFAULT '',
    started REAL,
    ended   REAL,
    PRIMARY KEY (card, number)
);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
RUNNABLE = ("queued", "running")
OPEN = ("queued", "running", "waiting", "stopped", "failed")


@dataclass(frozen=True)
class Step:
    number: int
    kind: str
    text: str
    status: str
    tries: int
    ask: str | None
    result: str
    note: str
    started: float | None
    ended: float | None

    @property
    def waiting_for(self) -> dict:
        """For a step waiting for your approval: {"provider", "reasons"}."""
        try:
            return json.loads(self.note) if self.status == "waiting" else {}
        except ValueError:
            return {}


@dataclass(frozen=True)
class Card:
    id: int
    created: float
    goal: str
    done: list
    deadline: str | None
    report: str
    status: str
    reason: str
    updated: float
    finished: float | None
    reported: bool
    steps: list = field(default_factory=list)

    def counts(self) -> tuple[int, int]:
        return sum(step.status in ("done", "skipped") for step in self.steps), len(self.steps)


class MissionStore:
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
            db.execute("PRAGMA synchronous=FULL")  # a checkpoint is on the disk before the next step starts
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

    # --- cards ---------------------------------------------------------------------------------

    def create(self, goal: str, done: list, steps: list[tuple[str, str]], deadline: str | None, report: str) -> int:
        now = time.time()
        with self.transaction() as db:
            card = db.execute("INSERT INTO cards (created, goal, done, deadline, report, status, updated, reported) "
                              "VALUES (?, ?, ?, ?, ?, 'queued', ?, 1)",
                              (now, goal, json.dumps(done), deadline, report, now)).lastrowid
            db.executemany("INSERT INTO steps (card, number, kind, text, status) VALUES (?, ?, ?, ?, 'todo')",
                           [(card, number, kind, text) for number, (kind, text) in enumerate(steps, 1)])
            _bump(db)
        return card

    def card(self, card_id: int) -> Card | None:
        with self.connect() as db:
            row = db.execute("SELECT id, created, goal, done, deadline, report, status, reason, updated, finished, reported "
                             "FROM cards WHERE id = ?", (card_id,)).fetchone()
            if row is None:
                return None
            steps = db.execute("SELECT number, kind, text, status, tries, ask, result, note, started, ended FROM steps "
                               "WHERE card = ? ORDER BY number", (card_id,)).fetchall()
        return Card(row[0], row[1], row[2], json.loads(row[3]), row[4], row[5], row[6], row[7], row[8], row[9],
                    bool(row[10]), [Step(*step) for step in steps])

    def cards(self) -> list[Card]:
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM cards ORDER BY id")]
        return [card for card in (self.card(card_id) for card_id in ids) if card]

    def status(self, card_id: int) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT status FROM cards WHERE id = ?", (card_id,)).fetchone()
        return row[0] if row else None

    def next_runnable(self) -> int | None:
        """The oldest card to work on: one that was running when it was cut off, then the queued ones."""
        with self.connect() as db:
            row = db.execute("SELECT id FROM cards WHERE status IN ('running', 'queued') "
                             "ORDER BY status = 'queued', id LIMIT 1").fetchone()
        return row[0] if row else None

    def start(self, card_id: int) -> bool:
        with self.transaction() as db:
            return db.execute("UPDATE cards SET status = 'running', reason = '', updated = ? WHERE id = ? AND "
                              "status IN ('queued', 'running')", (time.time(), card_id)).rowcount == 1

    def settle(self, card_id: int) -> str:
        """A card whose steps are all through: done, waiting (for your approval) or failed, by its steps."""
        card = self.card(card_id)
        states = [step.status for step in card.steps]
        waiting, failed = states.count("waiting"), states.count("failed")
        if waiting:
            status, reason = "waiting", f"{waiting} step{'s wait' if waiting != 1 else ' waits'} for your approval"
        elif failed:
            status, reason = "failed", f"{failed} step{'s' if failed != 1 else ''} could not be done"
        else:
            status, reason = "done", ""
        with self.transaction() as db:
            db.execute("UPDATE cards SET status = ?, reason = ?, updated = ?, finished = ?, reported = 0 WHERE id = ? AND "
                       "status = 'running'", (status, reason, time.time(), time.time(), card_id))
            _bump(db)
        return status

    def stop(self, card_id: int, reason: str, told: bool = True) -> bool:
        with self.transaction() as db:
            stopped = db.execute("UPDATE cards SET status = 'stopped', reason = ?, updated = ?, reported = ? WHERE id = ? "
                                 "AND status IN ('queued', 'running', 'waiting')",
                                 (reason, time.time(), 1 if told else 0, card_id)).rowcount == 1
            if stopped:
                _bump(db)
        return stopped

    def halt_running(self, reason: str) -> list[int]:
        """Guardian, after a stop halted the mission run: the card that was running keeps its checkpoint, stopped."""
        with self.transaction() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM cards WHERE status = 'running'")]
            db.execute("UPDATE cards SET status = 'stopped', reason = ?, updated = ? WHERE status = 'running'",
                       (reason, time.time()))
            if ids:
                _bump(db)
        return ids

    def resume(self, card_id: int, skip: bool, answered=lambda ask: False) -> bool:
        """Queue a stopped, waiting or failed card again. Failed steps are tried again; steps waiting for your
        approval stay waiting (their approved answers are collected), or with skip, those with no answer are skipped."""
        with self.transaction() as db:
            row = db.execute("SELECT status FROM cards WHERE id = ?", (card_id,)).fetchone()
            if row is None or row[0] not in ("stopped", "waiting", "failed"):
                return False
            db.execute("UPDATE steps SET status = 'todo', tries = 0, note = '' WHERE card = ? AND status = 'failed'",
                       (card_id,))
            if skip:
                for number, ask in db.execute("SELECT number, ask FROM steps WHERE card = ? AND status = 'waiting'",
                                              (card_id,)).fetchall():
                    if not (ask and answered(ask)):
                        db.execute("UPDATE steps SET status = 'skipped', result = '', note = 'not approved: skipped' "
                                   "WHERE card = ? AND number = ?", (card_id, number))
            db.execute("UPDATE cards SET status = 'queued', reason = '', updated = ?, finished = NULL, reported = 1 "
                       "WHERE id = ?", (time.time(), card_id))
            _bump(db)
        return True

    def remove(self, card_id: int) -> bool:
        with self.transaction() as db:
            gone = db.execute("DELETE FROM cards WHERE id = ? AND status NOT IN ('running', 'queued')",
                              (card_id,)).rowcount
            if gone:
                db.execute("DELETE FROM steps WHERE card = ?", (card_id,))
                _bump(db)
        return bool(gone)

    def unreported(self) -> list[Card]:
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM cards WHERE reported = 0 ORDER BY id")]
        return [card for card in (self.card(card_id) for card_id in ids) if card]

    def mark_reported(self, card_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE cards SET reported = 1 WHERE id = ?", (card_id,))

    # --- steps: a checkpoint at each start and each end ------------------------------------------

    def begin_step(self, card_id: int, number: int, ask: str | None) -> None:
        with self.transaction() as db:
            db.execute("UPDATE steps SET status = 'running', tries = tries + 1, ask = COALESCE(?, ask), started = ?, "
                       "ended = NULL WHERE card = ? AND number = ?", (ask, time.time(), card_id, number))
            db.execute("UPDATE cards SET updated = ? WHERE id = ?", (time.time(), card_id))

    def finish_step(self, card_id: int, number: int, status: str, result: str = "", note: str = "") -> None:
        with self.transaction() as db:
            db.execute("UPDATE steps SET status = ?, result = ?, note = ?, ended = ? WHERE card = ? AND number = ?",
                       (status, result, note, time.time(), card_id, number))
            db.execute("UPDATE cards SET updated = ? WHERE id = ?", (time.time(), card_id))

    def undo_step(self, card_id: int, number: int) -> None:
        """You stopped the mission while this step ran: it starts again from the beginning next time, not counted."""
        with self.transaction() as db:
            db.execute("UPDATE steps SET status = 'todo', tries = MAX(tries - 1, 0), started = NULL WHERE card = ? AND "
                       "number = ? AND status = 'running'", (card_id, number))

    def version(self) -> int:
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key = 'version'").fetchone()
        return int(row[0]) if row else 0


def _bump(db) -> None:
    db.execute("INSERT INTO state (key, value) VALUES ('version', '1') "
               "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)")


# --- the report you get when a card ends --------------------------------------------------------------

def report_text(card: Card, longest: int = 1500) -> str:
    done, total = card.counts()
    head = {"done": f"Mission {card.id} done: {card.goal}",
            "waiting": f"Mission {card.id} waits for you: {card.goal}. {card.reason}: at the PC, "
                       f"`kairu mission continue {card.id}`",
            "failed": f"Mission {card.id} finished with problems: {card.goal}. {card.reason}",
            "stopped": f"Mission {card.id} stopped: {card.goal}. {card.reason}"}.get(card.status, f"Mission {card.id}")
    lines = [f"{head}."]
    for step in card.steps:
        if step.kind == "ask":
            outcome = {"done": step.result, "waiting": "waits for your approval (personal data)",
                       "skipped": "skipped (not approved)", "failed": step.result or step.note or "could not be done",
                       "todo": "not done yet", "running": "not done yet"}[step.status]
            lines.append(f"{step.number}. {step.text} -> {outcome}")
        else:
            lines.append(f"{step.number}. counted {step.text} s" if step.status == "done"
                         else f"{step.number}. count {step.text} s: {step.status}")
    lines.append(f"Kairu's checks: every step through: {'yes' if done == total else f'{done} of {total}'}; "
                 "report sent: yes.")
    if card.done:
        lines.append("Your checklist (please tick it yourself): " + "; ".join(card.done) + ".")
    text = "\n".join(lines)
    return text if len(text) <= longest else text[:longest - 2].rstrip() + " …"


# --- for Guardian: reading only, never creating the file -------------------------------------------

def exists(data_dir) -> bool:
    return (Path(data_dir) / DB_NAME).exists()


def runnable(data_dir) -> bool:
    return exists(data_dir) and MissionStore(data_dir).next_runnable() is not None


def version(data_dir) -> int:
    return MissionStore(data_dir).version() if exists(data_dir) else 0


def summary(data_dir) -> list[dict]:
    if not exists(data_dir):
        return []
    return [{"id": card.id, "status": card.status, "done": card.counts()[0], "steps": card.counts()[1]}
            for card in MissionStore(data_dir).cards()]
