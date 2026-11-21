"""The small provider actions Guardian runs for you.

    provider.add     High ("yes" and your PIN): take the key `kairu provider add` left sealed (NAME.pending) and
                     keep it as NAME.key (kairu/brain/keys.py); the provider is ready again at once
    provider.remove  delete a provider's key from this PC
    provider.pause   leave a provider alone for some minutes, as if it were at its free limit (0 minutes: use it
                     again now); this is how the gate test simulates a free limit

They change only Kairu's own files. Each ends with exit code 1, and a reason on Guardian's log, when there is
nothing to do. The key itself never appears in a detail, a log or the audit log.
"""

import sys
import time

from kairu.brain import keys
from kairu.brain.providers import PROVIDERS, ACCOUNT, valid_key
from kairu.brain.store import BrainStore
from kairu.brain.usage import clock
from kairu.protect.sealed import SealBroken

MOST_MINUTES = 24 * 60


def add(data_dir: str, provider: str) -> None:
    known = _provider(provider)
    try:
        given = keys.take_pending(data_dir, provider)
    except SealBroken:
        _fail("the key that was left could not be read; run `kairu provider add` again")
    if not given:
        _fail(f"no key was given for {provider}; run `kairu provider add {provider}`")
    key, account = given.get("key", ""), given.get("account", "")
    if not isinstance(key, str) or valid_key(known, key):
        _fail(f"that is not a key: {valid_key(known, key) if isinstance(key, str) else 'no key'}")
    if known.needs_account and not ACCOUNT.fullmatch(account or ""):
        _fail(f"{known.label} needs your account ID (32 letters and digits) with the key")
    keys.save(data_dir, provider, key, account if known.needs_account else "")
    store = BrainStore(data_dir)
    store.free_again(provider)
    store.event(provider, "key", f"{known.label}: key added")


def remove(data_dir: str, provider: str) -> None:
    known = _provider(provider)
    if not keys.remove(data_dir, provider):
        _fail(f"there is no {known.label} key on this PC")
    BrainStore(data_dir).event(provider, "key", f"{known.label}: key removed")


def pause(data_dir: str, provider: str, minutes: float) -> None:
    known = _provider(provider)
    if not 0 <= minutes <= MOST_MINUTES:
        _fail(f"minutes must be from 0 to {MOST_MINUTES}")
    store = BrainStore(data_dir)
    if minutes == 0:
        store.free_again(provider)
        store.event(provider, "resume", f"{known.label}: used again (you resumed it)")
        return
    until = time.time() + minutes * 60
    store.leave_alone(provider, until, "paused by you")
    store.event(provider, "pause", f"{known.label} paused by you until {clock(until)} (as if at its free limit)")


def _provider(name: str):
    if name not in PROVIDERS:
        _fail(f"provider must be one of {', '.join(PROVIDERS)}")
    return PROVIDERS[name]


def _fail(why: str):
    print(f"kairu: {why}", file=sys.stderr)
    raise SystemExit(1)
