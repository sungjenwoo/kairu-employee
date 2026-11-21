"""The Kairu bar's Sprint Day 4 parts: a plan's card, and typing "stop" while a task runs. Skipped where there is no screen."""

import threading

from kairu import safemode
from kairu.guardian import Action, Decision, Verdict
from kairu.policy import Tier
from kairu.store import Store
from tests_kairu.test_bar import StandInCore, bar, on_a_worker, pump, type_in  # noqa: F401 (bar is a fixture)

PLAN = "Plan: 1) move *.pdf into pdfs (Medium); 2) put old.txt in the Recycle Bin (High)."
DELETE = Decision(Verdict.NEEDS_APPROVAL, Action("files.delete", {"job": "a" * 16, "name": "old.txt"}), Tier.HIGH, "High tier",
                  "Move one file or folder in your work folder to the Recycle Bin", "request-2")


def test_typing_stop_while_a_task_runs_is_the_stop(bar, config):
    go = threading.Event()
    bar.core.handle = lambda order: go.wait(5) and "Done."
    type_in(bar.order_box, "put the pdfs in a folder")
    bar.send()
    assert bar.busy
    type_in(bar.order_box, "Kairu, stop")
    bar.send()
    assert safemode.is_safe(Store(config.data_dir)) and "Stopped everything" in bar.reply_line.cget("text")
    assert bar.order_box.get() == ""
    go.set()
    pump(bar, lambda: not bar.busy)


def test_stop_typed_is_never_sent_to_the_core(bar, config):
    type_in(bar.order_box, "stop")
    bar.send()
    assert bar.core.orders == [] and safemode.is_safe(Store(config.data_dir))


def test_a_plans_card_shows_the_whole_plan_and_asks_once_for_yes_and_the_pin(bar):
    box = on_a_worker(bar, lambda: bar.ask_plan_approval(DELETE, PLAN))
    assert "approval of this plan" in bar.card_heading.cget("text")
    text = bar.card_text.cget("text")
    assert text.startswith(PLAN) and "files.delete" in text and "name: old.txt" in text and "High" in text and "whole plan" in text
    assert bar.pin_box.winfo_ismapped() and bar.yes_box.get() == "" and bar.pin_box.get() == ""
    type_in(bar.yes_box, "yes")
    type_in(bar.pin_box, "482916")
    bar.approve_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["result"].token == "token" and bar.client.approved == [("request-2", "yes", "482916")]


def test_a_plan_with_no_high_step_needs_only_yes(bar):
    box = on_a_worker(bar, lambda: bar.ask_confirmation(PLAN + ' Type "yes" to run it.'))
    assert not bar.pin_box.winfo_ismapped() and PLAN in bar.card_text.cget("text")
    type_in(bar.yes_box, "yes")
    bar.approve_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["result"] is True


def test_the_bar_gives_the_core_its_plan_card(config):
    from tests_kairu.test_bar import make_bar
    made = make_bar(config)
    try:
        assert made.core.plan_approver == made.ask_plan_approval
    finally:
        made.close()
