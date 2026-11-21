"""data/link.db: the paired devices, the nonces and Gate messages already seen, and where reading stopped.

It holds public keys and Gate topics only; this PC's private keys are sealed on their own
(kairu/link/keys.py). On Linux the file is readable by you only (mode 600). Several Kairu programs
use it at once (Guardian, link.receive, link.send, device.pair, device.remove); SQLite keeps them in order.

The devices "version" goes up whenever a device is paired or removed, so link.receive and Guardian
notice at once.

Guardian itself only reads it, through the functions at the bottom, which never create the file.
"""

import base64
import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from kairu.link.kinds import MOST_DEVICES, NONCE_SECONDS, SEAL_PURPOSE

DB_NAME = "link.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    sign      TEXT NOT NULL,   -- Ed25519 public key, base64
    box       TEXT NOT NULL,   -- X25519 public key, base64
    topic     TEXT NOT NULL,   -- the Gate topic this PC and the device share
    paired_at REAL NOT NULL,
    last_seen REAL
);
CREATE TABLE IF NOT EXISTS nonces (
    device TEXT NOT NULL,
    nonce  TEXT NOT NULL,
    ts     REAL NOT NULL,
    PRIMARY KEY (device, nonce)
);
CREATE INDEX IF NOT EXISTS nonces_ts ON nonces (ts);
CREATE TABLE IF NOT EXISTS relayed (   -- Gate message ids already handled, so a reconnect does not handle one twice
    id TEXT PRIMARY KEY,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvers (   -- Phase D2: a phone's fingerprint key (kairu/link/approver.py)
    device TEXT PRIMARY KEY,
    key    TEXT NOT NULL,                 -- Ed25519 public key, base64
    added  REAL NOT NULL
);
"""


class TooManyDevices(Exception):
    pass


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    sign: bytes
    box: bytes
    topic: str
    paired_at: float
    last_seen: float | None = None


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


class LinkStore:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DB_NAME
        new = not self.path.exists()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        if new and sys.platform != "win32":
            os.chmod(self.path, 0o600)  # who you paired, and your Gate topics, are yours alone

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

    # --- devices -------------------------------------------------------------------------------

    def devices(self) -> list[Device]:
        with self.connect() as db:
            rows = db.execute("SELECT id, name, sign, box, topic, paired_at, last_seen FROM devices ORDER BY paired_at").fetchall()
        return [_device(row) for row in rows]

    def device(self, device_id: str) -> Device | None:
        with self.connect() as db:
            row = db.execute("SELECT id, name, sign, box, topic, paired_at, last_seen FROM devices WHERE id = ?",
                             (device_id,)).fetchone()
        return _device(row) if row else None

    def add_device(self, device: Device) -> None:
        """Pair a device (again, if its id is known: its topic and name are replaced)."""
        with self.transaction() as db:
            known = db.execute("SELECT 1 FROM devices WHERE id = ?", (device.id,)).fetchone()
            if not known and db.execute("SELECT COUNT(*) FROM devices").fetchone()[0] >= MOST_DEVICES:
                raise TooManyDevices(f"Kairu pairs at most {MOST_DEVICES} devices; remove one first")
            db.execute("INSERT OR REPLACE INTO devices (id, name, sign, box, topic, paired_at, last_seen) "
                       "VALUES (?, ?, ?, ?, ?, ?, NULL)",
                       (device.id, device.name, _b64(device.sign), _b64(device.box), device.topic, device.paired_at))
            _bump(db)

    def remove_device(self, device_id: str) -> bool:
        with self.transaction() as db:
            gone = db.execute("DELETE FROM devices WHERE id = ?", (device_id,)).rowcount
            db.execute("DELETE FROM nonces WHERE device = ?", (device_id,))
            db.execute("DELETE FROM approvers WHERE device = ?", (device_id,))
            if gone:
                _bump(db)
        return bool(gone)

    def set_approver(self, device_id: str, key: str) -> bool:
        """Keep a paired phone's fingerprint key (device.approver). False if the device is not paired."""
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone():
                return False
            db.execute("INSERT OR REPLACE INTO approvers (device, key, added) VALUES (?, ?, ?)", (device_id, key, time.time()))
            _bump(db)
        return True

    def approver(self, device_id: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT a.key FROM approvers a JOIN devices d ON d.id = a.device WHERE a.device = ?",
                             (device_id,)).fetchone()
        return row[0] if row else None

    def touch(self, device_id: str, when: float) -> None:
        with self.connect() as db:
            db.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (when, device_id))

    def version(self) -> int:
        return int(self.get("version", "0"))

    # --- what was seen -------------------------------------------------------------------------

    def first_sight(self, relay_id: str, now: float) -> bool:
        """True the first time this Gate message id comes (and it is remembered); False after that."""
        with self.transaction() as db:
            db.execute("DELETE FROM relayed WHERE at < ?", (now - NONCE_SECONDS,))
            return db.execute("INSERT OR IGNORE INTO relayed (id, at) VALUES (?, ?)", (relay_id, now)).rowcount == 1

    def new_nonce(self, device_id: str, nonce: str, ts: float, now: float) -> bool:
        """True if this device never sent this nonce (and it is remembered); False means a replay."""
        with self.transaction() as db:
            db.execute("DELETE FROM nonces WHERE ts < ?", (now - NONCE_SECONDS,))
            return db.execute("INSERT OR IGNORE INTO nonces (device, nonce, ts) VALUES (?, ?, ?)",
                              (device_id, nonce, ts)).rowcount == 1

    def cursor(self) -> float | None:
        """The Gate time of the newest message handled: reading starts again from there."""
        value = self.get("cursor")
        return None if value is None else float(value)

    def set_cursor(self, when: float) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO state (key, value) VALUES ('cursor', ?) ON CONFLICT(key) DO UPDATE SET value = "
                       "MAX(CAST(value AS REAL), CAST(excluded.value AS REAL))", (repr(float(when)),))

    def get(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]


def _bump(db) -> None:
    db.execute("INSERT INTO state (key, value) VALUES ('version', '1') "
               "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)")


def _device(row) -> Device:
    return Device(row[0], row[1], base64.b64decode(row[2]), base64.b64decode(row[3]), row[4], row[5], row[6])


# --- for Guardian: reading only, never creating the file -----------------------------------------

def exists(data_dir) -> bool:
    return (Path(data_dir) / DB_NAME).exists()


def paired(data_dir) -> list[Device]:
    return LinkStore(data_dir).devices() if exists(data_dir) else []


def find(data_dir, device_id: str) -> Device | None:
    return LinkStore(data_dir).device(device_id) if exists(data_dir) else None


def approver(data_dir, device_id: str) -> str | None:
    """A paired phone's fingerprint key (base64), or None if fingerprint approval is not on for it."""
    return LinkStore(data_dir).approver(device_id) if exists(data_dir) else None


def version(data_dir) -> int:
    return LinkStore(data_dir).version() if exists(data_dir) else 0


# --- the pairing offer (kairu/link/pairing.py writes it; `kairu device pair` shows it) ------------------

OFFER_NAME = "link-pair.offer"


def read_offer(data_dir) -> dict | None:
    """The waiting offer ({"text", "code", "expires"}), or None."""
    from kairu.protect import sealed
    try:
        return sealed.read(Path(data_dir) / OFFER_NAME, SEAL_PURPOSE)
    except sealed.SealBroken:
        return None


def forget_offer(data_dir) -> None:
    (Path(data_dir) / OFFER_NAME).unlink(missing_ok=True)
