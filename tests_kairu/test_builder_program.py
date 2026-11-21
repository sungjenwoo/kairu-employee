"""The Builder (BUILDER.md) through the real Guardian program: a website, a Python program and its tests, a skill Forge
learns and then uses, and Five Paths.

KAIRU_TEST_PC is set, so opening a page or an app is the pretend PC's (kairu/tasks/pc.py), and the free AI is a stand-in on
127.0.0.1 (tests_kairu/fake_provider.py). Every step is decided and run by Guardian; your words never reach its audit log.
"""

import json

import pytest

from kairu import audit
from kairu.build.store import BuilderStore
from kairu.guardian import Verdict
from kairu.store import Store
from tests_kairu.test_day4_program import (Owner, calls, config_path, core_for, desk, logged, providers, runs,  # noqa: F401
                                            work)
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from kairu.brain import keys
from tests_kairu.test_builder import program as python_build
from tests_kairu.test_builder import recipe, site

GROQ_KEY = "gsk_" + "k" * 40


@pytest.fixture
def owner(program_with_pin):
    keys.save(program_with_pin.data_dir, "groq", GROQ_KEY)
    return Owner(program_with_pin)


def ran(program):
    return [row["action"] for row in runs(program.data_dir)]


# --- Builder powers -------------------------------------------------------------------------------------------------

def test_a_website_is_drafted_shown_made_in_a_new_folder_and_opened(program_with_pin, owner, providers, work, desk):
    from tests_kairu.test_builder import as_blocks
    providers.script["groq"] = [as_blocks(site())]  # the form the AI is asked for
    reply = core_for(program_with_pin, owner).handle("build a website for Fresh Bakes, a bakery in Hyderabad")
    assert reply == "Made fresh-bakes in your work folder: index.html, style.css, script.js. Opened fresh-bakes/index.html."
    [shown] = owner.confirmed
    assert shown.startswith("A website in a new folder fresh-bakes: index.html (") and shown.endswith('"yes" to make it in your work folder.')
    assert (work / "fresh-bakes" / "script.js").read_text() == site()["files"][2]["text"] + "\n"
    assert "open file index.html" in calls(desk) and owner.cards == []
    assert ran(program_with_pin)[-3:] == ["build.draft", "build.write", "files.open"]
    asked = providers.heard("groq")[0]["body"]
    assert "Website brief: build a website for Fresh Bakes" in asked["messages"][1]["content"]
    everything = logged(program_with_pin.data_dir)
    assert "Fresh Bakes" not in everything and "fresh-bakes" not in everything and audit.verify(Store(program_with_pin.data_dir)).ok


def test_without_your_yes_nothing_is_written(program_with_pin, owner, providers, work):
    providers.script["groq"] = [json.dumps(site())]
    owner.yes = False
    assert core_for(program_with_pin, owner).handle("make a website for Fresh Bakes") == \
        "Not made: you didn't say yes. Nothing was written."
    assert list(work.iterdir()) == [] and "build.write" not in ran(program_with_pin)


def test_a_build_that_would_reach_the_network_is_never_shown_or_made(program_with_pin, owner, providers, work):
    files = site()["files"]
    files[2] = {"name": "script.js", "text": "fetch('https://example.com/track')"}
    providers.script["groq"] = [json.dumps(site(files=files))]
    reply = core_for(program_with_pin, owner).handle("build a website for Fresh Bakes")
    assert reply.startswith("The build didn't come out right (script.js would reach the network")
    assert owner.confirmed == [] and list(work.iterdir()) == []


def test_a_python_program_is_made_and_its_tests_run_only_with_your_pin(program_with_pin, owner, providers, work):
    providers.script["groq"] = [json.dumps(python_build())]
    reply = core_for(program_with_pin, owner).handle("build a python app that converts temperatures")
    assert reply == ("Made temperature-converter in your work folder: convert.py, test_convert.py. "
                     "(pretend PC) Would run the tests in temperature-converter with unittest.")
    [card] = owner.cards
    assert card.verdict is Verdict.NEEDS_APPROVAL and card.tier == "High" and card.action.name == "build.test"
    owner.yes = False
    assert core_for(program_with_pin, owner).handle("test temperature-converter") == "Not done: you refused it."


def test_refusing_the_tests_pin_still_keeps_the_files_and_says_how_to_test(program_with_pin, owner, providers, work):
    providers.script["groq"] = [json.dumps(python_build())]
    owner.approver = lambda decision: owner.cards.append(decision)  # the card is shown, and you say no
    reply = core_for(program_with_pin, owner).handle("build a python app that converts temperatures")
    assert reply.endswith('Not tested yet: it is code an AI wrote, so its tests run only with your PIN. Say "test temperature-converter".')
    assert (work / "temperature-converter" / "convert.py").exists()


def test_the_builder_works_only_at_main_kairus_own_pc(program_with_pin, owner, providers):
    from kairu.tasks.core import TaskCore
    phone = TaskCore(program_with_pin.config, program_with_pin.client, source="dev-" + "1" * 16)
    assert phone.handle("build a website for Fresh Bakes") == "The Builder works at Main Kairu's own PC."
    assert providers.heard() == []


# --- Forge --------------------------------------------------------------------------------------------------------

def test_forge_learns_a_skill_after_five_dry_runs_and_your_pin_then_uses_it(program_with_pin, owner, providers, work, desk):
    providers.script["groq"] = [json.dumps(recipe())]
    core = core_for(program_with_pin, owner)
    reply = core.handle("learn to make a study folder for physics")
    assert reply.startswith('Forge wrote "make a study folder" for "make a study folder for {subject}": 1) make {subject}-plan.md (Medium)')
    assert "Dry runs on a stand-in laptop: 5 of 5 passed." in reply
    assert reply.endswith('Learned "make a study folder". Say, for example: make a study folder for physics.')
    [card] = owner.plans
    assert card.endswith("Keep this skill?") and owner.cards[0].action.name == "forge.save" and owner.cards[0].tier == "High"
    assert list(work.iterdir()) == [] and calls(desk) == []  # the dry runs touched only the stand-in laptop
    assert ran(program_with_pin)[-3:] == ["forge.draft", "forge.test", "forge.save"]

    used = core.handle("make a study folder for biology")
    assert used.startswith('Using the skill "make a study folder". ') and owner.confirmed[-1].startswith("Plan: 1) make biology-plan.md")
    assert (work / "biology" / "biology-plan.md").read_text().startswith("Study plan for biology")
    assert any(line.startswith("browse") and "biology" in line for line in calls(desk))
    assert core.handle("what skills have you learned") == \
        'Skills I learned (1): make a study folder ("make a study folder for {subject}").'
    assert core.handle("forget the skill make a study folder") == 'Forgot the skill "make a study folder".'
    assert BuilderStore(program_with_pin.data_dir).skills() == []


def test_forge_drops_a_recipe_with_two_pin_steps_before_any_dry_run(program_with_pin, owner, providers):
    deleting = recipe(steps=[{"action": "files.delete", "details": {"name": "{subject}.txt"}},
                             {"action": "files.delete", "details": {"name": "{subject}-old.txt"}}])
    providers.script["groq"] = [json.dumps(deleting)]
    reply = core_for(program_with_pin, owner).handle("learn to make a study folder for physics")
    assert reply == "Forge dropped it: it has 2 steps that need your PIN, and a plan may have only one. Nothing was kept."
    assert "forge.test" not in ran(program_with_pin) and owner.cards == []


def test_without_your_pin_forge_keeps_nothing(program_with_pin, owner, providers):
    providers.script["groq"] = [json.dumps(recipe())]
    owner.yes = False
    reply = core_for(program_with_pin, owner).handle("forge a skill for making a study folder")
    assert reply.endswith("Not kept: you refused it.") and BuilderStore(program_with_pin.data_dir).skills() == []


def test_forge_it_means_the_last_order_kairu_couldnt_do(program_with_pin, owner, providers):
    from kairu.tasks.core import CANT
    core = core_for(program_with_pin, owner)
    assert core.handle("forge it") == "Which order should I learn? Say: learn to, then the order."
    assert core.handle("tidy my desktop") == CANT
    providers.script["groq"] = [json.dumps(recipe())]
    core.handle("forge it")
    assert "Order to learn: tidy my desktop" in providers.heard("groq")[-1]["body"]["messages"][1]["content"]


# --- Five Paths -------------------------------------------------------------------------------------------------------

def plan(*steps):
    return json.dumps({"steps": [{"action": action, "details": details} for action, details in steps]})


def test_five_paths_drop_what_breaks_the_rules_rank_the_rest_and_run_only_your_pick(program_with_pin, owner, providers, work,
                                                                                    desk):
    (work / "a.pdf").write_text("a")
    providers.script["groq"] = [
        plan(("files.move", {"name": "*.pdf", "to": "pdfs"})),  # Fast
        plan(("files.find", {"what": "*.pdf", "when": ""}), ("files.move", {"name": "*.pdf", "to": "pdfs"})),  # Careful
        "I am not sure.",  # Simple: no plan
        plan(("files.delete", {"name": "a.pdf"}), ("files.delete", {"name": "b.pdf"})),  # Creative: two PIN steps
        plan(("files.move", {"name": "../*.pdf", "to": "pdfs"})),  # Thorough: outside the work folder
        json.dumps({"done": "every pdf is in a folder called pdfs", "scores": [
            {"path": 1, "score": 6, "why": "Quick, but doesn't look first."},
            {"path": 2, "score": 9, "why": "Looks first, then moves."},
            {"path": 4, "score": 8, "why": "Bold."}, {"path": 5, "score": 7, "why": "Wide."}]}),
    ]
    core = core_for(program_with_pin, owner)
    reply = core.handle("try five ways to put my pdfs in one folder")
    lines = reply.split("\n")
    assert lines[0] == "Five Paths for: put my pdfs in one folder. Done when: every pdf is in a folder called pdfs."
    assert lines[1].startswith("Path 2 BEST (Careful, 9/10): Looks first, then moves. Steps: find *.pdf in your work folder (Low)")
    assert lines[2].startswith("Path 1 (Fast, 6/10)")
    assert "Simple (the AI's answer wasn't a plan)" in lines[3] and "Creative (it has 2 steps that need your PIN" in lines[3]
    assert "Thorough (step 1 (files.move): Refused:" in lines[3]
    assert lines[4] == 'Say "run path 2" for the best one, or another number. Only the one you pick runs.'
    assert "files.move" not in ran(program_with_pin) and (work / "a.pdf").exists()
    assert core.handle("run path 4").startswith("Path 4 didn't pass the rule checks")
    picked = core.handle("run the best path")
    assert picked.startswith("Path 2 (Careful): ") and (work / "pdfs" / "a.pdf").exists()
    assert owner.confirmed[-1].startswith("Plan: 1) find *.pdf in your work folder (Low); 2) move *.pdf into pdfs (Medium).")
    assert ran(program_with_pin)[-3:] == ["task.plan", "files.find", "files.move"]


def test_without_a_judge_the_paths_are_ranked_by_rules_and_said_so(program_with_pin, owner, providers, work):
    providers.script["groq"] = [plan(("files.find", {"what": "pdfs", "when": ""}))] * 5 + ["not json"]
    reply = core_for(program_with_pin, owner).handle("try 5 ways to find my pdfs")
    assert "judged by rules: fewer steps first (the judge didn't answer)" in reply and reply.count("\nPath ") == 1
    assert "Not shown: Careful (the same steps as path 1); Simple (the same steps as path 1)" in reply
    later = providers.heard("groq")[1]["body"]["messages"][0]["content"]
    assert "The other paths already planned:\nFast: find pdfs in your work folder" in later and "clearly different" in later


def test_a_second_build_with_the_same_name_gets_a_free_folder_and_the_first_is_untouched(program_with_pin, owner, providers, work):
    from tests_kairu.test_builder import as_blocks
    (work / "fresh-bakes").mkdir()
    (work / "fresh-bakes" / "index.html").write_text("mine")
    providers.script["groq"] = [as_blocks(site())]
    reply = core_for(program_with_pin, owner).handle("build a website for Fresh Bakes")
    assert reply.startswith("Made fresh-bakes-2 in your work folder") and "fresh-bakes-2:" in owner.confirmed[0]
    assert (work / "fresh-bakes" / "index.html").read_text() == "mine"
