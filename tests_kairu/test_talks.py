"""Your talk history (MEMORY.md "Talk history"): Kairu keeps your talks at the PC by itself, on this PC only, and tells
them by rules. Everything talks to stand-ins on this PC: nothing leaves the PC."""

import json
import re
import time
from datetime import datetime, timedelta

import pytest

from kairu.brain import ask, router
from kairu.brain.gateway import ANSWERED, MEMORY, REFUSED, Gateway, Result
from kairu.brain.store import MOST_TALKS, TALK_DAYS, BrainStore
from kairu.config import ROOT
from kairu.memory import actions, talks
from kairu.memory.store import MemoryStore
from tests_kairu.helpers import kairu
from tests_kairu.program import program, program_with_pin  # noqa: F401 (fixtures)
from tests_kairu.test_brain_gateway import SETTINGS, Transport, data_dir  # noqa: F401 (fixture)
from tests_kairu.test_brain_program import logged
from tests_kairu.test_research_program import (brain, config_path, providers, relay, research_on, runs, web)  # noqa: F401

NOON = datetime(2026, 11, 14, 12, 0).timestamp()
YESTERDAY = NOON - 86400


def gate(data_dir, transport=None):
    return Gateway(data_dir, dict(SETTINGS), transport or Transport(),
                   lambda message: {"verdict": "ok", "mode": "normal", "running": []}, sleep=lambda seconds: None)


@pytest.fixture
def talked(data_dir):
    store = BrainStore(data_dir)
    store.keep_talk("who is the prime minister of India", "Narendra Modi. Want to know more about him?", YESTERDAY)
    store.keep_talk("how do solar panels work", "They turn sunlight into electricity.\nWant an example?", NOON - 3600)
    store.keep_talk("what is green tea", "Tea made from unoxidised leaves. Want to know more?", NOON - 60)
    return data_dir


# --- the router ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("said, when, about", [
    ("what did I ask yesterday", "yesterday", ""), ("what did we talk about today?", "today", ""),
    ("Kairu, what did I ask you this morning", "today", ""), ("show our chat history", "recent", ""),
    ("what did I say", "recent", ""), ("what did I ask you about solar panels", "recent", "solar panels"),
    ("did I ask about tea", "recent", "tea"), ("what did you say about black holes", "recent", "black holes"),
])
def test_asking_about_our_talks(said, when, about):
    route = router.route(said)
    assert (route.level, route.kind, route.name, route.when, route.query) == ("L0", "memory", "talks", when, about)


@pytest.mark.parametrize("said", ["forget our talks", "clear the chat history", "delete our conversations",
                                  "wipe my talk history"])
def test_forgetting_our_talks_is_memory_forget(said):
    route = router.route(said)
    assert (route.kind, route.name, route.query) == ("memory", "forget", talks.TALKS)


@pytest.mark.parametrize("said", ["what did Einstein say about time", "what did the teacher ask", "talk to me",
                                  "forget about my exam", "what do you remember"])
def test_other_words_are_not_the_talk_history(said):
    assert router.route(said).name != "talks" and router.route(said).query != talks.TALKS


# --- the store -------------------------------------------------------------------------------------------------

def test_talks_are_kept_oldest_first_short_and_only_for_30_days_and_300(data_dir):
    store = BrainStore(data_dir)
    now = time.time()
    store.keep_talk("old one", "answer", now - (TALK_DAYS + 1) * 86400)
    store.keep_talk("  a   question ", "x" * 1000, now)
    assert [talk["question"] for talk in store.talks()] == ["a question"] and len(store.talks()[0]["answer"]) == 400
    for number in range(MOST_TALKS + 5):
        store.keep_talk(f"q{number}", "a", now)
    kept = store.talks()
    assert len(kept) == MOST_TALKS and kept[-1]["question"] == f"q{MOST_TALKS + 4}"
    assert store.forget_talks() == MOST_TALKS and store.talks() == []


@pytest.mark.parametrize("question, answer, kind, expected", [
    ("who is the pm", "Modi.", "cloud", True),
    ("my otp is 482916 is it safe", "Never share it.", "cloud", False),
    ("what is it", "The key is Bearer abcdefghijklmnopqrstuvwxyz0123", "cloud", False),
    ("what do you remember", "Here is what I remember: ...", "memory", False),
    ("", "x", "cloud", False),
])
def test_what_is_kept(question, answer, kind, expected):
    assert talks.kept(question, answer, "L3", kind) is expected


def test_told_by_day_and_by_words(talked):
    today = talks.told(talked, "today", now=NOON)
    assert today.startswith("Today you asked:") and "how do solar panels work → They turn sunlight into electricity." in today
    assert "prime minister" not in today and "\n" in today
    yesterday = talks.told(talked, "yesterday", now=NOON)
    assert yesterday == "Yesterday you asked:\n- 12:00 who is the prime minister of India → Narendra Modi. Want to know more about him?"
    assert "About solar panels" in talks.told(talked, "recent", "solar panels", now=NOON)
    assert talks.told(talked, "recent", "black holes", now=NOON) == "I don't find a talk about black holes."
    assert talks.told(talked, "today", now=NOON + 2 * 86400) == "We haven't talked yet today."


# --- the Gateway and the ask action ------------------------------------------------------------------------------

def test_asking_about_our_talks_is_answered_on_this_pc_and_nothing_is_sent(talked):
    BrainStore(talked).keep_talk("what is green tea", "Tea made from unoxidised leaves.", time.time() - 1)  # today, whenever this runs
    transport = Transport()
    result = gate(talked, transport).ask("what did we talk about today", "pc")
    assert (result.status, result.level) == (ANSWERED, "L0") and "green tea" in result.text
    assert transport.sent == [] and BrainStore(talked).context("pc") is None


def test_the_talks_are_told_only_at_the_pc(talked):
    for source in ("dev-" + "a" * 16, "mission:1"):
        assert gate(talked).ask("what did I ask yesterday", source).status == REFUSED


def test_forget_our_talks_is_handed_to_guardian_and_deletes_them_all(talked):
    assert gate(talked).ask("forget our talks", "pc").status == MEMORY
    assert len(BrainStore(talked).talks()) == 3  # the brain changes nothing itself
    actions.forget(talked, talks.TALKS, "0123456789abcdef")
    assert MemoryStore(talked).take("0123456789abcdef") == {"did": "forgot", "count": 3, "talks": True}
    assert BrainStore(talked).talks() == []


def test_a_talk_is_never_added_to_a_question_sent_to_a_cloud_ai(talked):
    transport = Transport()
    gateway = gate(talked, transport)
    gateway.ask("what did I ask yesterday", "pc")
    gateway.ask("tell me more", "pc")
    gateway.ask("what is a black hole", "pc")
    yours = json.dumps([message for request in transport.sent for message in request["body"]["messages"]
                        if message["role"] != "system"])  # Kairu's own rules name "the prime minister" as an example
    assert len(transport.sent) == 2 and "Narendra" not in yours and "prime minister" not in yours


def answer(text="Tokyo. Want to know more?", status=ANSWERED, kind="cloud"):
    return Result(status, "L3", text, route=router.Route("L3", kind))


@pytest.mark.parametrize("source, result, settings, kept", [
    ("pc", answer(), {}, True),
    ("pc", answer(), {"talk_history": False}, False),
    ("dev-" + "a" * 16, answer(), {}, False),
    ("mission:3", answer(), {}, False),
    ("pc", answer(status="needs_approval"), {}, False),
    ("pc", answer(kind="memory"), {}, False),
])
def test_the_ask_action_keeps_an_answered_talk_at_the_pc(data_dir, source, result, settings, kept):
    ask._remember_talk(data_dir, "what is the capital of japan", source, result, settings)
    assert len(BrainStore(data_dir).talks()) == (1 if kept else 0)


def test_the_talk_history_reaches_no_network():
    text = (ROOT / "kairu" / "memory" / "talks.py").read_text(encoding="utf-8")
    for module in ("urllib", "http", "socket", "requests", "kairu.brain.providers", "kairu.link", "kairu.research", "kairu.channel"):
        assert not re.search(rf"^\s*(?:from|import)\s+{re.escape(module)}\b", text, re.MULTILINE), module


# --- through the real Guardian program ----------------------------------------------------------------------------

def test_kairu_keeps_the_talk_tells_it_and_forgets_it_through_guardian(brain, web, providers):
    asked = kairu("ask", "who is the prime minister of India", timeout=60)
    assert asked.returncode == 0, asked.stdout + asked.stderr
    told = kairu("ask", "what did I ask today", timeout=60)
    assert "Today you asked:" in told.stdout and "who is the prime minister of India" in told.stdout
    assert "L0" in told.stdout and len(providers.heard()) == 1  # only the first question went to the AI
    gone = kairu("ask", "forget our talks", timeout=60)
    assert "I forgot our talks" in gone.stdout and runs(brain.data_dir)["memory.forget"] == ["started", "finished"]
    assert "haven't talked yet today" in kairu("ask", "what did I ask today", timeout=60).stdout
    assert "prime minister" not in logged(brain.data_dir)  # the audit log keeps hashes, never the words
