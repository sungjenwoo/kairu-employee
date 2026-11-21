"""data/builder.db: what the Builder drafted, the skills Forge kept, and the last Five Paths, on this PC only.

    drafts    Builder powers: each build the AI wrote (its files), under the answer id of the build.draft that made it, until it
              is made (build.write) or DRAFT_MINUTES pass. The sha256 is of exactly the files you were shown: build.write makes
              only a draft whose files still have it.
    recipes   Forge: each recipe the AI wrote, its five dry runs and their result, until it is kept or DRAFT_MINUTES pass.
    skills    the recipes you kept with "yes" and your PIN (forge.save): a name, the orders it answers, its steps.
    paths     Five Paths: the task, its "done when", the five plans and the judge's scores; the newest is what "run path 2" picks.
    builds    the folders build.write made, with the sha256 of each file as made: build.test runs only those, unchanged.

Nothing in it is a permission: Guardian never reads it to decide anything, and every step a recipe or a path holds is decided
by policy.yaml when it runs. Your briefs stay here and never go into the audit log (policy.yaml: private). On Linux the file is
readable by you only.
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

DB_NAME = "builder.db"
DRAFT_MINUTES = 60
PATHS_MINUTES = 30  # "run path 2" picks from Five Paths at most this old
MOST_SKILLS = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ask    TEXT NOT NULL UNIQUE,
    at     REAL NOT NULL,
    kind   TEXT NOT NULL,      -- site, app, slides or tests
    folder TEXT NOT NULL,      -- the new folder's name in the work folder
    files  TEXT NOT NULL,      -- JSON: [{"name", "text"}]
    sha256 TEXT NOT NULL,
    state  TEXT NOT NULL       -- drafted, made
);
CREATE TABLE IF NOT EXISTS builds (
    folder TEXT PRIMARY KEY,   -- relative to the work folder
    at     REAL NOT NULL,
    kind   TEXT NOT NULL,
    files  TEXT NOT NULL       -- JSON: {name: sha256 as made}
);
CREATE TABLE IF NOT EXISTS recipes (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ask    TEXT NOT NULL UNIQUE,
    at     REAL NOT NULL,
    recipe TEXT NOT NULL,      -- JSON, as kairu/build/forge.py read it
    sha256 TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT -1,  -- dry runs passed (of forge.RUNS); -1 not tried yet
    notes  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS skills (
    name   TEXT PRIMARY KEY,
    at     REAL NOT NULL,
    recipe TEXT NOT NULL,
    sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paths (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ask    TEXT NOT NULL UNIQUE,
    at     REAL NOT NULL,
    task   TEXT NOT NULL,
    done   TEXT NOT NULL,      -- "done when", as you said it or as the judge wrote it
    paths  TEXT NOT NULL,      -- JSON: [{"style", "steps": [[action, details], ...] or null, "why_not", "score", "why"}]
    ranked TEXT NOT NULL DEFAULT '[]'  -- JSON: after the rule checks, the numbers you can pick, best first
);
"""


def exists(data_dir) -> bool:
    return (Path(os.fspath(data_dir)) / DB_NAME).exists()


def digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class BuilderStore:
    def __init__(self, data_dir):
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

    def _old(self, db, table: str, minutes: float) -> None:
        db.execute(f"DELETE FROM {table} WHERE at < ?", (time.time() - minutes * 60,))

    # --- Builder powers ---------------------------------------------------------------------------------

    def add_draft(self, ask: str, kind: str, folder: str, files: list[dict]) -> tuple[int, str]:
        sha = digest({"kind": kind, "folder": folder, "files": files})
        with self.connect() as db:
            self._old(db, "drafts", DRAFT_MINUTES)
            number = db.execute("INSERT INTO drafts (ask, at, kind, folder, files, sha256, state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (ask, time.time(), kind, folder, json.dumps(files), sha, "drafted")).lastrowid
        return number, sha

    def draft(self, number: int | None = None, ask: str | None = None) -> dict | None:
        with self.connect() as db:
            self._old(db, "drafts", DRAFT_MINUTES)
            row = db.execute("SELECT id, ask, kind, folder, files, sha256, state FROM drafts WHERE id = ? OR ask = ?",
                             (number if number is not None else -1, ask or "")).fetchone()
        if row is None:
            return None
        return {"id": row[0], "ask": row[1], "kind": row[2], "folder": row[3], "files": json.loads(row[4]), "sha256": row[5],
                "state": row[6]}

    def made(self, number: int, folder: str, kind: str, hashes: dict) -> None:
        with self.connect() as db:
            db.execute("UPDATE drafts SET state = 'made' WHERE id = ?", (number,))
            db.execute("INSERT OR REPLACE INTO builds (folder, at, kind, files) VALUES (?, ?, ?, ?)",
                       (folder, time.time(), kind, json.dumps(hashes)))

    def build(self, folder: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT folder, at, kind, files FROM builds WHERE lower(folder) = lower(?)", (folder,)).fetchone()
        return {"folder": row[0], "at": row[1], "kind": row[2], "files": json.loads(row[3])} if row else None

    def newest_build(self, kind: str | None = None) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT folder FROM builds WHERE ? IS NULL OR kind = ? ORDER BY at DESC LIMIT 1",
                             (kind, kind)).fetchone()
        return self.build(row[0]) if row else None

    # --- Forge --------------------------------------------------------------------------------------------

    def add_recipe(self, ask: str, recipe: dict) -> tuple[int, str]:
        sha = digest(recipe)
        with self.connect() as db:
            self._old(db, "recipes", DRAFT_MINUTES)
            number = db.execute("INSERT INTO recipes (ask, at, recipe, sha256) VALUES (?, ?, ?, ?)",
                                (ask, time.time(), json.dumps(recipe), sha)).lastrowid
        return number, sha

    def recipe(self, number: int | None = None, ask: str | None = None) -> dict | None:
        with self.connect() as db:
            self._old(db, "recipes", DRAFT_MINUTES)
            row = db.execute("SELECT id, recipe, sha256, passed, notes FROM recipes WHERE id = ? OR ask = ?",
                             (number if number is not None else -1, ask or "")).fetchone()
        if row is None:
            return None
        return {"id": row[0], "recipe": json.loads(row[1]), "sha256": row[2], "passed": row[3], "notes": row[4]}

    def tried(self, number: int, passed: int, notes: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE recipes SET passed = ?, notes = ? WHERE id = ?", (passed, notes, number))

    def keep_skill(self, recipe: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO skills (name, at, recipe, sha256) VALUES (?, ?, ?, ?)",
                       (recipe["name"], time.time(), json.dumps(recipe), digest(recipe)))

    def skills(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT recipe, sha256 FROM skills ORDER BY name").fetchall()
        kept = []
        for recipe, sha in rows:
            try:
                data = json.loads(recipe)
            except ValueError:
                continue
            if digest(data) == sha:  # a recipe changed by hand since it was kept is never used
                kept.append(data)
        return kept

    def skill_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]

    def forget_skill(self, name: str) -> bool:
        with self.connect() as db:
            return db.execute("DELETE FROM skills WHERE lower(name) = lower(?)", (name,)).rowcount > 0

    # --- Five Paths ----------------------------------------------------------------------------------------

    def add_paths(self, ask: str, task: str, done: str, paths: list[dict]) -> int:
        with self.connect() as db:
            self._old(db, "paths", DRAFT_MINUTES)
            return db.execute("INSERT INTO paths (ask, at, task, done, paths) VALUES (?, ?, ?, ?, ?)",
                              (ask, time.time(), task, done, json.dumps(paths))).lastrowid

    def paths(self, ask: str | None = None) -> dict | None:
        """The Five Paths of this answer id, or (no id) the newest, if it is at most PATHS_MINUTES old."""
        with self.connect() as db:
            if ask:
                row = db.execute("SELECT id, at, task, done, paths, ranked FROM paths WHERE ask = ?", (ask,)).fetchone()
            else:
                row = db.execute("SELECT id, at, task, done, paths, ranked FROM paths WHERE at >= ? ORDER BY id DESC LIMIT 1",
                                 (time.time() - PATHS_MINUTES * 60,)).fetchone()
        if row is None:
            return None
        return {"id": row[0], "at": row[1], "task": row[2], "done": row[3], "paths": json.loads(row[4]),
                "ranked": json.loads(row[5])}

    def rank(self, number: int, ranked: list[int]) -> None:
        with self.connect() as db:
            db.execute("UPDATE paths SET ranked = ? WHERE id = ?", (json.dumps(ranked), number))
