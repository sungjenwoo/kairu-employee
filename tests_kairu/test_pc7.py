"""PC7 (BAR.md "When a plan is cut off"): a plan cut off by a stop or a Guardian restart leaves nothing half-done, says what
was and wasn't done, and goes on only after your yes again, each step decided by Guardian again. Also PC6's plans with a
command (PC5) and the RAM check (`kairu doctor`).
"""

import json
import time

import pytest

from kairu import safemode
from kairu.store import Store
from kairu.tasks import core as core_module
from kairu.tasks.core import Step
from kairu.tasks.journal import PlanJournal, cut_off_note
from tests_kairu.helpers import PIN, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_day4_program import (calls, config_path, core_for, desk, owner, providers,  # noqa: F401 (fixtures)
                                           work)

VOLUMES = json.dumps({"steps": [{"action": "system.volume", "details": {"setting": "30"}},
                                {"action": "system.volume", "details": {"setting": "40"}},
                                {"action": "system.volume", "details": {"setting": "50"}}]})


def test_the_journal_keeps_steps_and_how_many_are_done_and_empties_without_deleting(tmp_path):
    journal = PlanJournal(tmp_path)
    steps = (Step("system.volume", {"setting": "30"}), Step("apps.open", {"name": "notepad"}))
    journal.start(steps, core_module.label)
    journal.step_done(1)
    data = journal.read()
    assert data["done"] == 1 and [s["action"] for s in data["steps"]] == ["system.volume", "apps.open"]
    note = cut_off_note(data)
    assert "after 1 of 2 steps" in note and "go on with the plan" in note
    journal.clear()
    assert journal.read() is None and journal.path.exists()  # emptied, never deleted
    journal.path.write_text("not json")
    assert journal.read() is None


def resume(program):
    program.client.resume("yes", PIN)
    wait_for(lambda: program.client.status()["mode"] != "safe", timeout=5)
    time.sleep(1.2)  # the stop's own watcher lets go of the halt flag within a second


def stopping_after(program, core, steps_done):
    """A stop right after the plan's steps_done-th step (the first _run_step keeps the plan in Guardian's log: task.plan)."""
    real, count = core._run_step, [-1]

    def then_stop(step, job=None, granted=None):
        done = real(step, job, granted)
        count[0] += 1
        if count[0] == steps_done:
            safemode.emergency_stop(Store(program.data_dir), "test")
            wait_for(lambda: program.client.status()["mode"] == "safe", timeout=5)
        return done
    core._run_step = then_stop
    return real


def test_a_plan_cut_off_by_a_stop_is_kept_then_goes_on_only_after_yes(program_with_pin, owner, providers, desk):
    providers.answers["groq"] = VOLUMES
    core = core_for(program_with_pin, owner)
    real = stopping_after(program_with_pin, core, 1)
    reply = core.handle("set the volume to thirty, then forty, then fifty, step by step")
    assert "Stopped" in reply and "go on with the plan" in reply
    assert calls(desk) == ["volume 30 None"]
    kept = PlanJournal(program_with_pin.config.data_dir).read()
    assert kept["done"] == 1 and len(kept["steps"]) == 3
    core._run_step = real
    resume(program_with_pin)
    owner.confirmed.clear()
    reply = core.handle("go on with the plan")
    assert len(owner.confirmed) == 1 and "40" in owner.confirmed[0] and "30" not in owner.confirmed[0]  # only the rest, shown
    assert calls(desk) == ["volume 30 None", "volume 40 None", "volume 50 None"]
    assert PlanJournal(program_with_pin.config.data_dir).read() is None
    assert core.handle("go on with the plan") == "There's no plan waiting."


def test_saying_no_to_the_rest_runs_none_of_it(program_with_pin, owner, providers, desk):
    providers.answers["groq"] = VOLUMES
    core = core_for(program_with_pin, owner)
    real = stopping_after(program_with_pin, core, 1)
    core.handle("set the volume to thirty, then forty, then fifty, step by step")
    core._run_step = real
    resume(program_with_pin)
    owner.yes = False
    assert "Nothing ran" in core.handle("continue the plan")
    assert calls(desk) == ["volume 30 None"]


def test_forget_the_plan_and_the_note_on_the_next_order(program_with_pin, owner, providers, desk):
    providers.answers["groq"] = VOLUMES
    core = core_for(program_with_pin, owner)
    real = stopping_after(program_with_pin, core, 2)
    core.handle("set the volume to thirty, then forty, then fifty, step by step")
    core._run_step = real
    resume(program_with_pin)
    fresh = core_for(program_with_pin, owner)  # as after the bar started again
    first = fresh.handle("what's open?")
    assert first.startswith("Open: notepad") and "cut off after 2 of 3 steps" in first
    assert "cut off" not in fresh.handle("what's open?")  # said once
    assert fresh.handle("forget the plan").startswith("Forgotten")
    assert fresh.handle("go on with the plan") == "There's no plan waiting."
    assert calls(desk) == ["volume 30 None", "volume 40 None"]


def test_a_journal_naming_a_skill_plans_may_not_use_is_forgotten_not_run(program_with_pin, owner, desk):
    journal = PlanJournal(program_with_pin.config.data_dir)
    journal.start((Step("system.volume", {"setting": "30"}), Step("system.restart", {})), core_module.label)
    journal.step_done(1)
    reply = core_for(program_with_pin, owner).handle("go on with the plan")
    assert "can't go on" in reply and owner.cards == [] and calls(desk) == []


def test_a_plan_may_hold_a_command_and_its_tier_comes_from_the_command():
    step = core_module._terminal_checked(Step("terminal.run", {"command": "git push --force", "folder": ""}))
    assert step.action == "terminal.run_any"  # a plan can't make a High command Low
    from kairu.tasks import plan
    assert plan.parse(json.dumps({"steps": [{"action": "terminal.run", "details": {"command": "git status"}}]}),
                      {"terminal.run"}) == [("terminal.run", {"command": "git status", "folder": ""})]


def test_the_doctor_reads_only_and_says_guardian_memory_and_a_waiting_plan(tmp_path):
    from types import SimpleNamespace

    from kairu import doctor
    cfg = SimpleNamespace(data_dir=tmp_path)
    PlanJournal(tmp_path).start((Step("system.volume", {"setting": "30"}),), core_module.label)
    lines = doctor.report(cfg, status={"mode": "normal"})
    assert lines[0] == "Guardian: running, normal." and any("Kairu uses" in line for line in lines)
    assert any("cut-off plan is waiting" in line for line in lines)
    assert doctor.report(cfg, status={"error": "ChannelError"})[0].startswith("Guardian: not running")
    if doctor.free_memory():
        assert any(line.startswith("This PC:") for line in lines)


def test_write_a_list_in_notepad_asks_the_brain_for_the_words_not_types_the_description():
    from kairu.tasks import skills
    task = core_module.understand("open notepad and write a short to-do list for the hackathon, then set the volume to 30",
                                  skills.SKILLS)
    assert task.plan and not task.steps  # a plan: shown first, run after yes
    plain = core_module.understand('type hello team in notepad', skills.SKILLS)
    assert plain.steps and plain.steps[0].details["text"] == "hello team"  # plain words are still typed as they are


def test_a_plan_that_would_type_a_list_makes_a_file_and_opens_it_instead():
    from kairu.tasks import plan
    usable = {"apps.open", "screen.type", "files.write", "files.open", "system.volume"}
    answer = json.dumps({"steps": [
        {"action": "apps.open", "details": {"name": "notepad"}},
        {"action": "screen.type", "details": {"app": "notepad", "text": "Hackathon to-do:\n1. Test the demo\n2. Charge the laptop",
                                              "field": "", "enter": "no"}},
        {"action": "system.volume", "details": {"setting": "30"}}]})
    steps = plan.parse(answer, usable)
    assert [a for a, _ in steps] == ["apps.open", "files.write", "files.open", "system.volume"]
    assert steps[1][1]["text"] == "Hackathon to-do:\\n1. Test the demo\\n2. Charge the laptop"  # files.write makes the lines
    assert steps[2][1]["name"] == steps[1][1]["name"] and steps[1][1]["name"].endswith(".txt")
    short = json.dumps({"steps": [{"action": "screen.type", "details": {"app": "notepad", "text": "hello team"}}]})
    assert plan.parse(short, usable)[0][0] == "screen.type"  # one short line is still typed


def test_a_number_written_as_a_number_is_fine_where_a_number_is_meant_but_never_for_a_name():
    from kairu.tasks import plan
    usable = {"system.volume", "task.wait", "files.move", "screen.type"}
    steps = plan.parse(json.dumps({"steps": [{"action": "system.volume", "details": {"setting": 30}},
                                             {"action": "task.wait", "details": {"seconds": 10}},
                                             {"action": "screen.type", "details": {"app": "notepad", "text": "hi", "enter": False}}]}),
                       usable)
    assert steps[0][1] == {"setting": "30"} and steps[1][1] == {"seconds": "10"} and steps[2][1]["enter"] == "no"
    with pytest.raises(plan.NoPlan, match="isn't short text"):
        plan.parse(json.dumps({"steps": [{"action": "files.move", "details": {"name": 5, "to": "b"}}]}), usable)


def test_a_task_of_known_steps_cut_off_by_a_stop_is_kept_too(program_with_pin, owner, desk):
    core = core_for(program_with_pin, owner)
    real, count = core._run_step, [0]

    def then_stop(step, job=None, granted=None):
        done = real(step, job, granted)
        count[0] += 1
        if count[0] == 1:
            safemode.emergency_stop(Store(program_with_pin.data_dir), "test")
            wait_for(lambda: program_with_pin.client.status()["mode"] == "safe", timeout=5)
        return done
    core._run_step = then_stop
    reply = core.handle("set the volume to 20, then set the volume to 50")
    assert "Stopped" in reply and "go on with the plan" in reply and calls(desk) == ["volume 20 None"]
    core._run_step = real
    resume(program_with_pin)
    owner.confirmed.clear()
    core.handle("go on with the plan")
    assert len(owner.confirmed) == 1 and calls(desk) == ["volume 20 None", "volume 50 None"]
