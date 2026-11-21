"""The audit anchor: deleting the newest rows, the database, or the anchor, or changing the anchor, is reported."""

import os
import sqlite3
import sys
from contextlib import closing

import pytest

from kairu import anchor, audit, pin
from kairu.guardian import Guardian, Verdict as Decision
from kairu.store import MissingDatabase, newest_row
from tests_kairu.helpers import PIN, kairu


def fill(guardian, count=6):
    for i in range(count):
        guardian.check("chat.reply" if i % 2 else "files.read")


def delete_newest(guardian, count):
    """Delete the newest audit rows, as someone with access to the file could (removing the append-only guard first)."""
    with closing(sqlite3.connect(guardian.store.path, isolation_level=None)) as db:
        db.execute("DROP TRIGGER audit_no_delete")
        db.execute("DELETE FROM audit WHERE id > (SELECT MAX(id) FROM audit) - ?", (count,))


def newest(guardian):
    with guardian.store.connect() as db:
        return newest_row(db)


def test_the_anchor_follows_every_new_row(guardian):
    fill(guardian)
    held = anchor.read(guardian.store.anchor_path)
    assert (held.rows, held.hash) == newest(guardian) and held.alerts == ()
    assert audit.verify(guardian.store).ok


def test_deleting_the_newest_rows_is_detected(guardian):
    fill(guardian)
    rows_before = newest(guardian)[0]
    delete_newest(guardian, 2)
    verdict = audit.verify(guardian.store)
    assert not verdict.ok and verdict.kind == anchor.NEWEST_DELETED
    assert f"the anchor says {rows_before} rows, the database has {rows_before - 2}" in verdict.problem
    result = kairu("audit", "verify")
    assert result.returncode == 1 and "newest rows deleted" in result.stdout


def test_deleted_newest_rows_stay_detected_after_kairu_writes_more(guardian):
    fill(guardian)
    delete_newest(guardian, 3)
    fill(guardian, 10)  # the anchor moves on, but keeps what it found
    verdict = audit.verify(guardian.store)
    assert verdict.kind == anchor.NEWEST_DELETED and "newest rows were deleted" in verdict.problem
    assert "newest rows deleted" in kairu("audit", "verify").stdout


def test_a_missing_database_is_reported_and_kairu_will_not_start_with_an_empty_one(guardian, config):
    fill(guardian)
    for suffix in ("", "-wal", "-shm"):
        guardian.store.path.with_name(guardian.store.path.name + suffix).unlink(missing_ok=True)
    result = kairu("audit", "verify")
    assert result.returncode == 1 and "database file missing" in result.stdout
    with pytest.raises(MissingDatabase, match="will not start with an empty database"):
        Guardian(config)  # so Safe Mode, the PIN and the log cannot be reset by deleting the file
    assert kairu("status").returncode == 2
    assert not guardian.store.path.exists()  # nothing quietly made a new one


def test_a_missing_anchor_is_reported(guardian):
    fill(guardian)
    guardian.store.anchor_path.unlink()
    verdict = audit.verify(guardian.store)
    assert verdict.kind == anchor.ANCHOR_MISSING
    result = kairu("audit", "verify")  # this run writes a "policy loaded" row, which makes a new anchor...
    assert result.returncode == 1 and "anchor missing" in result.stdout
    fill(guardian, 3)
    assert audit.verify(guardian.store).kind == anchor.ANCHOR_MISSING  # ...that still says the old one went missing


def test_a_changed_anchor_is_reported(guardian):
    fill(guardian)
    raw = bytearray(guardian.store.anchor_path.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    guardian.store.anchor_path.write_bytes(bytes(raw))
    verdict = audit.verify(guardian.store)
    assert verdict.kind == anchor.ANCHOR_TAMPERED and "tampered" in verdict.problem
    result = kairu("audit", "verify")
    assert result.returncode == 1 and "anchor tampered" in result.stdout


def test_an_older_copy_of_the_anchor_put_back_is_reported(guardian):
    fill(guardian)
    old = guardian.store.anchor_path.read_bytes()
    fill(guardian, 4)
    guardian.store.anchor_path.write_bytes(old)
    assert audit.verify(guardian.store).kind == anchor.ANCHOR_MISMATCH
    fill(guardian, 2)
    assert audit.verify(guardian.store).kind == anchor.ANCHOR_MISMATCH  # still on record after more rows


def test_an_anchor_written_for_other_rows_is_reported(guardian):
    fill(guardian)
    rows, _ = newest(guardian)
    anchor.write(guardian.store.anchor_path, anchor.Anchor(rows, "a" * 64))  # right count, wrong newest hash
    verdict = audit.verify(guardian.store)
    assert verdict.kind == anchor.ANCHOR_MISMATCH and "does not match" in verdict.problem


@pytest.mark.skipif(sys.platform == "win32", reason="on Windows, DPAPI protects the anchor instead")
def test_on_linux_the_anchor_is_readable_only_by_you(guardian):
    fill(guardian)
    assert guardian.store.anchor_path.stat().st_mode & 0o777 == 0o600
    os.chmod(guardian.store.anchor_path, 0o644)
    verdict = audit.verify(guardian.store)
    assert verdict.kind == anchor.ANCHOR_TAMPERED and "other users can read or change" in verdict.problem


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_on_windows_the_anchor_is_sealed_with_dpapi(guardian):
    fill(guardian)
    raw = guardian.store.anchor_path.read_bytes()
    assert b'"rows"' not in raw and b"Kairu" not in raw  # not readable as it is
    assert anchor.read(guardian.store.anchor_path).rows == newest(guardian)[0]


def test_a_failed_anchor_write_leaves_the_database_and_the_anchor_as_they_were(guardian, monkeypatch):
    fill(guardian)
    before, held = newest(guardian), guardian.store.anchor_path.read_bytes()

    def power_cut(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(anchor.os, "replace", power_cut)
    assert guardian.check("chat.reply").verdict is Decision.DENY  # unrecorded, so refused
    monkeypatch.undo()
    assert newest(guardian) == before and guardian.store.anchor_path.read_bytes() == held
    assert not list(guardian.store.anchor_path.parent.glob("*.tmp"))
    assert audit.verify(guardian.store).ok


def test_reanchor_accepts_the_log_as_it_is_and_keeps_a_record(guardian, with_pin):
    fill(guardian)
    delete_newest(guardian, 2)
    problem = audit.verify(guardian.store)
    assert pin.check(guardian.store, PIN)[0]
    audit.reanchor(guardian.store, problem)
    assert audit.verify(guardian.store).ok
    row = audit.tail(guardian.store, 1)[0]
    assert (row["kind"], row["decision"], row["details"]["accepted"]) == ("anchor", "re-anchored", "newest rows deleted")


def test_kairu_audit_reanchor_needs_yes(guardian, with_pin):
    fill(guardian)
    guardian.store.anchor_path.unlink()
    result = kairu("audit", "reanchor", input_text="no\n")
    assert result.returncode == 1 and 'did not type "yes"' in result.stdout
    assert not audit.verify(guardian.store).ok


def test_kairu_audit_reanchor_refuses_when_rows_inside_were_changed(guardian):
    fill(guardian)
    with closing(sqlite3.connect(guardian.store.path, isolation_level=None)) as db:
        db.execute("DROP TRIGGER audit_no_update")
        db.execute("UPDATE audit SET decision = 'deny' WHERE id = 2")  # row 2 is an allowed files.read
    result = kairu("audit", "reanchor")
    assert result.returncode == 1 and "Refused" in result.stdout


def broken_disk(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(anchor.os, "replace", fail)  # no audit row can be written from here on


def test_a_stop_holds_even_when_no_audit_row_can_be_written(guardian, runner, monkeypatch, capsys):
    from kairu import safemode
    broken_disk(monkeypatch)
    runner.stop("test")
    assert safemode.is_safe(guardian.store) and safemode.stop_count(guardian.store) == 1
    assert "audit row could not be written" in capsys.readouterr().err


def test_the_wrong_pin_lock_holds_even_when_no_audit_row_can_be_written(guardian, with_pin, monkeypatch):
    from kairu import safemode
    broken_disk(monkeypatch)
    for _ in range(pin.MAX_FAILURES):
        assert not pin.check(guardian.store, "999999")[0]
    assert safemode.is_safe(guardian.store)
    assert "too many wrong PINs" in pin.check(guardian.store, PIN)[1]
