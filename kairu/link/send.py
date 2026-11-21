"""link.send: one signed, encrypted Kairu Link message from this PC to one paired device, through the Gate.

Guardian runs it like any action: for each reply to your phone (kairu/guardian_program.py), and for
`kairu link send`. Its details are the device, the message type and the text; the relay's address
comes from Guardian's own config.yaml, never from a request. When the relay says "too many requests"
it waits and tries again, for at most a minute. Exit code 1, with the reason on Guardian's log, when
it could not send; the text itself is never written anywhere.
"""

import sys
import time

from kairu.link import keys
from kairu.link.kinds import TYPES
from kairu.link.message import seal
from kairu.link.relay import Backoff, RateLimited, Relay, RelayError
from kairu.link.store import LinkStore

GIVE_UP_SECONDS = 60


def main(data_dir: str, relay: str, device: str, type: str, text: str) -> None:
    target = LinkStore(data_dir).device(device)
    if target is None:
        _fail(f"{device[:40]} is not a paired device")
    if type not in TYPES:
        _fail(f"a message type is one of {', '.join(TYPES)}")
    me = keys.load(data_dir)
    if me is None:
        _fail("this PC has no Link keys yet: pair a device first")
    try:
        envelope = seal(me, target.id, target.box, type, text)
    except ValueError as error:
        _fail(str(error))
    deliver(Relay(relay), target.topic, envelope)


def deliver(relay: Relay, topic: str, envelope: str, give_up: float = GIVE_UP_SECONDS) -> dict:
    backoff, deadline = Backoff(first=1, most=20), time.monotonic() + give_up
    while True:
        try:
            return relay.publish(topic, envelope)
        except RateLimited as limited:
            wait, why = backoff.next(limited.retry_after, rate_limited=True), str(limited)
        except RelayError as error:
            wait, why = backoff.next(), str(error)
        if time.monotonic() + wait > deadline:
            _fail(f"not sent: {why}")
        print(f"link.send: {why}; trying again in {wait:.0f} s", file=sys.stderr, flush=True)
        time.sleep(wait)


def _fail(why: str):
    print(f"link.send: {why}", file=sys.stderr, flush=True)
    raise SystemExit(1)
