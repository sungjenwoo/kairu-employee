"""data/workspace.db: the workspace's projects, missions and what was said in them. On this PC only.

    projects   a name, your own notes, archived or not
    missions   a title, the project it belongs to (or none), when it was last used
    messages   in a mission, in order: your orders ("you"), Kairu's answers ("kairu"), each step of a task ("step")
    files      in a mission (W2): the names of the files and folders its finished steps made, changed, opened, showed or put
               in the Recycle Bin, as the steps named them (relative to the work folder). Never read from the disk.

What you typed and what Kairu answered stay in this file only: never in Guardian's audit log, never sent anywhere. Nothing in
it is a permission, and Guardian never reads it. On Linux the file is readable by you only. Deleting a mission deletes its
messages.
"""

import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

DB_NAME = "workspace.db"
LONGEST_NAME = 80
LONGEST_NOTES = 4000
LONGEST_TEXT = 8000
TITLE_WORDS = 8
FILE_WAYS = ("made", "opened", "shown", "renamed", "moved into", "recycled")
MOST_FILES = 40

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    notes    TEXT NOT NULL DEFAULT '',
    created  REAL NOT NULL,
    updated  REAL NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS missions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    project  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    title    TEXT NOT NULL,
    created  REAL NOT NULL,
    updated  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    mission  INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    at       REAL NOT NULL,
    who      TEXT NOT NULL CHECK (who IN ('you', 'kairu', 'step')),
    text     TEXT NOT NULL,
    state    TEXT NOT NULL DEFAULT ''   -- a step's: done, not done
);
CREATE INDEX IF NOT EXISTS messages_by_mission ON messages (mission, id);
CREATE TABLE IF NOT EXISTS files (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    mission  INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    at       REAL NOT NULL,
    name     TEXT NOT NULL,
    how      TEXT NOT NULL      -- made, opened, shown, renamed, moved into, recycled
);
CREATE INDEX IF NOT EXISTS files_by_mission ON files (mission, id);
"""


class NotFound(Exception):
    """No such project or mission."""


class BadName(Exception):
    """Its text says why."""


def _name(text: str, what: str = "A name") -> str:
    name = " ".join(str(text or "").split())
    if not name:
        raise BadName(f"{what} can't be empty")
    if len(name) > LONGEST_NAME:
        raise BadName(f"{what} can have at most {LONGEST_NAME} characters")
    return name


def title_for(order: str) -> str:
    """A new mission's title: the first words of its first order."""
    words = " ".join(str(order or "").split()).split(" ")
    title = " ".join(words[:TITLE_WORDS]).strip(" .,!?;:")
    if len(words) > TITLE_WORDS:
        title += "…"
    return (title or "New mission")[:LONGEST_NAME]


class WorkspaceStore:
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
            db.execute("PRAGMA foreign_keys=ON")
            db.row_factory = sqlite3.Row
            yield db

    # --- projects ----------------------------------------------------------------------------------

    def add_project(self, name: str, notes: str = "") -> dict:
        now = time.time()
        with self.connect() as db:
            number = db.execute("INSERT INTO projects (name, notes, created, updated) VALUES (?, ?, ?, ?)",
                                (_name(name, "A project's name"), str(notes or "")[:LONGEST_NOTES], now, now)).lastrowid
        return self.project(number)

    def project(self, number: int) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id = ?", (int(number),)).fetchone()
            if row is None:
                raise NotFound("no such project")
            missions = db.execute("SELECT COUNT(*) FROM missions WHERE project = ?", (row["id"],)).fetchone()[0]
        return {**_project(row), "missions": missions}

    def projects(self, archived: bool = False) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT p.*, (SELECT COUNT(*) FROM missions m WHERE m.project = p.id) AS count FROM projects p "
                              "WHERE archived = ? ORDER BY updated DESC, id DESC", (int(archived),)).fetchall()
        return [{**_project(row), "missions": row["count"]} for row in rows]

    def change_project(self, number: int, name: str | None = None, notes: str | None = None,
                       archived: bool | None = None) -> dict:
        self.project(number)
        with self.connect() as db:
            if name is not None:
                db.execute("UPDATE projects SET name = ? WHERE id = ?", (_name(name, "A project's name"), int(number)))
            if notes is not None:
                db.execute("UPDATE projects SET notes = ? WHERE id = ?", (str(notes)[:LONGEST_NOTES], int(number)))
            if archived is not None:
                db.execute("UPDATE projects SET archived = ? WHERE id = ?", (int(bool(archived)), int(number)))
            db.execute("UPDATE projects SET updated = ? WHERE id = ?", (time.time(), int(number)))
        return self.project(number)

    def delete_project(self, number: int) -> None:
        """The project goes; its missions stay, in Recent, with no project."""
        self.project(number)
        with self.connect() as db:
            db.execute("DELETE FROM projects WHERE id = ?", (int(number),))

    # --- missions ----------------------------------------------------------------------------------

    def add_mission(self, title: str = "New mission", project: int | None = None) -> dict:
        if project is not None:
            self.project(project)
        now = time.time()
        with self.connect() as db:
            number = db.execute("INSERT INTO missions (project, title, created, updated) VALUES (?, ?, ?, ?)",
                                (project, _name(title, "A mission's title"), now, now)).lastrowid
            if project is not None:
                db.execute("UPDATE projects SET updated = ? WHERE id = ?", (now, project))
        return self.mission(number)

    def mission(self, number: int) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM missions WHERE id = ?", (int(number),)).fetchone()
        if row is None:
            raise NotFound("no such mission")
        return _mission(row)

    def missions(self, project: int | None = None, most: int = 50) -> list[dict]:
        """A project's missions, or with no project given, the newest missions of all."""
        with self.connect() as db:
            if project is None:
                rows = db.execute("SELECT * FROM missions ORDER BY updated DESC, id DESC LIMIT ?", (most,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM missions WHERE project = ? ORDER BY updated DESC, id DESC LIMIT ?",
                                  (int(project), most)).fetchall()
        return [_mission(row) for row in rows]

    def change_mission(self, number: int, title: str | None = None, project: int | None = None,
                       no_project: bool = False) -> dict:
        self.mission(number)
        if project is not None:
            self.project(project)
        with self.connect() as db:
            if title is not None:
                db.execute("UPDATE missions SET title = ? WHERE id = ?", (_name(title, "A mission's title"), int(number)))
            if project is not None or no_project:
                db.execute("UPDATE missions SET project = ? WHERE id = ?", (None if no_project else project, int(number)))
        return self.mission(number)

    def delete_mission(self, number: int) -> None:
        self.mission(number)
        with self.connect() as db:
            db.execute("DELETE FROM missions WHERE id = ?", (int(number),))

    def search(self, words: str, most: int = 20) -> list[dict]:
        """Missions whose title or messages have these words."""
        text = " ".join(str(words or "").split())
        if not text:
            return []
        like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self.connect() as db:
            rows = db.execute("SELECT DISTINCT m.* FROM missions m LEFT JOIN messages s ON s.mission = m.id "
                              "WHERE m.title LIKE ? ESCAPE '\\' OR s.text LIKE ? ESCAPE '\\' ORDER BY m.updated DESC LIMIT ?",
                              (like, like, most)).fetchall()
        return [_mission(row) for row in rows]

    # --- messages ----------------------------------------------------------------------------------

    def say(self, mission: int, who: str, text: str, state: str = "") -> dict:
        self.mission(mission)
        now = time.time()
        with self.connect() as db:
            number = db.execute("INSERT INTO messages (mission, at, who, text, state) VALUES (?, ?, ?, ?, ?)",
                                (int(mission), now, who, str(text)[:LONGEST_TEXT], state)).lastrowid
            db.execute("UPDATE missions SET updated = ? WHERE id = ?", (now, int(mission)))
            db.execute("UPDATE projects SET updated = ? WHERE id = (SELECT project FROM missions WHERE id = ?)", (now, int(mission)))
        return {"id": number, "at": now, "who": who, "text": str(text)[:LONGEST_TEXT], "state": state}

    def messages(self, mission: int, after: int = 0) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id, at, who, text, state FROM messages WHERE mission = ? AND id > ? ORDER BY id",
                              (int(mission), int(after))).fetchall()
        return [dict(row) for row in rows]

    # --- files (W2) ----------------------------------------------------------------------------------

    def note_file(self, mission: int, name: str, how: str) -> None:
        """A finished step's file or folder, by the name the step gave it."""
        name = " ".join(str(name or "").split())[:LONGEST_NAME * 3]
        if not name or how not in FILE_WAYS:
            return
        with self.connect() as db:
            db.execute("INSERT INTO files (mission, at, name, how) VALUES (?, ?, ?, ?)", (int(mission), time.time(), name, how))

    def files(self, mission: int) -> list[dict]:
        """Each name once, newest first, with what last happened to it."""
        with self.connect() as db:
            rows = db.execute("SELECT name, how, at FROM files WHERE id IN (SELECT MAX(id) FROM files WHERE mission = ? "
                              "GROUP BY name) ORDER BY id DESC LIMIT ?", (int(mission), MOST_FILES)).fetchall()
        return [dict(row) for row in rows]


def _project(row) -> dict:
    return {"id": row["id"], "name": row["name"], "notes": row["notes"], "created": row["created"], "updated": row["updated"],
            "archived": bool(row["archived"])}


def _mission(row) -> dict:
    return {"id": row["id"], "project": row["project"], "title": row["title"], "created": row["created"], "updated": row["updated"]}
