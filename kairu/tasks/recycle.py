"""The Windows Recycle Bin, for files.delete and its undo: standard library and ctypes only, no new package.

Kairu never deletes anything for good. A file or folder goes to the Recycle Bin, and "undo" brings it back from there.

    WindowsBin   this PC: SHFileOperationW with "allow undo" puts it in the Bin. Before that, Kairu checks that this drive has a
                 Bin that would take it (a fixed drive, the Bin not set to delete at once, the item not bigger than the Bin);
                 if not, it refuses, and nothing is deleted. Windows is also told to warn rather than delete for good, as a
                 last guard. Restoring reads the Bin's own records ($I files in $Recycle.Bin\\<your SID>), finds the one for
                 this item, and moves it back, as Explorer's Restore does.
    FakeBin      KAIRU_TEST_PC names a folder: the Bin is a folder in it, so tests (and Linux CI) never touch a real Bin
    NoBin        any other system: "not on this system"

What the Bin answers with is a token, kept in the undo log: for the real Bin, the name of its $I record. The token is checked
again before a restore: it must still name the same original path, or nothing is moved.
"""

import json
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path

from kairu.tasks import pc

TOKEN = re.compile(r"[A-Za-z]:\|\$I[0-9A-Za-z]{6}(?:\.[^\\/:*?\"<>|]{0,40})?|fake:\d{1,12}")


class CannotRecycle(Exception):
    """It would not go to the Recycle Bin, so nothing was deleted. Its text says why."""


class CannotRestore(Exception):
    """Windows can't bring it back. Its text says why, plainly."""


def backend():
    folder = os.environ.get(pc.TEST_PC, "")
    if folder:
        return FakeBin(Path(folder) / "bin")
    return WindowsBin() if sys.platform == "win32" else NoBin()


def size_of(path: Path) -> int:
    """Bytes in a file, or in everything under a folder (links are not followed)."""
    if not path.is_dir() or path.is_symlink():
        return path.lstat().st_size
    total = 0
    for root, folders, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                pass
    return total


class NoBin:
    def recycle(self, path: Path) -> str:
        raise pc.NotOnThisSystem("not on this system: the Recycle Bin is Windows'")

    def restore(self, token: str, original: Path) -> None:
        raise pc.NotOnThisSystem("not on this system: the Recycle Bin is Windows'")


class FakeBin:
    """A pretend Bin for the tests: each item in its own numbered folder, with a note of where it came from."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def recycle(self, path: Path) -> str:
        if (self.folder.parent / "no-bin").exists():  # a test says this drive has no Bin
            raise CannotRecycle("this drive has no Recycle Bin")
        self.folder.mkdir(parents=True, exist_ok=True)
        number = str(time.time_ns() % 10**12)
        place = self.folder / number
        place.mkdir()
        shutil.move(str(path), str(place / path.name))
        (place / "from.json").write_text(json.dumps({"path": str(path)}), encoding="utf-8")
        return f"fake:{number}"

    def restore(self, token: str, original: Path) -> None:
        if not TOKEN.fullmatch(token) or not token.startswith("fake:"):
            raise CannotRestore("the undo log's record of the Recycle Bin isn't one Kairu made")
        place = self.folder / token.split(":", 1)[1]
        if not (place / "from.json").exists():
            raise CannotRestore("it is no longer in the Recycle Bin (it may have been emptied)")
        if json.loads((place / "from.json").read_text(encoding="utf-8"))["path"] != str(original):
            raise CannotRestore("the Recycle Bin's record is for another place")
        item = place / original.name
        if not os.path.lexists(item):
            raise CannotRestore("it is no longer in the Recycle Bin (it may have been emptied)")
        shutil.move(str(item), str(original))
        shutil.rmtree(place, ignore_errors=True)


# --- the real Bin ---------------------------------------------------------------------------------------

FO_DELETE = 3
FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_WANTNUKEWARNING = 0x0004, 0x0010, 0x0040, 0x4000
DRIVE_FIXED = 3
RECORD_SECONDS = 3
BIT_BUCKET = r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume"
POLICIES = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"


class WindowsBin:
    def recycle(self, path: Path) -> str:
        """Into the Bin, or CannotRecycle and nothing changed. The token of its $I record; "" if that record can't be found."""
        path = Path(path)
        self._check_it_would_go_to_the_bin(path)
        started = time.time()
        problem = _shell_delete(str(path))
        if problem:
            raise CannotRecycle(f"Windows refused it (code {problem})")
        if os.path.lexists(path):
            raise CannotRecycle("Windows left it where it was")
        return self.find(path, started - 2) or ""

    def _check_it_would_go_to_the_bin(self, path: Path) -> None:
        import ctypes
        import winreg
        drive = os.path.splitdrive(str(path))[0]
        if not re.fullmatch(r"[A-Za-z]:", drive):
            raise CannotRecycle("it isn't on a drive letter, so it has no Recycle Bin")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetDriveTypeW.argtypes = (ctypes.c_wchar_p,)
        if kernel32.GetDriveTypeW(drive + "\\") != DRIVE_FIXED:
            raise CannotRecycle(f"{drive} isn't a fixed drive, so Windows would delete it for good instead of using the Recycle Bin")
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            if _registry_number(hive, POLICIES, "NoRecycleFiles") == 1:
                raise CannotRecycle("the Recycle Bin is switched off on this PC (a policy)")
        volume = _volume_guid(drive)
        if volume:
            key = f"{BIT_BUCKET}\\{volume}"
            if _registry_number(winreg.HKEY_CURRENT_USER, key, "NukeOnDelete") == 1:
                raise CannotRecycle(f"the Recycle Bin on {drive} is set to delete files at once")
            most = _registry_number(winreg.HKEY_CURRENT_USER, key, "MaxCapacity")  # megabytes
            if most is not None and size_of(path) > most * 2**20:
                raise CannotRecycle(f"it is bigger than the Recycle Bin on {drive} ({most} MB)")

    def records(self, drive: str):
        """(record name, original path, deleted at) for every item of yours in this drive's Bin."""
        from kairu import winpipe
        folder = Path(f"{drive}\\") / "$Recycle.Bin" / winpipe.current_user_sid()
        try:
            names = [entry.name for entry in os.scandir(folder) if entry.name.startswith("$I")]
        except OSError:
            return
        for name in names:
            found = read_record(folder / name)
            if found:
                yield name, found[0], found[1]

    def find(self, original: Path, since: float, seconds: float = RECORD_SECONDS) -> str | None:
        """The token of the newest record for this path; Windows writes it a moment after the delete returns, so look a while."""
        drive = os.path.splitdrive(str(original))[0]
        wanted = os.path.normcase(str(original))
        deadline = time.monotonic() + seconds
        while True:
            matches = [(when, name) for name, path, when in self.records(drive) if os.path.normcase(path) == wanted and when >= since]
            if matches or time.monotonic() > deadline:
                return f"{drive}|{max(matches)[1]}" if matches else None
            time.sleep(0.1)

    def restore(self, token: str, original: Path) -> None:
        if not TOKEN.fullmatch(token) or token.startswith("fake:"):
            raise CannotRestore("the undo log's record of the Recycle Bin isn't one Kairu made")
        drive, name = token.split("|", 1)
        if os.path.normcase(os.path.splitdrive(str(original))[0]) != os.path.normcase(drive):
            raise CannotRestore("the Recycle Bin's record is for another drive")
        from kairu import winpipe
        folder = Path(f"{drive}\\") / "$Recycle.Bin" / winpipe.current_user_sid()
        record, item = folder / name, folder / ("$R" + name[2:])
        found = read_record(record) if record.exists() else None
        if found is None or not os.path.lexists(item):
            raise CannotRestore("it is no longer in the Recycle Bin (it may have been emptied, or restored already)")
        if os.path.normcase(found[0]) != os.path.normcase(str(original)):
            raise CannotRestore("the Recycle Bin's record is for another place")
        try:
            os.rename(item, original)
        except OSError as error:
            raise CannotRestore(f"Windows refused to move it back ({type(error).__name__})") from None
        try:
            record.unlink()
        except OSError:
            pass


def read_record(path: Path) -> tuple[str, float] | None:
    """A $I record: (the original path, when it was deleted, as a Unix time); None if it isn't one."""
    try:
        data = path.read_bytes()[:8192]
    except OSError:
        return None
    if len(data) < 24:
        return None
    version, _size, filetime = struct.unpack_from("<qqq", data, 0)
    if version == 1:
        raw = data[24:24 + 520]
    elif version == 2 and len(data) >= 28:
        length = struct.unpack_from("<i", data, 24)[0]
        raw = data[28:28 + 2 * max(0, min(length, 4000))]
    else:
        return None
    text = raw.decode("utf-16-le", errors="replace").split("\x00", 1)[0]
    return (text, filetime / 1e7 - 11644473600) if text else None


def _shell_delete(path: str) -> int:
    """SHFileOperationW: to the Bin, no questions, no progress window; Windows' warning instead of a delete for good. 0: done."""
    import ctypes
    from ctypes import wintypes

    class FileOp(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p)]

    shell32 = ctypes.WinDLL("shell32")
    shell32.SHFileOperationW.argtypes = (ctypes.POINTER(FileOp),)
    operation = FileOp(None, FO_DELETE, path + "\x00", None, FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_WANTNUKEWARNING,
                       False, None, None)
    result = shell32.SHFileOperationW(ctypes.byref(operation))
    return result or (1 if operation.fAnyOperationsAborted else 0)


def _registry_number(hive, key: str, name: str) -> int | None:
    import winreg
    try:
        with winreg.OpenKey(hive, key) as opened:
            value = winreg.QueryValueEx(opened, name)[0]
    except OSError:
        return None
    return value if isinstance(value, int) else None


def _volume_guid(drive: str) -> str:
    """{GUID} of the volume this drive letter names, as the Bin's settings are kept under; "" if Windows does not say."""
    import ctypes
    buffer = ctypes.create_unicode_buffer(64)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetVolumeNameForVolumeMountPointW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong)
    if not kernel32.GetVolumeNameForVolumeMountPointW(drive + "\\", buffer, 64):
        return ""
    found = re.search(r"\{[0-9A-Fa-f-]{36}\}", buffer.value)
    return found.group(0) if found else ""
