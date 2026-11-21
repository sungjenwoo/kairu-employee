"""data/shadows.db on the owner's PC: the Shadows, what each last said, the lessons waiting, and the installed packs.

It holds a Shadow's public keys and its Gate topic only while the Shadow is out. When it comes home, or the owner
gives up on it, they are deleted (forget_keys): nothing signed by that Shadow's key is read again. Nothing in this
file is a permission. On Linux it is readable by you only (mode 600).
"""

import base64
import json
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from pathlib import Path

from kairu.link.store import Device
from kairu.shadow.kinds import ACTIVE, MOST_SHADOWS

DB_NAME = "shadows.db"
OFFER_NAME = "shadow-invite.offer"
NONCE_SECONDS = 13 * 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS shadows (
    number   INTEGER PRIMARY KEY AUTOINCREMENT,
    id       TEXT NOT NULL UNIQUE,     -- sh- and 8 hex digits
    friend   TEXT NOT NULL,
    mission  TEXT NOT NULL,
    pack     TEXT NOT NULL,
    branch   TEXT NOT NULL,
    repo     TEXT NOT NULL,
    hours    REAL NOT NULL,
    state    TEXT NOT NULL,
    created  REAL NOT NULL,
    joined   REAL,
    ended    REAL,
    device   TEXT,                     -- the Shadow's temporary key's id, public keys and topic: only while it is out
    sign     TEXT,
    box      TEXT,
    topic    TEXT,
    since    TEXT,                     -- the last Gate message read on its topic
    last_seen REAL,
    progress TEXT,                     -- what it last said about its work (JSON)
    report   TEXT,                     -- its return report (JSON)
    mode     TEXT NOT NULL DEFAULT 'pack',   -- pack or cowork (ADR-039)
    base     TEXT NOT NULL DEFAULT ''        -- a Cowork Shadow's starting branch
);
CREATE TABLE IF NOT EXISTS nonces (
    device TEXT NOT NULL,
    nonce  TEXT NOT NULL,
    ts     REAL NOT NULL,
    PRIMARY KEY (device, nonce)
);
CREATE TABLE IF NOT EXISTS lessons (
    number INTEGER PRIMARY KEY AUTOINCREMENT,
    shadow INTEGER NOT NULL,
    text   TEXT NOT NULL,
    state  TEXT NOT NULL,              -- waiting, kept or dropped
    at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS packs (
    name        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    version     TEXT NOT NULL,
    made_by     TEXT NOT NULL,
    digest      TEXT NOT NULL,         -- what you approved with your PIN: a pack whose files differ is never run
    uses        TEXT NOT NULL,
    shadow      INTEGER NOT NULL,
    installed   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    job    TEXT PRIMARY KEY,
    pack   TEXT NOT NULL,
    ok     INTEGER NOT NULL,
    output TEXT NOT NULL,
    at     REAL NOT NULL
);
"""


class TooManyShadows(Exception):
    pass


class ShadowStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.path = self.data_dir / DB_NAME
        self.data_dir.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with self._open() as db:
            db.executescript(SCHEMA)
            have = {row[1] for row in db.execute("PRAGMA table_info(shadows)")}
            for column, kind in (("mode", "TEXT NOT NULL DEFAULT 'pack'"), ("base", "TEXT NOT NULL DEFAULT ''")):
                if column not in have:  # a shadows.db made by Shadow v0
                    db.execute(f"ALTER TABLE shadows ADD COLUMN {column} {kind}")
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)

    @contextmanager
    def _open(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    # Shadows

    def create(self, sid: str, friend: str, mission: str, pack: str, branch: str, repo: str, hours: float,
               mode: str = "pack", base: str = "") -> int:
        with self._open() as db:
            out = db.execute(f"SELECT COUNT(*) FROM shadows WHERE state IN ({','.join('?' * (len(ACTIVE) + 1))})",
                             ("invited", *ACTIVE)).fetchone()[0]
            if out >= MOST_SHADOWS:
                raise TooManyShadows(f"{MOST_SHADOWS} Shadows are out already; recall one first")
            return db.execute("INSERT INTO shadows (id, friend, mission, pack, branch, repo, hours, state, created, mode, "
                              "base) VALUES (?, ?, ?, ?, ?, ?, ?, 'invited', ?, ?, ?)",
                              (sid, friend, mission, pack, branch, repo, hours, time.time(), mode, base)).lastrowid

    def joined(self, number: int, device: Device) -> None:
        now = time.time()
        with self._open() as db:
            db.execute("UPDATE shadows SET state = 'working', joined = ?, last_seen = ?, device = ?, sign = ?, box = ?, "
                       "topic = ? WHERE number = ? AND state = 'invited'",
                       (now, now, device.id, _b64(device.sign), _b64(device.box), device.topic, number))

    def set_state(self, number: int, state: str, only_from: tuple[str, ...] | None = None) -> bool:
        ended = time.time() if state not in ("invited", *ACTIVE) else None
        with self._open() as db:
            query, values = "UPDATE shadows SET state = ?, ended = COALESCE(?, ended) WHERE number = ?", [state, ended, number]
            if only_from:
                query += f" AND state IN ({','.join('?' * len(only_from))})"
                values += only_from
            return db.execute(query, values).rowcount == 1

    def forget_keys(self, number: int) -> None:
        """The Shadow's temporary key is revoked here: its public keys, its topic and its nonces are deleted."""
        with self._open() as db:
            row = db.execute("SELECT device FROM shadows WHERE number = ?", (number,)).fetchone()
            if row and row["device"]:
                db.execute("DELETE FROM nonces WHERE device = ?", (row["device"],))
            db.execute("UPDATE shadows SET sign = NULL, box = NULL, topic = NULL, since = NULL WHERE number = ?", (number,))

    def heard(self, number: int, since: str | None = None, progress: dict | None = None, report: dict | None = None) -> None:
        with self._open() as db:
            if since is not None:
                db.execute("UPDATE shadows SET since = ? WHERE number = ?", (since, number))
            if progress is not None:
                db.execute("UPDATE shadows SET progress = ?, last_seen = ? WHERE number = ?",
                           (json.dumps(progress), time.time(), number))
            if report is not None:
                db.execute("UPDATE shadows SET report = ?, last_seen = ? WHERE number = ?",
                           (json.dumps(report), time.time(), number))

    def remember(self, device: str, nonce: str, ts: float, now: float) -> bool:
        with self._open() as db:
            db.execute("DELETE FROM nonces WHERE ts < ?", (now - NONCE_SECONDS,))
            try:
                db.execute("INSERT INTO nonces (device, nonce, ts) VALUES (?, ?, ?)", (device, nonce, ts))
            except sqlite3.IntegrityError:
                return False
            return True

    def get(self, number: int) -> dict | None:
        with self._open() as db:
            row = db.execute("SELECT * FROM shadows WHERE number = ?", (number,)).fetchone()
        return _shadow(row) if row else None

    def all(self) -> list[dict]:
        with self._open() as db:
            return [_shadow(row) for row in db.execute("SELECT * FROM shadows ORDER BY number")]

    def device(self, shadow: dict) -> Device | None:
        if not shadow.get("sign") or not shadow.get("topic"):
            return None
        return Device(shadow["device"], shadow["friend"], base64.b64decode(shadow["sign"]), base64.b64decode(shadow["box"]),
                      shadow["topic"], shadow["joined"] or 0.0)

    # lessons

    def add_lessons(self, number: int, lines: list[str]) -> None:
        with self._open() as db:
            db.executemany("INSERT INTO lessons (shadow, text, state, at) VALUES (?, ?, 'waiting', ?)",
                           [(number, line, time.time()) for line in lines])

    def lessons(self, state: str | None = None) -> list[dict]:
        with self._open() as db:
            rows = db.execute("SELECT * FROM lessons" + (" WHERE state = ?" if state else "") + " ORDER BY number",
                              (state,) if state else ())
            return [dict(row) for row in rows]

    def decide_lesson(self, number: int, keep: bool) -> bool:
        with self._open() as db:
            return db.execute("UPDATE lessons SET state = ? WHERE number = ? AND state = 'waiting'",
                              ("kept" if keep else "dropped", number)).rowcount == 1

    # packs

    def install(self, about: dict, digest: str, uses: list[str], shadow: int) -> None:
        with self._open() as db:
            db.execute("INSERT OR REPLACE INTO packs (name, title, description, version, made_by, digest, uses, shadow, "
                       "installed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (about["name"], about["title"], about["description"], about["version"], about["made_by"], digest,
                        ", ".join(uses), shadow, time.time()))

    def packs(self) -> list[dict]:
        with self._open() as db:
            return [dict(row) for row in db.execute("SELECT * FROM packs ORDER BY name")]

    def pack(self, name: str) -> dict | None:
        with self._open() as db:
            row = db.execute("SELECT * FROM packs WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def remove_pack(self, name: str) -> bool:
        with self._open() as db:
            return db.execute("DELETE FROM packs WHERE name = ?", (name,)).rowcount == 1

    def ran(self, job: str, pack: str, ok: bool, output: str) -> None:
        with self._open() as db:
            db.execute("DELETE FROM runs WHERE at < ?", (time.time() - 24 * 3600,))
            db.execute("INSERT OR REPLACE INTO runs (job, pack, ok, output, at) VALUES (?, ?, ?, ?, ?)",
                       (job, pack, int(ok), output, time.time()))

    def run_result(self, job: str) -> dict | None:
        with self._open() as db:
            row = db.execute("SELECT * FROM runs WHERE job = ?", (job,)).fetchone()
        return dict(row) if row else None


def _shadow(row) -> dict:
    shadow = dict(row)
    for key in ("progress", "report"):
        shadow[key] = json.loads(shadow[key]) if shadow[key] else None
    return shadow


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def packs_folder(data_dir) -> Path:
    return Path(data_dir).resolve() / "packs"
