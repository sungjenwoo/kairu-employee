"""Guardian's SQLite file (data/guardian.db): the audit log and Guardian's state.

The state is a small key/value table: Safe Mode, the emergency-stop counter, the PIN hash and
the wrong-PIN count. It is on disk, so it survives a restart. Several Kairu processes can use
the file at once (for example `kairu stop` while `kairu demo` runs); SQLite's locking keeps
them in order.

Every transaction that adds audit rows also moves the audit anchor (kairu/anchor.py) before it
commits, while it still holds the write lock, so the anchor and the database move together.

guardian.db is created on the first run only. If it is missing while an anchor exists, Kairu
refuses to start with an empty one (MissingDatabase): that would quietly reset Safe Mode, the PIN
and the audit log.
"""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from kairu import anchor

DB_NAME = "guardian.db"
ANCHOR_NAME = "audit.anchor"
GENESIS = "0" * 64  # the "previous hash" of the first audit row

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id        INTEGER PRIMARY KEY,
    ts        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    action    TEXT,
    decision  TEXT,
    details   TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
    BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
    BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class MissingDatabase(Exception):
    pass


class Store:
    def __init__(self, data_dir: Path, anchor_path: Path | None = None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / DB_NAME
        self.anchor_path = Path(anchor_path) if anchor_path else self.data_dir / ANCHOR_NAME
        if not self.path.exists() and self.anchor_path.exists():
            try:
                had = f"it had {anchor.read(self.anchor_path).rows} audit rows"
            except anchor.AnchorTampered:
                had = "it existed"
            raise MissingDatabase(f"{self.path} is missing, but the audit anchor shows {had}. Kairu will not start "
                                  "with an empty database, because that would quietly reset Safe Mode, the PIN and the "
                                  "audit log. See \"Starting again\" in GUARDIAN.md.")
        with self.connect(create=True) as db:
            db.execute("PRAGMA journal_mode=WAL")  # readers (the stop watcher) never wait for a writer
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self, create: bool = False):
        """A fresh connection in autocommit mode; use `transaction` for several statements at once.

        Only the first run may create the file: afterwards a missing guardian.db is an error, not a new empty one.
        """
        uri = f"{self.path.as_uri()}?mode={'rwc' if create else 'rw'}"
        with closing(sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)) as db:
            yield db

    @contextmanager
    def transaction(self, fresh_anchor: bool = False):
        """A write transaction that holds the lock from the start, so two processes never interleave.

        If it added audit rows, the anchor is moved to the newest one before the commit. fresh_anchor
        writes a new anchor without the old one's alerts (kairu audit reanchor).
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                before = newest_row(db)
                yield db
                after = newest_row(db)
                if after != before or fresh_anchor:
                    anchor.advance(self.anchor_path, before, after, fresh=fresh_anchor)
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    def get(self, key: str, default: str | None = None, db=None) -> str | None:
        if db is None:
            with self.connect() as db:
                return self.get(key, default, db)
        row = db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def put(self, key: str, value, db=None) -> None:
        if db is None:
            with self.connect() as db:
                return self.put(key, value, db)
        db.execute("INSERT INTO state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (key, str(value)))


def newest_row(db) -> tuple[int, str]:
    """(id, hash) of the newest audit row, or (0, GENESIS) when there is none."""
    row = db.execute("SELECT id, hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else (0, GENESIS)
