"""Helpers for the tests: running the kairu command, and waiting."""

import os
import subprocess
import sys
import time
from pathlib import Path

from kairu.config import ROOT

PIN = "482916"
POLICY = ROOT / "policy.yaml"  # the real, shipped policy


def kairu(*args, input_text=None, timeout=20):
    """Run `python -m kairu ...` as its own process, as you would in a terminal."""
    return subprocess.run([sys.executable, "-m", "kairu", *args], cwd=ROOT, env=os.environ.copy(), input=input_text,
                          capture_output=True, text=True, timeout=timeout)


def wait_for(condition, timeout=10.0, every=0.01):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        time.sleep(every)


def heartbeat_stopped(path: Path, quiet_for=0.3) -> bool:
    """True if the action stopped rewriting its heartbeat file."""
    before = path.read_text()
    time.sleep(quiet_for)
    return path.read_text() == before


def alive(pid: int) -> bool:
    """True if the process is still running. A process that has ended but not been collected counts as gone."""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0x102  # WAIT_TIMEOUT: still running
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state not in ("Z", "X")  # Z: ended, waiting to be collected
