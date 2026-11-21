"""Kairu's memory (stage M1, MEMORY.md): the router, the store, the two Guardian actions, what the brain may do, and runs
through the real Guardian program. Everything talks to stand-ins on this PC: nothing leaves the PC.
"""

import json
import re

import pytest

from kairu import executors, policy
from kairu.brain import router
from kairu.brain.gateway import ANSWERED, MEMORY, NEEDS_APPROVAL, REFUSED, Gateway
from kairu.brain.store import BrainStore
from kairu.config import ROOT
from kairu.memory import actions, conduct, recall
from kairu.memory.store import LONGEST_FACT, MOST_FACTS, MemoryStore, words
from kairu.policy import Tier
from tests_kairu.helpers import POLICY, kairu
from tests_kairu.program import program, program_with_pin  # noqa: F401 (fixtures)
from tests_kairu.test_brain_gateway import SETTINGS, Transport, data_dir  # noqa: F401 (fixture)
from tests_kairu.test_brain_program import logged
from tests_kairu.test_research_program import (brain, config_path, providers, relay, research_on, runs, web)  # noqa: F401

RULES = policy.load(POLICY).rules
JOB = "0123456789abcdef"
SISTER = "my sister's name is Anu"


def gate(data_dir, transport=None):
    return Gateway(data_dir, dict(SETTINGS), transport or Transport(),
                   lambda message: {"verdict": "ok", "mode": "normal", "running": []}, sleep=lambda seconds: None)


# --- the router -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("said, name, words_", [
    ("Kairu, remember that my sister's name is Anu", "remember", SISTER),
    ("remember my exam is on 20 Nov", "remember", "my exam is on 20 Nov"),
    ("please don't forget that I like tea", "remember", "I like tea"),
    ("note that Omesh owes me a pizza", "remember", "Omesh owes me a pizza"),
    ("keep in mind: the lab is in Block C", "remember", "the lab is in Block C"),
    ("forget about my sister", "forget", "my sister"),
    ("forget that I like tea", "forget", "I like tea"),
    ("forget everything", "forget", "*"),
    ("clear your memory", "forget", "*"),
    ("forget everything you remember about me", "forget", "*"),
    ("what do you remember?", "recall", ""),
    ("what do you know about me", "recall", ""),
    ("show me what you remember", "recall", ""),
    ("what do you remember about my exam", "recall", "my exam"),
])
def test_only_these_words_reach_the_memory_and_the_line_is_kept_as_typed(said, name, words_):
    route = router.route(said)
    assert (route.level, route.kind, route.name, route.query) == ("L0", "memory", name, words_)


@pytest.mark.parametrize("said", ["forget it", "forget that", "remember what I said", "remember when we met?", "remember me",
                                  "what do you know about black holes", "do you remember my birthday", "memory",
                                  "how does memory work", "who is the prime minister of India"])
def test_other_words_do_not(said):
    assert router.route(said).kind != "memory"


def test_a_request_to_do_something_is_never_a_memory():
    assert router.route("delete my files and remember that").kind == "action"


# --- the policy and the actions -----------------------------------------------------------------------------

def test_the_two_actions_are_in_the_policy_private_and_never_read_only():
    remember, forget = RULES["memory.remember"], RULES["memory.forget"]
    assert remember.tier is Tier.LOW and forget.tier is Tier.MEDIUM
    for name, rule in (("memory.remember", remember), ("memory.forget", forget)):
        assert rule.private and not rule.read_only and rule.feature is None and name in executors.EXECUTORS
        assert executors.EXECUTORS[name].supplied == ("data_dir",)  # the folder is Guardian's, never a request's
    assert "takes only" in executors.argument_problem("memory.remember", executors.EXECUTORS["memory.remember"],
                                                      {"text": "x", "job": JOB, "source": "pc", "data_dir": "elsewhere"})


def test_remember_keeps_the_line_once(tmp_path):
    actions.remember(str(tmp_path), f"  {SISTER}. ", JOB, "pc")
    store = MemoryStore(tmp_path)
    assert store.take(JOB) == {"did": "saved"} and [fact["text"] for fact in store.all()] == [SISTER]
    actions.remember(str(tmp_path), SISTER.upper(), JOB, "dev-" + "a" * 16)
    assert store.take(JOB) == {"did": "known"} and len(store.all()) == 1


@pytest.mark.parametrize("line", ["my otp is 482916", "the key is Bearer abcdefghijklmnopqrstuvwxyz0123"])
def test_a_secret_is_never_kept_whoever_asks_and_the_reason_is_only_a_label(tmp_path, line):
    actions.remember(str(tmp_path), line, JOB, "pc")
    store = MemoryStore(tmp_path)
    done = store.take(JOB)
    assert done["did"] == "refused" and "never keep secrets" in done["why"] and store.all() == []
    assert "482916" not in done["why"] and "abcdefghij" not in done["why"]
    assert "482916" not in (tmp_path / "memory.db").read_bytes().decode("latin-1")


@pytest.mark.parametrize("text, source", [("ok", "pc"), ("x" * (LONGEST_FACT + 1), "pc"), (SISTER, "mission:3"),
                                          (SISTER, "someone"), (SISTER, "")])
def test_a_line_must_be_short_and_from_you(tmp_path, text, source):
    actions.remember(str(tmp_path), text, JOB, source)
    assert MemoryStore(tmp_path).take(JOB)["did"] == "refused" and MemoryStore(tmp_path).all() == []


def test_memory_is_full_at_500_lines(tmp_path):
    store = MemoryStore(tmp_path)
    for number in range(MOST_FACTS):
        assert store.add(f"line number {number}", "pc") == "saved"
    assert store.add("one more", "pc") == "full" and len(store.all()) == MOST_FACTS


def test_forget_deletes_only_the_lines_about_those_words(tmp_path):
    store = MemoryStore(tmp_path)
    for line in (SISTER, "my sister likes chess", "my exam is on 20 Nov"):
        store.add(line, "pc")
    actions.forget(str(tmp_path), "my sister", JOB)
    assert store.take(JOB) == {"did": "forgot", "count": 2} and [fact["text"] for fact in store.all()] == ["my exam is on 20 Nov"]
    actions.forget(str(tmp_path), "my cat", JOB)
    assert store.take(JOB) == {"did": "forgot", "count": 0} and len(store.all()) == 1
    actions.forget(str(tmp_path), "*", JOB)
    assert store.take(JOB) == {"did": "forgot", "count": 1, "all": True} and store.all() == []


def test_a_job_id_is_16_hex_digits(tmp_path):
    for action, arguments in ((actions.remember, (SISTER, "../x", "pc")), (actions.forget, ("*", "x"))):
        with pytest.raises(SystemExit):
            action(str(tmp_path), *arguments)


def test_words_say_what_a_line_is_about():
    assert words("What is my sister's name?") == {"sister", "name"} and words("my sisters") == {"sister"}
    assert words("the class") == {"class"}


# --- what Kairu tells from it --------------------------------------------------------------------------------

@pytest.fixture
def remembered(data_dir):
    store = MemoryStore(data_dir)
    for line in (SISTER, "my exam is on 20 Nov", "I like tea", "my sister likes chess"):
        store.add(line, "pc")
    return data_dir


@pytest.mark.parametrize("question, answer", [
    ("what is my sister's name?", f"You told me:\n- {SISTER}\n- my sister likes chess"),  # the line with more of your words first
    ("Kairu, when is my exam", "You told me: my exam is on 20 Nov."),
    ("do you remember my exam date?", "You told me: my exam is on 20 Nov."),
])
def test_a_question_about_something_of_yours_is_answered_on_this_pc_and_nothing_is_sent(remembered, question, answer):
    transport = Transport()
    result = gate(remembered, transport).ask(question, "pc")
    assert (result.status, result.level, result.text, result.note) == (ANSWERED, "L0", answer, "from Kairu's memory")
    assert transport.sent == [] and BrainStore(remembered).context("pc") is None


# --- smarter matching (M3, 15 Nov 2026): related words, word endings, questions about someone you told Kairu about -----

@pytest.fixture
def people(data_dir):
    store = MemoryStore(data_dir)
    for line in (SISTER, "my mother was born on 5 June", "Ravi works at Infosys", "Anu lives in Kukatpally", "I like tea",
                 "my sister likes chess"):
        store.add(line, "pc")
    return data_dir


@pytest.mark.parametrize("question, answer", [
    ("who is Anu", f"You told me:\n- Anu lives in Kukatpally\n- {SISTER}"),
    ("when is my mom's birthday", "You told me: my mother was born on 5 June."),
    ("when is mummy's birthday", "You told me: my mother was born on 5 June."),
    ("where does Anu live", "You told me: Anu lives in Kukatpally."),
    ("where does Ravi work", "You told me: Ravi works at Infosys."),
    ("what does my sister like", "You told me: my sister likes chess."),
    ("who is Ravi?", "You told me: Ravi works at Infosys."),
    ("what is my favourite drink", "I don't have that exactly. The closest I remember:\n- my sister likes chess\n- I like tea"),
])
def test_memory_matches_related_words_on_this_pc_and_nothing_is_sent(people, question, answer):
    transport = Transport()
    result = gate(people, transport).ask(question, "pc")
    assert (result.status, result.level, result.text) == (ANSWERED, "L0", answer)
    assert transport.sent == []


@pytest.mark.parametrize("question", ["who is the prime minister of India", "what is the capital of France",
                                      "tell me about black holes", "what is the weather today", "who is Modi"])
def test_a_general_question_is_never_answered_from_memory(people, question):
    assert recall.about_me(people, question) == ""


def test_my_dads_birthday_is_never_answered_with_my_mothers(people):
    assert recall.about_me(people, "when is my dad's birthday") == ""


def test_forget_never_uses_the_loose_match(people):
    store = MemoryStore(people)
    assert store.related("my favourite drink") and store.find("my favourite drink") == []
    assert [fact["text"] for fact in store.find("my mom")] == ["my mother was born on 5 June"]


def test_related_words_are_in_one_group_only():
    from kairu.memory.store import RELATED
    every = [word for group in RELATED.values() for word in group]
    assert len(every) == len(set(every))


def test_what_kairu_does_not_remember_goes_on_as_before(remembered):
    transport = Transport()
    assert gate(remembered, transport).ask("what is my friend Ravi's phone number", "pc").status == NEEDS_APPROVAL
    told = gate(remembered, transport).ask("do you remember my roll number?", "pc")
    assert (told.level, told.text) == ("L0", 'I don\'t remember your roll number yet. Say "remember that ..." and I\'ll keep it.')
    assert gate(remembered, transport).ask("who is the prime minister of India", "pc").level == "L3"
    assert all("Anu" not in json.dumps(request) and "20 Nov" not in json.dumps(request) for request in transport.sent)


def test_what_do_you_remember_lists_the_lines_newest_first(remembered):
    result = gate(remembered).ask("what do you remember", "pc")
    assert result.text == f"Here is what I remember:\n- my sister likes chess\n- I like tea\n- my exam is on 20 Nov\n- {SISTER}"
    about = gate(remembered).ask("what do you remember about my exam", "pc")
    assert about.text == "Here is what I remember about my exam:\n- my exam is on 20 Nov"
    assert "anything about my cat" in gate(remembered).ask("what do you remember about my cat", "pc").text


def test_with_nothing_remembered_it_says_so(data_dir):
    assert gate(data_dir).ask("what do you remember", "pc").text == recall.NONE_YET


def test_memory_is_told_only_at_the_pc_and_never_to_a_mission(remembered):
    phone = "dev-" + "a" * 16
    assert gate(remembered).ask("what do you remember", phone).status == REFUSED
    asked = gate(remembered).ask("when is my exam", phone)  # as before: the phone gets nothing from the memory
    assert asked.level == "L3" and "20 Nov" not in asked.text
    for said in ("what do you remember", "remember that I like coffee", "forget everything"):
        assert gate(remembered).ask(said, "mission:2").status == REFUSED


def test_the_brain_changes_nothing_itself_it_hands_remember_and_forget_on(remembered):
    before = MemoryStore(remembered).all()
    for said, name in (("remember that I like coffee", "remember"), ("forget about my sister", "forget"),
                       ("forget everything", "forget")):
        result = gate(remembered).ask(said, "pc")
        assert (result.status, result.route.name) == (MEMORY, name)
    assert MemoryStore(remembered).all() == before


def test_the_brain_refuses_a_secret_before_guardian_is_even_asked(data_dir):
    result = gate(data_dir).ask("remember that my otp is 482916", "pc")
    assert result.status == REFUSED and "never keep secrets" in result.text and "482916" not in result.text


def test_a_memory_line_never_becomes_a_follow_up_that_could_go_to_a_cloud_ai(remembered):
    transport = Transport()
    gateway = gate(remembered, transport)
    gateway.ask("who is the prime minister of India", "pc")
    gateway.ask("what do you remember", "pc")
    gateway.ask("tell me more", "pc")
    assert "Anu" not in json.dumps(transport.sent) and "sister" not in json.dumps(transport.sent)


# --- asking Guardian -----------------------------------------------------------------------------------------

class FakeGuardian:
    def __init__(self, data_dir, verdict="ok", outcome="finished"):
        self.data_dir, self.verdict, self.outcome, self.requests = str(data_dir), verdict, outcome, []

    def __call__(self, message):
        self.requests.append(message)
        if message["op"] == "run":
            if self.verdict != "ok":
                return {"verdict": self.verdict, "reason": "refused for the test"}
            details = dict(message["details"])
            if self.outcome == "finished":
                {"memory.remember": actions.remember, "memory.forget": actions.forget}[message["action"]](self.data_dir, **details)
            return {"verdict": "ok", "run": 1, "pid": 1}
        return {"verdict": "ok", "outcome": self.outcome}


def test_the_keeper_asks_guardian_to_run_each_change_and_only_that(tmp_path):
    guardian = FakeGuardian(tmp_path)
    keeper = conduct.Keeper(tmp_path, guardian, poll=0)
    assert keeper.remember(SISTER, "pc") == "Got it, I'll remember that. It stays on this PC."
    assert keeper.remember(SISTER, "pc") == "I already remember that."
    assert keeper.forget("my sister") == "Done. I forgot 1 line about that."
    assert keeper.forget("my sister") == "I have nothing about that to forget."
    assert keeper.forget("*") == "I had nothing to forget."
    assert {message["op"] for message in guardian.requests} <= {"run", "run_status", "end"}
    assert [message["action"] for message in guardian.requests if message["op"] == "run"] == \
        ["memory.remember"] * 2 + ["memory.forget"] * 3


@pytest.mark.parametrize("guardian", [dict(verdict="deny"), dict(outcome="halted"), dict(outcome="failed")])
def test_when_guardian_refuses_or_stops_it_kairu_says_so_and_keeps_nothing(tmp_path, guardian):
    keeper = conduct.Keeper(tmp_path, FakeGuardian(tmp_path, **guardian), poll=0)
    assert keeper.remember(SISTER, "pc").startswith(conduct.NOTHING) and keeper.forget("*").startswith(conduct.NOTHING)
    assert MemoryStore(tmp_path).all() == []


# --- no authority, and nothing leaves ---------------------------------------------------------------------------

MEMORY_FILES = sorted((ROOT / "kairu" / "memory").glob("*.py"))


@pytest.mark.parametrize("path", MEMORY_FILES, ids=[path.name for path in MEMORY_FILES])
def test_the_memory_holds_no_authority_and_reaches_no_network(path):
    text = path.read_text(encoding="utf-8")
    assert "GuardianClient" not in text and "approve" not in re.findall(r"[\"']op[\"']\s*:\s*[\"'](\w+)", text)
    for module in ("urllib", "http", "socket", "requests", "kairu.brain.providers", "kairu.link", "kairu.research"):
        assert not re.search(rf"^\s*(?:from|import)\s+{re.escape(module)}\b", text, re.MULTILINE), f"{path.name} imports {module}"
    if path.name != "conduct.py":
        assert "kairu.channel" not in text and "from kairu import channel" not in text


# --- through the real Guardian program ---------------------------------------------------------------------------

def test_remember_ask_and_forget_through_guardian_and_nothing_is_sent_or_logged(brain, web, providers):
    told = kairu("ask", f"remember that {SISTER}", timeout=60)
    assert told.returncode == 0, told.stdout + told.stderr
    assert "Got it, I'll remember that" in told.stdout and "L0: answered on this PC, nothing sent" in told.stdout
    asked = kairu("ask", "what is my sister's name?", timeout=60)
    assert f"You told me: {SISTER}." in asked.stdout and "L0" in asked.stdout
    assert SISTER in kairu("ask", "what do you remember", timeout=60).stdout
    assert "never keep secrets" in kairu("ask", "remember that my otp is 482916", timeout=60).stdout
    gone = kairu("ask", "forget about my sister", timeout=60)
    assert "I forgot 1 line about that" in gone.stdout
    assert "I don't remember anything yet" in kairu("ask", "what do you remember", timeout=60).stdout
    started = runs(brain.data_dir)
    assert started["memory.remember"] == ["started", "finished"] and started["memory.forget"] == ["started", "finished"]
    assert providers.heard() == [] and web.queries == []
    log = logged(brain.data_dir)
    assert "Anu" not in log and "sister" not in log and "482916" not in log  # the audit log keeps hashes, never the words


def test_the_dry_run_says_it_stays_on_this_pc(brain, web, providers):
    shown = kairu("ask", "--dry-run", f"remember that {SISTER}", timeout=60)
    assert "Kairu's memory, on this PC (remember)" in shown.stdout and "Nothing was sent" in shown.stdout
    assert not (brain.data_dir / "memory.db").exists() or MemoryStore(brain.data_dir).all() == []
