"""Guardian starts every action itself, runs only its own code for it, and an emergency stop halts it within 1 second."""

import json
import os
import signal
import subprocess
import sys
import time

import pytest

from kairu import audit, channel, executors, safemode
from kairu.config import ROOT
from kairu.executors import Executor
from kairu.guardian import Action, Refused
from kairu.guardian_program import MOST_RUNNING, Service
from kairu.store import Store
from tests_kairu.helpers import PIN, alive, kairu, wait_for
from tests_kairu.program import parent_pid, program, program_with_pin  # noqa: F401 (fixtures)

LIMIT = 1.0  # seconds
LONG = Action("demo.count", {"seconds": 60, "quiet": True})


def rows(program, kind="run"):
    return [(row["action"], row["decision"], row["details"]) for row in audit.tail(Store(program.config.data_dir), 500, kind=kind)]


def finished(program, run_id, timeout=20.0):
    wait_for(lambda: program.client.run_status(run_id)["outcome"] is not None, timeout=timeout, every=0.05)
    return program.client.run_status(run_id)["outcome"]


# --- through the real Guardian program ------------------------------------------------------------

def test_guardian_starts_the_action_itself(program):
    started = program.client.run(LONG)
    assert parent_pid(started["pid"]) == program.pid  # Guardian's own child, in Guardian's Job Object / process group
    assert program.client.run_status(started["run"])["outcome"] is None
    assert [run["pid"] for run in program.client.status()["running"]] == [started["pid"]]
    assert f"demo.count (run {started['run']}, process {started['pid']})" in kairu("status").stdout

    program.client.end(started["run"])  # ending one action is not an emergency stop
    assert program.client.run_status(started["run"])["outcome"] == "halted" and not alive(started["pid"])
    assert program.client.status()["mode"] == "normal"
    assert ("demo.count", "started", {"pid": started["pid"], "run": started["run"], "target": "kairu.demo:count"}) in rows(program)


def test_kairu_stop_halts_every_action_running_inside_guardian_within_1_second(program):
    runs = [program.client.run(LONG) for _ in range(3)]
    started = time.monotonic()  # includes starting Python for `kairu stop`
    stopper = subprocess.Popen([sys.executable, "-m", "kairu", "stop"], cwd=ROOT, stdout=subprocess.DEVNULL)
    wait_for(lambda: not any(alive(run["pid"]) for run in runs), timeout=5, every=0.01)
    elapsed = time.monotonic() - started
    stopper.wait(10)
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    # the programs are gone; Guardian notes their outcome just after (the 1-second limit above is unchanged)
    outcomes = lambda: [program.client.run_status(run["run"])["outcome"] for run in runs]
    wait_for(lambda: None not in outcomes())
    assert outcomes() == ["halted"] * 3
    halts = lambda: [details for action, decision, details in rows(program) if decision == "halted"]
    wait_for(lambda: len(halts()) == 3)  # the rows are written just after the actions end
    assert all(details["seconds_since_stop"] < LIMIT for details in halts())
    print(f"\n  `kairu stop` -> {len(runs)} actions inside Guardian halted in {elapsed:.3f} s")


@pytest.mark.skipif(sys.platform != "win32", reason="Ctrl+Alt+K is a Windows hotkey")
def test_pressing_ctrl_alt_k_halts_kairu_demo_running_inside_guardian_within_1_second(program):
    import ctypes
    from kairu import hotkey
    demo = subprocess.Popen([sys.executable, "-m", "kairu", "demo", "--seconds", "60"], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    try:
        lines = []
        while not lines or "to stop it" not in lines[-1]:  # it holds the key, and Guardian runs the action
            lines.append(demo.stdout.readline())
            assert lines[-1], "".join(lines)
        assert "inside Guardian" in "".join(lines) and f"Press {hotkey.NAME}" in lines[-1], "".join(lines)
        user32 = ctypes.WinDLL("user32")
        for vk in (0x11, 0x12, hotkey.VK_K):  # Ctrl, Alt, K down, then up
            user32.keybd_event(vk, 0, 0, 0)
        for vk in (hotkey.VK_K, 0x12, 0x11):
            user32.keybd_event(vk, 0, 2, 0)
        output = demo.communicate(timeout=10)[0]
    finally:
        demo.kill()
    assert demo.returncode == 0 and "Halted" in output, output
    halts = lambda: [details for action, decision, details in rows(program) if decision == "halted"]
    wait_for(lambda: halts())  # the row is written just after the action ends, as in the `kairu stop` test above
    halted = halts()
    assert len(halted) == 1 and halted[0]["seconds_since_stop"] < LIMIT
    assert hotkey.NAME in program.client.status()["safe_reason"]
    print(f"\n  Ctrl+Alt+K -> `kairu demo` inside Guardian halted {halted[0]['seconds_since_stop']:.3f} s after the stop was written")


def test_after_a_stop_guardian_runs_nothing_until_you_resume(program_with_pin):
    guardian = program_with_pin.client
    assert kairu("stop").returncode == 0
    with pytest.raises(Refused, match="Safe Mode"):
        guardian.run(LONG)
    guardian.resume("yes", PIN)
    assert finished(program_with_pin, guardian.run(Action("demo.count", {"seconds": 0, "quiet": True}))["run"]) == "finished"


def test_guardian_runs_only_its_own_code_with_only_the_details_it_takes(program, tmp_path):
    guardian = program.client
    for name in ("chat.reply", "files.read", "message.send", "credentials.reveal", "system.destroy", "files.shred"):  # files.delete has code since Day 4, files.write since W2
        with pytest.raises(Refused, match="no code"):
            guardian.run(name)
    bait = tmp_path / "bait.txt"  # demo.count's heartbeat would rewrite it; Guardian must not let a request ask for that
    bait.write_text("untouched")
    for details, problem in [({"seconds": 1, "heartbeat": str(bait)}, "takes only"),
                             ({"seconds": 1, "target": "os:system"}, "takes only"),
                             ({"seconds": "1"}, "must be a number"),
                             ({"seconds": True}, "must be a number"),
                             ({"quiet": "yes"}, "must be true or false")]:
        with pytest.raises(Refused, match=problem):
            guardian.run(Action("demo.count", details))
    for message in [{"op": "run", "action": "demo.count", "target": "os:system"},
                    {"op": "run", "action": "demo.count", "details": {"seconds": 1}, "command": "calc.exe"},
                    {"op": "run", "action": "demo.count", "details": {"seconds": 1}, "tier": "Low", "verdict": "allow"},
                    {"op": "run_status", "run": "1"},
                    {"op": "run_status", "run": 0},
                    {"op": "end", "run": True}]:
        assert channel.request(program.data_dir, message)["verdict"] == "deny", message
    assert not [row for row in rows(program) if row[1] == "started"]  # nothing ran
    time.sleep(0.2)
    assert bait.read_text() == "untouched"
    assert program.client.status()["pid"] == program.pid  # and Guardian is still there


def test_quitting_guardian_ends_its_actions(program):
    started = program.client.run(LONG)
    assert kairu("guardian", "quit").returncode == 0
    assert not alive(started["pid"])
    assert ("demo.count", "halted") in [(action, decision) for action, decision, _ in rows(program)]
    assert any(details.get("why") == "Guardian quit" for _, decision, details in rows(program) if decision == "halted")


@pytest.mark.skipif(sys.platform != "win32", reason="on Linux, actions outlive a Guardian that is killed (GUARDIAN.md)")
def test_if_guardian_is_killed_its_actions_end_with_it(program):
    started = program.client.run(LONG)
    time.sleep(0.3)
    assert alive(started["pid"]) and alive(program.pid)
    began = time.monotonic()
    os.kill(program.pid, signal.SIGTERM)  # on Windows: ended at once, no clean-up of its own
    wait_for(lambda: not alive(started["pid"]), timeout=5, every=0.01)
    print(f"\n  Guardian killed -> its action gone in {time.monotonic() - began:.3f} s")


def test_at_most_8_actions_run_at_once(program):
    runs = [program.client.run(LONG) for _ in range(MOST_RUNNING)]
    with pytest.raises(Refused, match="already running"):
        program.client.run(LONG)
    for run in runs:
        program.client.end(run["run"])
    assert not any(alive(run["pid"]) for run in runs)


def test_kairu_demo_starts_guardian_when_needed_and_leaves_none_behind(config, config_path):
    result = kairu("demo", "--seconds", "0.5", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "started it" in result.stdout and "inside Guardian" in result.stdout and "demo.count finished" in result.stdout
    assert "Guardian is not running" in kairu("status").stdout  # the Guardian it started has gone again
    with pytest.raises(channel.NotRunning):
        channel.connect(config.data_dir)


def test_kairu_demo_leaves_a_running_guardian_running(program):
    result = kairu("demo", "--seconds", "0.3", timeout=60)
    assert result.returncode == 0 and "started it" not in result.stdout and "demo.count finished" in result.stdout
    assert program.client.status()["pid"] == program.pid


# --- the same Service in this process, with code listed for actions that have none ----------------

def ask(service, **message) -> dict:
    return service.answer(json.dumps(message).encode())


@pytest.fixture
def service(guardian, monkeypatch):
    def listing(**actions):
        monkeypatch.setattr(executors, "EXECUTORS", actions)
    made = Service(guardian)
    made.listing = listing
    yield made
    made.close()


QUICK = Executor("kairu.demo:count", {"seconds": float, "quiet": bool})


def test_a_high_tier_action_runs_only_with_its_approval_once_and_for_its_exact_details(service, with_pin):
    service.listing(**{"files.delete": QUICK})
    details = {"seconds": 0, "quiet": True}
    refused = ask(service, op="run", action="files.delete", details=details)
    assert refused["verdict"] == "deny" and "not approved" in refused["reason"]

    def approval():
        asked = ask(service, op="check", action="files.delete", details=details)
        return ask(service, op="approve", request_id=asked["request_id"], confirmation="yes", pin=PIN)["approval"]

    token = approval()
    first = ask(service, op="run", action="files.delete", details=details, approval=token)
    assert first["verdict"] == "ok"
    again = ask(service, op="run", action="files.delete", details=details, approval=token)
    assert again["verdict"] == "deny" and "already used" in again["reason"]
    other = ask(service, op="run", action="files.delete", details={"seconds": 1, "quiet": True}, approval=approval())
    assert other["verdict"] == "deny" and "different action or different details" in other["reason"]
    wait_for(lambda: ask(service, op="run_status", run=first["run"])["outcome"] == "finished")


def test_critical_never_runs_even_if_code_were_listed_for_it(service, guardian, with_pin):
    service.listing(**{name: QUICK for name in ("credentials.reveal", "security.disable", "files.delete")})
    asked = ask(service, op="check", action="files.delete", details={})
    high = ask(service, op="approve", request_id=asked["request_id"], confirmation="yes", pin=PIN)["approval"]
    for name in ("credentials.reveal", "security.disable"):
        for offered in (None, "0" * 32, high):
            answer = ask(service, op="run", action=name, details={"seconds": 0}, approval=offered)
            assert answer["verdict"] == "deny" and "Critical" in answer["reason"]
    assert service.runner.running() == []
    assert not [row for row in audit.tail(guardian.store, 200, kind="run") if row["decision"] == "started"]


def test_a_stop_ends_the_whole_family_an_action_started_inside_guardian(service, tmp_path):
    service.listing(**{"demo.count": Executor("tests_kairu.family:action", {"folder": str, "stubborn": bool})})
    started = ask(service, op="run", action="demo.count", details={"folder": str(tmp_path), "stubborn": True})
    assert started["verdict"] == "ok"
    names = ("action", "child", "grandchild")
    wait_for(lambda: all((tmp_path / f"{name}.pid").exists() and (tmp_path / f"{name}.pid").read_text() for name in names))
    pids = [int((tmp_path / f"{name}.pid").read_text()) for name in names]
    began = time.monotonic()
    stopper = subprocess.Popen([sys.executable, "-m", "kairu", "stop"], cwd=ROOT, stdout=subprocess.DEVNULL)
    wait_for(lambda: not any(alive(pid) for pid in pids), timeout=5, every=0.01)
    elapsed = time.monotonic() - began
    stopper.wait(10)
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert safemode.is_safe(service.store)
    print(f"\n  `kairu stop` -> a family that ignores the request to end, inside Guardian, gone in {elapsed:.3f} s")
