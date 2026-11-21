"""`kairu doctor` (PC7): an owner command, never a Kairu action. Read only: it changes nothing, sends nothing.

It prints Guardian's state, what is running, the PC's free memory, and how much memory each of Kairu's own programs uses
(Python programs started from Kairu's folder, and Piper or Kokoro), with a warning when Kairu takes more than BUDGET_MB or
the PC has less than LOW_FREE_PERCENT free. Standard library and ctypes only.
"""

import ctypes
import os
import sys
from pathlib import Path

KAIRU_FOLDER = Path(__file__).resolve().parents[1]
BUDGET_MB = 1200  # everything of Kairu together: Guardian, the bar, the workspace, the voice (600 MB with Kokoro), an action
LOW_FREE_PERCENT = 15
MB = 1024 * 1024


def kairu_processes() -> list[tuple[int, str, float]]:
    """(pid, name, MB in use) for each of Kairu's programs."""
    return _windows() if sys.platform == "win32" else _linux()


def _ours(path: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(KAIRU_FOLDER)
    except (OSError, ValueError):
        return False


def _linux() -> list[tuple[int, str, float]]:
    found = []
    for entry in Path("/proc").iterdir() if Path("/proc").is_dir() else ():
        if not entry.name.isdigit():
            continue
        try:
            words = (entry / "cmdline").read_bytes().split(b"\0")
            text = " ".join(word.decode(errors="replace") for word in words if word)
            if "kairu" not in text.lower() or int(entry.name) == os.getpid():
                continue
            rss = next((line.split()[1] for line in (entry / "status").read_text().splitlines() if line.startswith("VmRSS:")), "0")
        except (OSError, StopIteration, IndexError):
            continue
        name = next((w for w in text.split() if "kairu" in w.lower()), text.split()[0] if text else "?")
        found.append((int(entry.name), Path(name).name[:40], int(rss) / 1024))
    return found


def _windows() -> list[tuple[int, str, float]]:
    """Kairu's programs on Windows: those started from Kairu's folder, and every program they started (a venv's pythonw.exe
    is a small launcher that starts the real Python from where Python is installed; Piper, Kokoro and each action are its
    children too)."""
    from ctypes import wintypes
    psapi, kernel32 = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return []
    parents, names = {}, {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID], names[entry.th32ProcessID] = entry.th32ParentProcessID, entry.szExeFile
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    def image(pid: int) -> str:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size, path = wintypes.DWORD(1024), ctypes.create_unicode_buffer(1024)
            return path.value if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) else ""
        finally:
            kernel32.CloseHandle(handle)

    def started(pid: int) -> int:
        """When the program started (Windows' file time), or 0 if it can't be read."""
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return 0
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                return 0
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            kernel32.CloseHandle(handle)

    ours = {pid for pid in parents if pid and pid != os.getpid() and _ours(image(pid))}
    begun = {pid: started(pid) for pid in ours}
    grown = True
    while grown:  # and every program they started, and theirs. Windows reuses numbers: a program whose parent number is one
        # of ours but which started before it had another parent long gone, so it is never counted (laptop, 16 Nov 2026)
        found = {}
        for pid, parent in parents.items():
            if parent in ours and pid not in ours and pid != os.getpid():
                when = started(pid)
                if when and begun.get(parent) and when >= begun[parent]:
                    found[pid] = when
        grown = bool(found)
        ours |= set(found)
        begun.update(found)
    out = []
    for pid in ours:
        handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
        if not handle:
            continue
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                out.append((pid, names.get(pid, "?"), counters.WorkingSetSize / MB))
        finally:
            kernel32.CloseHandle(handle)
    return out


def free_memory() -> tuple[float, float] | None:
    """(free MB, total MB) of the PC."""
    if sys.platform == "win32":
        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullAvailPhys / MB, status.ullTotalPhys / MB
        return None
    try:
        info = {line.split(":")[0]: int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()}
        return info["MemAvailable"] / 1024, info["MemTotal"] / 1024
    except (OSError, KeyError, ValueError, IndexError):
        return None


def report(cfg, status=None) -> list[str]:
    lines = []
    if status is None:
        try:
            from kairu.client import GuardianClient
            status = GuardianClient(cfg).status()
        except Exception as error:  # Guardian not running is an answer too
            status = {"error": type(error).__name__}
    if "error" in status:
        lines.append("Guardian: not running (start it with `kairu guardian`).")
    else:
        mode = "Safe Mode" if status.get("mode") == "safe" else "normal"
        lines.append(f"Guardian: running, {mode}.")
    processes = kairu_processes()
    total = sum(mb for _, _, mb in processes)
    for pid, name, mb in sorted(processes, key=lambda item: -item[2]):
        lines.append(f"  {name:<28} pid {pid:<7} {mb:7.0f} MB")
    lines.append(f"Kairu uses {total:.0f} MB in {len(processes)} programs (budget {BUDGET_MB} MB)."
                 + ("  OVER BUDGET" if total > BUDGET_MB else ""))
    memory = free_memory()
    if memory:
        free, whole = memory
        low = free / whole * 100 < LOW_FREE_PERCENT
        lines.append(f"This PC: {free:.0f} MB free of {whole:.0f} MB." + ("  LOW: close something heavy." if low else ""))
    plan = Path(cfg.data_dir) / "plan-journal.json"
    if plan.exists() and plan.stat().st_size > 2:
        lines.append('A cut-off plan is waiting: say "go on with the plan" or "forget the plan" in the bar.')
    return lines
