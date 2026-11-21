"""Kairu Link messages: signed with the sender's Ed25519 key, encrypted to the receiver's X25519 key.

What travels through the Gate (the relay) is an envelope, JSON text of at most 4,000 bytes:

    {"v": 1, "from": SENDER_ID, "to": RECEIVER_ID, "box": BASE64}

"box" is crypto_box (X25519 + XSalsa20-Poly1305, random nonce) from the sender's key to the
receiver's, holding a 64-byte Ed25519 signature followed by the payload it signs, JSON (UTF-8):

    {"from", "to", "type", "tier", "ts" (milliseconds), "nonce" (32 hex digits, random), "body" (text)}

The relay sees who talks to whom (two ids) and how long the message is; nothing else.

open_envelope() refuses, in this order, with a Rejected naming one of kinds.PROBLEMS:
  malformed        not this shape, too long, or not JSON
  wrong_receiver   addressed to another device
  unknown_sender   not a paired device: nothing is decrypted
  tampered         the encryption does not open: changed on the way, or not for this PC
  bad_signature    it opens, but the sender's signing key did not sign it
  from_future / expired   the timestamp rules in kinds.py
  replayed         its nonce came before (remember() says so)
Only then is it a Message, and even then only a request: Guardian decides what, if anything, happens.

The tier in a message is what the sender believes; it decides nothing. Guardian's policy does.
"""

import base64
import binascii
import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from nacl.exceptions import BadSignatureError, CryptoError
from nacl.public import Box, PublicKey
from nacl.signing import VerifyKey

from kairu.link.keys import Identity
from kairu.link.kinds import (DEVICE_ID, FUTURE_SECONDS, LIVE, MAX_AGE_SECONDS, MAX_BODY_BYTES, MAX_ENVELOPE_BYTES,
                              QUEUE_SECONDS, TIERS, TYPES)
from kairu.link.store import Device

ENVELOPE_KEYS = {"v", "from", "to", "box"}
PAYLOAD_KEYS = {"from", "to", "type", "tier", "ts", "nonce", "body"}
NONCE = re.compile(r"[0-9a-f]{32}")


class Rejected(Exception):
    def __init__(self, problem: str, sender: str, digest: str):
        super().__init__(problem)
        self.problem, self.sender, self.digest = problem, sender, digest


@dataclass(frozen=True)
class Message:
    sender: str
    receiver: str
    type: str
    tier: str
    ts: float  # seconds
    nonce: str
    body: str
    digest: str  # SHA-256 of the envelope as it came: what the audit log keeps instead of the words


def digest(envelope: str) -> str:
    return hashlib.sha256(envelope.encode("utf-8", "replace")).hexdigest()


def sender_of(envelope: str) -> str | None:
    """Who an envelope says it is from, unchecked: only to skip this device's own messages on a shared topic."""
    try:
        outer = json.loads(envelope) if len(envelope) <= MAX_ENVELOPE_BYTES else None
    except ValueError:
        return None
    return outer.get("from") if isinstance(outer, dict) and isinstance(outer.get("from"), str) else None


def seal(me: Identity, receiver_id: str, receiver_box: bytes, kind: str, body: str, tier: str = "Low",
         now: float | None = None, nonce: str | None = None) -> str:
    """One envelope from `me` to the receiver. Raises ValueError if it cannot be a Kairu Link message."""
    if kind not in TYPES or tier not in TIERS or not DEVICE_ID.fullmatch(receiver_id):
        raise ValueError("not a Kairu Link message type, tier or device")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError(f"the text is longer than {MAX_BODY_BYTES} bytes")
    payload = json.dumps({"from": me.id, "to": receiver_id, "type": kind, "tier": tier,
                          "ts": int(round((time.time() if now is None else now) * 1000)),
                          "nonce": nonce or secrets.token_hex(16), "body": body},
                         ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signed = me.signing.sign(payload).signature + payload
    boxed = Box(me.private, PublicKey(receiver_box)).encrypt(signed)
    envelope = json.dumps({"v": 1, "from": me.id, "to": receiver_id, "box": base64.b64encode(boxed).decode("ascii")},
                          separators=(",", ":"))
    if len(envelope) > MAX_ENVELOPE_BYTES:
        raise ValueError(f"the message is longer than {MAX_ENVELOPE_BYTES} bytes")
    return envelope


def open_envelope(envelope: str, me: Identity, lookup: Callable[[str], Device | None],
                  remember: Callable[[str, str, float, float], bool], relay_time: float | None = None,
                  now: float | None = None) -> Message:
    """The message, if it passes every check. Raises Rejected otherwise.

    lookup(device id) gives a paired device or None. remember(device, nonce, ts, now) is True the
    first time a nonce comes, False for a replay. relay_time is when the Gate received it (None if
    it did not come through the Gate).
    """
    found = digest(envelope)
    sender = ""

    def refuse(problem: str):
        raise Rejected(problem, sender, found)

    if len(envelope.encode("utf-8", "replace")) > MAX_ENVELOPE_BYTES:
        refuse("malformed")
    try:
        outer = json.loads(envelope)
    except ValueError:
        refuse("malformed")
    if (not isinstance(outer, dict) or set(outer) != ENVELOPE_KEYS or outer["v"] != 1
            or not all(isinstance(outer[key], str) for key in ("from", "to", "box"))
            or not DEVICE_ID.fullmatch(outer["from"])):
        refuse("malformed")
    sender = outer["from"]
    if outer["to"] != me.id:
        refuse("wrong_receiver")
    device = lookup(sender)
    if device is None:
        refuse("unknown_sender")
    try:
        boxed = base64.b64decode(outer["box"], validate=True)
    except (binascii.Error, ValueError):
        refuse("malformed")
    try:
        signed = Box(me.private, PublicKey(device.box)).decrypt(boxed)
    except (CryptoError, ValueError, TypeError):
        refuse("tampered")
    if len(signed) <= 64:
        refuse("tampered")
    try:
        VerifyKey(device.sign).verify(signed[64:], signed[:64])
    except (BadSignatureError, ValueError):
        refuse("bad_signature")
    try:
        payload = json.loads(signed[64:].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        refuse("malformed")
    if (not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS or payload["type"] not in TYPES
            or payload["tier"] not in TIERS or type(payload["ts"]) is not int or not isinstance(payload["nonce"], str)
            or not NONCE.fullmatch(payload["nonce"]) or not isinstance(payload["body"], str)
            or len(payload["body"].encode("utf-8")) > MAX_BODY_BYTES):
        refuse("malformed")
    if payload["from"] != sender or payload["to"] != me.id:
        refuse("wrong_receiver")
    now = time.time() if now is None else now
    ts = payload["ts"] / 1000
    arrived = now if relay_time is None else relay_time
    if ts - now > FUTURE_SECONDS or ts - arrived > FUTURE_SECONDS:
        refuse("from_future")
    if arrived - ts > MAX_AGE_SECONDS or now - ts > QUEUE_SECONDS:
        refuse("expired")
    if payload["type"] in LIVE and now - ts > MAX_AGE_SECONDS:
        refuse("expired")
    if not remember(sender, payload["nonce"], ts, now):
        refuse("replayed")
    return Message(sender, me.id, payload["type"], payload["tier"], ts, payload["nonce"], payload["body"], found)
