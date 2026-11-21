"""Starting the bar at sign-in, with Windows Task Scheduler (`kairu bar install` / `uninstall`), like Guardian's task.

The task is called "Kairu Bar <8 letters>". It runs once when you sign in, as you, with normal rights, and starts the bar
hidden: Ctrl+Alt+Space shows it. Unlike Guardian's task it does not repeat: a bar you quit stays quit until you start it
or sign in again. bar.task in the data folder holds its name. Windows only.
"""

import hashlib
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from kairu import autostart
from kairu.autostart import AutostartError
from kairu.config import ROOT

MARKER = "bar.task"


def task_name(data_dir) -> str:
    from kairu import winpipe
    key = f"{winpipe.current_user_sid()}|{os.path.normcase(str(Path(data_dir).resolve()))}"
    return f"Kairu Bar {hashlib.sha256(key.encode()).hexdigest()[:8]}"


def installed(data_dir) -> str | None:
    try:
        name = (Path(data_dir) / MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name if name.startswith("Kairu Bar ") else None


def definition(python: str, config_file) -> str:
    from kairu import winpipe
    me = winpipe.current_user_sid()
    arguments = f'-m kairu --config "{Path(config_file).resolve()}" bar start --hidden'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Starts the Kairu bar, hidden, when you sign in. Ctrl+Alt+Space shows it. Made by `kairu bar install`; `kairu bar uninstall` removes it.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{me}</UserId></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{me}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{escape(python)}</Command><Arguments>{escape(arguments)}</Arguments><WorkingDirectory>{escape(str(ROOT))}</WorkingDirectory></Exec>
  </Actions>
</Task>
"""


def install(data_dir, python: str, config_file) -> str:
    """Make (or replace) the task. Its name; AutostartError if Windows refused."""
    if sys.platform != "win32":
        raise AutostartError("starting the bar at sign-in is built with Windows Task Scheduler, so for Windows only")
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    name = task_name(data_dir)
    path = data_dir / "bar-task.xml"
    path.write_text(definition(python, config_file), encoding="utf-16")
    try:
        made = autostart._schtasks("/Create", "/TN", name, "/XML", str(path), "/F")
    finally:
        path.unlink(missing_ok=True)
    if made.returncode:
        raise AutostartError(f"Task Scheduler did not make the task: {made.output.strip()}")
    (data_dir / MARKER).write_text(name, encoding="utf-8")
    return name


def uninstall(data_dir) -> str | None:
    """Remove the task. Its name, or None if there was none."""
    if sys.platform != "win32":
        return None
    name = installed(data_dir) or task_name(data_dir)
    removed = autostart._schtasks("/Delete", "/TN", name, "/F")
    (Path(data_dir) / MARKER).unlink(missing_ok=True)
    return name if removed.returncode == 0 else None
