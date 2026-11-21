"""Fingerprint approvals from the phone (Phase D2, PHONE.md, ADR-023 and ADR-035).

A paired phone may approve its own High requests with its fingerprint, once you have turned that on for it at this PC:

  1. The phone makes an Ed25519 key inside Android's Keystore that signs only after a strong biometric (its fingerprint)
     for each signature, and asks for `device.approver` with the key's public half. That is High: it waits for your
     "yes" and PIN typed here (`kairu link approve N`), and is never approved by a fingerprint. Then enroll() keeps the
     key in data/link.db for that phone only.
  2. When one of that phone's requests is High, the PC tells the phone what it is (the action, its details, the tier,
     and a fingerprint of exactly that action and details). Your fingerprint on the phone signs statement() for it.
  3. Guardian has the signature checked by this module's own short program (`python -m kairu.link.approver`), so the
     Guardian program itself never loads PyNaCl. Only a signature by that phone's key, over that request's number,
     that exact action and details, and its expiry, is an approval. It approves that request once.

A phone can approve only its own requests; what you ask at the PC still needs your PIN at the PC. Critical never asks.
"""

import base64
import binascii
import json
import re
import sys

from kairu.link.kinds import DEVICE_ID

KEY_BYTES = 32
FINGERPRINT = re.compile(r"[0-9a-f]{64}")


class NotAKey(ValueError):
    pass


def statement(device: str, number: int, fingerprint: str, expires: int) -> bytes:
    """What the phone's fingerprint signs for one request: nothing else is an approval."""
    if not DEVICE_ID.fullmatch(device) or type(number) is not int or not FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("not an approval statement")
    return f"kairu-approve-v1|{device}|{number}|{fingerprint}|{int(expires)}".encode("ascii")


def key_bytes(key: str) -> bytes:
    """The raw 32-byte Ed25519 public key, from base64 (raw, or Android's 44-byte X.509 form)."""
    try:
        raw = base64.b64decode(key, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise NotAKey("not base64") from None
    if len(raw) == 44 and raw[:12] == bytes.fromhex("302a300506032b6570032100"):
        raw = raw[12:]
    if len(raw) != KEY_BYTES:
        raise NotAKey("not an Ed25519 public key")
    return raw


def verify(key: str, signed: bytes, signature: str) -> bool:
    """True if `signature` (base64) is the key's Ed25519 signature of `signed`. Loads PyNaCl: never call it in Guardian."""
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
    try:
        VerifyKey(key_bytes(key)).verify(signed, base64.b64decode(signature, validate=True))
        return True
    except (BadSignatureError, NotAKey, binascii.Error, ValueError, TypeError):
        return False


def enroll(data_dir: str, device: str, key: str) -> None:
    """device.approver: keep the phone's fingerprint key, after your "yes" and PIN at this PC."""
    from kairu.link.store import LinkStore
    try:
        raw = key_bytes(key)
    except NotAKey as error:
        print(f"device.approver: {error}", file=sys.stderr)
        raise SystemExit(1)
    if not LinkStore(data_dir).set_approver(device, base64.b64encode(raw).decode("ascii")):
        print("device.approver: that device is not paired", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    """`python -m kairu.link.approver`: reads {"key", "statement", "signature"} (JSON) on stdin; exit 0 if it verifies."""
    try:
        data = json.loads(sys.stdin.read(8192))
        ok = verify(data["key"], base64.b64decode(data["statement"], validate=True), data["signature"])
    except (ValueError, KeyError, TypeError, binascii.Error):
        ok = False
    print("valid" if ok else "invalid")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
