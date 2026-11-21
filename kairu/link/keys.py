"""This PC's own Kairu Link keys: an Ed25519 key that signs, and an X25519 key that messages are encrypted to.

They are made once, the first time you pair a device, and kept in data/link-pc.key, sealed like the
Gmail key (kairu/protect/sealed.py: DPAPI for your Windows account; mode 600 on Linux). Every paired
device has keys of its own; this PC keeps only their public halves (kairu/link/store.py), so one
device's keys never open another's messages. Nothing in Kairu shows a private key: that would be
credentials.reveal, Critical, always refused.

A device's id is made from its signing key ("dev-" or "pc-" and 16 hex digits of its SHA-256), so a
device cannot claim another's id with a key of its own.
"""

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from nacl.public import PrivateKey
from nacl.signing import SigningKey

from kairu.link.kinds import SEAL_PURPOSE as PURPOSE
from kairu.protect import sealed

KEY_NAME = "link-pc.key"


@dataclass(frozen=True)
class Identity:
    id: str
    signing: SigningKey
    private: PrivateKey

    @property
    def sign_public(self) -> bytes:
        return bytes(self.signing.verify_key)

    @property
    def box_public(self) -> bytes:
        return bytes(self.private.public_key)


def device_id(sign_public: bytes, prefix: str = "dev") -> str:
    return f"{prefix}-{hashlib.sha256(sign_public).hexdigest()[:16]}"


def new_identity(prefix: str = "pc") -> Identity:
    signing = SigningKey.generate()
    return Identity(device_id(bytes(signing.verify_key), prefix), signing, PrivateKey.generate())


def load(data_dir) -> Identity | None:
    """This PC's keys, or None before the first pairing. Raises sealed.SealBroken if the file cannot be unsealed."""
    secret = sealed.read(Path(data_dir) / KEY_NAME, PURPOSE)
    if secret is None:
        return None
    try:
        signing = SigningKey(base64.b64decode(secret["sign"]))
        private = PrivateKey(base64.b64decode(secret["box"]))
    except (KeyError, TypeError, ValueError) as error:
        raise sealed.SealBroken(f"{KEY_NAME} is not a Kairu Link key ({type(error).__name__})") from None
    identity = Identity(device_id(bytes(signing.verify_key), "pc"), signing, private)
    if secret.get("id") != identity.id:
        raise sealed.SealBroken(f"{KEY_NAME} does not match its own id")
    return identity


def load_or_create(data_dir) -> Identity:
    identity = load(data_dir)
    if identity is None:
        identity = new_identity("pc")
        sealed.write(Path(data_dir) / KEY_NAME, {
            "id": identity.id,
            "sign": base64.b64encode(bytes(identity.signing)).decode(),
            "box": base64.b64encode(bytes(identity.private)).decode(),
        }, PURPOSE)
    return identity
