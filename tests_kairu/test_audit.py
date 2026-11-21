"""The audit log: every request, decision and approval, hash-chained; tampering is found."""

import json
import sqlite3

import pytest

from kairu import audit
from kairu.guardian import Action, Refused
from tests_kairu.helpers import PIN, kairu


def raw(guardian):
    """Open guardian.db the way someone tampering with it would, with the append-only guard removed."""
    db = sqlite3.connect(guardian.store.path, isolation_level=None)
    db.execute("DROP TRIGGER audit_no_update")
    db.execute("DROP TRIGGER audit_no_delete")
    return db


def fill(guardian):
    guardian.check("chat.reply")
    guardian.check("credentials.reveal")
    guardian.check("files.shred")
    decision = guardian.check(Action("files.delete", {"path": "old.txt"}))
    guardian.approve(decision.request_id, "yes", PIN)


def test_every_request_decision_and_approval_is_recorded(guardian, with_pin):
    fill(guardian)
    with pytest.raises(Refused):
        guardian.approve(guardian.check("message.send").request_id, "yes", "000000")
    rows = [(row["kind"], row["action"], row["decision"]) for row in audit.tail(guardian.store, 100)]
    assert ("check", "chat.reply", "allow") in rows
    assert ("check", "credentials.reveal", "deny") in rows
    assert ("check", "files.shred", "deny") in rows
    assert ("check", "files.delete", "needs_approval") in rows
    assert ("approval", "files.delete", "granted") in rows
    assert ("approval", "message.send", "refused") in rows
    assert ("pin", None, "set") in rows


def test_an_untouched_log_verifies(guardian, with_pin):
    fill(guardian)
    verdict = audit.verify(guardian.store)
    assert verdict.ok and verdict.rows == 7  # policy loaded, PIN set, 4 checks, 1 approval
    result = kairu("audit", "verify")
    assert result.returncode == 0 and "intact" in result.stdout


def test_each_row_stores_the_hash_of_the_row_before(guardian, with_pin):
    fill(guardian)
    with sqlite3.connect(guardian.store.path) as db:
        rows = db.execute("SELECT prev_hash, hash FROM audit ORDER BY id").fetchall()
    assert rows[0][0] == audit.GENESIS
    assert all(later[0] == earlier[1] for earlier, later in zip(rows, rows[1:]))


def test_kairu_itself_can_only_add_rows(guardian):
    guardian.check("chat.reply")
    with sqlite3.connect(guardian.store.path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute("UPDATE audit SET decision = 'allow'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute("DELETE FROM audit")
    assert audit.verify(guardian.store).ok


def test_a_changed_decision_is_detected(guardian, with_pin):
    fill(guardian)
    db = raw(guardian)
    row = db.execute("SELECT id FROM audit WHERE action = 'credentials.reveal'").fetchone()[0]
    db.execute("UPDATE audit SET decision = 'allow' WHERE id = ?", (row,))
    verdict = audit.verify(guardian.store)
    assert not verdict.ok and verdict.bad_row == row and "changed" in verdict.problem
    result = kairu("audit", "verify")
    assert result.returncode == 1 and f"TAMPERED at row {row}" in result.stdout


def test_a_changed_detail_is_detected(guardian, with_pin):
    fill(guardian)
    db = raw(guardian)
    row_id, details = db.execute("SELECT id, details FROM audit WHERE action = 'files.delete' AND kind = 'approval'").fetchone()
    forged = json.dumps({**json.loads(details), "details": {"path": "C:/Windows"}})
    db.execute("UPDATE audit SET details = ? WHERE id = ?", (forged, row_id))
    assert audit.verify(guardian.store).bad_row == row_id


def test_a_deleted_row_is_detected(guardian, with_pin):
    fill(guardian)
    raw(guardian).execute("DELETE FROM audit WHERE action = 'files.shred'")
    verdict = audit.verify(guardian.store)
    assert not verdict.ok and "missing" in verdict.problem


def test_an_inserted_row_is_detected(guardian, with_pin):
    fill(guardian)
    db = raw(guardian)
    last_id, last_hash = db.execute("SELECT id, hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    db.execute("INSERT INTO audit VALUES (?, '2026-10-25T00:00:00+00:00', 'approval', 'money.spend', 'granted', '{}', ?, ?)",
               (last_id + 1, last_hash, "f" * 64))
    verdict = audit.verify(guardian.store)
    assert not verdict.ok and verdict.bad_row == last_id + 1


def test_swapped_rows_are_detected(guardian, with_pin):
    fill(guardian)
    db = raw(guardian)
    a, b = db.execute("SELECT id, kind, action, decision, details, prev_hash, hash FROM audit ORDER BY id LIMIT 2 OFFSET 2").fetchall()
    for target, source in ((a, b), (b, a)):
        db.execute("UPDATE audit SET kind=?, action=?, decision=?, details=?, prev_hash=?, hash=? WHERE id=?", (*source[1:], target[0]))
    assert not audit.verify(guardian.store).ok
