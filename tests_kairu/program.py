"""Helpers for the Guardian-program tests: the real program started with `kairu guardian run`, raw frames, memory."""

import os
import signal
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from kairu import channel, client
from kairu.config import Config
from tests_kairu.helpers import PIN, alive, kairu, wait_for


@dataclass
class Program:
    client: client.GuardianClient
    pid: int
    config: Config

    @property
    def data_dir(self) -> Path:
        return Path(self.config.data_dir)


def start(config) -> Program:
    started = kairu("guardian", "run", timeout=60)
    assert started.returncode == 0, started.stdout + started.stderr
    guardian = client.GuardianClient(config)
    return Program(guardian, guardian.status()["pid"], config)


def end(program: Program) -> None:
    try:
        client.quit_guardian(program.config)
    except channel.ChannelError:
        pass
    try:
        wait_for(lambda: not alive(program.pid), timeout=5)  # it may still be finishing; Windows refuses to end a process that is exiting
    except AssertionError:
        os.kill(program.pid, signal.SIGTERM)  # it did not quit: end it (on Windows, at once)
        wait_for(lambda: not alive(program.pid))


@pytest.fixture
def program(config, config_path):
    """The real Guardian program, in the background, for this test's own data folder."""
    running = start(config)
    yield running
    end(running)


@pytest.fixture
def program_with_pin(program):
    program.client.set_pin(PIN)
    return program


def frame(body: bytes, claimed: int | None = None) -> bytes:
    """A message as it travels on the channel: its length (or a false one), then its bytes."""
    return struct.pack(">I", len(body) if claimed is None else claimed) + body


def parent_pid(pid: int) -> int:
    """The process that started this one."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Entry(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        try:
            entry = Entry(dwSize=ctypes.sizeof(Entry))
            more = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
            while more:
                if entry.th32ProcessID == pid:
                    return entry.th32ParentProcessID
                more = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(snapshot))
        raise LookupError(f"no process {pid}")
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])


def children(pid: int) -> list[int]:
    """The processes this one started (on Windows a venv's python.exe is a small starter, the real Python its child)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Entry(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot, found = kernel32.CreateToolhelp32Snapshot(0x2, 0), []
        try:
            entry = Entry(dwSize=ctypes.sizeof(Entry))
            more = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
            while more:
                if entry.th32ParentProcessID == pid:
                    found.append(entry.th32ProcessID)
                more = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(snapshot))
        return found
    found = []
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            if int(stat.read_text().rsplit(")", 1)[1].split()[1]) == pid:
                found.append(int(stat.parent.name))
        except (OSError, ValueError, IndexError):
            pass
    return found


def family_memory_mib(pid: int) -> tuple[float, float]:
    """memory_mib of a process and the processes it started, added up."""
    readings = [memory_mib(member) for member in [pid, *children(pid)]]
    return sum(now for now, _ in readings), sum(peak for _, peak in readings)


def memory_mib(pid: int) -> tuple[float, float]:
    """(working set now, peak working set) of a process, in MiB. Linux: VmRSS and VmHWM."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                     "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                     "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
        handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
        assert handle, ctypes.get_last_error()
        try:
            counters = Counters(cb=ctypes.sizeof(Counters))
            assert kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb), ctypes.get_last_error()
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(handle))
        return counters.WorkingSetSize / 2**20, counters.PeakWorkingSetSize / 2**20
    fields = dict(line.split(":", 1) for line in Path(f"/proc/{pid}/status").read_text().splitlines() if ":" in line)
    return int(fields["VmRSS"].split()[0]) / 1024, int(fields["VmHWM"].split()[0]) / 1024
