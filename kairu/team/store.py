"""data/team.db on Main Kairu's PC: the Clones, the projects and their tasks, and what each Clone last said.

Nothing in this file is a permission. A Clone's words (its reports) are data, shown to you on the team board and never
handed to Guardian or to an AI. A Clone's Link keys for talking to it live in data/team/<id>.json (readable by you only),
written by kairu/team/peer.py; this database keeps only its name, its share and where its keys are.
"""

import json
import os
import re
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

DB_NAME = "team.db"
MOST_CLONES = 5  # Kairu Link's own limit of paired devices on the Clone's side is 5 too
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,29}")

# a task's states
WAITING, SENT, DONE, BLOCKED = "waiting", "working", "done", "blocked"
STATES = (WAITING, SENT, DONE, BLOCKED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS clones (
    name     TEXT PRIMARY KEY,
    device   TEXT NOT NULL,      -- Main Kairu's own device id towards this Clone (dev- and 16 hex digits)
    share    REAL NOT NULL,      -- how much of a project it takes: 1 is an even share, 2 is twice that
    added    REAL NOT NULL,
    seen     REAL,
    since    INTEGER NOT NULL DEFAULT 0,  -- the Gate time of the last message read from it
    skills   TEXT NOT NULL DEFAULT '',    -- what its person is good at, in a few words (the manager's words, for the split)
    pending  TEXT NOT NULL DEFAULT '[]'   -- growth record entries and offers waiting for this Clone's next order (JSON)
);
CREATE TABLE IF NOT EXISTS projects (
    number   INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    brief    TEXT NOT NULL,
    deadline REAL,
    created  REAL NOT NULL,
    started  REAL,
    ended    REAL,
    state    TEXT NOT NULL       -- planned, running, done, stopped
);
CREATE TABLE IF NOT EXISTS tasks (
    project  INTEGER NOT NULL,
    number   INTEGER NOT NULL,   -- 1, 2, ... within its project
    title    TEXT NOT NULL,
    clone    TEXT NOT NULL,
    orders   TEXT NOT NULL,      -- JSON list of the orders, in order
    done     TEXT NOT NULL,      -- what "done" means, in words
    after    TEXT NOT NULL,      -- JSON list of task numbers that must be done first
    minutes  REAL NOT NULL,
    state    TEXT NOT NULL,
    step     INTEGER NOT NULL DEFAULT 0,  -- orders finished so far
    sent     REAL,               -- when the order now running was sent
    started  REAL,
    finished REAL,
    last     TEXT NOT NULL DEFAULT '',    -- what its Clone last said about it
    log      TEXT NOT NULL DEFAULT '[]',  -- JSON list of [time, words] for each order's result
    note     TEXT NOT NULL DEFAULT '',    -- Main Kairu's own note, sent along with this task's next order
    warned   INTEGER NOT NULL DEFAULT 0,  -- 1 once its Clone was told the task is slipping
    blocked_once INTEGER NOT NULL DEFAULT 0,  -- 1 if it was ever blocked (and then, if done, someone stepped in)
    checked  REAL,                        -- when the manager confirmed its "done when" check (team.check)
    PRIMARY KEY (project, number)
);
CREATE TABLE IF NOT EXISTS offers (
    number   INTEGER PRIMARY KEY AUTOINCREMENT,
    clone    TEXT NOT NULL,
    words    TEXT NOT NULL,      -- the manager's offer ("Lead the next research project"), the manager's own words
    made     REAL NOT NULL,
    state    TEXT NOT NULL,      -- waiting (for the Clone's next order), sent, accepted, declined, withdrawn
    answered REAL
);
CREATE TABLE IF NOT EXISTS feed (
    number   INTEGER PRIMARY KEY AUTOINCREMENT,
    project  INTEGER NOT NULL,
    time     REAL NOT NULL,
    who      TEXT NOT NULL,      -- "Main Kairu" or a Clone's name
    whom     TEXT NOT NULL,      -- a Clone's name, or "" for the manager
    words    TEXT NOT NULL       -- Main Kairu's own notes, or what a Clone said with `kairu team say` (data, shown only)
);
"""


UPGRADES = (("clones", "skills", "TEXT NOT NULL DEFAULT ''"), ("tasks", "note", "TEXT NOT NULL DEFAULT ''"),
            ("tasks", "warned", "INTEGER NOT NULL DEFAULT 0"), ("tasks", "blocked_once", "INTEGER NOT NULL DEFAULT 0"),
            ("tasks", "checked", "REAL"), ("clones", "pending", "TEXT NOT NULL DEFAULT '[]'"))
OFFER_STATES = ("waiting", "sent", "accepted", "declined", "withdrawn")
LONGEST_OFFER = 200
MOST_PENDING = 40
LONGEST_SKILLS = 120
LONGEST_FEED = 400


class TeamError(Exception):
    pass


def clean_name(name) -> str:
    name = " ".join(str(name or "").split())
    if not NAME.fullmatch(name):
        raise TeamError("a Clone's name is 1 to 30 letters, digits, spaces, dots, dashes or underscores")
    return name


class TeamStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / DB_NAME
        self.data_dir.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)
            for table, column, kind in UPGRADES:  # a team.db from before these columns
                if column not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
            db.commit()
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    # --- Clones ------------------------------------------------------------------------------------

    def clones(self) -> list[dict]:
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM clones ORDER BY added")]

    def clone(self, name: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM clones WHERE lower(name) = lower(?)", (name,)).fetchone()
        return dict(row) if row else None

    def add_clone(self, name: str, device: str, share: float = 1.0, skills: str = "") -> None:
        name, skills = clean_name(name), clean_skills(skills)
        check_share(share)
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM clones WHERE lower(name) = lower(?)", (name,)).fetchone():
                raise TeamError(f"there is already a Clone called {name}")
            if db.execute("SELECT count(*) FROM clones").fetchone()[0] >= MOST_CLONES:
                raise TeamError(f"Main Kairu leads at most {MOST_CLONES} Clones")
            db.execute("INSERT INTO clones (name, device, share, added, skills) VALUES (?, ?, ?, ?, ?)",
                       (name, device, share, time.time(), skills))

    def set_clone(self, name: str, share: float | None = None, skills: str | None = None) -> None:
        """The manager changes a Clone's share or skills (team.set): words for the next split, never a permission."""
        fields = {}
        if share is not None:
            fields["share"] = check_share(share)
        if skills is not None:
            fields["skills"] = clean_skills(skills)
        if not fields:
            return
        with self.transaction() as db:
            changed = db.execute(f"UPDATE clones SET {', '.join(f'{key} = ?' for key in fields)} WHERE lower(name) = lower(?)",
                                 (*fields.values(), name)).rowcount
        if not changed:
            raise TeamError(f"there is no Clone called {name}")

    def remove_clone(self, name: str) -> bool:
        with self.transaction() as db:
            return db.execute("DELETE FROM clones WHERE lower(name) = lower(?)", (name,)).rowcount > 0

    def heard(self, name: str, since: int, when: float) -> None:
        with self.transaction() as db:
            db.execute("UPDATE clones SET since = max(since, ?), seen = ? WHERE name = ?", (since, when, name))

    # --- projects and tasks --------------------------------------------------------------------------

    def add_project(self, name: str, brief: str, deadline: float | None, tasks: list[dict]) -> int:
        with self.transaction() as db:
            number = db.execute("INSERT INTO projects (name, brief, deadline, created, state) VALUES (?, ?, ?, ?, 'planned')",
                                (name[:80], brief[:2000], deadline, time.time())).lastrowid
            for index, task in enumerate(tasks, 1):
                db.execute("INSERT INTO tasks (project, number, title, clone, orders, done, after, minutes, state) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (number, index, task["title"], task["clone"], json.dumps(task["orders"]), task["done"],
                            json.dumps(task["after"]), float(task["minutes"]), WAITING))
        return number

    def projects(self) -> list[dict]:
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY number DESC")]

    def project(self, number: int) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM projects WHERE number = ?", (number,)).fetchone()
        return dict(row) if row else None

    def latest(self) -> int | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT max(number) FROM projects").fetchone()
        return row[0] if row and row[0] else None

    def set_project(self, number: int, **fields) -> None:
        allowed = {"state", "started", "ended"}
        if set(fields) - allowed:
            raise TeamError(f"a project's {sorted(set(fields) - allowed)} can't be changed")
        with self.transaction() as db:
            db.execute(f"UPDATE projects SET {', '.join(f'{key} = ?' for key in fields)} WHERE number = ?",
                       (*fields.values(), number))

    def tasks(self, project: int) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM tasks WHERE project = ? ORDER BY number", (project,)).fetchall()
        out = []
        for row in rows:
            task = dict(row)
            task["orders"], task["after"], task["log"] = json.loads(task["orders"]), json.loads(task["after"]), json.loads(task["log"])
            out.append(task)
        return out

    def set_task(self, project: int, number: int, **fields) -> None:
        allowed = {"state", "step", "sent", "started", "finished", "last", "clone", "note", "warned", "blocked_once", "checked"}
        if set(fields) - allowed:
            raise TeamError(f"a task's {sorted(set(fields) - allowed)} can't be changed")
        if "last" in fields:
            fields["last"] = str(fields["last"])[:600]
        with self.transaction() as db:
            db.execute(f"UPDATE tasks SET {', '.join(f'{key} = ?' for key in fields)} WHERE project = ? AND number = ?",
                       (*fields.values(), project, number))

    def log_result(self, project: int, number: int, words: str) -> None:
        with self.transaction() as db:
            row = db.execute("SELECT log FROM tasks WHERE project = ? AND number = ?", (project, number)).fetchone()
            if row:
                log = json.loads(row["log"])[-19:] + [[round(time.time()), str(words)[:600]]]
                db.execute("UPDATE tasks SET log = ? WHERE project = ? AND number = ?", (json.dumps(log), project, number))


    # --- the team feed: Main Kairu's notes to its Clones and what the Clones said (data, shown only) -------------------

    def add_feed(self, project: int, who: str, whom: str, words: str, when: float | None = None) -> None:
        words = " ".join(str(words).split())[:LONGEST_FEED]
        if not words:
            return
        with self.transaction() as db:
            db.execute("INSERT INTO feed (project, time, who, whom, words) VALUES (?, ?, ?, ?, ?)",
                       (project, when or time.time(), who, whom, words))
            db.execute("DELETE FROM feed WHERE project = ? AND number NOT IN "
                       "(SELECT number FROM feed WHERE project = ? ORDER BY number DESC LIMIT 200)", (project, project))

    def feed(self, project: int, most: int = 30) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM feed WHERE project = ? ORDER BY number DESC LIMIT ?", (project, most)).fetchall()
        return [dict(row) for row in reversed(rows)]


    # --- growth: what waits for a Clone's next order, and the manager's offers (TEAM.md "Growth") -------------------

    def pending(self, clone: str) -> list[str]:
        found = self.clone(clone)
        try:
            items = json.loads(found["pending"]) if found else []
        except ValueError:
            items = []
        return [str(item) for item in items if isinstance(item, str)]

    def add_pending(self, clone: str, words: str) -> None:
        words = " ".join(str(words).split())[:LONGEST_FEED]
        if words and self.clone(clone):
            items = (self.pending(clone) + [words])[-MOST_PENDING:]
            with self.transaction() as db:
                db.execute("UPDATE clones SET pending = ? WHERE lower(name) = lower(?)", (json.dumps(items), clone))

    def set_pending(self, clone: str, items: list[str]) -> None:
        with self.transaction() as db:
            db.execute("UPDATE clones SET pending = ? WHERE lower(name) = lower(?)", (json.dumps(items[-MOST_PENDING:]), clone))

    def add_offer(self, clone: str, words: str) -> int:
        words = " ".join(str(words).split())
        if not 3 <= len(words) <= LONGEST_OFFER or re.search(r"[<>{}\[\]`]|\bpin\b|password", words, re.I):
            raise TeamError(f"an offer is 3 to {LONGEST_OFFER} letters, without a PIN, password or brackets")
        found = self.clone(clone)
        if found is None:
            raise TeamError(f"there is no Clone called {clone}")
        with self.transaction() as db:
            return db.execute("INSERT INTO offers (clone, words, made, state) VALUES (?, ?, ?, 'waiting')",
                              (found["name"], words, time.time())).lastrowid

    def offers(self, clone: str | None = None) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM offers WHERE ? IS NULL OR lower(clone) = lower(?) ORDER BY number",
                              (clone, clone)).fetchall()
        return [dict(row) for row in rows]

    def set_offer(self, number: int, state: str, answered: float | None = None) -> None:
        if state not in OFFER_STATES:
            raise TeamError(f"an offer is one of {', '.join(OFFER_STATES)}")
        with self.transaction() as db:
            db.execute("UPDATE offers SET state = ?, answered = COALESCE(?, answered) WHERE number = ?", (state, answered, number))


def check_share(share) -> float:
    if type(share) not in (int, float) or not 0.25 <= share <= 4:
        raise TeamError("a share is 0.25 to 4 (1 is an even share)")
    return float(share)


def clean_skills(skills) -> str:
    """A few words about what a Clone's person is good at ("research, writing"). Letters, digits, spaces and , . & + / - only."""
    skills = " ".join(str(skills or "").split())
    if len(skills) > LONGEST_SKILLS or not re.fullmatch(r"[A-Za-z0-9 ,.&+/#-]*", skills):
        raise TeamError(f"skills are up to {LONGEST_SKILLS} letters, digits, spaces and , . & + / # -")
    return skills


def exists(data_dir) -> bool:
    return (Path(data_dir) / DB_NAME).exists()
