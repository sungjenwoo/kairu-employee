"""data/meetings.db on this PC: each meeting Kairu read, its transcript, and what came out of it.

    meetings  one row per meeting: its title, the day it was held, the file it came from (a name in your work folder, with
              its sha256), how it was heard (a transcript you gave, or Gemini writing down a recording), the transcript lines
              (secrets already left out), the summary and the people
    items     what came out of it: each decision, action and open question, with its owner, its deadline (a real date or ""),
              the words that show it (quote, and whether that quote is really in the transcript) and its status. Stage 2 (the
              decision ledger, HACKATHON.md) reads and changes the status: open, done, replaced. Stage 5 (proof): an item whose
              Clone work is all done becomes done, with its proof (who did it, its "done when" check, what was made)
    work      stage 5: which Clone task (team.db project and task) came from which meeting item, kept when Main Kairu splits a
              meeting (team.split); only links, never an order

Nothing here is a permission or an order, and nothing is sent anywhere: the file never uses the network. A transcript's
words never go into Guardian's audit log (Guardian keeps only hashes of an action's details). A secret is never kept: a
line with one is replaced before anything is written (kairu/meeting/read.py left_out).
"""

import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

DB_NAME = "meetings.db"
STATUSES = ("open", "done", "replaced", "dropped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    number     INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    held       TEXT NOT NULL,          -- YYYY-MM-DD
    file       TEXT NOT NULL,          -- the name in your work folder ("" for a recording made from the mic)
    sha256     TEXT NOT NULL,
    heard      TEXT NOT NULL,          -- "transcript" (your file), "gemini" (Gemini wrote it down), "mic" (recorded here)
    minutes    REAL,                   -- how long the recording was, if known
    transcript TEXT NOT NULL,          -- JSON list of lines, secrets left out
    summary    TEXT NOT NULL DEFAULT '',
    people     TEXT NOT NULL DEFAULT '[]',
    left_out   INTEGER NOT NULL DEFAULT 0,  -- lines left out because they held a secret
    provider   TEXT NOT NULL DEFAULT '',
    seconds    REAL,                   -- how long Kairu took, from the start of the action to the items
    made       REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    meeting    INTEGER NOT NULL,
    number     INTEGER NOT NULL,       -- 1, 2, ... within its meeting
    kind       TEXT NOT NULL,          -- decision, action, question
    what       TEXT NOT NULL,
    owner      TEXT NOT NULL DEFAULT '',
    due        TEXT NOT NULL DEFAULT '',  -- YYYY-MM-DD or ""
    due_said   TEXT NOT NULL DEFAULT '',
    replaces   TEXT NOT NULL DEFAULT '',
    quote      TEXT NOT NULL DEFAULT '',
    at         TEXT NOT NULL DEFAULT '',
    sure       TEXT NOT NULL DEFAULT 'medium',
    heard      INTEGER NOT NULL DEFAULT 0,      -- 1: the quote is really in the transcript
    owner_heard INTEGER NOT NULL DEFAULT 0,     -- 1: the owner's name is in the transcript
    status     TEXT NOT NULL DEFAULT 'open',
    changed    REAL,
    proof      TEXT NOT NULL DEFAULT '',        -- stage 5: what the Clones made for it (shown only)
    done_at    REAL,                            -- stage 5: when its Clone work was all done
    PRIMARY KEY (meeting, number)
);
CREATE TABLE IF NOT EXISTS work (
    project    INTEGER NOT NULL,       -- the team.db project Main Kairu split it into
    task       INTEGER NOT NULL,       -- that project's task
    meeting    INTEGER NOT NULL,       -- the meeting item it came from
    item       INTEGER NOT NULL,
    how        TEXT NOT NULL,          -- "named": the split named the item's id; "matched": Kairu matched the words; "only": the one item
    made       REAL NOT NULL,
    PRIMARY KEY (project, task, meeting, item)
);
CREATE TABLE IF NOT EXISTS conflicts (
    meeting    INTEGER NOT NULL,       -- the meeting that raised it (the newer one)
    number     INTEGER NOT NULL,       -- 1, 2, ... within that meeting
    kind       TEXT NOT NULL,          -- decision, deadline, owner, workload, dependency
    what       TEXT NOT NULL,          -- the conflict in one plain sentence
    item       INTEGER NOT NULL DEFAULT 0,      -- the newer meeting's item it is about (0: none)
    earlier_meeting INTEGER NOT NULL DEFAULT 0, -- the earlier meeting's item it clashes with (0: none)
    earlier_item    INTEGER NOT NULL DEFAULT 0,
    quote      TEXT NOT NULL DEFAULT '',        -- the newer meeting's words
    heard      INTEGER NOT NULL DEFAULT 0,      -- 1: that quote is really in the newer transcript
    status     TEXT NOT NULL DEFAULT 'open',    -- open, kept-new, kept-old
    PRIMARY KEY (meeting, number)
);
"""

CONFLICT_KINDS = ("decision", "deadline", "owner", "workload", "dependency")
CONFLICT_STATUSES = ("open", "kept-new", "kept-old")

UPGRADES = (("items", "proof", "TEXT NOT NULL DEFAULT ''"), ("items", "done_at", "REAL"))  # a meetings.db from stage 1-3
LINK_HOW = ("named", "matched", "only")

ITEM_FIELDS = ("kind", "what", "owner", "due", "due_said", "replaces", "quote", "at", "sure", "heard", "owner_heard")


class MeetingError(Exception):
    pass


def exists(data_dir) -> bool:
    return (Path(data_dir) / DB_NAME).exists()


class MeetingStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / DB_NAME
        self.data_dir.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)
            for table, column, kind in UPGRADES:
                if column not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
            db.commit()
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def add(self, title: str, held: str, file: str, sha256: str, heard: str, transcript: list[str], reading: dict,
            minutes: float | None = None, left_out: int = 0, provider: str = "", seconds: float | None = None) -> int:
        with closing(self.connect()) as db:
            cursor = db.execute(
                "INSERT INTO meetings (title, held, file, sha256, heard, minutes, transcript, summary, people, left_out, "
                "provider, seconds, made) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (title, held, file, sha256, heard, minutes, json.dumps(transcript), reading.get("summary", ""),
                 json.dumps(reading.get("people", [])), left_out, provider, seconds, time.time()))
            number = cursor.lastrowid
            for index, item in enumerate(reading.get("items", []), 1):
                db.execute(f"INSERT INTO items (meeting, number, {', '.join(ITEM_FIELDS)}) VALUES (?, ?, "
                           f"{', '.join('?' for _ in ITEM_FIELDS)})",
                           (number, index, *[int(item[name]) if name in ("heard", "owner_heard") else item.get(name, "")
                                             for name in ITEM_FIELDS]))
            for index, found in enumerate(reading.get("conflicts", []), 1):
                db.execute("INSERT INTO conflicts (meeting, number, kind, what, item, earlier_meeting, earlier_item, quote, "
                           "heard) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (number, index, found["kind"], found["what"], int(found.get("item", 0)),
                            int(found.get("earlier_meeting", 0)), int(found.get("earlier_item", 0)), found.get("quote", ""),
                            int(bool(found.get("heard")))))
            db.commit()
        return int(number)

    def _meeting(self, row, db, transcript: bool) -> dict:
        found = dict(row)
        found["people"] = json.loads(found["people"])
        lines = json.loads(found.pop("transcript"))
        found["lines"] = len(lines)
        if transcript:
            found["transcript"] = lines
        found["items"] = [dict(item, heard=bool(item["heard"]), owner_heard=bool(item["owner_heard"])) for item in
                          db.execute("SELECT * FROM items WHERE meeting = ? ORDER BY number", (row["number"],))]
        found["conflicts"] = [self._conflict(dict(item), db) for item in
                              db.execute("SELECT * FROM conflicts WHERE meeting = ? ORDER BY number", (row["number"],))]
        return found

    def _conflict(self, found: dict, db) -> dict:
        """A conflict with the earlier item it clashes with (its words, meeting title and day), when there is one."""
        found["heard"] = bool(found["heard"])
        found["earlier"] = None
        if found["earlier_meeting"]:
            row = db.execute("SELECT i.what, i.quote, i.owner, i.due, i.status, m.title, m.held FROM items i JOIN meetings m "
                             "ON m.number = i.meeting WHERE i.meeting = ? AND i.number = ?",
                             (found["earlier_meeting"], found["earlier_item"])).fetchone()
            found["earlier"] = dict(row) if row else None
        return found

    def meeting(self, number: int, transcript: bool = False) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM meetings WHERE number = ?", (int(number),)).fetchone()
            return self._meeting(row, db, transcript) if row else None

    def meetings(self, most: int = 50) -> list[dict]:
        """The newest first, each with its counts (no transcript, no items)."""
        with closing(self.connect()) as db:
            rows = db.execute("SELECT number, title, held, file, heard, minutes, made, summary, people FROM meetings "
                              "ORDER BY held DESC, number DESC LIMIT ?", (most,)).fetchall()
            out = []
            for row in rows:
                counts = {kind: count for kind, count in db.execute(
                    "SELECT kind, COUNT(*) FROM items WHERE meeting = ? GROUP BY kind", (row["number"],))}
                out.append({**dict(row), "people": json.loads(row["people"]), "decisions": counts.get("decision", 0),
                            "actions": counts.get("action", 0), "questions": counts.get("question", 0)})
            return out

    def latest(self) -> int | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT number FROM meetings ORDER BY made DESC LIMIT 1").fetchone()
            return int(row[0]) if row else None

    def known(self, sha256: str) -> int | None:
        """The meeting already read from exactly this file, if any."""
        with closing(self.connect()) as db:
            row = db.execute("SELECT number FROM meetings WHERE sha256 = ? AND sha256 != '' ORDER BY number DESC LIMIT 1",
                             (sha256,)).fetchone()
            return int(row[0]) if row else None

    def set_status(self, meeting: int, number: int, status: str) -> None:
        if status not in STATUSES:
            raise MeetingError(f"a status is one of {', '.join(STATUSES)}")
        with closing(self.connect()) as db:
            changed = db.execute("UPDATE items SET status = ?, changed = ? WHERE meeting = ? AND number = ?",
                                 (status, time.time(), int(meeting), int(number))).rowcount
            db.commit()
        if not changed:
            raise MeetingError(f"meeting {meeting} has no item {number}")

    def ledger(self, before: str = "", leave_out_sha: str = "") -> list[dict]:
        """Every decision and action across meetings (stage 2, the decision ledger), oldest meeting first, each with its
        meeting's number, title and day. before (YYYY-MM-DD): only meetings held on or before that day."""
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT i.*, m.title AS meeting_title, m.held AS held FROM items i JOIN meetings m ON m.number = i.meeting "
                "WHERE i.kind IN ('decision', 'action') AND (? = '' OR m.held <= ?) AND (? = '' OR m.sha256 != ?) "
                "ORDER BY m.held, m.number, i.number", (before, before, leave_out_sha, leave_out_sha)).fetchall()
            return [dict(row, heard=bool(row["heard"]), owner_heard=bool(row["owner_heard"])) for row in rows]

    def conflicts(self, status: str = "") -> list[dict]:
        """Every conflict a meeting raised, newest meeting first (status "" : all)."""
        with closing(self.connect()) as db:
            rows = db.execute("SELECT c.*, m.title AS meeting_title, m.held AS held FROM conflicts c JOIN meetings m "
                              "ON m.number = c.meeting WHERE (? = '' OR c.status = ?) ORDER BY m.held DESC, c.meeting DESC, "
                              "c.number", (status, status)).fetchall()
            out = []
            for row in rows:
                found = self._conflict(dict(row), db)
                item = db.execute("SELECT what, owner, due FROM items WHERE meeting = ? AND number = ?",
                                  (row["meeting"], row["item"])).fetchone() if row["item"] else None
                found["newer"] = dict(item) if item else None
                out.append(found)
            return out

    def resolve(self, meeting: int, number: int, keep: str) -> dict:
        """The manager decides a conflict: keep the new one (the earlier item becomes replaced) or the old one (the newer item
        is dropped). Returns the conflict."""
        if keep not in ("new", "old"):
            raise MeetingError("keep the new one or the old one")
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM conflicts WHERE meeting = ? AND number = ?", (int(meeting), int(number))).fetchone()
            if not row:
                raise MeetingError(f"meeting {meeting} has no conflict {number}")
            now = time.time()
            if keep == "new" and row["earlier_meeting"]:
                db.execute("UPDATE items SET status = 'replaced', changed = ? WHERE meeting = ? AND number = ?",
                           (now, row["earlier_meeting"], row["earlier_item"]))
            if keep == "old" and row["item"]:
                db.execute("UPDATE items SET status = 'dropped', changed = ? WHERE meeting = ? AND number = ?",
                           (now, row["meeting"], row["item"]))
            db.execute("UPDATE conflicts SET status = ? WHERE meeting = ? AND number = ?",
                       (f"kept-{keep}", int(meeting), int(number)))
            db.commit()
            return dict(row)

    # --- stage 5: proof and tracking (kairu/meeting/proof.py) -----------------------------------------------------------

    def link(self, project: int, task: int, meeting: int, item: int, how: str) -> None:
        """Clone task (project, task) came from this meeting item. Kept once; a link to an item that isn't there is refused."""
        if how not in LINK_HOW:
            raise MeetingError(f"a link is one of {', '.join(LINK_HOW)}")
        with closing(self.connect()) as db:
            if not db.execute("SELECT 1 FROM items WHERE meeting = ? AND number = ?", (int(meeting), int(item))).fetchone():
                raise MeetingError(f"meeting {meeting} has no item {item}")
            db.execute("INSERT OR IGNORE INTO work (project, task, meeting, item, how, made) VALUES (?, ?, ?, ?, ?, ?)",
                       (int(project), int(task), int(meeting), int(item), how, time.time()))
            db.commit()

    def links(self) -> list[dict]:
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM work ORDER BY project, task, meeting, item")]

    def set_done(self, meeting: int, number: int, proof: str, when: float | None = None) -> bool:
        """Its Clone work is done: an open item becomes done with its proof; a done item's proof is brought up to date.
        A replaced or dropped item stays as the manager decided. True if anything changed."""
        proof = " ".join(str(proof).split())[:1200]
        with closing(self.connect()) as db:
            row = db.execute("SELECT status, proof FROM items WHERE meeting = ? AND number = ?",
                             (int(meeting), int(number))).fetchone()
            if not row or row["status"] not in ("open", "done") or (row["status"] == "done" and row["proof"] == proof):
                return False
            now = when or time.time()
            db.execute("UPDATE items SET status = 'done', proof = ?, done_at = COALESCE(done_at, ?), changed = ? "
                       "WHERE meeting = ? AND number = ?", (proof, now, time.time(), int(meeting), int(number)))
            db.commit()
            return True

    def reopen(self, meeting: int, number: int) -> None:
        """A decision an earlier version marked done from its Clone work: open again (a decision isn't finished by a task).
        Only one with Kairu's proof on it; one the manager changed is left as it is."""
        with closing(self.connect()) as db:
            db.execute("UPDATE items SET status = 'open', proof = '', done_at = NULL, changed = ? WHERE meeting = ? AND "
                       "number = ? AND kind = 'decision' AND status = 'done' AND proof != ''",
                       (time.time(), int(meeting), int(number)))
            db.commit()

    def items_of(self, kind: str = "", status: str = "") -> list[dict]:
        """Every item of this kind and status ("" : any), with its meeting's title and day, oldest meeting first."""
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT i.*, m.title AS meeting_title, m.held AS held FROM items i JOIN meetings m ON m.number = i.meeting "
                "WHERE (? = '' OR i.kind = ?) AND (? = '' OR i.status = ?) ORDER BY m.held, m.number, i.number",
                (kind, kind, status, status)).fetchall()
            return [dict(row, heard=bool(row["heard"]), owner_heard=bool(row["owner_heard"])) for row in rows]

    def forget(self, number: int) -> bool:
        with closing(self.connect()) as db:
            db.execute("DELETE FROM work WHERE meeting = ?", (int(number),))
            db.execute("DELETE FROM conflicts WHERE meeting = ?", (int(number),))
            db.execute("DELETE FROM items WHERE meeting = ?", (int(number),))
            gone = db.execute("DELETE FROM meetings WHERE number = ?", (int(number),)).rowcount
            db.commit()
        return bool(gone)
