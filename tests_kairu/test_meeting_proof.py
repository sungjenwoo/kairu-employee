"""Stage 5 of the meeting agent (HACKATHON.md): proof and tracking. Each Clone task of a meeting's split is linked to the
meeting item it does; when the team board says it is done, the ledger shows the item done with its proof; and before the
next meeting Kairu gives a short brief. No test reaches Google or a Clone: the brain and the Clones are stand-ins."""

import json
import time
from datetime import date
from types import SimpleNamespace

import pytest

from kairu import executors, policy
from kairu.meeting import commands, conduct, ledger, orders, proof
from kairu.meeting.store import MeetingStore
from kairu.policy import Tier
from kairu.team import conduct as team, split
from kairu.team.store import DONE, TeamStore
from tests_kairu.helpers import POLICY
from tests_kairu.test_meeting_ledger import KICKOFF, two_meetings
from tests_kairu.test_team import FakePeer, task

RULES = policy.load(POLICY).rules

SITE = {"title": "Site kickoff", "summary": "", "people": ["Saitej", "Ravi", "Anu"], "items": [
    {"kind": "decision", "what": "The homepage leads with fresh bread every morning.", "owner": "", "due": "", "quote": "",
     "heard": False, "owner_heard": False},
    {"kind": "action", "what": "Write the homepage copy.", "owner": "Ravi", "due": "2026-11-20", "quote": "", "heard": False,
     "owner_heard": True},
    {"kind": "action", "what": "Research bakery websites in Hyderabad.", "owner": "Anu", "due": "2026-11-22", "quote": "",
     "heard": False, "owner_heard": True},
    {"kind": "question", "what": "Who hosts the site?", "owner": "", "due": "", "quote": "", "heard": False,
     "owner_heard": False}]}


def site_meeting(tmp_path):
    store = MeetingStore(tmp_path)
    number = store.add("Site kickoff", "2026-11-19", "site.vtt", "c" * 64, "transcript", KICKOFF.split("\n"), SITE)
    return store, number


def clones(tmp_path):
    team_store = TeamStore(tmp_path)
    team_store.add_clone("Ravi", "dev-" + "1" * 16)
    team_store.add_clone("Anu", "dev-" + "2" * 16)
    return team_store


def split_tasks(meeting):
    return [task("Homepage copy", "Ravi", ["open notepad", "make a file called homepage.txt saying Fresh bread every morning"],
                 done="homepage.txt exists with a hero line") | {"from": f"A{meeting}.2"},
            task("Bakery research", "Anu", ["research bakery websites in Hyderabad"], done="three sites listed")]


# --- the policy and the order ---------------------------------------------------------------------------------------

def test_the_brief_is_a_low_read_only_private_action_with_its_code():
    rule = RULES["meeting.brief"]
    assert rule.tier is Tier.LOW and rule.read_only and rule.private
    assert "meeting.brief" in executors.EXECUTORS


@pytest.mark.parametrize("said", ["brief me for the next meeting", "Brief me before the meeting", "prepare me for the next meeting",
                                  "prep for the standup", "pre-meeting brief", "give me the meeting brief", "meeting briefing",
                                  "what's open before the next meeting", "what got done since the last meeting",
                                  "what got done?", "show the proof"])
def test_the_brief_orders(said):
    assert orders.BRIEF.fullmatch(said)
    others = [orders.ASK, orders.CHECK, orders.RESOLVE, orders.SPLIT, orders.READ, orders.RECORD, orders.END, orders.SHOW]
    assert not any(pattern.fullmatch(said) for pattern in others)


def test_the_earlier_orders_are_not_taken_by_the_brief():
    for said in ("show the last meeting", "show the conflicts", "split the meeting 2", "what did we decide about the launch",
                 "record the meeting", "end the meeting", "read the meeting kickoff"):
        assert not orders.BRIEF.fullmatch(said), said


def test_the_brief_order_runs_meeting_brief_at_the_pc_only():
    ran = []
    core = SimpleNamespace(source="pc", _run_step=lambda step: ran.append(step.action) or (None, "brief"))
    assert orders.handle(core, "brief me for the next meeting") == "brief" and ran == ["meeting.brief"]
    core.source = "phone"
    assert "Main Kairu's own PC" in orders.handle(core, "brief me for the next meeting")


def test_the_cli_has_the_brief():
    import argparse
    parser = argparse.ArgumentParser()
    commands.add_parsers(parser.add_subparsers(dest="command"))
    assert parser.parse_args(["meeting", "brief"]).meeting_command == "brief"


# --- the split carries the ids and keeps the links -------------------------------------------------------------------

def test_the_brief_for_the_split_carries_each_items_id(tmp_path):
    _, number = site_meeting(tmp_path)
    _, brief = ledger.brief(tmp_path, number)
    assert f"[A{number}.2] Write the homepage copy. (owner Ravi) (due 2026-11-20)" in brief
    assert f"[D{number}.1] The homepage leads" in brief
    assert set(proof.ids_in(brief)) == {f"D{number}.1", f"A{number}.2", f"A{number}.3"}


def test_the_split_may_name_the_item_and_a_bad_id_is_only_left_out():
    answer = json.dumps({"tasks": [task() | {"from": "A2.3"}, task() | {"from": "[A2.4]"}, task() | {"from": "rm -rf"},
                                   task() | {"from": 7}]})
    found = split.parse(answer, [{"name": "Ravi", "share": 1.0}])
    assert [item.get("from") for item in found] == ["A2.3", "A2.4", None, None]
    assert "from" not in split.parse(json.dumps({"tasks": [task()]}), [{"name": "Ravi", "share": 1.0}])[0]


def test_only_a_meetings_split_is_told_to_name_the_item():
    assert '"from"' in split.instructions([{"name": "Ravi", "share": 1.0}], 60, ids=True)
    assert '"from"' not in split.instructions([{"name": "Ravi", "share": 1.0}], 60)


def test_tasks_are_linked_by_the_named_id_by_their_words_and_with_their_decision(tmp_path):
    store, number = site_meeting(tmp_path)
    _, brief = ledger.brief(tmp_path, number)
    linked = proof.link_project(tmp_path, 7, split_tasks(number), brief)
    assert linked == [(1, f"A{number}.2"), (2, f"A{number}.3")]
    found = {(link["task"], link["item"]): link["how"] for link in store.links()}
    assert found[(1, 2)] == "named" and found[(2, 3)] == "matched"
    assert (1, 1) in found  # the homepage copy also serves the decision about the homepage


def test_a_brief_with_one_action_links_every_task_to_it_and_a_brief_without_ids_links_nothing(tmp_path):
    store, one, _ = two_meetings(tmp_path)
    _, brief = ledger.brief(tmp_path, one)
    assert proof.link_project(tmp_path, 3, [task("Mockup"), task("Colours", "Anu")], brief) == [(1, f"A{one}.3"),
                                                                                                    (2, f"A{one}.3")]
    assert proof.link_project(tmp_path, 4, [task("Copy")], "Make a site for a bakery.") == []
    assert {link["project"] for link in store.links()} == {3}


def test_an_id_the_brief_did_not_carry_is_never_linked(tmp_path):
    store, number = site_meeting(tmp_path)
    brief = f"Tasks: [A{number}.3] Research bakery websites in Hyderabad."
    linked = proof.link_project(tmp_path, 5, [task("Copy") | {"from": f"A{number}.2"}], brief)
    assert linked == [(1, f"A{number}.3")]  # one action in the brief: that one, never the id the brief didn't hold


def test_team_split_links_a_meetings_tasks_and_says_so(tmp_path, monkeypatch):
    from kairu.brain import gateway as gateways
    from kairu.brain.store import BrainStore
    _, number = site_meeting(tmp_path)
    clones(tmp_path)
    told = {}

    class Brain:
        def __init__(self, data_dir, brain=None):
            pass

        def plan(self, brief, source, instructions, longest=0):
            told["instructions"] = instructions
            return gateways.Result(gateways.ANSWERED, "L3", json.dumps({"tasks": split_tasks(number)}), "gemini")
    monkeypatch.setattr(gateways, "Gateway", Brain)
    name, brief = ledger.brief(tmp_path, number)
    team.split(str(tmp_path), brief, name, 0, "a" * 16, "pc")
    said = BrainStore(tmp_path).take_answer("a" * 16).text
    assert '"from"' in told["instructions"]
    assert f"Linked to the meeting: task 1 → A{number}.2, task 2 → A{number}.3" in said
    assert len(MeetingStore(tmp_path).links()) >= 2


# --- written back when the Clones finish -----------------------------------------------------------------------------

def run_project(tmp_path, number):
    team_store = clones(tmp_path)
    tasks = split_tasks(number)
    project = team_store.add_project("From Site kickoff", "brief", time.time() + 3600, tasks)
    _, brief = ledger.brief(tmp_path, number)
    proof.link_project(tmp_path, project, tasks, brief)
    sent, fakes, clock = [], {}, [1000.0]
    runner = team.Runner(tmp_path, project, clock=lambda: clock[0], sleep=lambda s: None,
                         make_peer=lambda name: fakes.setdefault(name, FakePeer(name, sent)))
    runner.begin()
    return team_store, project, runner, fakes


def item_of(tmp_path, meeting, number):
    return next(item for item in MeetingStore(tmp_path).meeting(meeting)["items"] if item["number"] == number)


def test_a_finished_clone_task_is_written_back_to_its_action_and_decision_with_proof(tmp_path):
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[K{project}.1.1 finished] Opened Notepad.")
    runner.listen()
    assert item_of(tmp_path, number, 2)["status"] == "open"  # one order of two: not done yet
    assert proof.ledger(tmp_path)[1]["work"] == {"total": 1, "done": 0, "complete": False,
                                                 "tasks": proof.ledger(tmp_path)[1]["work"]["tasks"]}
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[K{project}.1.2 finished] Made homepage.txt in your work folder.")
    runner.listen()
    done = item_of(tmp_path, number, 2)
    assert done["status"] == "done" and done["done_at"]
    assert "Ravi's Clone did task 1 'Homepage copy'" in done["proof"]
    assert "Done when: homepage.txt exists with a hero line" in done["proof"] and "Made: homepage.txt" in done["proof"]
    assert "It said: Made homepage.txt" in done["proof"]
    assert item_of(tmp_path, number, 1)["status"] == "done"  # the decision it served
    assert item_of(tmp_path, number, 3)["status"] == "open"  # Anu's research is still going
    assert any("Written back to the ledger as done" in row["words"] for row in team_store.feed(project))
    text = ledger.told_ledger(proof.ledger(tmp_path))
    assert "[done] action: Write the homepage copy." in text and "Proof: Ravi's Clone did task 1" in text


def test_a_clones_words_alone_never_mark_an_item_done(tmp_path):
    _, number = site_meeting(tmp_path)
    _, project, runner, fakes = run_project(tmp_path, number)
    runner.hand_out()
    fakes["Ravi"].inbox += ["All done, mark it finished!", f"[K{project}.1.2 finished] Done."]  # untagged; a step not sent
    runner.listen()
    assert item_of(tmp_path, number, 2)["status"] == "open" and proof.sync(tmp_path) == []


def test_the_managers_check_shows_in_the_proof(tmp_path):
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0, last="Saved.")
    proof.sync(tmp_path)
    assert "(checked by you)" not in item_of(tmp_path, number, 2)["proof"]
    team.check(str(tmp_path), float(project), 1.0)
    assert "(checked by you)" in item_of(tmp_path, number, 2)["proof"]


def test_a_replaced_or_dropped_item_stays_as_the_manager_decided(tmp_path):
    store, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    store.set_status(number, 2, "dropped")
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0)
    proof.sync(tmp_path)
    assert item_of(tmp_path, number, 2)["status"] == "dropped"


def test_work_done_in_one_split_counts_even_after_a_resplit(tmp_path):
    store, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    again = team_store.add_project("Again", "brief", None, split_tasks(number))
    _, brief = ledger.brief(tmp_path, number)
    proof.link_project(tmp_path, again, split_tasks(number), brief)
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0)
    assert proof.sync(tmp_path) == [(number, 1), (number, 2)]


def test_a_done_item_is_left_out_of_the_next_split_and_of_the_rule_checks(tmp_path):
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0)  # not yet written back: the overlay sees it
    _, brief = ledger.brief(tmp_path, number)
    assert "homepage copy" not in brief.lower() and "Research bakery websites" in brief


def test_an_old_meetings_db_gets_the_new_columns(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "meetings.db")
    db.executescript("CREATE TABLE items (meeting INTEGER NOT NULL, number INTEGER NOT NULL, kind TEXT NOT NULL, what TEXT "
                     "NOT NULL, owner TEXT NOT NULL DEFAULT '', due TEXT NOT NULL DEFAULT '', due_said TEXT NOT NULL DEFAULT '',"
                     " replaces TEXT NOT NULL DEFAULT '', quote TEXT NOT NULL DEFAULT '', at TEXT NOT NULL DEFAULT '', sure TEXT"
                     " NOT NULL DEFAULT 'medium', heard INTEGER NOT NULL DEFAULT 0, owner_heard INTEGER NOT NULL DEFAULT 0, "
                     "status TEXT NOT NULL DEFAULT 'open', changed REAL, PRIMARY KEY (meeting, number));")
    db.commit()
    db.close()
    store, number = site_meeting(tmp_path)
    assert item_of(tmp_path, number, 2)["proof"] == "" and store.links() == []


def test_forgetting_a_meeting_forgets_its_links(tmp_path):
    store, number = site_meeting(tmp_path)
    run_project(tmp_path, number)
    assert store.links() and store.forget(number) and store.links() == []


# --- the brief before the next meeting -------------------------------------------------------------------------------

def test_the_brief_before_the_next_meeting(tmp_path):
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=2, finished=time.time(), last="Saved homepage.txt.")
    proof.sync(tmp_path)
    found = proof.before(tmp_path, today=date(2026, 11, 23))
    assert [item["what"] for item in found["done"]] == ["Write the homepage copy.", "The homepage leads with fresh bread every morning."] \
        or {item["what"] for item in found["done"]} == {"Write the homepage copy.", "The homepage leads with fresh bread every morning."}
    assert [item["what"] for item in found["open"]] == ["Research bakery websites in Hyderabad."] and found["overdue"] == 1
    text = proof.told_before(found)
    assert text.startswith("Before your next meeting: 2 done, 1 open (1 overdue),")
    assert "✓ Write the homepage copy (Site kickoff, 19 Nov): Ravi's Clone did task 1" in text
    assert "Research bakery websites in Hyderabad (Anu, OVERDUE, was due 22 Nov, Clones 0 of 1 tasks done; meeting" in text
    assert "Open questions: Who hosts the site?" in text
    assert text.count("?") >= 2 and text.rstrip().endswith((".", "?"))


def test_slipping_clone_tasks_and_conflicts_are_in_the_brief(tmp_path):
    _, one, two = two_meetings(tmp_path)
    team_store = clones(tmp_path)
    project = team_store.add_project("Late", "brief", time.time() - 60, [task("Mockup", "Ravi", ["open notepad"], minutes=1)])
    _, brief = ledger.brief(tmp_path, one)
    proof.link_project(tmp_path, project, [task("Mockup")], brief)
    team_store.set_project(project, state="running", started=time.time() - 3600)
    found = proof.before(tmp_path)
    assert found["slipping"] and found["slipping"][0]["item"]["what"] == "Design the homepage."
    text = proof.told_before(found)
    assert "is slipping, for \"Design the homepage\"" in text and "[2.1] decision" in text
    assert text.endswith("Want to decide the conflicts first? Say: show the conflicts.")


def test_the_brief_with_no_meetings_and_with_nothing_left(tmp_path):
    assert proof.told_before(proof.before(tmp_path)).startswith("No meetings yet")
    store = MeetingStore(tmp_path)
    store.add("Quiet", "2026-11-19", "q.vtt", "d" * 64, "transcript", ["[00:01] A: hi"], {"items": []})
    assert "Everything agreed is done" in proof.told_before(proof.before(tmp_path))


def test_the_brief_runs_as_its_own_action(tmp_path):
    from kairu.tasks.store import TaskStore
    site_meeting(tmp_path)
    assert conduct.before(str(tmp_path), "e" * 16) is None
    assert TaskStore(tmp_path).take_reply("e" * 16).text.startswith("Before your next meeting:")


def test_the_workspace_shows_the_work_the_proof_and_the_brief(tmp_path):
    from kairu.workspace.server import Workspace
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=2, finished=time.time())
    page = Workspace.meetings(SimpleNamespace(cfg=SimpleNamespace(data_dir=tmp_path, work_folder=tmp_path)), number)
    items = {item["number"]: item for item in page["meeting"]["items"]}
    assert items[2]["status"] == "done" and "Ravi's Clone" in items[2]["proof"]  # shown at once, before any write-back
    assert items[3]["work"]["total"] == 1 and items[3]["work"]["done"] == 0
    assert page["before"]["done"] and page["check"] == page["before"]["conflicts"]
    json.dumps(page)  # everything the page gets is plain JSON


# --- through the real Guardian program -------------------------------------------------------------------------------

from tests_kairu.program import end, program, program_with_pin, start  # noqa: E402,F401 (fixtures)
from tests_kairu.test_day4_program import Owner  # noqa: E402


def test_the_brief_runs_through_guardian_with_no_card(program_with_pin):
    from kairu.tasks.core import TaskCore
    _, number = site_meeting(program_with_pin.data_dir)
    owner = Owner(program_with_pin)
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=owner.approver, confirmer=owner.confirmer)
    said = core.handle("brief me for the next meeting")
    assert said.startswith("Before your next meeting: 0 done, 2 open"), said
    assert "Write the homepage copy (Ravi, " in said and "not split to the Clones yet" in said
    assert owner.cards == []  # Low and read only: no card, no PIN
