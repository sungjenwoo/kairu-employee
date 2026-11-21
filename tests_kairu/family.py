"""A family of programs for the stop tests: the action starts a child, and the child starts a grandchild.

Each one writes its process id to <folder>/<name>.pid and rewrites <folder>/<name>.beat every 0.05 s.
With stubborn, each one also ignores the request to end (on Linux; Windows has no such request),
so only a kill can stop them.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

NEXT = {"action": "child", "child": "grandchild"}


def live(name: str, folder: str, stubborn: bool) -> None:
    folder = Path(folder)
    if stubborn and sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (folder / f"{name}.pid").write_text(str(os.getpid()))
    if name in NEXT:
        subprocess.Popen([sys.executable, "-m", "tests_kairu.family", NEXT[name], str(folder), "1" if stubborn else "0"])
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        (folder / f"{name}.beat").write_text(repr(time.time()))
        time.sleep(0.05)


def action(folder: str, stubborn: bool = False) -> None:
    """What the runner starts, inside kairu.worker."""
    live("action", folder, stubborn)


def leave_running(folder: str, stubborn: bool = False) -> None:
    """An action that starts its child, waits until the grandchild is running too, then ends, leaving them behind.

    It ends only once <folder>/leave exists (the test writes it after seeing the child and grandchild
    running), so a slow test never looks for them after the runner has already, rightly, ended them.
    """
    folder = Path(folder)
    (folder / "action.pid").write_text(str(os.getpid()))
    (folder / "action.beat").write_text(repr(time.time()))
    subprocess.Popen([sys.executable, "-m", "tests_kairu.family", "child", str(folder), "1" if stubborn else "0"])
    deadline = time.monotonic() + 20
    while not (folder / "grandchild.beat").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    deadline = time.monotonic() + 20
    while not (folder / "leave").exists() and time.monotonic() < deadline:
        time.sleep(0.01)


if __name__ == "__main__":
    live(sys.argv[1], sys.argv[2], sys.argv[3] == "1")
