"""A secret kept on this PC only: the Gmail sign-in key (data/protect-gmail.key), and the Kairu Link keys.

On Windows it is sealed with DPAPI for your Windows account, like the audit anchor: another
account, or a copy taken to another PC, cannot read it. On Linux the file is readable by you only
(mode 600). It is written atomically. Nothing in Kairu shows it: showing a key is Critical
(credentials.reveal) and always refused.

`purpose` is mixed into the seal (DPAPI's extra entropy), so a file sealed for one purpose (the
Link's keys, kairu/link/keys.py) cannot be read as another (the Gmail key). The default is the Gmail
key's, as before.

The limit is the same as for the anchor (GUARDIAN.md): a program already running as you could
ask Windows to unseal it.
"""

import json
import os
import sys
import time
from pathlib import Path

ENTROPY = b"Kairu protection key v1"


class SealBroken(Exception):
    pass


def write(path: Path, secret: dict, purpose: bytes = ENTROPY) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _seal(json.dumps(secret).encode(), purpose)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, path)


def read(path: Path, purpose: bytes = ENTROPY) -> dict | None:
    """The secret, or None if there is none. Raises SealBroken if the file cannot be unsealed."""
    try:
        raw = _read_bytes(Path(path))
    except FileNotFoundError:
        return None
    if sys.platform != "win32" and Path(path).stat().st_mode & 0o077:
        raise SealBroken(f"other users can read {Path(path).name}; delete it and connect again")
    try:
        secret = json.loads(_unseal(raw, purpose))
    except (ValueError, OSError) as error:
        raise SealBroken(f"{Path(path).name} could not be read ({error})") from None
    if not isinstance(secret, dict):
        raise SealBroken(f"{Path(path).name} is not a Kairu key")
    return secret


def _read_bytes(path: Path) -> bytes:
    for _ in range(50):
        try:
            return path.read_bytes()
        except PermissionError:  # Windows: it is being put in place right now (write)
            time.sleep(0.02)
    return path.read_bytes()  # still refused after a second: a real refusal, and it is raised


def delete(path: Path) -> bool:
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False


def _seal(data: bytes, purpose: bytes = ENTROPY) -> bytes:
    return _dpapi(data, protect=True, purpose=purpose) if sys.platform == "win32" else data


def _unseal(data: bytes, purpose: bytes = ENTROPY) -> bytes:
    return _dpapi(data, protect=False, purpose=purpose) if sys.platform == "win32" else data


def _dpapi(data: bytes, protect: bool, purpose: bytes = ENTROPY) -> bytes:
    """CryptProtectData / CryptUnprotectData for the current Windows user, through ctypes."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes):
        buffer = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = (ctypes.POINTER(Blob), wintypes.LPCWSTR if protect else ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob))
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p
    (source, keep1), (entropy, keep2), result = blob(data), blob(purpose), Blob()
    if not function(ctypes.byref(source), "Kairu protection key" if protect else None, ctypes.byref(entropy), None, None,
                    0x1, ctypes.byref(result)):
        raise OSError(f"Windows could not {'seal' if protect else 'unseal'} the key (error {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)
