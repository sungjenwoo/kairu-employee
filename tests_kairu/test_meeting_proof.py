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
    assert "from field" in split.instructions([{"name": "Ravi", "share": 1.0}], 60, ids=True)
    assert "from field" not in split.instructions([{"name": "Ravi", "share": 1.0}], 60)


def test_the_backstop_lets_a_meetings_split_leave(tmp_path):
    """Found on the laptop, 21 Nov 2026: a quoted id ("A2.3") beside the rules' word "password" read as a password.
    The whole request, instructions and brief, must pass the backstop unchanged."""
    from kairu.brain import privacy
    laptop_meetings(tmp_path)
    _, brief = ledger.brief(tmp_path)
    for team_size in ([{"name": "Me", "share": 1.0}], [{"name": "Ravi", "share": 1.0, "skills": "design, writing"},
                                                       {"name": "Anu", "share": 2.0}]):
        leaving = split.instructions(team_size, 120, {"Me": 30}, ids=True) + "\n" + f"Order: {brief}"
        assert privacy.secrets_in(leaving) == [], privacy.secrets_in(leaving)


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

        def plan(self, brief, source, instructions, longest=0, tokens=None):
            told["instructions"] = instructions
            told["room"] = (longest, tokens)
            return gateways.Result(gateways.ANSWERED, "L3", json.dumps({"tasks": split_tasks(number)}), "gemini")
    monkeypatch.setattr(gateways, "Gateway", Brain)
    name, brief = ledger.brief(tmp_path, number)
    team.split(str(tmp_path), brief, name, 0, "a" * 16, "pc")
    said = BrainStore(tmp_path).take_answer("a" * 16).text
    assert "from field" in told["instructions"]
    from kairu.brain import privacy
    assert privacy.secrets_in(told["instructions"] + brief) == []  # the backstop would let it leave
    assert f"Linked to the meeting: task 1 → A{number}.2, task 2 → A{number}.3" in said
    assert len(MeetingStore(tmp_path).links()) >= 2
    assert told["room"] == (team.SPLIT_ANSWER, team.SPLIT_TOKENS)  # a long split is never cut off


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
    work = proof.ledger(tmp_path)[1]["work"]
    assert (work["total"], work["done"], work["complete"], work["check"]) == (1, 0, False, [])
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[K{project}.1.2 finished] Made homepage.txt in your work folder.")
    runner.listen()
    done = item_of(tmp_path, number, 2)
    assert done["status"] == "done" and done["done_at"]
    assert "Ravi's Clone did task 1 'Homepage copy'" in done["proof"]
    assert "Done when: homepage.txt exists with a hero line" in done["proof"] and "File asked for: homepage.txt" in done["proof"]
    assert "Steps: Opened Notepad · Made homepage.txt in your work folder." in done["proof"] and "Check:" not in done["proof"]
    assert item_of(tmp_path, number, 1)["status"] == "open"  # the decision it served shows its work and stays open
    decision = next(item for item in proof.ledger(tmp_path) if (item["meeting"], item["number"]) == (number, 1))
    assert decision["status"] == "open" and decision["work"]["done"] == 1
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
    brief = f"Decided: [D{number}.1] The homepage. Tasks: [A{number}.2] Write the homepage copy.; [A{number}.3] Research."
    proof.link_project(tmp_path, again, split_tasks(number), brief)
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0)
    assert proof.sync(tmp_path) == [(number, 2)]  # the action; its decision only shows the work


def test_a_done_item_is_left_out_of_the_next_split_and_of_the_rule_checks(tmp_path):
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0)  # not yet written back: the overlay sees it
    team_store.set_project(project, state="stopped")  # so the research, split but stopped, may be split again
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
    assert [item["what"] for item in found["done"]] == ["Write the homepage copy."]  # actions only
    assert [item["what"] for item in found["open"]] == ["Research bakery websites in Hyderabad."] and found["overdue"] == 1
    text = proof.told_before(found)
    assert text.startswith("Before your next meeting: 1 done, 1 open (1 overdue),")
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


# --- the brief passes the privacy filter (found on the laptop, 21 Nov 2026: a 900-letter brief counted as "maybe pasted") --

LAPTOP_ONE = {"title": "Fresh Bakes kickoff", "summary": "", "people": [], "items": [
    {"kind": "decision", "what": "Drop the mobile app for now.", "status": "replaced"},
    {"kind": "decision", "what": "Use a warm brown and cream colour palette matching the shop."},
    {"kind": "decision", "what": "Launch on the 28th of November."},
    {"kind": "action", "what": "Own the homepage design and create the first mockup.", "owner": "Priya", "due": "2026-11-16"},
    {"kind": "action", "what": "Build the menu and ordering page.", "owner": "Ravi", "due": "2026-11-20"},
    {"kind": "action", "what": "Write the copy for all pages.", "owner": "Anu", "due": "2026-11-18"},
    {"kind": "action", "what": "Ask the client whether they want online payments or just pickup orders.", "owner": "Saitej"}]}
LAPTOP_TWO = {"title": "Fresh Bakes weekly sync", "summary": "", "people": [], "items": [
    {"kind": "decision", "what": "Add the mobile app back to the project scope."},
    {"kind": "decision", "what": "Launch the website earlier on the 25th of November."},
    {"kind": "decision", "what": "Use online payments with Razorpay."},
    {"kind": "action", "what": "Build the mobile app.", "owner": "Ravi", "due": "2026-11-28", "status": "dropped"},
    {"kind": "action", "what": "Own the payment page design.", "owner": "Priya", "due": "2026-11-24"},
    {"kind": "action", "what": "Set up hosting and the domain.", "owner": "Anu", "due": "2026-11-21"}]}


def laptop_meetings(tmp_path):
    store = MeetingStore(tmp_path)
    numbers = []
    for held, reading in (("2026-11-12", LAPTOP_ONE), ("2026-11-19", LAPTOP_TWO)):
        items = [dict({"owner": "", "due": "", "quote": "", "heard": False, "owner_heard": bool(item.get("owner"))}, **item)
                 for item in reading["items"]]
        number = store.add(reading["title"], held, f"{held}.vtt", held * 6, "transcript", ["[00:01] A: hi"],
                           dict(reading, items=items))
        for index, item in enumerate(items, 1):
            if item.get("status"):
                store.set_status(number, index, item["status"])
        numbers.append(number)
    return store, numbers


def test_the_laptops_six_actions_go_in_a_brief_the_privacy_filter_lets_through(tmp_path):
    from kairu.brain import privacy
    laptop_meetings(tmp_path)
    name, brief, rest = ledger.brief_and_rest(tmp_path)
    verdict = privacy.classify(brief)
    assert not verdict.secret and not verdict.personal, verdict.why()
    assert len(brief) <= privacy.LONGEST
    assert rest == 0 and len([key for key in proof.ids_in(brief) if key.startswith("A")]) == 6
    assert "[A1.4] Own the homepage design and create the first mockup. (owner Priya) (due 2026-11-16)" in brief


def test_more_actions_than_fit_wait_for_the_next_split_and_a_split_one_is_not_split_again(tmp_path):
    from kairu.brain import privacy
    store = MeetingStore(tmp_path)
    many = {"title": "Big", "summary": "", "people": [], "items": [
        {"kind": "action", "what": f"Write the long description of bakery product number {n} for the website catalogue.",
         "owner": "Anu", "due": "2026-11-30", "quote": "", "heard": False, "owner_heard": True} for n in range(1, 13)]}
    number = store.add("Big", "2026-11-19", "big.vtt", "e" * 64, "transcript", ["[00:01] A: hi"], many)
    _, first, rest = ledger.brief_and_rest(tmp_path)
    assert 0 < rest < 12 and not privacy.classify(first).personal
    team_store = clones(tmp_path)
    tasks = [task(f"Product {n}", "Anu") for n in range(1, 13 - rest)]
    project = team_store.add_project("Big 1", first, None, tasks)
    for index, key in enumerate(sorted(proof.ids_in(first), key=lambda k: int(k.split(".")[1])), 1):
        store.link(project, index, number, int(key.split(".")[1]), "named")
    _, second, left = ledger.brief_and_rest(tmp_path)
    assert not set(proof.ids_in(first)) & set(proof.ids_in(second))  # the next split takes only the rest
    team_store.set_project(project, state="stopped")
    assert set(proof.ids_in(first)) <= set(proof.ids_in(ledger.brief_and_rest(tmp_path)[1])) | set(proof.ids_in(second))


def test_when_every_open_action_is_split_the_split_says_start_it(tmp_path):
    _, number = site_meeting(tmp_path)
    run_project(tmp_path, number)
    with pytest.raises(ValueError, match="already split"):
        ledger.brief(tmp_path)


def test_a_long_split_answer_comes_back_whole_from_the_gateway(tmp_path, monkeypatch):
    """Eight tasks of four orders each, through the real Gateway with a stand-in provider: the max_tokens asked for is the
    split's, and the JSON comes back whole, so the split reads it (the laptop got "not JSON" from a cut-off answer)."""
    from kairu.brain import gateway as gateways, keys
    from kairu.brain.providers import Reply
    asked = {}
    tasks = [task(f"Task number {n} of the bakery website", "Ravi",
                  [f"make a file called part{n}.txt saying Section {n} of the bakery site with fresh bread"] * 4,
                  done=f"part{n}.txt exists with section {n}") | {"from": "A1.4"} for n in range(1, 9)]
    whole = json.dumps({"tasks": tasks}, indent=2)
    assert len(whole) > 4000  # longer than the old 4000-letter cut

    def fake_chat(provider, key, messages, account="", model=None, transport=None, max_tokens=700, timeout=0):
        asked["max_tokens"] = max_tokens
        return Reply(whole, 10, 10, None, None, None)
    monkeypatch.setattr(gateways, "chat", fake_chat)
    keys.save(tmp_path, "groq", "gsk_" + "x" * 52)
    result = gateways.Gateway(tmp_path, {"public_to_cloud": True, "providers": ["groq"]}).plan(
        "Work agreed in the meetings. Tasks: [A1.4] Build the site.", "pc", "Split it.", longest=team.SPLIT_ANSWER,
        tokens=team.SPLIT_TOKENS)
    assert result.status == gateways.ANSWERED, result.text
    assert asked["max_tokens"] == team.SPLIT_TOKENS
    assert len(split.parse(result.text, [{"name": "Ravi", "share": 1.0}])) == 8


# --- found on the laptop, 21 Nov 2026: honest proof, and decisions stay open --------------------------------------------

LAPTOP_LOG = [[1, "Opened notepad."], [2, 'Typed "Homepage mockup layout: hero image, tagline, navigation" in Notepad.'],
              [3, "Another window came to the front, so I pressed nothing."], [4, "Closed notepad."]]


def test_the_proof_lists_every_step_and_calls_out_one_that_did_nothing():
    task = {"clone": "Me", "number": 1, "title": "Homepage mockup", "project": 2, "finished": 0, "done": "a file exists",
            "orders": ["open notepad", "type Homepage mockup layout in notepad",
                       "save it in notepad as homepage_mockup.txt in notepad", "close notepad"], "log": LAPTOP_LOG}
    said = proof._proof_of(task)
    assert "File asked for: homepage_mockup.txt" in said
    assert "Steps: Opened notepad · Typed" in said and "· Closed notepad." in said
    assert "Check: step 3 (Another window came to the front, so I pressed nothing)" in said
    good = dict(task, log=[[1, "Opened notepad."], [2, "Typed 74 characters in Notepad."], [3, "Pressed Ctrl+S in Notepad."],
                           [4, "Closed notepad."]])
    assert "Check:" not in proof._proof_of(good)


def test_a_step_that_did_nothing_blocks_the_task_so_its_action_is_not_written_back(tmp_path):
    from kairu.team.store import BLOCKED
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[K{project}.1.1 finished] Opened notepad.")
    runner.listen()
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[K{project}.1.2 finished] Another window came to the front, so I pressed nothing.")
    runner.listen()
    assert team_store.tasks(project)[0]["state"] == BLOCKED
    assert item_of(tmp_path, number, 2)["status"] == "open"


def test_a_decision_an_earlier_version_marked_done_is_open_again(tmp_path):
    store, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=2, finished=2000.0)
    with __import__("contextlib").closing(store.connect()) as db:  # as the first stage 5 version left it on the laptop
        db.execute("UPDATE items SET status = 'done', proof = 'old proof', done_at = 1 WHERE meeting = ? AND number = 1",
                   (number,))
        db.commit()
    assert next(i for i in proof.ledger(tmp_path) if i["number"] == 1)["status"] == "open"  # every reader at once
    proof.sync(tmp_path)
    decision = item_of(tmp_path, number, 1)
    assert decision["status"] == "open" and decision["proof"] == "" and decision["done_at"] is None
    store.set_status(number, 1, "replaced")
    proof.sync(tmp_path)
    assert item_of(tmp_path, number, 1)["status"] == "replaced"  # the manager's choice is never undone
    assert "1. [replaced] decision: The homepage leads" in ledger.told_ledger(proof.ledger(tmp_path))


def test_a_task_done_before_the_fix_with_a_step_that_did_nothing_never_makes_its_action_done(tmp_path):
    _, number = site_meeting(tmp_path)
    team_store, project, runner, fakes = run_project(tmp_path, number)
    team_store.set_task(project, 1, state=DONE, step=4, finished=2000.0)
    with __import__("contextlib").closing(team_store.connect()) as db:
        db.execute("UPDATE tasks SET log = ?, orders = ? WHERE project = ? AND number = 1",
                   (json.dumps(LAPTOP_LOG), json.dumps(["open notepad", "type Homepage mockup in notepad",
                                                        "save it in notepad as homepage_mockup.txt in notepad",
                                                        "close notepad"]), project))
        db.commit()
    assert proof.sync(tmp_path) == []
    item = next(i for i in proof.ledger(tmp_path) if i["number"] == 2)
    assert item["status"] == "open" and item["work"]["check"] == ["task 1 step 3"]
    assert "(check task 1 step 3: it did nothing)" in ledger.told_ledger(proof.ledger(tmp_path))
    assert "check task 1 step 3: it did nothing" in proof.told_before(proof.before(tmp_path))


def test_a_resent_close_and_a_step_that_worked_on_retry_are_proof_not_a_check():
    base = {"clone": "Me", "number": 5, "title": "Payment page", "project": 2, "finished": 0, "done": "a file exists",
            "orders": ["open notepad", "type Payment page in notepad", "save it in notepad as pay.txt in notepad",
                       "close notepad"]}
    resent = dict(base, log=[[1, "Opened notepad."], [2, "Typed it."], [3, "Pressed Ctrl+S in Notepad."],
                             [4, "Refused: notepad isn't open."]])
    assert proof._odd(resent) == [] and "Check:" not in proof._proof_of(resent)
    retried = dict(base, log=[[1, "Opened notepad."], [2, "Typed it."], [3, "Another window came to the front, so I pressed nothing."],
                              [4, "Pressed Ctrl+S in Notepad."], [5, "Closed notepad."]])
    assert proof._odd(retried) == []
    failed_open = dict(base, log=[[1, "Refused: notepad isn't open."], [2, "Typed it."], [3, "Saved."], [4, "Closed notepad."]])
    assert proof._odd(failed_open) == [1]  # only a close may find its app already closed
