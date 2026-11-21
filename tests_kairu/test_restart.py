"""What Guardian keeps on disk is still there after a restart; what must not outlive it is gone."""

import pytest

from kairu import audit, pin, safemode
from kairu.guardian import Guardian, Refused, Verdict
from kairu.runner import Runner
from tests_kairu.helpers import PIN, kairu


def restart(guardian):
    return Guardian(guardian.config)  # a new Guardian on the same data folder, as after closing Kairu


def test_safe_mode_survives_a_restart(guardian):
    guardian.emergency_stop("test")
    again = restart(guardian)
    assert safemode.is_safe(again.store)
    assert again.check("files.write").verdict is Verdict.DENY
    status = kairu("status")  # and in a brand-new process
    assert "Safe Mode (emergency stop (test))" in status.stdout


def test_a_stop_from_kairu_stop_survives_a_restart(guardian):
    assert kairu("stop").returncode == 0
    assert restart(guardian).check("files.write").verdict is Verdict.DENY


def test_resuming_survives_a_restart(guardian, with_pin):
    guardian.emergency_stop("test")
    restart(guardian).resume("yes", PIN)
    assert restart(guardian).check("files.write").verdict is Verdict.ALLOW


def test_the_pin_survives_a_restart(guardian, with_pin):
    again = restart(guardian)
    assert pin.is_set(again.store)
    granted = again.approve(again.check("files.delete").request_id, "yes", PIN)
    assert granted.action == "files.delete"


def test_wrong_pin_count_and_lock_survive_a_restart(guardian, with_pin):
    for _ in range(pin.MAX_FAILURES - 1):
        assert not pin.check(guardian.store, "999999")[0]
    again = restart(guardian)
    assert not pin.check(again.store, "999999")[0]  # the fifth, counted across the restart
    assert safemode.is_safe(again.store)
    assert "too many wrong PINs" in pin.check(restart(guardian).store, PIN)[1]


def test_the_audit_chain_continues_across_restarts(guardian):
    guardian.check("chat.reply")
    for _ in range(3):
        restart(guardian).check("files.read")
    kairu("stop")
    verdict = audit.verify(guardian.store)
    assert verdict.ok and verdict.rows >= 9


def test_an_unanswered_request_does_not_survive_a_restart(guardian, with_pin):
    decision = guardian.check("files.delete")
    with pytest.raises(Refused, match="no such request"):
        restart(guardian).approve(decision.request_id, "yes", PIN)


def test_an_unused_approval_does_not_survive_a_restart(guardian, with_pin):
    granted = guardian.approve(guardian.check("files.delete").request_id, "yes", PIN)
    assert restart(guardian).authorize("files.delete", granted).verdict is Verdict.DENY


def test_a_stop_made_before_the_runner_started_does_not_halt_later_work_twice(guardian, with_pin):
    guardian.emergency_stop("test")
    guardian.resume("yes", PIN)
    runner = Runner(restart(guardian))
    try:
        run = runner.run("demo.count", "kairu.demo:count", seconds=0.3, quiet=True)
        assert run.wait(10) == "finished"
    finally:
        runner.close()
