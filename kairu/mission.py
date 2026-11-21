"""Mission Mode (ADR-018): the PC stays awake with the lid closed while it is charging, then sleeps normally again.

    kairu mission-mode on     High: "yes" and your PIN. It runs as the action mission_mode.on, inside Guardian.
    kairu mission-mode off    ends it; Guardian puts the lid setting back at once.

While it runs, this action:
  - starts only while the PC is on mains power, and ends when it is unplugged (GetSystemPowerStatus,
    checked every 2 seconds);
  - keeps Windows from sleeping (SetThreadExecutionState: the system, not the screen). Windows drops
    this by itself when the process ends, however it ends;
  - sets "When I close the lid" to "Do nothing" for mains power only (powercfg), after writing the old
    value to data/mission-mode.json. On battery your own setting always applies;
  - ends by itself after mission_mode.max_hours (default 4); when Windows gives a temperature
    (the "Thermal Zone Information" counter) of max_celsius or more; or when the processor stays above
    cpu_percent for cpu_minutes, a stand-in for heat where Windows gives no temperature (many laptops
    give none to a normal program; the owner's PC gives none).

The lid setting is ALWAYS put back (restore()):
  - by this action itself when it ends on its own (unplugged, a limit);
  - by Guardian as soon as the action ends any other way: `kairu mission-mode off`, a stop (Ctrl+Alt+K,
    the tray's STOP, `kairu stop`), Guardian quitting or being ended (its Job Object ends the action);
  - by `kairu stop` itself when Guardian is not running;
  - by Guardian when it next starts, if the PC crashed or lost power while Mission Mode was on.
data/mission-mode.json exists only between the change and its undoing, and restore() can run any
number of times. Putting the setting back does not send a PC whose lid is already closed to sleep:
Windows applies the lid setting when the lid closes, so such a PC sleeps after its normal idle time.

KAIRU_TEST_POWER names a folder that stands in for the PC's power (StandIn): the tests use it so that
they never touch the real lid setting. It changes nothing on the PC.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

STATE_NAME = "mission-mode.json"  # the lid value to put back; exists only while it is changed
LAST_NAME = "mission-mode.last.json"  # how the last Mission Mode ended
CHECK_SECONDS = 2.0
DO_NOTHING = 0
LID_ACTIONS = {0: "Do nothing", 1: "Sleep", 2: "Hibernate", 3: "Shut down"}
ENDINGS = {  # how it ended -> what Kairu says
    "unplugged": "the PC was unplugged",
    "time": "it reached its time cap",
    "heat": "the PC reported too high a temperature",
    "cpu": "the processor stayed busy too long (the CPU cap)",
}
SUB_BUTTONS = "4f971e89-eebd-4455-a8de-9e59040e7347"
LIDACTION = "5ca83367-6e45-459f-a27b-476b1d01c936"
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
HEX = re.compile(r"0x([0-9a-fA-F]{8})")


class MissionError(Exception):
    pass


# --- the PC's power ---------------------------------------------------------------------------------

class WindowsPower:
    """The real thing, through ctypes and powercfg.exe (Windows' own tool, by its full path)."""

    def __init__(self):
        import ctypes
        self._ctypes = ctypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._cpu_last = None
        self._pdh = None

    def on_mains(self) -> bool | None:
        ctypes = self._ctypes

        class Status(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

        status = Status()
        if not self._kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        return {0: False, 1: True}.get(status.ACLineStatus)  # 255: Windows cannot tell

    def lid(self) -> tuple[str, int]:
        """(the active power plan's GUID, its lid-close action on mains power)."""
        found = GUID.search(_powercfg("/getactivescheme"))
        if not found:
            raise MissionError("powercfg did not name the active power plan")
        return found.group(0), self.lid_of(found.group(0))

    def lid_of(self, scheme: str) -> int:
        values = HEX.findall(_powercfg("/qh", scheme, SUB_BUTTONS, LIDACTION))  # /qh: the lid setting may be hidden
        if len(values) < 2:
            raise MissionError("this PC's power plan has no lid-close setting")
        return int(values[-2], 16)  # the last two are "Current AC" then "Current DC", in every language

    def set_lid(self, scheme: str, value: int) -> None:
        _powercfg("/setacvalueindex", scheme, SUB_BUTTONS, LIDACTION, str(int(value)))
        _powercfg("/setactive", "SCHEME_CURRENT")  # so the change takes effect now

    def keep_awake(self, on: bool) -> None:
        es_continuous, es_system_required = 0x80000000, 0x00000001
        function = self._kernel32.SetThreadExecutionState
        function.restype = self._ctypes.c_uint32
        function.argtypes = (self._ctypes.c_uint32,)
        if not function(es_continuous | (es_system_required if on else 0)):
            raise MissionError("Windows refused to keep the PC awake")

    def celsius(self) -> float | None:
        """The hottest thermal zone Windows reports, or None where it reports none."""
        ctypes = self._ctypes
        from ctypes import wintypes
        try:
            if self._pdh is None:
                pdh = ctypes.WinDLL("pdh")
                query, counter = ctypes.c_void_p(), ctypes.c_void_p()
                if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) or pdh.PdhAddEnglishCounterW(
                        query, "\\Thermal Zone Information(*)\\Temperature", 0, ctypes.byref(counter)):
                    self._pdh = False
                    return None
                self._pdh = (pdh, query, counter)
            if not self._pdh:
                return None
            pdh, query, counter = self._pdh

            class Value(ctypes.Structure):
                _fields_ = [("CStatus", wintypes.DWORD), ("pad", wintypes.DWORD), ("doubleValue", ctypes.c_double)]

            class Item(ctypes.Structure):
                _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", Value)]

            if pdh.PdhCollectQueryData(query):
                return None
            size, count = wintypes.DWORD(0), wintypes.DWORD(0)
            pdh.PdhGetFormattedCounterArrayW(counter, 0x200, ctypes.byref(size), ctypes.byref(count), None)
            if not size.value:
                return None
            buffer = ctypes.create_string_buffer(size.value)
            if pdh.PdhGetFormattedCounterArrayW(counter, 0x200, ctypes.byref(size), ctypes.byref(count), buffer):
                return None
            items = ctypes.cast(buffer, ctypes.POINTER(Item))
            kelvin = [items[i].FmtValue.doubleValue for i in range(count.value) if items[i].FmtValue.CStatus in (0, 1)]
        except OSError:
            return None
        readings = [value - 273.15 for value in kelvin if 273.15 < value < 273.15 + 150]
        return max(readings) if readings else None

    def cpu_percent(self) -> float | None:
        """How busy the processor was since the last call (all cores), or None on the first call."""
        ctypes = self._ctypes
        times = [ctypes.c_ulonglong() for _ in range(3)]  # idle, kernel (which includes idle), user
        if not self._kernel32.GetSystemTimes(*(ctypes.byref(value) for value in times)):
            return None
        idle, total = times[0].value, times[1].value + times[2].value
        last, self._cpu_last = self._cpu_last, (idle, total)
        if last is None or total <= last[1]:
            return None
        return 100.0 * (1 - (idle - last[0]) / (total - last[1]))


class StandIn:
    """The tests' stand-in for the PC's power: one small file per value in the folder KAIRU_TEST_POWER names.

    ac (true/false), scheme, lid_ac, awake, celsius (or null), cpu. Writes go to lid_ac and awake only.
    """

    def __init__(self, folder):
        self.folder = Path(folder)

    def _get(self, name, default=None):
        for _ in range(50):
            try:
                return json.loads((self.folder / name).read_text())
            except (FileNotFoundError, ValueError):
                return default
            except PermissionError:  # Windows: it is being replaced right now (_put)
                time.sleep(0.01)
        return json.loads((self.folder / name).read_text())

    def _put(self, name, value) -> None:
        temp = self.folder / f"{name}.{os.getpid()}.{id(value)}.tmp"
        temp.write_text(json.dumps(value))
        for _ in range(50):
            try:
                os.replace(temp, self.folder / name)
                return
            except PermissionError:  # Windows: someone is reading it right now
                time.sleep(0.01)
        os.replace(temp, self.folder / name)

    def on_mains(self):
        return self._get("ac")

    def lid(self):
        return self._get("scheme", "stand-in"), self.lid_of(self._get("scheme", "stand-in"))

    def lid_of(self, scheme):
        return self._get("lid_ac", 1)

    def set_lid(self, scheme, value):
        if self._get("broken"):
            raise MissionError("powercfg failed (stand-in)")
        self._put("lid_ac", int(value))

    def keep_awake(self, on):
        self._put("awake", bool(on))

    def celsius(self):
        return self._get("celsius")

    def cpu_percent(self):
        return self._get("cpu")


def power():
    """The PC's power, or None where Mission Mode cannot run (not Windows)."""
    if os.environ.get("KAIRU_TEST_POWER"):
        return StandIn(os.environ["KAIRU_TEST_POWER"])
    return WindowsPower() if sys.platform == "win32" else None


def _powercfg(*args: str) -> str:
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "powercfg.exe"
    try:
        done = subprocess.run([str(program), *args], capture_output=True, text=True, errors="replace", timeout=20,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MissionError(f"powercfg could not run ({type(error).__name__})") from None
    if done.returncode:
        raise MissionError(f"powercfg {args[0]} failed: {(done.stdout + done.stderr).strip()[:200]}")
    return done.stdout


# --- the saved value, and putting it back -----------------------------------------------------------

BUSY_TRIES, BUSY_SECONDS = 50, 0.01  # Windows refuses a file for a moment while another process replaces or deletes it


def _patiently(do):
    """do(), again for up to about 0.5 s while Windows says the file is busy (PermissionError): on Windows a file
    that another process is replacing, deleting or still has open cannot be opened, replaced or deleted for that
    moment. After that the PermissionError is raised: then something really does keep the file from Kairu."""
    for _ in range(BUSY_TRIES):
        try:
            return do()
        except PermissionError:
            time.sleep(BUSY_SECONDS)
    return do()


def saved(data_dir) -> dict | None:
    """What restore() would put back, or None when nothing is changed."""
    try:
        return json.loads(_patiently((Path(data_dir) / STATE_NAME).read_text))
    except FileNotFoundError:
        return None
    except ValueError:
        return {}  # unreadable: restore() puts Windows' default back


def restore(data_dir, pc=None) -> str | None:
    """Put the lid setting back if Mission Mode changed it. What was done, or None if nothing was changed.

    Raises MissionError if Windows refused; the saved value is then kept, for the next try.
    """
    path = Path(data_dir) / STATE_NAME
    state = saved(data_dir)
    if state is None:
        return None
    pc = pc or power()
    if pc is None:
        raise MissionError("Mission Mode's lid setting can only be put back on Windows")
    scheme, value = state.get("scheme"), state.get("lid_ac")
    if not isinstance(scheme, str) or value not in LID_ACTIONS:
        scheme, value, note = pc.lid()[0], 1, " (the saved value could not be read, so Windows' default)"
    else:
        note = ""
    pc.set_lid(scheme, value)
    if pc.lid_of(scheme) != value:
        raise MissionError("Windows did not take the lid setting back")
    _patiently(lambda: path.unlink(missing_ok=True))
    return f"the lid setting on mains power is back to \"{LID_ACTIONS[value]}\"{note}"


def last_ending(data_dir) -> dict | None:
    try:
        return json.loads(_patiently((Path(data_dir) / LAST_NAME).read_text))
    except (FileNotFoundError, ValueError):
        return None


def _write(path: Path, data: dict) -> None:
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        json.dump(data, out)
        out.flush()
        os.fsync(out.fileno())
    _patiently(lambda: os.replace(temp, path))


# --- the action -------------------------------------------------------------------------------------

def run(data_dir: str, max_hours: float = 4, cpu_percent: float = 85, cpu_minutes: float = 10,
        max_celsius: float = 85) -> None:
    """The mission_mode.on action (see above). Returns only by ending: exit code 0 when it ended by itself."""
    pc = power()
    if pc is None:
        _fail("Mission Mode is for Windows")
    if pc.on_mains() is not True:
        _fail("Mission Mode starts only while the PC is charging (plugged in to mains power)")
    folder = Path(data_dir)
    try:
        restore(folder, pc)  # a change left by a crash goes back first, so the value saved below is truly yours
        scheme, old = pc.lid()
        _write(folder / STATE_NAME, {"scheme": scheme, "lid_ac": old, "since": time.time(), "pid": os.getpid(),
                                     "max_hours": max_hours})  # written before anything changes
        pc.set_lid(scheme, DO_NOTHING)
        pc.keep_awake(True)
    except MissionError as error:
        _fail(str(error))  # Guardian puts back whatever was changed
    print(f"mission_mode.on: on; lid on mains was \"{LID_ACTIONS.get(old, old)}\", now \"Do nothing\"",
          file=sys.stderr, flush=True)
    started, busy_since = time.monotonic(), None
    pc.cpu_percent()  # the first reading only sets the start
    while True:
        time.sleep(CHECK_SECONDS)
        now = time.monotonic()
        reason, detail = None, ""
        if pc.on_mains() is not True:
            reason = "unplugged"
        elif now - started >= max_hours * 3600:
            reason, detail = "time", f"{max_hours:g} hours"
        else:
            celsius = pc.celsius()
            busy = pc.cpu_percent()
            busy_since = (busy_since or now) if busy is not None and busy >= cpu_percent else None
            if celsius is not None and celsius >= max_celsius:
                reason, detail = "heat", f"{celsius:.0f} C, limit {max_celsius:g} C"  # plain text: it goes to Guardian's log
            elif busy_since is not None and now - busy_since >= cpu_minutes * 60:
                reason, detail = "cpu", f"above {cpu_percent:g}% for {cpu_minutes:g} minutes"
        if reason:
            end(folder, pc, reason, detail)
            return


def end(folder: Path, pc, reason: str, detail: str = "") -> None:
    put_back = ""
    try:
        put_back = restore(folder, pc) or ""
    except MissionError as error:
        put_back = f"the lid setting could not be put back yet ({error}); Guardian tries again"
    pc.keep_awake(False)
    _write(folder / LAST_NAME, {"reason": reason, "detail": detail, "at": time.time(), "put_back": put_back})
    print(f"mission_mode.on: ended: {ENDINGS[reason]}{' (' + detail + ')' if detail else ''}; {put_back}",
          file=sys.stderr, flush=True)


def _fail(why: str):
    print(f"mission_mode.on: {why}", file=sys.stderr, flush=True)
    raise SystemExit(1)
