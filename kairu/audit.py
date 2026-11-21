"""The audit log: one row for every request, decision, approval, stop and run, in guardian.db.

Each row stores the hash of the row before it, and its own hash covers its id, its contents and
that previous hash. Changing, inserting, removing or reordering any row breaks the chain, and
`kairu audit verify` (verify() below) finds the first row where it breaks. The database also
refuses UPDATE and DELETE on the table, so Kairu itself can only ever add rows.

A hash chain alone cannot catch the newest rows being deleted, or every hash being rewritten
from some row onwards. For that, verify() also compares the database with the audit anchor
(kairu/anchor.py), a separate file holding the row count and newest hash.

Never put a PIN or other secret in `details`.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from kairu import anchor
from kairu.store import GENESIS, Store, newest_row

CHAIN_BROKEN = "chain_broken"
LABELS = {
    CHAIN_BROKEN: "rows were changed, inserted or removed",
    anchor.NEWEST_DELETED: "newest rows deleted",
    anchor.DB_MISSING: "database file missing",
    anchor.ANCHOR_MISSING: "anchor missing",
    anchor.ANCHOR_TAMPERED: "anchor tampered",
    anchor.ANCHOR_MISMATCH: "anchor and database do not match",
}


def _row_hash(row_id: int, ts: str, kind: str, action, decision, details: str, prev_hash: str) -> str:
    fields = [row_id, ts, kind, action, decision, details, prev_hash]
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode("utf-8")).hexdigest()


def record(store: Store, kind: str, action: str | None = None, decision: str | None = None, db=None, **details) -> int:
    """Append one row and return its id. Pass `db` to write inside a transaction you already hold."""
    if db is None:
        with store.transaction() as db:
            return record(store, kind, action, decision, db, **details)
    last_id, prev_hash = newest_row(db)
    row_id = last_id + 1
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    body = json.dumps(details, sort_keys=True, separators=(",", ":"), default=str)
    digest = _row_hash(row_id, ts, kind, action, decision, body, prev_hash)
    db.execute("INSERT INTO audit (id, ts, kind, action, decision, details, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (row_id, ts, kind, action, decision, body, prev_hash, digest))
    return row_id


@dataclass
class Verdict:
    ok: bool
    rows: int
    bad_row: int | None = None
    problem: str = ""
    kind: str = "ok"  # or CHAIN_BROKEN, or one of the anchor kinds (anchor.NEWEST_DELETED, ...)


def verify(store: Store) -> Verdict:
    """Check the chain row by row, then compare the database with the anchor. The first problem found."""
    with store.connect() as db:  # read the anchor and the newest row while no one is writing, so they agree
        db.execute("BEGIN IMMEDIATE")
        try:
            newest = newest_row(db)
            try:
                anchored, anchor_problem = anchor.read(store.anchor_path), anchor.protection_problem(store.anchor_path)
            except anchor.AnchorTampered as error:
                anchored, anchor_problem = None, f"the anchor was tampered with: {error}"
        finally:
            db.execute("ROLLBACK")

    broken, count, hash_at_anchor = _walk(store, anchored.rows if anchored else 0)
    if broken:
        return broken
    if anchor_problem:
        return Verdict(False, count, None, anchor_problem, anchor.ANCHOR_TAMPERED)
    if anchored is None:
        if newest[0] == 0:
            return Verdict(True, 0)
        return Verdict(False, count, None, f"the anchor ({store.anchor_path.name}) is missing, so deleted newest rows "
                       f"could not be noticed; the database has {newest[0]} rows", anchor.ANCHOR_MISSING)
    if anchored.alerts:
        first = anchored.alerts[0]
        return Verdict(False, count, first.row, "; ".join(alert.text for alert in anchored.alerts), first.kind)
    if anchored.rows > newest[0]:
        return Verdict(False, count, newest[0] + 1, f"the newest rows were deleted: the anchor says {anchored.rows} rows, "
                       f"the database has {newest[0]} (rows {newest[0] + 1} to {anchored.rows} are gone)", anchor.NEWEST_DELETED)
    if anchored.rows < newest[0] or hash_at_anchor != anchored.hash:
        return Verdict(False, count, anchored.rows, f"the anchor ({anchored.rows} rows) does not match the database "
                       f"({newest[0]} rows): rows were rewritten or added without Kairu, or an older or edited anchor "
                       "was put in place", anchor.ANCHOR_MISMATCH)
    return Verdict(True, count)


def _walk(store: Store, anchor_rows: int) -> tuple[Verdict | None, int, str]:
    """Check every row's links and hash. (the first broken row, or None; rows checked; hash of row anchor_rows)"""
    expected_id, prev_hash, count, hash_at = 1, GENESIS, 0, GENESIS
    with store.connect() as db:
        for row in db.execute("SELECT id, ts, kind, action, decision, details, prev_hash, hash FROM audit ORDER BY id"):
            row_id, ts, kind, action, decision, details, stored_prev, stored_hash = row
            if row_id != expected_id:
                problem = f"expected row {expected_id} next, found row {row_id}: rows are missing"
                return Verdict(False, count, row_id, problem, CHAIN_BROKEN), count, hash_at
            if stored_prev != prev_hash:
                problem = "its previous-row hash does not match the row before it"
                return Verdict(False, count, row_id, problem, CHAIN_BROKEN), count, hash_at
            if _row_hash(row_id, ts, kind, action, decision, details, stored_prev) != stored_hash:
                problem = "its contents do not match its hash: the row was changed"
                return Verdict(False, count, row_id, problem, CHAIN_BROKEN), count, hash_at
            if row_id == anchor_rows:
                hash_at = stored_hash
            expected_id, prev_hash, count = row_id + 1, stored_hash, count + 1
    return None, count, hash_at


def reanchor(store: Store, verdict: Verdict) -> None:
    """Accept the database as it is now: a fresh anchor without alerts, and a row saying what was accepted."""
    with store.transaction(fresh_anchor=True) as db:
        record(store, "anchor", decision="re-anchored", db=db, accepted=LABELS.get(verdict.kind, verdict.kind),
               problem=verdict.problem, rows=verdict.rows)


def tail(store: Store, count: int = 20, kind: str | None = None) -> list[dict]:
    """The newest rows, oldest first, with `details` decoded."""
    query = "SELECT id, ts, kind, action, decision, details FROM audit"
    query += " WHERE kind = ?" if kind else ""
    with store.connect() as db:
        rows = db.execute(query + " ORDER BY id DESC LIMIT ?", (kind, count) if kind else (count,)).fetchall()
    return [{"id": r[0], "ts": r[1], "kind": r[2], "action": r[3], "decision": r[4], "details": json.loads(r[5])}
            for r in reversed(rows)]
