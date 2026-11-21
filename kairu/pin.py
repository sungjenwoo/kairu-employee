"""Your Kairu PIN: set on this PC, stored only as an Argon2id hash in guardian.db.

The PIN itself is never stored or logged. After 5 wrong PINs in a row, Kairu enters Safe Mode and
refuses every PIN for 60 seconds; each further wrong PIN starts the 60 seconds again. The count
is on disk, so restarting Kairu does not reset it.
"""

import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from kairu import audit, safemode
from kairu.store import Store

MIN_LENGTH = 6
MAX_FAILURES = 5
LOCK_SECONDS = 60

_hasher = PasswordHasher()  # Argon2id, RFC 9106 low-memory profile: 3 passes, 64 MiB, 4 lanes


class PinError(Exception):
    pass


def is_set(store: Store) -> bool:
    return bool(store.get("pin_hash"))


def set_pin(store: Store, new_pin: str, current_pin: str | None = None) -> None:
    """Set the PIN, or change it: changing needs the current PIN."""
    changing = is_set(store)
    if changing:
        ok, why = check(store, current_pin or "")
        if not ok:
            audit.record(store, "pin", decision="change refused", reason=why)
            raise PinError(f"the current PIN was not accepted: {why}")
    if len(new_pin) < MIN_LENGTH:
        raise PinError(f"the PIN must be at least {MIN_LENGTH} characters")
    with store.transaction() as db:
        store.put("pin_hash", _hasher.hash(new_pin), db)
        audit.record(store, "pin", decision="changed" if changing else "set", db=db)


def check(store: Store, pin: str) -> tuple[bool, str]:
    """(True, "") for the right PIN; otherwise (False, why)."""
    stored = store.get("pin_hash")
    if not stored:
        return False, "no PIN is set; run `kairu pin set` first"
    locked_until = float(store.get("pin_locked_until", "0"))
    if time.time() < locked_until:
        return False, f"too many wrong PINs; try again in {int(locked_until - time.time()) + 1} s"
    try:
        _hasher.verify(stored, pin)
    except (VerificationError, InvalidHashError):
        return False, _count_failure(store)
    with store.transaction() as db:
        store.put("pin_failures", 0, db)
        if _hasher.check_needs_rehash(stored):
            store.put("pin_hash", _hasher.hash(pin), db)
    return True, ""


def _count_failure(store: Store) -> str:
    with store.transaction() as db:  # the count and the lock first, on their own, so nothing can undo them
        failures = int(store.get("pin_failures", "0", db)) + 1
        store.put("pin_failures", failures, db)
        if failures >= MAX_FAILURES:
            store.put("pin_locked_until", repr(time.time() + LOCK_SECONDS), db)
    if failures < MAX_FAILURES:
        return f"wrong PIN ({MAX_FAILURES - failures} left before Safe Mode)"
    safemode.enter(store, f"{failures} wrong PINs in a row")
    return f"wrong PIN; {failures} in a row, so Kairu is in Safe Mode and PINs are refused for {LOCK_SECONDS} s"
