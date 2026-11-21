"""The stop ends an action's whole family: the action, its child and its grandchild, within 1 second."""

import subprocess
import sys
import time

from kairu.config import ROOT
from tests_kairu.helpers import alive, heartbeat_stopped, wait_for

LIMIT = 1.0  # seconds
FAMILY = ("action", "child", "grandchild")


def start_family(runner, tmp_path, stubborn=False, target="tests_kairu.family:action", running=FAMILY):
    """Start the action and wait until all three programs have started; their process ids."""
    run = runner.run("demo.count", target, folder=str(tmp_path), stubborn=stubborn)
    wait_for(lambda: all((tmp_path / f"{name}.beat").exists() for name in FAMILY), timeout=20)
    pids = {name: int((tmp_path / f"{name}.pid").read_text()) for name in FAMILY}
    assert all(alive(pids[name]) for name in running)
    return run, pids


def time_until_gone(started, run, pids) -> float:
    run.wait(LIMIT)
    wait_for(lambda: not any(alive(pid) for pid in pids.values()), timeout=LIMIT)
    return time.monotonic() - started


def assert_family_gone(tmp_path, pids):
    still = [name for name, pid in pids.items() if alive(pid)]
    assert not still, f"still running: {still}"
    assert all(heartbeat_stopped(tmp_path / f"{name}.beat") for name in FAMILY)


def test_stop_ends_the_action_its_child_and_its_grandchild_within_1_second(runner, tmp_path):
    run, pids = start_family(runner, tmp_path)
    started = time.monotonic()
    runner.stop("test")
    elapsed = time_until_gone(started, run, pids)
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert run.outcome == "halted"
    assert_family_gone(tmp_path, pids)
    print(f"\n  stop -> action, child and grandchild gone in {elapsed:.3f} s")


def test_stop_ends_a_family_that_ignores_the_request_to_end(runner, tmp_path):
    run, pids = start_family(runner, tmp_path, stubborn=True)
    started = time.monotonic()
    runner.stop("test")
    elapsed = time_until_gone(started, run, pids)
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_family_gone(tmp_path, pids)
    print(f"\n  stop -> a family that ignores the request to end gone in {elapsed:.3f} s")


def test_kairu_stop_in_another_terminal_ends_the_whole_family(guardian, runner, tmp_path):
    run, pids = start_family(runner, tmp_path, stubborn=True)
    started = time.monotonic()  # includes starting Python for `kairu stop`
    stopper = subprocess.Popen([sys.executable, "-m", "kairu", "stop"], cwd=ROOT, stdout=subprocess.DEVNULL)
    elapsed = time_until_gone(started, run, pids)
    stopper.wait(10)
    assert elapsed < LIMIT, f"took {elapsed:.3f} s"
    assert_family_gone(tmp_path, pids)
    print(f"\n  `kairu stop` -> whole family gone in {elapsed:.3f} s")


def test_programs_an_action_leaves_running_end_with_it(runner, tmp_path):
    run, pids = start_family(runner, tmp_path, stubborn=True, target="tests_kairu.family:leave_running")
    (tmp_path / "leave").write_text("")  # all three seen running; now the action ends, leaving the other two behind
    assert run.wait(10) == "finished"
    wait_for(lambda: not alive(pids["child"]) and not alive(pids["grandchild"]), timeout=LIMIT)
    assert_family_gone(tmp_path, pids)
