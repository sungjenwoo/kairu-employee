"""The audit anchor: a small file kept apart from guardian.db, holding the audit log's row count and newest hash.

The hash chain in guardian.db catches a changed, inserted or removed row, but not the newest rows
being deleted, because what is left is still a valid chain. The anchor remembers how long the
chain was, so `kairu audit verify` can tell.

It is rewritten in the same database transaction as every new audit row, and atomically: a new
file is written and flushed to disk, then renamed over the old one, so it is never half-written.
On Windows it is sealed with DPAPI for your Windows account (CryptProtectData), so it cannot be
read or changed by another account, or edited without Windows noticing. On Linux it is readable
and writable only by you (mode 600) and carries a checksum.

Before it is rewritten, the old anchor is compared with the database. If they disagree (rows were
deleted, or the anchor went missing or was changed), that is kept as an alert inside the new
anchor, so the evidence is not lost when Kairu carries on writing. Alerts stay until you accept the
database as it is with `kairu audit reanchor` ("yes" and your PIN).
"""

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

FORMAT = 1
ENTROPY = b"Kairu Guardian audit anchor v1"  # DPAPI: only blobs made with this are accepted
MAX_ALERTS = 50

# what went wrong; audit.verify reports these
NEWEST_DELETED = "newest_rows_deleted"
DB_MISSING = "database_missing"
ANCHOR_MISSING = "anchor_missing"
ANCHOR_TAMPERED = "anchor_tampered"
ANCHOR_MISMATCH = "anchor_mismatch"


class AnchorTampered(Exception):
    pass


@dataclass(frozen=True)
class Alert:
    kind: str
    row: int  # the row being added when it was noticed
    text: str


@dataclass(frozen=True)
class Anchor:
    rows: int
    hash: str
    alerts: tuple[Alert, ...] = ()


def read(path: Path) -> Anchor | None:
    """The anchor, or None if there is no anchor file. Raises AnchorTampered if it is not a valid anchor."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(_unseal(raw))
        check = payload.pop("check")
        alerts = tuple(Alert(str(a["kind"]), int(a["row"]), str(a["text"])) for a in payload["alerts"])
        anchor = Anchor(int(payload["rows"]), str(payload["hash"]), alerts)
        if payload["format"] != FORMAT:
            raise ValueError
    except AnchorTampered:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise AnchorTampered("it is not a valid anchor file") from None
    if check != _checksum(payload):
        raise AnchorTampered("its contents do not match its checksum: it was edited")
    return anchor


def write(path: Path, anchor: Anchor) -> None:
    """Replace the anchor atomically: write a new file, flush it to disk, then rename it over the old one."""
    path = Path(path)
    payload = {"format": FORMAT, "rows": anchor.rows, "hash": anchor.hash,
               "alerts": [{"kind": a.kind, "row": a.row, "text": a.text} for a in anchor.alerts]}
    payload["check"] = _checksum(payload)
    data = _seal(json.dumps(payload, sort_keys=True).encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        for attempt in range(50):
            try:
                os.replace(temp, path)
                break
            except PermissionError:  # Windows: someone is reading the anchor at this moment (kairu audit verify)
                if attempt == 49:
                    raise
                time.sleep(0.01)
    except BaseException:
        temp.unlink(missing_ok=True)  # the old anchor is untouched
        raise
    if sys.platform != "win32":  # make the rename itself survive a power cut
        folder = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)


def advance(path: Path, before: tuple[int, str], after: tuple[int, str], fresh: bool = False) -> None:
    """Move the anchor from the newest row `before` a transaction to the newest row `after` it.

    Anything wrong with the old anchor is kept as an alert in the new one, unless `fresh`.
    """
    alerts: list[Alert] = []
    row = before[0] + 1
    if not fresh:
        try:
            old = read(path)
        except AnchorTampered as error:
            alerts.append(Alert(ANCHOR_TAMPERED, row, f"the anchor was tampered with ({error}) when row {row} was added"))
        else:
            if old is None and before[0] > 0:
                alerts.append(Alert(ANCHOR_MISSING, row, f"the anchor was missing when row {row} was added, though the "
                                                         f"database already had {before[0]} rows; it was made again"))
            elif old is not None:
                alerts.extend(old.alerts)
                if old.rows > before[0]:
                    alerts.append(Alert(NEWEST_DELETED, row, f"the newest rows were deleted: the anchor said {old.rows} rows, "
                                                             f"but the database had {before[0]} when row {row} was added"))
                elif (old.rows, old.hash) != before:
                    alerts.append(Alert(ANCHOR_MISMATCH, row, f"the anchor said {old.rows} rows ending in {old.hash[:12]}…, "
                                                              f"but the database had {before[0]} ending in {before[1][:12]}… "
                                                              f"when row {row} was added"))
    write(path, Anchor(after[0], after[1], tuple(alerts[:MAX_ALERTS])))


def protection_problem(path: Path) -> str:
    """On Linux: why the anchor file is not private to you, or "" if it is. (DPAPI covers this on Windows.)"""
    if sys.platform == "win32":
        return ""
    try:
        info = Path(path).stat()
    except FileNotFoundError:
        return ""
    if info.st_uid != os.getuid():
        return "the anchor file belongs to another user"
    if info.st_mode & 0o077:
        return f"other users can read or change the anchor file (permissions {info.st_mode & 0o777:o}, should be 600)"
    return ""


def _checksum(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --- sealing: DPAPI on Windows, plain bytes elsewhere ----------------------------------------

def _seal(data: bytes) -> bytes:
    return _dpapi(data, protect=True) if sys.platform == "win32" else data


def _unseal(data: bytes) -> bytes:
    return _dpapi(data, protect=False) if sys.platform == "win32" else data


def _dpapi(data: bytes, protect: bool) -> bytes:
    """CryptProtectData / CryptUnprotectData for the current Windows user, through ctypes."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes):
        buffer = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer  # keep the buffer alive

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    # the second argument is the description: a string going in, and an optional string pointer coming out
    function.argtypes = (ctypes.POINTER(Blob), wintypes.LPCWSTR if protect else ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob))
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    (source, keep1), (entropy, keep2), result = blob(data), blob(ENTROPY), Blob()
    description = "Kairu audit anchor" if protect else None
    ui_forbidden = 0x1  # never show a prompt
    if not function(ctypes.byref(source), description, ctypes.byref(entropy), None, None, ui_forbidden, ctypes.byref(result)):
        error = ctypes.get_last_error()
        if protect:
            raise OSError(f"CryptProtectData failed (Windows error {error})")
        raise AnchorTampered(f"Windows could not unseal it (error {error}): it was changed, or made by another Windows account")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)
