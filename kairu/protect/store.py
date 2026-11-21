"""The protection store (data/protection.db): what Guardian's monitors found, and where each source stands.

Written by the monitors (kairu/protect/watch.py) and by the small actions Guardian runs for you
(kairu/protect/actions.py); read by `kairu alerts` and `kairu protect status`. Nothing in it is a
permission: Guardian never reads it to decide anything.

  alerts       one row per alert: what was found, why, the evidence, what could not be checked;
               "new" until you dismiss it. The same thing never alerts twice (its key is unique).
  sources      each source's health: Active, Paused, Disconnected, Permission removed, ...
  checkpoints  where a source stopped (Gmail's history id), so it can catch up after a gap
  deadlines    yours and the ones found in emails, with the reminders already given
  settings     pauses, and when a source was last watched

Alert details are kept for RETENTION_DAYS; Guardian's audit log keeps only each alert's kind,
source, time and fingerprint.
"""

import json
import os
import re
import sqlite3
import sys
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kairu.protect import kinds

DB_NAME = "protection.db"
RETENTION_DAYS = 90

# a source's health, as `kairu protect status` shows it
ACTIVE, DEGRADED, PAUSED, DISCONNECTED, PERMISSION_REMOVED, NOT_SET_UP = (
    "Active", "Degraded", "Paused", "Disconnected", "Permission removed", "Not set up")

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id             INTEGER PRIMARY KEY,
    key            TEXT NOT NULL UNIQUE,
    created        TEXT NOT NULL,
    source         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    severity       TEXT NOT NULL,
    classification TEXT NOT NULL,
    confidence     TEXT NOT NULL,
    title          TEXT NOT NULL,
    body           TEXT NOT NULL,
    found_late     INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'new',
    closed         TEXT,
    reported       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sources (
    name         TEXT PRIMARY KEY,
    state        TEXT NOT NULL,
    detail       TEXT NOT NULL DEFAULT '',
    last_checked TEXT,
    failures     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checkpoints (
    source TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deadlines (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    due        TEXT NOT NULL,
    origin     TEXT NOT NULL,
    origin_key TEXT UNIQUE,
    note       TEXT NOT NULL DEFAULT '',
    created    TEXT NOT NULL,
    stage      INTEGER NOT NULL DEFAULT 0,
    closed     TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


@dataclass
class Finding:
    """One alert, as a monitor found it. `key` makes it unique: the same thing never alerts twice."""
    key: str
    source: str
    kind: str
    severity: str
    classification: str
    title: str
    lines: list[tuple[str, str]] = field(default_factory=list)  # ("From", "...") shown under the title
    why: list[str] = field(default_factory=list)  # the evidence, one point each
    not_checked: list[str] = field(default_factory=list)
    you_can: str = ""
    confidence: str = ""  # high, medium, low, or "" where it does not apply
    confidence_reason: str = ""
    found_late: bool = False

    def __post_init__(self):
        if self.source not in kinds.SOURCES or self.kind not in kinds.KINDS or self.severity not in kinds.SEVERITIES:
            raise ValueError(f"not a known source, kind or severity: {self.source}, {self.kind}, {self.severity}")
        if self.classification not in kinds.CLASSIFICATIONS:
            raise ValueError(f"not a classification: {self.classification}")


@dataclass
class Alert:
    id: int
    created: datetime
    source: str
    kind: str
    severity: str
    classification: str
    confidence: str
    title: str
    lines: list
    why: list
    not_checked: list
    you_can: str
    confidence_reason: str
    found_late: bool
    status: str
    key: str


class ProtectStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DB_NAME
        new = not self.path.exists()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)  # what your email alerts say is yours alone

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

    # --- alerts ------------------------------------------------------------------------------

    def add_alert(self, finding: Finding, db=None) -> int | None:
        """Store a new alert and return its number; None if this one was alerted before."""
        if db is None:
            with self.transaction() as db:
                return self.add_alert(finding, db)
        body = json.dumps({"lines": finding.lines, "why": finding.why, "not_checked": finding.not_checked,
                           "you_can": finding.you_can, "confidence_reason": finding.confidence_reason})
        cursor = db.execute(
            "INSERT OR IGNORE INTO alerts (key, created, source, kind, severity, classification, confidence, title, body, "
            "found_late) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (finding.key, iso(now_utc()), finding.source, finding.kind, finding.severity, finding.classification,
             finding.confidence, finding.title, body, int(finding.found_late)))
        return cursor.lastrowid if cursor.rowcount else None

    def has_alert(self, key: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM alerts WHERE key = ?", (key,)).fetchone() is not None

    def alerts(self, include_closed: bool = False, limit: int = 50) -> list[Alert]:
        query = "SELECT * FROM alerts" + ("" if include_closed else " WHERE status = 'new'") + " ORDER BY id DESC LIMIT ?"
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [_alert(row) for row in db.execute(query, (limit,))]

    def alert(self, number: int) -> Alert | None:
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM alerts WHERE id = ?", (number,)).fetchone()
        return _alert(row) if row else None

    def close_alert(self, number: int, false_alarm: bool = False) -> bool:
        """Mark an alert done (or a false alarm, kept as your report). False if there is no such open alert."""
        with self.transaction() as db:
            cursor = db.execute("UPDATE alerts SET status = ?, closed = ? WHERE id = ? AND status = 'new'",
                                ("false_alarm" if false_alarm else "dismissed", iso(now_utc()), number))
            return cursor.rowcount == 1

    def unreported(self) -> list[tuple[int, str, str, str, str]]:
        """(number, source, kind, severity, key) of alerts Guardian has not been told about yet."""
        with self.connect() as db:
            return db.execute("SELECT id, source, kind, severity, key FROM alerts WHERE reported = 0 ORDER BY id").fetchall()

    def mark_reported(self, number: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE alerts SET reported = 1 WHERE id = ?", (number,))

    def forget_old(self, days: int = RETENTION_DAYS) -> int:
        """Delete alert details older than `days`. Guardian's audit log keeps its own short row for each."""
        cutoff = iso(now_utc() - timedelta(days=days))
        with self.transaction() as db:
            return db.execute("DELETE FROM alerts WHERE created < ? AND reported = 1", (cutoff,)).rowcount

    def count_new(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM alerts WHERE status = 'new'").fetchone()[0]

    # --- sources, checkpoints, settings -------------------------------------------------------

    def set_source(self, name: str, state: str, detail: str = "", checked: bool = False, failures: int | None = None) -> None:
        with self.transaction() as db:
            db.execute("INSERT INTO sources (name, state, detail) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                       "state = excluded.state, detail = excluded.detail", (name, state, detail))
            if checked:
                db.execute("UPDATE sources SET last_checked = ? WHERE name = ?", (iso(now_utc()), name))
            if failures is not None:
                db.execute("UPDATE sources SET failures = ? WHERE name = ?", (failures, name))

    def source(self, name: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT state, detail, last_checked, failures FROM sources WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return {"state": row[0], "detail": row[1], "last_checked": parse_iso(row[2]), "failures": row[3]}

    def sources(self) -> dict[str, dict]:
        with self.connect() as db:
            names = [row[0] for row in db.execute("SELECT name FROM sources ORDER BY name")]
        return {name: self.source(name) for name in names}

    def checkpoint(self, source: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM checkpoints WHERE source = ?", (source,)).fetchone()
        return row[0] if row else None

    def set_checkpoint(self, source: str, value: str | None) -> None:
        with self.connect() as db:
            if value is None:
                db.execute("DELETE FROM checkpoints WHERE source = ?", (source,))
            else:
                db.execute("INSERT INTO checkpoints (source, value) VALUES (?, ?) ON CONFLICT(source) DO UPDATE SET "
                           "value = excluded.value", (source, value))

    def setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str | None) -> None:
        with self.connect() as db:
            if value is None:
                db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
                           "value = excluded.value", (key, value))

    def paused(self, source: str) -> bool:
        return self.setting("paused:all") == "1" or self.setting(f"paused:{source}") == "1"

    # --- deadlines ----------------------------------------------------------------------------

    def add_deadline(self, title: str, due: datetime, origin: str, origin_key: str | None = None, note: str = "") -> int | None:
        """A new deadline's number; None if this one is already known.

        Already known: the same origin_key (the same email), or, for a deadline found in an email, an open one
        due at the same minute with the same title or the same sentence (a sender's second reminder email).
        """
        with self.transaction() as db:
            if origin == "email":
                for other_title, other_note in db.execute(
                        "SELECT title, note FROM deadlines WHERE closed IS NULL AND due = ?", (due.isoformat(timespec="minutes"),)):
                    if same_title(other_title, title) or (note and other_note == note):
                        return None
            cursor = db.execute("INSERT OR IGNORE INTO deadlines (title, due, origin, origin_key, note, created) "
                                "VALUES (?, ?, ?, ?, ?, ?)", (title, due.isoformat(timespec="minutes"), origin, origin_key,
                                                              note, iso(now_utc())))
            return cursor.lastrowid if cursor.rowcount else None

    def deadlines(self, open_only: bool = True) -> list[dict]:
        query = "SELECT id, title, due, origin, note, stage, closed FROM deadlines"
        query += " WHERE closed IS NULL" if open_only else ""
        with self.connect() as db:
            rows = db.execute(query + " ORDER BY due").fetchall()
        return [{"id": r[0], "title": r[1], "due": datetime.fromisoformat(r[2]), "origin": r[3], "note": r[4],
                 "stage": r[5], "closed": r[6]} for r in rows]

    def set_deadline_stage(self, number: int, stage: int, close: bool = False) -> None:
        with self.connect() as db:
            db.execute("UPDATE deadlines SET stage = ?, closed = CASE WHEN ? THEN ? ELSE closed END WHERE id = ?",
                       (stage, int(close), iso(now_utc()), number))

    def remove_deadline(self, number: int) -> bool:
        with self.connect() as db:
            cursor = db.execute("UPDATE deadlines SET closed = ? WHERE id = ? AND closed IS NULL", (iso(now_utc()), number))
            return cursor.rowcount == 1


_TAGS = re.compile(r"^\s*(\[[^\]]*\]|re|fwd?|fw|reminder(\s*-?\s*\d+)?)\s*[:\-]?\s*", re.I)


def same_title(a: str, b: str) -> bool:
    """True if two email subjects are the same apart from tags such as "[Reminder-1]:", "Re:" or "Fwd:"."""
    def plain(text: str) -> str:
        text = (text or "").strip().rstrip("…").lower()
        while (stripped := _TAGS.sub("", text, count=1)) != text:
            text = stripped
        return " ".join(text.split())
    one, two = plain(a), plain(b)
    return bool(one) and (one == two or (min(len(one), len(two)) >= 40 and (one.startswith(two) or two.startswith(one))))


def _alert(row) -> Alert:
    body = json.loads(row["body"])
    return Alert(row["id"], parse_iso(row["created"]), row["source"], row["kind"], row["severity"], row["classification"],
                 row["confidence"], row["title"], [tuple(line) for line in body.get("lines", [])], body.get("why", []),
                 body.get("not_checked", []), body.get("you_can", ""), body.get("confidence_reason", ""),
                 bool(row["found_late"]), row["status"], row["key"])
