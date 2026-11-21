"""Your free AI providers' keys, on this PC only: data/brain-keys/NAME.key.

Each is sealed like the Gmail key (kairu/protect/sealed.py): DPAPI for your Windows account (another account,
or a copy on another PC, cannot read it), readable by you only on Linux; with its own purpose mixed into the
seal, so a provider key cannot be read as any other Kairu key. Nothing in Kairu shows a key: showing one is
Critical (credentials.reveal). A key goes only to its own provider, in the Authorization header.

How a key gets here: `kairu provider add NAME` asks Guardian for provider.add (High: "yes" and your PIN),
then reads the key you paste (it is not shown) and leaves it, sealed, as NAME.pending; Guardian's provider.add
action moves it into NAME.key and deletes the pending file. The key never passes through Guardian's channel,
an action's details or the audit log.
"""

import os
import sys
from pathlib import Path

from kairu.protect import sealed

PURPOSE = b"Kairu brain provider key v1"
FOLDER = "brain-keys"


def _folder(data_dir) -> Path:
    folder = Path(data_dir) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(folder, 0o700)
    return folder


def key_path(data_dir, provider: str) -> Path:
    return Path(data_dir) / FOLDER / f"{provider}.key"


def pending_path(data_dir, provider: str) -> Path:
    return Path(data_dir) / FOLDER / f"{provider}.pending"


def has(data_dir, provider: str) -> bool:
    return key_path(data_dir, provider).exists()


def load(data_dir, provider: str) -> tuple[str, str] | None:
    """(key, account) or None if there is no key. Raises sealed.SealBroken if it cannot be unsealed."""
    secret = sealed.read(key_path(data_dir, provider), PURPOSE)
    if secret is None:
        return None
    key, account = secret.get("key"), secret.get("account", "")
    if not isinstance(key, str) or not isinstance(account, str):
        raise sealed.SealBroken(f"{provider}.key is not a provider key")
    return key, account


def leave_pending(data_dir, provider: str, key: str, account: str = "") -> None:
    """`kairu provider add`, after your approval: the key, sealed, for the provider.add action to take."""
    _folder(data_dir)
    sealed.write(pending_path(data_dir, provider), {"key": key, "account": account}, PURPOSE)


def take_pending(data_dir, provider: str) -> dict | None:
    path = pending_path(data_dir, provider)
    try:
        return sealed.read(path, PURPOSE)
    finally:
        sealed.delete(path)


def save(data_dir, provider: str, key: str, account: str = "") -> None:
    _folder(data_dir)
    sealed.write(key_path(data_dir, provider), {"key": key, "account": account}, PURPOSE)


def remove(data_dir, provider: str) -> bool:
    gone = sealed.delete(key_path(data_dir, provider))
    sealed.delete(pending_path(data_dir, provider))
    return gone
