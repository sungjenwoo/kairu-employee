"""Starting Guardian at sign-in, with Windows Task Scheduler (`kairu guardian install` / `uninstall`).

The task is called "Kairu Guardian <8 letters>", one per Windows account and data folder. It:
  - starts when you sign in: an "At log on" trigger for your account only;
  - starts again every minute: a trigger that repeats every minute from the moment it is
    installed, so a Guardian that ended is back within a minute, from now on and not only after
    your next sign-in;
  - runs only while you are signed in, as you, with normal rights (least privilege, never as
    administrator), at normal priority;
  - runs `pythonw -m kairu --config <config.yaml> guardian run --autostart`, which starts the
    Guardian program in the background only if it is not running already, and then ends.
Creating it needs no administrator rights. It uses schtasks.exe, which is part of Windows.

guardian.task in the data folder holds the task's name, so Kairu knows it exists: when Kairu is
used while Guardian is down, it asks Task Scheduler to run the task (request_start), and still
refuses until Guardian answers.

guardian.paused in the data folder holds a time until which the task starts nothing. Only
tools/check_guardian.py writes it, while the tests run, and it runs out by itself.

Windows only: on Linux, install says so and the rest does nothing.
"""

import hashlib
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from kairu.config import ROOT

MARKER = "guardian.task"
PAUSE = "guardian.paused"
NAMESPACE = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
ASK_AGAIN_SECONDS = 10  # Kairu asks Task Scheduler at most this often
_asked: dict[str, float] = {}


class AutostartError(Exception):
    pass


def task_name(data_dir) -> str:
    from kairu import winpipe
    key = f"{winpipe.current_user_sid()}|{os.path.normcase(str(Path(data_dir).resolve()))}"
    return f"Kairu Guardian {hashlib.sha256(key.encode()).hexdigest()[:8]}"


def installed(data_dir) -> str | None:
    """The task's name, if `kairu guardian install` made one for this data folder."""
    try:
        name = (Path(data_dir) / MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name if name.startswith("Kairu Guardian ") else None


def definition(python: str, config_file) -> str:
    """The task, in Task Scheduler's XML."""
    from kairu import winpipe
    me = winpipe.current_user_sid()
    first = (datetime.now() + timedelta(minutes=1)).replace(microsecond=0).isoformat()
    every_minute = "<Repetition><Interval>PT1M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>"
    arguments = f'-m kairu --config "{Path(config_file).resolve()}" guardian run --autostart'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Starts Kairu Guardian when you sign in, and again within a minute whenever it is not running. Made by `kairu guardian install`; `kairu guardian uninstall` removes it.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{me}</UserId></LogonTrigger>
    <TimeTrigger><Enabled>true</Enabled><StartBoundary>{first}</StartBoundary>{every_minute}</TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{me}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{escape(python)}</Command><Arguments>{escape(arguments)}</Arguments><WorkingDirectory>{escape(str(ROOT))}</WorkingDirectory></Exec>
  </Actions>
</Task>
"""


def install(data_dir, python: str, config_file) -> str:
    """Make (or replace) the task for this data folder. Its name; AutostartError if Windows refused."""
    if sys.platform != "win32":
        raise AutostartError("starting at sign-in is built with Windows Task Scheduler, so for Windows only")
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    name = task_name(data_dir)
    path = data_dir / "guardian-task.xml"
    path.write_text(definition(python, config_file), encoding="utf-16")
    try:
        made = _schtasks("/Create", "/TN", name, "/XML", str(path), "/F")
    finally:
        path.unlink(missing_ok=True)
    if made.returncode:
        hint = " It needs administrator rights on this PC." if "denied" in made.output.lower() else ""
        raise AutostartError(f"Task Scheduler did not make the task: {made.output.strip()}{hint}")
    (data_dir / MARKER).write_text(name, encoding="utf-8")
    return name


def uninstall(data_dir) -> str | None:
    """Remove the task. Its name, or None if there was none."""
    if sys.platform != "win32":
        return None
    name = installed(data_dir) or task_name(data_dir)
    removed = _schtasks("/Delete", "/TN", name, "/F")
    (Path(data_dir) / MARKER).unlink(missing_ok=True)
    return name if removed.returncode == 0 else None


def query(name: str) -> ElementTree.Element | None:
    """The task as Task Scheduler holds it, or None if there is no such task."""
    found = _schtasks("/Query", "/TN", name, "/XML")
    if found.returncode:
        return None
    return ElementTree.fromstring(found.output.split("?>", 1)[-1].strip())


def request_start(data_dir) -> bool:
    """Ask Task Scheduler to run this data folder's task now. True if it agreed (Guardian follows in a moment)."""
    name = installed(data_dir)
    if not name or paused(data_dir) or time.monotonic() - _asked.get(name, -1e9) < ASK_AGAIN_SECONDS:
        return False
    _asked[name] = time.monotonic()
    return _schtasks("/Run", "/TN", name).returncode == 0


def pause(data_dir, seconds: float) -> None:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    (Path(data_dir) / PAUSE).write_text(repr(time.time() + seconds), encoding="utf-8")


def unpause(data_dir) -> None:
    (Path(data_dir) / PAUSE).unlink(missing_ok=True)


def paused(data_dir) -> bool:
    try:
        until = float((Path(data_dir) / PAUSE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return time.time() < until


class _Result:
    def __init__(self, returncode: int, output: str):
        self.returncode, self.output = returncode, output


def _schtasks(*args: str) -> _Result:
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "schtasks.exe"
    try:
        done = subprocess.run([str(program), *args], capture_output=True, timeout=30,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        return _Result(1, str(error))
    raw = done.stdout + done.stderr
    text = raw.decode("utf-16") if raw.startswith(b"\xff\xfe") else raw.decode("oem", errors="replace")
    return _Result(done.returncode, text)
