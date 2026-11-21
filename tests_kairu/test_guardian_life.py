"""Guardian's life: one at a time, Ctrl+Alt+K held by Guardian, Safe Mode after an unclear exit, and the sign-in task."""

import os
import signal
import subprocess
import sys
import time

import pytest
import yaml

from kairu import audit, autostart, channel, client, hotkey
from kairu.config import ROOT
from kairu.guardian import Action, Verdict
from kairu.store import Store
from tests_kairu.helpers import POLICY, alive, kairu, wait_for
from tests_kairu.program import end, program, start  # noqa: F401 (fixture)

LIMIT = 1.0  # seconds
LONG = Action("demo.count", {"seconds": 60, "quiet": True})
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def guardian_rows(config):
    return [(row["decision"], row["details"]) for row in audit.tail(Store(config.data_dir), 200, kind="guardian")]


def kill(pid: int) -> None:
    """End a process at once, without a chance to clean up: Task Manager's End task, or kill -9."""
    os.kill(pid, signal.SIGTERM if sys.platform == "win32" else signal.SIGKILL)
    wait_for(lambda: not alive(pid))


def press_ctrl_alt_k() -> None:
    import ctypes
    user32 = ctypes.WinDLL("user32")
    for vk in (0x11, 0x12, hotkey.VK_K):  # Ctrl, Alt, K down, then up
        user32.keybd_event(vk, 0, 0, 0)
    for vk in (hotkey.VK_K, 0x12, 0x11):
        user32.keybd_event(vk, 0, 2, 0)


# --- only one Guardian ----------------------------------------------------------------------------

def test_only_one_guardian_runs_at_a_time(program, tmp_path):
    second = subprocess.run([sys.executable, "-m", channel.GUARDIAN_MODULE, "--config", str(tmp_path / "config.yaml")],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert second.returncode == 1 and "already running" in second.stderr
    other = tmp_path / "other"  # not even one for another data folder: Ctrl+Alt+K could reach only one of them
    other.mkdir()
    (other / "config.yaml").write_text(yaml.safe_dump({"guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    third = subprocess.run([sys.executable, "-m", channel.GUARDIAN_MODULE, "--config", str(other / "config.yaml")],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert third.returncode == 1 and "another Guardian is already running under your account" in third.stderr
    assert not (other / "data" / "guardian.db").exists()  # it stopped before touching anything
    again = kairu("guardian", "run")
    assert again.returncode == 0 and f"already running (process {program.pid})" in again.stdout
    assert program.client.status()["pid"] == program.pid


# --- clean and unclear exits ----------------------------------------------------------------------

def test_after_guardian_is_killed_the_next_start_is_in_safe_mode(program, config):
    assert program.client.status()["mode"] == "normal"
    kill(program.pid)
    restarted = start(config)
    try:
        state = restarted.client.status()
        assert state["mode"] == "safe" and f"process {program.pid}" in state["safe_reason"]
        assert "without a clean exit" in state["safe_reason"]
        assert restarted.client.check("files.write").verdict is Verdict.DENY  # read-only until you resume
        assert ("unclean exit found", {"previous": state["safe_reason"].split("(")[1].split(")")[0]}) in guardian_rows(config)
    finally:
        end(restarted)


def test_after_a_clean_quit_the_next_start_is_not_in_safe_mode(program, config):
    assert kairu("guardian", "quit").returncode == 0
    restarted = start(config)
    try:
        assert restarted.client.status()["mode"] == "normal"
        stops = [details for decision, details in guardian_rows(config) if decision == "stopped"]
        assert stops[-1]["clean"] is True and stops[-1]["why"] == "kairu guardian quit"
        assert "unclean exit found" not in [decision for decision, _ in guardian_rows(config)]
    finally:
        end(restarted)


@pytest.mark.skipif(sys.platform == "win32", reason="Linux: a plain kill")
def test_on_linux_a_kill_signal_ends_actions_but_is_not_a_clean_exit(program, config):
    started = program.client.run(LONG)
    os.kill(program.pid, signal.SIGTERM)  # Linux sends this at sign-out too, so Guardian cannot be sure
    wait_for(lambda: not alive(program.pid))
    assert not alive(started["pid"])  # its actions ended first
    restarted = start(config)
    try:
        assert restarted.client.status()["mode"] == "safe"
    finally:
        end(restarted)


def session_window(pid: int):
    import ctypes
    from kairu import session
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.SendMessageTimeoutW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                           ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t))
    window = user32.FindWindowW(session.CLASS_NAME, session.title(pid))
    assert window, "Guardian's hidden session window was not found"

    def send(message, wparam=0, lparam=0) -> int:
        answer = ctypes.c_size_t()
        assert user32.SendMessageTimeoutW(window, message, wparam, lparam, 0x2, 10000, ctypes.byref(answer))  # SMTO_ABORTIFHUNG
        return answer.value
    return send


@windows_only
@pytest.mark.parametrize("lparam,kind", [(0x80000000, "sign-out"), (0, "shutdown or restart")])
def test_signing_out_shutting_down_or_restarting_is_a_clean_exit(program, config, lparam, kind):
    started = program.client.run(LONG)
    send = session_window(program.pid)
    assert send(0x0011, 0, lparam) == 1  # WM_QUERYENDSESSION: Guardian never holds it up
    send(0x0016, 1, lparam)  # WM_ENDSESSION: the session ends; Windows would end Guardian after this answer
    wait_for(lambda: not alive(program.pid))
    assert not alive(started["pid"])
    stops = [details for decision, details in guardian_rows(config) if decision == "stopped"]
    assert stops[-1]["clean"] is True and stops[-1]["why"] == kind
    restarted = start(config)
    try:
        assert restarted.client.status()["mode"] == "normal"
    finally:
        end(restarted)


@windows_only
def test_nothing_that_windows_ends_without_asking_stands_above_guardian(program):
    """The sign-out bug: Guardian ran as the child of the venv's windowless starter, and died with it."""
    from kairu import winpipe
    program_file = winpipe.process_identity(program.pid)[2]
    assert ".venv" not in program_file.lower() and program_file.lower().endswith("pythonw.exe")  # the real Python
    assert not alive(winpipe.parent_pid(program.pid))  # what started it has ended; Guardian stands alone
    assert program.client.status()["shutdown_level"] == 0x3FF  # and Windows tells it among the first


@windows_only
def test_being_asked_to_end_the_session_is_not_yet_a_clean_exit(program, config):
    send = session_window(program.pid)
    assert send(0x0011, 0, 0x80000000) == 1  # WM_QUERYENDSESSION, but Windows is not really ending the session
    kill(program.pid)
    restarted = start(config)
    try:
        assert restarted.client.status()["mode"] == "safe"
    finally:
        end(restarted)


@windows_only
def test_a_cancelled_sign_out_takes_back_nothing_and_a_later_kill_still_gives_safe_mode(program, config):
    send = session_window(program.pid)
    send(0x0011, 0, 0x80000000)
    send(0x0016, 0, 0x80000000)  # WM_ENDSESSION, FALSE: another program cancelled the sign-out
    assert program.client.status()["pid"] == program.pid  # Guardian runs on
    kill(program.pid)
    restarted = start(config)
    try:
        assert restarted.client.status()["mode"] == "safe"
    finally:
        end(restarted)


def test_a_clean_exit_recorded_just_before_windows_ended_guardian_counts_and_gets_its_audit_row(config, config_path):
    from kairu import guardian_program
    store = Store(config.data_dir)
    store.put(guardian_program.RUNNING, "")  # what record_clean leaves if Windows ends Guardian right after it
    store.put(guardian_program.CLEAN_EXIT, "sign-out (process 4242, started earlier)")
    running = start(config)
    try:
        assert running.client.status()["mode"] == "normal"
        stops = [details for decision, details in guardian_rows(config) if decision == "stopped"]
        assert stops[-1] == {"clean": True, "why": "sign-out (process 4242, started earlier)", "note": "recorded at the next start"}
    finally:
        end(running)


@windows_only
def test_the_tray_shows_guardians_state(program):
    from kairu import tray
    assert tray.describe("normal", "", 0, True) == ("Kairu Guardian: normal, nothing running. Ctrl+Alt+K ready", tray.IDI_SHIELD)
    assert tray.describe("normal", "", 2, True)[0] == "Kairu Guardian: normal, 2 actions running. Ctrl+Alt+K ready"
    assert tray.describe("normal", "", 1, True)[1] == tray.IDI_INFORMATION
    text, icon = tray.describe("safe", "emergency stop (Ctrl+Alt+K)", 0, False)
    assert icon == tray.IDI_WARNING and "Safe Mode: emergency stop (Ctrl+Alt+K)" in text and "kairu resume" in text
    assert "Ctrl+Alt+K not held" in text
    assert program.client.status()["tray"] in ("shown", tray.Tray(lambda: ("", 0), lambda: None).status)
    print(f"\n  Guardian's tray icon: {program.client.status()['tray']}")


@windows_only
def test_stop_everything_in_the_tray_halts_every_action_within_1_second(program):
    from kairu import tray
    runs = [program.client.run(LONG) for _ in range(2)]
    send = session_window(program.pid)
    began = time.monotonic()
    send(0x0111, tray.STOP_ID, 0)  # WM_COMMAND: what choosing "Stop everything" does
    wait_for(lambda: not any(alive(run["pid"]) for run in runs), timeout=5, every=0.01)
    elapsed = time.monotonic() - began
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    state = program.client.status()
    assert state["mode"] == "safe" and "Stop everything" in state["safe_reason"]
    print(f"\n  tray Stop everything -> {len(runs)} actions halted in {elapsed:.3f} s")


@windows_only
def test_the_stop_item_is_drawn_as_a_big_red_band():
    import ctypes
    from ctypes import wintypes
    from kairu import tray
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    for name in ("CreateCompatibleDC", "CreateCompatibleBitmap", "SelectObject"):
        getattr(gdi32, name).restype = wintypes.HANDLE
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    user32.GetDC.argtypes = (wintypes.HWND,)
    gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    gdi32.SelectObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    gdi32.DeleteObject.argtypes = gdi32.DeleteDC.argtypes = (wintypes.HANDLE,)
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    gdi32.GetPixel.argtypes, gdi32.GetPixel.restype = (wintypes.HDC, ctypes.c_int, ctypes.c_int), wintypes.DWORD
    user32.GetDC.restype = wintypes.HDC
    screen = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, 300, 56)
    gdi32.SelectObject(dc, bitmap)
    item = tray._DrawItem(itemID=tray.STOP_ID, hDC=dc, rcItem=wintypes.RECT(0, 0, 300, 56))
    tray._draw_stop(item)
    assert gdi32.GetPixel(dc, 3, 3) == 0x002020C8  # red, edge to edge
    colours = {gdi32.GetPixel(dc, x, 28) for x in range(60, 240)}
    assert 0x00FFFFFF in colours or len(colours) > 2  # with white letters across the middle
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    user32.ReleaseDC(None, screen)


@windows_only
def test_a_close_request_to_guardians_window_does_not_end_it(program):
    session_window(program.pid)(0x0010)  # WM_CLOSE
    time.sleep(0.3)
    assert program.client.status()["pid"] == program.pid


# --- Ctrl+Alt+K, held by Guardian ------------------------------------------------------------------

@windows_only
def test_ctrl_alt_k_held_by_guardian_stops_actions_with_no_kairu_window_open(program):
    assert program.client.status()["hotkey"] == "held"
    runs = [program.client.run(LONG) for _ in range(2)]  # nothing of Kairu's is open but Guardian itself
    began = time.monotonic()
    press_ctrl_alt_k()
    wait_for(lambda: not any(alive(run["pid"]) for run in runs), timeout=5, every=0.01)
    elapsed = time.monotonic() - began
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    state = program.client.status()
    assert state["mode"] == "safe" and hotkey.NAME in state["safe_reason"]
    print(f"\n  Ctrl+Alt+K held by Guardian -> {len(runs)} actions halted in {elapsed:.3f} s")
    assert "Guardian holds Ctrl+Alt+K already" in kairu("hotkey").stdout


@windows_only
def test_guardian_takes_ctrl_alt_k_as_soon_as_another_program_lets_go(config, config_path):
    other = hotkey.Hotkey(lambda: None)
    assert other.start(), other.error
    try:
        running = start(config)
    finally:
        other.close()
    try:
        assert running.client.status()["hotkey"] != "held"  # it was taken when Guardian started
        wait_for(lambda: running.client.status()["hotkey"] == "held", timeout=hotkey.RETRY_SECONDS + 5)
    finally:
        end(running)


# --- starting at sign-in ---------------------------------------------------------------------------

def test_the_task_launcher_starts_guardian_only_when_it_is_not_running(config, config_path):
    assert kairu("guardian", "run", "--autostart").returncode == 0
    first = client.GuardianClient(config, start_if_down=False).status()["pid"]
    try:
        assert kairu("guardian", "run", "--autostart").returncode == 0
        assert client.GuardianClient(config, start_if_down=False).status()["pid"] == first  # no second one
    finally:
        client.quit_guardian(config)
    wait_for(lambda: not alive(first))


def test_while_the_check_runs_the_task_starts_nothing_and_after_it_guardian_is_back(config, config_path):
    running = start(config)
    assert client.pause_for_check(config) is True
    wait_for(lambda: not alive(running.pid))
    assert kairu("guardian", "run", "--autostart").returncode == 0  # paused: starts nothing
    assert not client.GuardianClient(config, start_if_down=False).alive()
    client.resume_after_check(config, config_path, was_running=True)
    back = client.GuardianClient(config, start_if_down=False).status()["pid"]
    end(type(running)(running.client, back, config))


@windows_only
def test_install_makes_the_task_with_the_right_settings_and_uninstall_removes_it(config, config_path):
    from kairu import winpipe
    installed = kairu("guardian", "install", timeout=90)
    try:
        assert installed.returncode == 0, installed.stdout + installed.stderr
        name = autostart.installed(config.data_dir)
        assert name and name.startswith("Kairu Guardian ")
        task = autostart.query(name)
        assert task is not None
        n = autostart.NAMESPACE
        me = winpipe.current_user_sid()
        is_me = lambda user: user == me or user.lower().endswith("\\" + os.environ["USERNAME"].lower())

        logon = task.find(f"{n}Triggers/{n}LogonTrigger")  # at sign-in, for this account only
        assert logon is not None and is_me(logon.findtext(f"{n}UserId"))
        every = task.find(f"{n}Triggers/{n}TimeTrigger/{n}Repetition")  # and every minute, for ever
        assert every.findtext(f"{n}Interval") == "PT1M" and every.find(f"{n}Duration") is None
        principal = task.find(f"{n}Principals/{n}Principal")
        assert is_me(principal.findtext(f"{n}UserId"))
        assert principal.findtext(f"{n}LogonType") == "InteractiveToken"  # only while signed in
        # normal rights, never administrator; Task Scheduler leaves this default out, but would show HighestAvailable
        assert principal.findtext(f"{n}RunLevel") in (None, "LeastPrivilege")
        settings = task.find(f"{n}Settings")
        assert settings.findtext(f"{n}MultipleInstancesPolicy") == "IgnoreNew"
        assert settings.findtext(f"{n}DisallowStartIfOnBatteries") == "false"
        assert settings.findtext(f"{n}StopIfGoingOnBatteries") == "false"
        assert settings.findtext(f"{n}Priority") == "5"
        run = task.find(f"{n}Actions/{n}Exec")
        assert run.findtext(f"{n}Command").lower().endswith("pythonw.exe")
        assert run.findtext(f"{n}Arguments") == f'-m kairu --config "{config_path.resolve()}" guardian run --autostart'
        assert client.GuardianClient(config, start_if_down=False).alive()  # and Guardian runs now
        assert f'Task Scheduler task "{name}"' in kairu("status").stdout

        removed = kairu("guardian", "uninstall")
        assert removed.returncode == 0 and name in removed.stdout
        assert autostart.query(name) is None and autostart.installed(config.data_dir) is None
    finally:
        autostart.uninstall(config.data_dir)
        try:
            client.quit_guardian(config)
        except channel.ChannelError:
            pass


@windows_only
def test_with_the_task_kairu_asks_task_scheduler_to_start_a_guardian_that_is_down(config, config_path):
    assert kairu("guardian", "install", timeout=90).returncode == 0
    try:
        client.quit_guardian(config)
        decision = client.GuardianClient(config).check("chat.reply")
        assert decision.verdict is Verdict.DENY and "asked Task Scheduler to start it" in decision.reason
        wait_for(lambda: client.GuardianClient(config, start_if_down=False).alive(), timeout=30, every=0.2)
        assert client.GuardianClient(config).check("chat.reply").verdict is Verdict.ALLOW
    finally:
        autostart.uninstall(config.data_dir)
        try:
            client.quit_guardian(config)
        except channel.ChannelError:
            pass


@pytest.mark.skipif(sys.platform == "win32", reason="checks the message shown on other systems")
def test_without_windows_install_says_it_is_windows_only(config, config_path):
    result = kairu("guardian", "install")
    assert result.returncode == 1 and "Windows" in result.stdout
