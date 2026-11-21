"""The folder monitor: watches the folders you approved (Downloads to start) for risky new files. Read-only.

Each round it lists the files in each approved folder (names, sizes and times only: it never opens,
runs, moves or deletes a file) and compares them with the last round:

  risky_download      a new program, script, installer or disk image (.exe, .msi, .bat, .iso, ...),
                      with the website it came from when Windows recorded it (the file's
                      Zone.Identifier note, which browsers write on every download)
  disguised_file      a new file whose name hides what it is: "invoice.pdf.exe", a hidden character
                      that reverses the letters, or spaces before the real extension
  many_files_changed  MANY_CHANGED or more existing files changed or vanished within one round, as
                      ransomware does when it scrambles files

The first look at a folder only learns what is already there; it raises no alerts. Files still
downloading (.crdownload, .part, ...) are skipped until the download ends.

Approving a folder is High (protect.add_folder or protect.watch_pc: "yes" and your PIN), and
system and private folders are refused (fence()).
"""

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from kairu.protect.mailrules import DOCUMENTS, PROGRAMS
from kairu.protect.store import Finding, ProtectStore, iso, now_utc

MOST_FILES = 20_000  # per folder per round; beyond this the folder is Degraded
DEPTH = 3  # folders inside an approved folder, at most
MANY_CHANGED = 40
MOST_FOLDERS = 5
IN_PROGRESS = {"crdownload", "part", "partial", "download", "tmp", "opdownload"}
SKIPPED_DIRS = {".git", "node_modules", "__pycache__", "$RECYCLE.BIN", "System Volume Information"}
FOLDERS = "folders"  # in protection.db settings: the approved folders, one per line


@dataclass(frozen=True)
class Entry:
    size: int
    mtime: float


class FolderProblem(ValueError):
    pass


def approved(store: ProtectStore) -> list[str]:
    return [line for line in (store.setting(FOLDERS) or "").splitlines() if line]


def fence(path: str, data_dir) -> str:
    """The folder's full path if Kairu may watch it; FolderProblem with the reason if not."""
    try:
        folder = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise FolderProblem(f"there is no folder {path}") from None
    if not folder.is_dir():
        raise FolderProblem(f"{folder} is a file, not a folder")
    home = Path.home().resolve()
    refused = [Path(data_dir).resolve(), home / ".ssh", home / ".gnupg", home / "AppData"]
    if sys.platform == "win32":
        for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            if os.environ.get(name):
                refused.append(Path(os.environ[name]).resolve())
    else:
        refused += [Path(p) for p in ("/etc", "/proc", "/sys", "/dev", "/usr", "/boot", "/var", "/root")]
    if folder == home or folder.parent == folder:
        raise FolderProblem(f"{folder} is too broad: choose a folder inside it, such as Downloads")
    for no in refused:
        if folder == no or no in folder.parents:
            raise FolderProblem(f"{folder} is a system or private folder, which Kairu never watches")
    return str(folder)


def downloads_folder() -> Path:
    """Your Downloads folder, as Windows knows it (also when OneDrive or you moved it); ~/Downloads elsewhere."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            guid = (ctypes.c_byte * 16).from_buffer_copy(  # FOLDERID_Downloads {374DE290-123F-4565-9164-39C4925E467B}
                bytes.fromhex("90E24D373F126545916439C4925E467B"))
            out = ctypes.c_wchar_p()
            shell32, ole32 = ctypes.WinDLL("shell32"), ctypes.WinDLL("ole32")
            shell32.SHGetKnownFolderPath.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                                     ctypes.POINTER(ctypes.c_wchar_p))
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
                try:
                    return Path(out.value)
                finally:
                    ole32.CoTaskMemFree(out)
        except (OSError, AttributeError):
            pass
    return Path.home() / "Downloads"


def origin(path: str) -> str:
    """The website a downloaded file came from, from Windows' Zone.Identifier note, or ""."""
    if sys.platform != "win32":
        return ""
    try:
        with open(path + ":Zone.Identifier", encoding="utf-8", errors="replace") as note:
            fields = dict(line.strip().split("=", 1) for line in note.read(4096).splitlines() if "=" in line)
    except OSError:
        return ""
    return fields.get("HostUrl") or fields.get("ReferrerUrl") or ""


def disguise(name: str) -> str:
    """Why a file's name hides what it is, or ""."""
    lowered = name.lower()
    if "‮" in name:
        return "its name has a hidden character that reverses its letters"
    parts = lowered.rsplit(".", 2)
    if len(parts) == 3 and parts[2] in PROGRAMS and parts[1] in DOCUMENTS:
        return f"its name ends in .{parts[1]}.{parts[2]}: it looks like a .{parts[1]} file but is a program"
    if len(parts) >= 2 and parts[-1] in PROGRAMS and parts[-2].endswith("   "):
        return "spaces hide its real extension (.exe or similar) at the end of a long name"
    return ""


def scan(folder: str) -> tuple[dict[str, Entry], bool]:
    """(path -> size and time of every file, True if the folder had more than MOST_FILES)."""
    found: dict[str, Entry] = {}
    pending = [(folder, 0)]
    while pending:
        where, depth = pending.pop()
        try:
            with os.scandir(where) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < DEPTH and entry.name not in SKIPPED_DIRS:
                                pending.append((entry.path, depth + 1))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    found[entry.path] = Entry(info.st_size, info.st_mtime)
                    if len(found) >= MOST_FILES:
                        return found, True
        except OSError:
            continue
    return found, False


class FolderMonitor:
    name = "folders"

    def __init__(self, store: ProtectStore, data_dir):
        self.store, self.data_dir = store, data_dir
        with store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS files (folder TEXT NOT NULL, path TEXT PRIMARY KEY, size INTEGER, mtime REAL)")

    def set_up(self) -> bool:
        return bool(approved(self.store))

    def check(self) -> tuple[list[Finding], str]:
        """(findings, a health note for `kairu protect status`)."""
        findings, notes = [], []
        for folder in approved(self.store):
            if not os.path.isdir(folder):
                notes.append(f"{Path(folder).name}: missing")
                continue
            now, too_many = scan(folder)
            findings += self._compare(folder, now)
            notes.append(f"{Path(folder).name}: {len(now)} file{'' if len(now) == 1 else 's'}" + (f" (only the first {MOST_FILES} watched)" if too_many else ""))
        return findings, "; ".join(notes)

    def _compare(self, folder: str, now: dict[str, Entry]) -> list[Finding]:
        with self.store.connect() as db:
            before = {path: Entry(size, mtime) for path, size, mtime in
                      db.execute("SELECT path, size, mtime FROM files WHERE folder = ?", (folder,))}
            first = not before and self.store.setting(f"folder:baseline:{folder}") is None
            findings = []
            if not first:
                new = [path for path in now if path not in before and _complete(path)]
                changed = [path for path, entry in now.items() if path in before and entry != before[path]]
                gone = [path for path in before if path not in now]
                for path in sorted(new, key=lambda p: now[p].mtime):
                    found = self._judge(folder, path, now[path])
                    if found:
                        findings.append(found)
                if len(changed) + len(gone) >= MANY_CHANGED:
                    findings.append(self._many(folder, len(changed), len(gone), changed + gone))
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM files WHERE folder = ?", (folder,))
            db.executemany("INSERT OR REPLACE INTO files (folder, path, size, mtime) VALUES (?, ?, ?, ?)",
                           [(folder, path, e.size, e.mtime) for path, e in now.items() if _complete(path)])
            db.execute("COMMIT")
        if first:
            self.store.set_setting(f"folder:baseline:{folder}", iso(now_utc()))
        return findings

    def _judge(self, folder: str, path: str, entry: Entry) -> Finding | None:
        name = os.path.basename(path)
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        hidden = disguise(name)
        if not hidden and extension not in PROGRAMS:
            return None
        came_from = origin(path)
        lines = [("File", name), ("Folder", os.path.dirname(path)), ("Size", _size(entry.size)),
                 ("From", came_from or "not recorded (Windows notes the website only for browser downloads)"),
                 ("Arrived", _local_time(entry.mtime))]
        key = f"folder:{path}:{int(entry.mtime)}"
        if hidden:
            return Finding(key=key, source="folders", kind="disguised_file", severity="high", classification="Suspected",
                           confidence="high", confidence_reason="real documents do not hide a program extension",
                           title=f"Disguised file: {name}", lines=lines,
                           why=[hidden, "files like this are a common way to trick people into running malware"],
                           not_checked=["what the file contains: Kairu never opens or runs files"],
                           you_can="Do not open it. Delete it yourself if you did not mean to download it; Kairu "
                                   "never deletes files. Kairu changed nothing.")
        return Finding(key=key, source="folders", kind="risky_download", severity="warning", classification="Confirmed fact",
                       title=f"A program was downloaded: {name}", lines=lines,
                       why=[f"it is a .{extension} file, which can run code on your PC"],
                       not_checked=["whether the program is safe: Kairu never opens or runs files"],
                       you_can="If you downloaded it on purpose from a site you trust, nothing to do. If not, do not open "
                               "it, and delete it yourself. Kairu changed nothing.")

    def _many(self, folder: str, changed: int, gone: int, paths: list[str]) -> Finding:
        sample = ", ".join(os.path.basename(p) for p in paths[:5])
        return Finding(key=f"many:{folder}:{iso(now_utc())}", source="folders", kind="many_files_changed", severity="high",
                       classification="Suspected", confidence="medium",
                       confidence_reason="ransomware changes many files quickly, but so do some programs and your own "
                                         "clean-ups",
                       title=f"Many files changed at once in {Path(folder).name}",
                       lines=[("Folder", folder), ("Changed", str(changed)), ("Gone or renamed", str(gone)),
                              ("For example", sample)],
                       why=[f"{changed + gone} existing files changed or vanished within one check (an alert needs "
                            f"{MANY_CHANGED})"],
                       not_checked=["which program changed them", "whether their contents are still readable"],
                       you_can="If you did not just move, unzip or delete files there yourself, press Ctrl+Alt+K, "
                               "disconnect from the internet, and check the files. Kairu changed nothing.")


def _complete(path: str) -> bool:
    return path.rsplit(".", 1)[-1].lower() not in IN_PROGRESS


def _size(size: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024


def _local_time(stamp: float) -> str:
    return time.strftime("%a %d %b %Y, %H:%M", time.localtime(stamp))
