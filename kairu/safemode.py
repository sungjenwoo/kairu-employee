"""Emergency stop and Safe Mode, kept in guardian.db so every Kairu process sees them.

An emergency stop (`kairu stop`, Ctrl+Alt+K, or a call to emergency_stop) does two things:
  1. adds one to the stop counter; every action runner watches it and halts everything it is
     running as soon as it changes (kairu/runner.py, within 1 second);
  2. puts Kairu in Safe Mode: only read-only actions are allowed until you resume with "yes" and
     your PIN (Guardian.resume).

This module needs only the database, not the policy or the PIN, so stopping still works when
anything else is broken. A stop or a switch to Safe Mode is written first, on its own, so it holds
even if its audit row cannot be written afterwards.
"""

import sys
import time

from kairu import audit
from kairu.store import Store

NORMAL, SAFE = "normal", "safe"


def mode(store: Store) -> str:
    return store.get("mode", NORMAL)


def is_safe(store: Store) -> bool:
    return mode(store) == SAFE


def reason(store: Store) -> str:
    return store.get("safe_reason", "")


def stop_count(store: Store, db=None) -> int:
    return int(store.get("stop_count", "0", db))


def enter(store: Store, why: str) -> None:
    """Switch to Safe Mode (it stays on across restarts until you resume)."""
    with store.transaction() as db:
        already = store.get("mode", NORMAL, db) == SAFE
        store.put("mode", SAFE, db)
        if not already:
            store.put("safe_reason", why, db)
    if not already:
        _record(store, "safe_mode", decision="entered", reason=why)


def leave(store: Store, db) -> None:
    store.put("mode", NORMAL, db)
    store.put("safe_reason", "", db)
    audit.record(store, "safe_mode", decision="left", db=db)


def emergency_stop(store: Store, source: str) -> int:
    """Halt everything and enter Safe Mode. Returns the new stop count."""
    with store.transaction() as db:
        count = stop_count(store, db) + 1
        store.put("stop_count", count, db)
        store.put("stop_requested_at", repr(time.time()), db)
        store.put("mode", SAFE, db)
        store.put("safe_reason", f"emergency stop ({source})", db)
    _record(store, "emergency_stop", decision="stopped", source=source, stop=count)
    return count


def stop_requested_at(store: Store) -> float | None:
    value = store.get("stop_requested_at")
    return None if value is None else float(value)


def _record(store: Store, kind: str, **fields) -> None:
    try:
        audit.record(store, kind, **fields)
    except Exception as error:  # the change above is already made; say that its record is missing
        print(f"kairu: warning: the {kind} took effect, but its audit row could not be written ({error})", file=sys.stderr)
