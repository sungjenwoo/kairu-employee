"""An action's own refusal ends as "refused" in Guardian's audit log and in run_status, not as a normal finish.

Found in the Sprint Day 1 gate (6 Nov 2026): a rename the fence refused was recorded as "finished".
"""

import pytest

from kairu import audit


@pytest.mark.parametrize("target,outcome,code", [("tests_kairu.actions:refuses", "refused", 3),
                                                 ("tests_kairu.actions:fails", "failed", 1),
                                                 ("tests_kairu.actions:says_nothing", "finished", 0)])
def test_how_an_action_ends_is_what_the_audit_log_says(guardian, runner, target, outcome, code):
    run = runner.run("demo.count", target)
    assert run.wait(30) == outcome
    run.recorded.wait(10)
    [row] = [row for row in audit.tail(guardian.store, 20, kind="run") if row["decision"] != "started"]
    assert row["decision"] == outcome and row["details"]["exit_code"] == code


def test_only_the_workers_own_mark_is_a_refusal():
    """A function that happens to return 3, or a look-alike object, is a normal finish: only REFUSED itself counts."""
    from kairu import worker
    assert worker.main(["tests_kairu.actions:says_nothing"]) == 0
    assert worker.main(["tests_kairu.actions:refuses"]) == worker.REFUSED_EXIT == 3
    assert worker.main(["tests_kairu.actions:fails"]) == worker.FAILED_EXIT == 1
