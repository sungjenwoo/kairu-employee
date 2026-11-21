"""device.pair: pair a new device (your phone) with this PC. It is High: "yes" and your PIN at the PC first.

  1. This PC's Link keys are made if there are none yet (kairu/link/keys.py).
  2. An offer is made: a one-time pairing topic (128 random bits) and a 6-digit code, both valid 10
     minutes. The QR code that `kairu device pair` shows holds the PC's id, its two public keys, the
     topic, the relay and when the offer ends. The 6-digit code is shown beside it, never inside it.
  3. The phone makes keys of its own and sends, on the pairing topic, a request encrypted to this PC
     and signed with its new key: its public keys, its name, and a proof that it knows the code
     (HMAC-SHA256 keyed with the code, over everything else in the request). A wrong code counts;
     after 5 the offer is cancelled.
  4. With the right code the device is paired: its public keys and a new random topic of its own go
     into data/link.db. The new topic goes back to the phone encrypted, so someone who only saw the
     QR code does not learn it.
It ends when the device is paired (exit code 0), or when the 10 minutes pass or the offer is
cancelled (exit code 1). Until then the offer waits for `kairu device pair` in data/link-pair.offer,
sealed like the keys; it is deleted when pairing ends, however it ends.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import sys
import threading
import time
from pathlib import Path

from nacl.exceptions import BadSignatureError, CryptoError
from nacl.public import Box, PublicKey
from nacl.signing import VerifyKey

from kairu.link import keys
from kairu.link.kinds import FUTURE_SECONDS, MAX_AGE_SECONDS, MAX_ENVELOPE_BYTES, MAX_NAME, PAIR_SECONDS, PAIR_TRIES
from kairu.link.message import NONCE, seal
from kairu.link.relay import Backoff, RateLimited, Relay, RelayError
from kairu.link.send import deliver
from kairu.link.store import OFFER_NAME, Device, LinkStore, TooManyDevices, forget_offer
from kairu.protect import sealed

PREFIX = "kairu-pair:1:"
REQUEST_KEYS = {"v", "pair", "to", "key", "box"}
PAYLOAD_KEYS = {"type", "from", "to", "name", "sign", "box", "ts", "nonce", "proof"}


class NotAPairing(Exception):
    """A message on the pairing topic that is not a usable pairing request. wrong_code: it was one, with a wrong code."""

    def __init__(self, why: str, wrong_code: bool = False):
        super().__init__(why)
        self.wrong_code = wrong_code


def offer_text(me: keys.Identity, topic: str, relay: str, expires: float) -> str:
    """What the QR code holds."""
    data = {"pc": me.id, "sign": _b64(me.sign_public), "box": _b64(me.box_public), "topic": topic, "relay": relay,
            "expires": int(expires)}
    return PREFIX + base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def proof(code: str, pc: str, device: str, sign: str, box: str, nonce: str) -> str:
    return hmac.new(code.encode(), f"kairu-pair-v1|{pc}|{device}|{sign}|{box}|{nonce}".encode(), hashlib.sha256).hexdigest()


def clean_name(name) -> str:
    """A device's name as it may be shown: printable characters only, at most 40."""
    text = " ".join("".join(ch for ch in str(name) if ch.isprintable()).split())[:MAX_NAME]
    return text or "phone"


def open_request(text: str, me: keys.Identity, code: str, now: float | None = None) -> Device:
    """The device asking to pair, if its request is sound and its code is right. Raises NotAPairing otherwise."""
    now = time.time() if now is None else now
    try:
        outer = json.loads(text) if len(text) <= MAX_ENVELOPE_BYTES else None
    except ValueError:
        outer = None
    if not isinstance(outer, dict) or set(outer) != REQUEST_KEYS or outer["v"] != 1 or outer["to"] != me.id \
            or not all(isinstance(outer[key], str) for key in ("pair", "key", "box")):
        raise NotAPairing("not a pairing request for this PC")
    try:
        box_public = base64.b64decode(outer["key"], validate=True)
        signed = Box(me.private, PublicKey(box_public)).decrypt(base64.b64decode(outer["box"], validate=True))
        payload_bytes, signature = signed[64:], signed[:64]
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS or not isinstance(payload["sign"], str):
            raise ValueError
        sign_public = base64.b64decode(payload["sign"], validate=True)
        VerifyKey(sign_public).verify(payload_bytes, signature)
    except (binascii.Error, CryptoError, BadSignatureError, UnicodeDecodeError, ValueError, TypeError):
        raise NotAPairing("a pairing request that does not open or is not signed by its own key") from None
    device = keys.device_id(sign_public)
    if (payload["type"] != "pair" or payload["from"] != device or outer["pair"] != device or payload["to"] != me.id
            or payload["box"] != outer["key"] or type(payload["ts"]) is not int or not isinstance(payload["nonce"], str)
            or not NONCE.fullmatch(payload["nonce"]) or not isinstance(payload["proof"], str)):
        raise NotAPairing("a pairing request whose parts do not agree")
    ts = payload["ts"] / 1000
    if now - ts > MAX_AGE_SECONDS or ts - now > FUTURE_SECONDS:
        raise NotAPairing("an old pairing request")
    wanted = proof(code, me.id, device, payload["sign"], payload["box"], payload["nonce"])
    if not hmac.compare_digest(wanted, payload["proof"]):
        raise NotAPairing("a pairing request with a wrong code", wrong_code=True)
    return Device(device, clean_name(payload["name"]), sign_public, box_public, secrets.token_hex(16), now)


def pair(data_dir: str, relay: str) -> None:
    """The device.pair action (see above)."""
    forget_offer(data_dir)
    me = keys.load_or_create(data_dir)
    code, topic, expires = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(16), time.time() + PAIR_SECONDS
    sealed.write(Path(data_dir) / OFFER_NAME, {"text": offer_text(me, topic, relay, expires), "code": code,
                                                "expires": expires}, keys.PURPOSE)
    try:
        device = listen(data_dir, Relay(relay), me, topic, code, expires)
    finally:
        forget_offer(data_dir)
    print(f"device.pair: paired {device.id}", file=sys.stderr, flush=True)


def listen(data_dir: str, relay: Relay, me: keys.Identity, topic: str, code: str, expires: float) -> Device:
    """Wait on the pairing topic for the right request until `expires`. The paired device; exit code 1 otherwise."""
    wrong, backoff, since = 0, Backoff(), int(time.time()) - 5
    while time.time() < expires:
        try:
            subscription = relay.subscribe([topic], since)
        except RelayError as error:
            wait = backoff.next(getattr(error, "retry_after", None), rate_limited=isinstance(error, RateLimited))
            _log(f"{error}; trying again in {wait:.0f} s")
            time.sleep(min(wait, max(0.0, expires - time.time())))
            continue
        timer = threading.Timer(max(0.0, expires - time.time()), subscription.close)
        timer.daemon = True
        timer.start()
        try:
            for event in subscription:
                if event.get("event") != "message" or not isinstance(event.get("message"), str):
                    continue
                since = max(since, int(event.get("time") or 0))
                try:
                    device = open_request(event["message"], me, code)
                except NotAPairing as refusal:
                    _log(str(refusal))
                    if refusal.wrong_code:
                        wrong += 1
                        if wrong >= PAIR_TRIES:
                            _fail(f"pairing cancelled: {wrong} wrong codes")
                    continue
                try:
                    LinkStore(data_dir).add_device(device)
                except TooManyDevices as error:
                    _fail(str(error))
                body = json.dumps({"paired": {"topic": device.topic, "pc": me.id}}, separators=(",", ":"))
                deliver(relay, topic, seal(me, device.id, device.box, "report", body))
                return device
        except RelayError as error:
            _log(f"{error}; reading again")
            time.sleep(min(backoff.next(), max(0.0, expires - time.time())))
        finally:
            timer.cancel()
            subscription.close()
    _fail("the 10 minutes passed before a device paired")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _log(text: str) -> None:
    print(f"device.pair: {text}", file=sys.stderr, flush=True)


def _fail(why: str):
    _log(why)
    raise SystemExit(1)
