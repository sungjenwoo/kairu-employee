"""Stage 2 and 3 of the meeting agent (HACKATHON.md): the decision ledger, conflicts between meetings, "what did we decide
about X?", deciding a conflict and the brief for Main Kairu's split. No test reaches Google: Gemini is a stand-in gateway."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from kairu import executors, policy
from kairu.brain.gateway import ANSWERED
from kairu.meeting import conduct, ledger, orders, read
from kairu.meeting.store import MeetingStore
from kairu.policy import Tier
from tests_kairu.helpers import POLICY

RULES = policy.load(POLICY).rules
KICKOFF = """[00:24] Saitej: Okay, decided: we drop the mobile app.
[00:36] Priya: I'll do the homepage design by Monday.
[02:10] Saitej: Launch is on the 28th of November."""
SYNC = """[00:10] Saitej: The client wants the mobile app back after all.
[00:30] Saitej: We move the launch to the 25th.
[00:50] Ravi: I'm already overloaded with the menu and the gallery."""

FIRST = {"title": "Kickoff", "summary": "", "people": ["Saitej", "Priya"], "items": [
    {"kind": "decision", "what": "Drop the mobile app.", "owner": "", "due": "", "quote": "we drop the mobile app", "heard": True,
     "owner_heard": False},
    {"kind": "decision", "what": "Launch on 28 November.", "owner": "Saitej", "due": "2026-11-28", "quote": "Launch is on the 28th",
     "heard": True, "owner_heard": True},
    {"kind": "action", "what": "Design the homepage.", "owner": "Priya", "due": "2026-11-16", "quote": "", "heard": False,
     "owner_heard": True}]}


def two_meetings(tmp_path):
    store = MeetingStore(tmp_path)
    one = store.add("Kickoff", "2026-11-12", "kickoff.vtt", "a" * 64, "transcript", KICKOFF.split("\n"), FIRST)
    second = {"title": "Weekly sync", "summary": "", "people": ["Saitej", "Ravi"], "items": [
        {"kind": "decision", "what": "Bring the mobile app back.", "owner": "", "due": "", "quote": "wants the mobile app back",
         "heard": True, "owner_heard": False},
        {"kind": "decision", "what": "Launch on 25 November.", "owner": "Saitej", "due": "2026-11-25", "quote": "move the launch",
         "heard": True, "owner_heard": True}],
        "conflicts": [
            {"kind": "decision", "what": "The mobile app was dropped on 12 Nov and is back today.", "item": 1,
             "earlier_meeting": one, "earlier_item": 1, "quote": "wants the mobile app back", "heard": True},
            {"kind": "deadline", "what": "The launch moves from 28 Nov to 25 Nov.", "item": 2, "earlier_meeting": one,
             "earlier_item": 2, "quote": "move the launch to the 25th", "heard": True}]}
    two = store.add("Weekly sync", "2026-11-19", "sync.vtt", "b" * 64, "transcript", SYNC.split("\n"), second)
    return store, one, two


# --- the policy -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, tier", [("meeting.check", Tier.LOW), ("meeting.ask", Tier.LOW),
                                        ("meeting.resolve", Tier.MEDIUM)])
def test_each_new_meeting_action_has_its_tier_and_code(name, tier):
    assert RULES[name].tier is tier
    assert name in executors.EXECUTORS


# --- Gemini's conflicts, read strictly ----------------------------------------------------------------------------

def test_conflicts_map_to_this_meetings_items_and_only_to_earlier_ids_that_were_shown():
    answer = {"title": "Sync", "summary": "", "people": ["Saitej"],
              "decisions": [{"what": "Bring the mobile app back.", "quote": "wants the mobile app back"},
                            {"what": "Launch on 25 November.", "due": "2026-11-25", "quote": "move the launch to the 25th"}],
              "actions": [], "questions": [],
              "conflicts": [
                  {"kind": "decision", "what": "The app is back.", "about": "decision 1", "earlier": "E1.1",
                   "quote": "wants the mobile app back"},
                  {"kind": "deadline", "what": "The launch moves.", "about": "decision 2", "earlier": "E7.9", "quote": "made up"},
                  {"kind": "astrology", "what": "Not a kind Kairu knows.", "about": "", "earlier": ""}]}
    reading = read.parse(json.dumps(answer), SYNC, date(2026, 11, 19), {(1, 1), (1, 2)})
    found = reading["conflicts"]
    assert [c["kind"] for c in found] == ["decision", "deadline"]
    assert found[0]["item"] == 1 and (found[0]["earlier_meeting"], found[0]["earlier_item"]) == (1, 1) and found[0]["heard"]
    assert found[1]["item"] == 2 and found[1]["earlier_meeting"] == 0 and not found[1]["heard"]  # an id never shown: none
    assert all("source" not in item for item in reading["items"])


def test_gemini_is_shown_the_earlier_open_items_and_its_conflicts_are_kept(tmp_path):
    store = MeetingStore(tmp_path)
    store.add("Kickoff", "2026-11-12", "kickoff.vtt", "a" * 64, "transcript", KICKOFF.split("\n"), FIRST)
    told = {}

    class Gemini:
        def meeting(self, instructions, text, media=None, json_answer=False):
            told["instructions"] = instructions
            return SimpleNamespace(status=ANSWERED, provider="gemini", text=json.dumps({
                "title": "Weekly sync", "summary": "", "people": ["Saitej"],
                "decisions": [{"what": "Bring the mobile app back.", "quote": "wants the mobile app back"}],
                "actions": [], "questions": [],
                "conflicts": [{"kind": "decision", "what": "The mobile app was dropped on 12 Nov and is back.",
                               "about": "decision 1", "earlier": "E1.1", "quote": "wants the mobile app back"}]}))

    number = conduct.understand(str(tmp_path), None, SYNC.split("\n"), date(2026, 11, 19), "", "sync.vtt", "b" * 64,
                                "transcript", None, 0.0, gateway=Gemini())
    assert "[E1.1] meeting 1 (2026-11-12), decision: Drop the mobile app." in told["instructions"]
    assert "conflicts" in told["instructions"]
    meeting = store.meeting(number)
    assert meeting["conflicts"][0]["earlier"]["what"] == "Drop the mobile app."
    assert "Conflicts with earlier meetings (1)" in conduct.told(meeting)


def test_the_first_meeting_is_read_as_before_with_no_ledger(tmp_path):
    told = {}

    class Gemini:
        def meeting(self, instructions, text, media=None, json_answer=False):
            told["instructions"] = instructions
            return SimpleNamespace(status=ANSWERED, provider="gemini", text=json.dumps(
                {"title": "Kickoff", "summary": "", "people": [], "decisions": [], "actions": [], "questions": []}))

    conduct.understand(str(tmp_path), None, KICKOFF.split("\n"), date(2026, 11, 12), "", "k.vtt", "a" * 64, "transcript",
                       None, 0.0, gateway=Gemini())
    assert "Cross-meeting memory" not in told["instructions"]


# --- the ledger, deciding a conflict ---------------------------------------------------------------------------------

def test_the_ledger_holds_every_decision_and_action_oldest_meeting_first(tmp_path):
    store, one, two = two_meetings(tmp_path)
    found = store.ledger()
    assert [(item["meeting"], item["number"]) for item in found] == [(one, 1), (one, 2), (one, 3), (two, 1), (two, 2)]
    assert store.ledger(before="2026-11-12") == found[:3]
    assert "Meeting 1: Kickoff (12 Nov)" in ledger.told_ledger(found)


def test_keeping_the_new_decision_marks_the_earlier_one_replaced_and_keeping_the_old_drops_the_new(tmp_path):
    store, one, two = two_meetings(tmp_path)
    store.resolve(two, 1, "new")
    assert store.meeting(one)["items"][0]["status"] == "replaced"
    store.resolve(two, 2, "old")
    assert store.meeting(two)["items"][1]["status"] == "dropped"
    assert store.conflicts("open") == []
    assert [c["status"] for c in store.conflicts()] == ["kept-new", "kept-old"]


def test_resolve_runs_as_its_own_action_and_refuses_a_conflict_that_isnt_there(tmp_path):
    from kairu.tasks.store import TaskStore
    _, one, two = two_meetings(tmp_path)
    assert conduct.resolve(str(tmp_path), "c" * 16, float(two), 1.0, "new") is None
    assert "Kept the new one" in TaskStore(tmp_path).take_reply("c" * 16).text
    assert conduct.resolve(str(tmp_path), "d" * 16, float(two), 9.0, "new") is not None


# --- Kairu's own checks ----------------------------------------------------------------------------------------------

def item(meeting, number, what, owner="", due="", kind="action", status="open"):
    return {"meeting": meeting, "number": number, "kind": kind, "what": what, "owner": owner, "due": due, "status": status,
            "held": "2026-11-19", "quote": ""}


def test_kairus_own_checks_find_no_owner_two_owners_overload_and_a_task_due_before_what_it_waits_on():
    found = ledger.rule_conflicts([
        item(1, 1, "Set up hosting and the domain"),
        item(1, 2, "Build the menu page", "Ravi", "2026-11-20"),
        item(2, 1, "Build the menu page for phones", "Anu", "2026-11-22"),
        item(2, 2, "Build the gallery", "Ravi", "2026-11-21"),
        item(2, 3, "Write the menu text", "Ravi", "2026-11-21"),
        item(2, 4, "Fix the footer", "Ravi", "2026-11-21"),
        item(2, 5, "Test the site after the gallery is built", "Priya", "2026-11-20"),
    ], today=date(2026, 11, 19))
    kinds = [clash["kind"] for clash in found]
    assert "owner" in kinds and "workload" in kinds and "dependency" in kinds
    assert any("Nobody owns" in clash["what"] for clash in found)
    assert any("two owners" in clash["what"] for clash in found)
    assert any("Ravi holds 4 open actions" in clash["what"] for clash in found)


def test_busy_minutes_on_the_team_board_count_as_workload():
    found = ledger.rule_conflicts([item(1, 1, "Build the menu page", "Ravi", "2026-11-20")], busy={"ravi": 300},
                                  today=date(2026, 11, 19))
    assert found and found[0]["kind"] == "workload" and "300 minutes" in found[0]["what"]


def test_done_and_replaced_items_raise_nothing():
    assert ledger.rule_conflicts([item(1, 1, "Set up hosting", status="done")]) == []


# --- "what did we decide about X?" and the brief ---------------------------------------------------------------------

def test_what_did_we_decide_gives_the_newest_with_the_meeting_and_the_day_then_what_came_before(tmp_path):
    two_meetings(tmp_path)
    said = ledger.ask(tmp_path, "the mobile app")
    assert said.startswith("About the mobile app: Bring the mobile app back. (Weekly sync, 19 Nov, open).")
    assert "Before that: Drop the mobile app. (Kickoff, 12 Nov" in said
    assert "don't find" in ledger.ask(tmp_path, "the parking lot")


def test_the_brief_holds_the_open_actions_with_owners_and_dates(tmp_path):
    two_meetings(tmp_path)
    name, brief = ledger.brief(tmp_path, 1)
    assert "Design the homepage. (owner Priya) (due 2026-11-16)" in brief and name == "From Kickoff"
    with pytest.raises(ValueError):
        ledger.brief(tmp_path, 2)  # meeting 2 has no actions


def test_the_conflict_check_counts_gemini_and_rule_conflicts(tmp_path):
    two_meetings(tmp_path)
    found = ledger.check(tmp_path)
    assert len(found["between"]) == 2
    text = ledger.told_check(found)
    assert "[2.1] decision: The mobile app was dropped" in text and "kairu meeting resolve" in text


# --- the orders ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("said, which", [
    ("what did we decide about the launch date", "ask"), ("What have we agreed on the mobile app", "ask"),
    ("check for conflicts", "check"), ("show the conflicts", "check"), ("any conflicts", "check"),
    ("show the ledger", "check"), ("keep the new one 2.1", "resolve"), ("keep the old decision 2.2", "resolve"),
    ("split the meeting", "split"), ("split the meeting 2 in 3 hours", "split"), ("turn the meeting into tasks", "split")])
def test_the_new_meeting_orders(said, which):
    patterns = {"ask": orders.ASK, "check": orders.CHECK, "resolve": orders.RESOLVE, "split": orders.SPLIT}
    assert patterns[which].fullmatch(said)
    assert [name for name, pattern in patterns.items() if pattern.fullmatch(said)] == [which]


def test_the_stage_1_orders_still_mean_what_they_did():
    assert orders.SHOW.fullmatch("what did we decide in the meeting")
    assert not orders.ASK.fullmatch("what did we decide in the meeting")
    assert orders.SHOW.fullmatch("show the last meeting") and not orders.CHECK.fullmatch("show the last meeting")
