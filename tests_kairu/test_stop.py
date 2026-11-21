"""Emergency stop: every running action halted within 1 second, then Safe Mode (read-only) until you resume."""

import subprocess
import sys
import time

import pytest

from kairu import audit, hotkey, safemode
from kairu.config import ROOT
from kairu.guardian import Action, Refused, Verdict
from kairu.runner import Runner
from tests_kairu.helpers import PIN, heartbeat_stopped, kairu, wait_for

LIMIT = 1.0  # seconds


def start_actions(runner, tmp_path, count=3):
    """Start `count` long actions (the last one ignores the request to end) and wait until all are running."""
    runs, beats = [], []
    for i in range(count):
        beat = tmp_path / f"beat{i}"
        target = "tests_kairu.actions:stubborn" if i == count - 1 else "kairu.demo:count"
        runs.append(runner.run("demo.count", target, seconds=60, heartbeat=str(beat), quiet=True))
        beats.append(beat)
    wait_for(lambda: all(beat.exists() for beat in beats))
    return runs, beats


def assert_all_halted(runs, beats):
    assert [run.outcome for run in runs] == ["halted"] * len(runs)
    assert all(run.process.poll() is not None for run in runs)  # the processes are gone
    assert all(heartbeat_stopped(beat) for beat in beats)  # and nothing they did continues


def test_stop_halts_every_running_action_within_1_second(guardian, runner, tmp_path):
    runs, beats = start_actions(runner, tmp_path)
    started = time.monotonic()
    runner.stop("test")
    for run in runs:
        run.wait(LIMIT)
    elapsed = time.monotonic() - started
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_all_halted(runs, beats)
    print(f"\n  in-process stop: {len(runs)} actions halted in {elapsed:.3f} s")


def test_kairu_stop_in_another_terminal_halts_them_within_1_second(guardian, runner, tmp_path):
    runs, beats = start_actions(runner, tmp_path)
    started = time.monotonic()  # includes starting Python for `kairu stop`
    stopper = subprocess.Popen([sys.executable, "-m", "kairu", "stop"], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    for run in runs:
        run.wait(LIMIT)
    elapsed = time.monotonic() - started
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_all_halted(runs, beats)
    assert "Emergency stop sent" in stopper.communicate(timeout=10)[0]
    print(f"\n  `kairu stop` from another process: {len(runs)} actions halted in {elapsed:.3f} s")


def test_kairu_stop_halts_kairu_demo_running_in_another_process(guardian, config_path):
    demo = subprocess.Popen([sys.executable, "-m", "kairu", "demo", "--seconds", "60"], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_for(lambda: audit.tail(guardian.store, 1, kind="run") and audit.tail(guardian.store, 1, kind="run")[0]["decision"] == "started")
        result = kairu("stop")
        output = demo.communicate(timeout=10)[0]
    finally:
        demo.kill()
    assert result.returncode == 0 and demo.returncode == 0
    assert "Halted" in output
    halted = audit.tail(guardian.store, 1, kind="run")[0]
    assert halted["decision"] == "halted" and halted["details"]["seconds_since_stop"] < LIMIT
    print(f"\n  `kairu stop` -> `kairu demo`: halted {halted['details']['seconds_since_stop']:.3f} s after the stop was written")


def test_the_hotkey_handler_halts_everything_within_1_second(guardian, runner, tmp_path):
    runs, beats = start_actions(runner, tmp_path)
    key = hotkey.Hotkey(lambda: runner.stop(hotkey.NAME))
    started = time.monotonic()
    key.on_press()  # what Windows calls when Ctrl+Alt+K is pressed; the real key is tested on Windows below
    for run in runs:
        run.wait(LIMIT)
    elapsed = time.monotonic() - started
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_all_halted(runs, beats)
    assert "Ctrl+Alt+K" in safemode.reason(guardian.store)


@pytest.mark.skipif(sys.platform != "win32", reason="Ctrl+Alt+K is a Windows hotkey")
def test_pressing_ctrl_alt_k_on_windows_halts_everything_within_1_second(guardian, runner, tmp_path):
    import ctypes
    runs, beats = start_actions(runner, tmp_path)
    key = hotkey.Hotkey(lambda: runner.stop(hotkey.NAME))
    assert key.start(), key.error
    try:
        user32, started = ctypes.WinDLL("user32"), time.monotonic()
        for vk in (0x11, 0x12, hotkey.VK_K):  # Ctrl, Alt, K down, then up
            user32.keybd_event(vk, 0, 0, 0)
        for vk in (hotkey.VK_K, 0x12, 0x11):
            user32.keybd_event(vk, 0, 2, 0)
        for run in runs:
            run.wait(LIMIT)
        elapsed = time.monotonic() - started
    finally:
        key.close()
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_all_halted(runs, beats)


@pytest.mark.skipif(sys.platform == "win32", reason="checks the message shown on other systems")
def test_without_windows_the_hotkey_says_to_use_kairu_stop():
    key = hotkey.Hotkey(lambda: None)
    assert key.start() is False and "kairu stop" in key.error


def test_after_a_stop_kairu_is_read_only_until_you_resume(guardian, runner, with_pin):
    runner.stop("test")
    assert safemode.is_safe(guardian.store)
    assert guardian.check("files.read").verdict is Verdict.ALLOW  # read-only still works
    assert guardian.check("chat.reply").verdict is Verdict.ALLOW
    for name in ("files.write", "demo.count", "files.delete"):  # changes, including High tier, do not
        decision = guardian.check(Action(name))
        assert decision.verdict is Verdict.DENY and "Safe Mode" in decision.reason
    with pytest.raises(Refused, match="Safe Mode"):
        runner.run("demo.count", "kairu.demo:count", seconds=0)

    with pytest.raises(Refused, match='did not type "yes"'):
        guardian.resume("no", PIN)
    with pytest.raises(Refused, match="wrong PIN"):
        guardian.resume("yes", "000000")
    assert safemode.is_safe(guardian.store)
    guardian.resume("yes", PIN)
    assert not safemode.is_safe(guardian.store)
    assert guardian.check("files.write").verdict is Verdict.ALLOW


def test_a_stop_while_waiting_for_approval_cancels_the_approval(guardian, with_pin):
    decision = guardian.check(Action("message.send", {"to": "bank"}))
    guardian.emergency_stop("test")
    with pytest.raises(Refused, match="Safe Mode"):
        guardian.approve(decision.request_id, "yes", PIN)


def test_an_approved_action_cannot_start_after_a_stop(guardian, runner, with_pin):
    action = Action("message.send", {"to": "bank"})
    granted = guardian.approve(guardian.check(action).request_id, "yes", PIN)
    runner.stop("test")
    with pytest.raises(Refused, match="Safe Mode"):
        runner.run(action, "kairu.demo:count", approval=granted, seconds=0)


def test_the_stop_and_the_halts_are_in_the_audit_log(guardian, runner, tmp_path):
    runs, _ = start_actions(runner, tmp_path, count=2)
    runner.stop("test")
    for run in runs:
        run.wait(LIMIT)
        assert run.recorded.wait(10)  # the rows are written just after the programs are gone
    rows = audit.tail(guardian.store, 10)
    kinds = [(row["kind"], row["decision"]) for row in rows]
    assert ("emergency_stop", "stopped") in kinds
    assert kinds.count(("run", "halted")) == 2
    assert all(row["details"]["seconds_since_stop"] < LIMIT for row in rows if row["decision"] == "halted")


# --- nothing that follows a run's end can keep a stop waiting ---------------------------------------

def test_a_stop_is_not_kept_waiting_by_the_work_after_another_action_ended(guardian, tmp_path):
    """Found while checking a CI flake: the watcher itself did this work, so a stop waited behind it."""
    busy = []

    def on_end(run):
        if run.action == "chat.reply":
            busy.append(True)
            time.sleep(1.5)  # far longer than a stop may take

    runner = Runner(guardian, on_end=on_end)
    try:
        runs, beats = start_actions(runner, tmp_path)
        runner.run("chat.reply", "kairu.demo:count", seconds=0.1, quiet=True)  # ends by itself
        wait_for(lambda: busy, timeout=30)
        started = time.monotonic()
        runner.stop("test")
        for run in runs:
            run.wait(LIMIT)
        elapsed = time.monotonic() - started
        assert elapsed < LIMIT, f"took {elapsed:.3f} s"
        assert_all_halted(runs, beats)
        print(f"\n  stop while the work after another action runs: {len(runs)} actions halted in {elapsed:.3f} s")
    finally:
        runner.close()


def test_a_slow_disk_neither_delays_a_stop_nor_changes_the_time_it_records(guardian, runner, tmp_path, monkeypatch):
    """The other half of that flake: seconds_since_stop was taken while the rows were being written."""
    real = audit.record

    def slow(store, kind, action=None, decision=None, db=None, **details):
        if decision == "halted":
            time.sleep(0.6)  # a disk that stalls on each of these rows
        return real(store, kind, action, decision, db, **details)

    runs, beats = start_actions(runner, tmp_path)
    monkeypatch.setattr(audit, "record", slow)
    started = time.monotonic()
    runner.stop("test")
    for run in runs:
        run.wait(LIMIT)
    elapsed = time.monotonic() - started
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_all_halted(runs, beats)
    assert all(run.recorded.wait(10) for run in runs)
    recorded = [row["details"]["seconds_since_stop"] for row in audit.tail(guardian.store, 10) if row["decision"] == "halted"]
    assert len(recorded) == len(runs) and all(0 <= seconds < LIMIT for seconds in recorded), recorded


def test_closing_the_runner_waits_for_the_work_after_the_last_action(guardian, tmp_path):
    """So Mission Mode's lid setting is put back before Guardian ends."""
    finished = []

    def on_end(run):
        time.sleep(0.5)
        finished.append(run.action)

    runner = Runner(guardian, on_end=on_end)
    runs, _ = start_actions(runner, tmp_path, count=1)
    runner.close("test")
    assert finished == ["demo.count"] and runs[0].outcome == "halted" and runs[0].recorded.is_set()
    rows = [row for row in audit.tail(guardian.store, 5, kind="run") if row["decision"] == "halted"]
    assert len(rows) == 1


def test_a_failure_after_one_run_ended_does_not_stop_the_next_run_being_recorded(guardian, tmp_path):
    told = []

    def on_end(run):
        told.append(run.run_id)
        raise RuntimeError("on purpose")

    runner = Runner(guardian, on_end=on_end)
    try:
        for _ in range(2):
            run = runner.run("demo.count", "kairu.demo:count", seconds=0.05, quiet=True)
            assert run.wait(30) == "finished" and run.recorded.wait(10)
    finally:
        runner.close()
    assert told == [1, 2]
    assert [row["decision"] for row in audit.tail(guardian.store, 10, kind="run")].count("finished") == 2
