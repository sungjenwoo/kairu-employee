"""tools/research_gate.py: the hand gate test works through the real Guardian program, with its pass and fail lines.

Stand-ins for the web, the AI, the Gate and the phone. What you would type or press is done by the Gate below.
"""

import importlib.util
import os

import pytest

from kairu import safemode
from kairu.config import ROOT
from kairu.research.search import TEST_SEARCH
from kairu.store import Store
from tests_kairu.helpers import PIN, kairu
from tests_kairu.program import program, program_with_pin  # noqa: F401 (fixtures)
from tests_kairu.test_link_program import pair_phone
from tests_kairu.test_research_program import PAGE_WORDS, brain, config_path, providers, relay, research_on, web  # noqa: F401

spec = importlib.util.spec_from_file_location("research_gate", ROOT / "tools" / "research_gate.py")
research_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research_gate)


class Answering(research_gate.Gate):
    """You, typing: every yes/no gets `answer`."""

    def __init__(self, answer=True, stdin=None):
        super().__init__(stdin)
        self.answer, self.said, self.phone, self.client_program = answer, [], None, None

    def say(self, text=""):
        self.said.append(text)
        print(text)

    def yes(self, question):
        self.say(f"asked: {question}")
        return self.answer

    def tell_to_press_the_keys(self):
        self.say("presses Ctrl+Alt+K")
        safemode.emergency_stop(Store(self.cfg.data_dir), "the gate tool's test")

    def tell_to_use_the_phone(self):
        self.phone.send("ask", research_gate.NEWS)

    def leave_safe_mode(self):
        self.client.resume("yes", PIN)

    def text(self):
        return "\n".join(self.said)


def test_steps_1_and_2_pass_on_a_real_answer_and_its_sources(brain, web, providers):
    gate = Answering()
    assert gate.ready()
    gate.step_1()
    gate.step_2()
    assert gate.results[1][0] and gate.results[2][0], gate.text()
    assert "Step 1: PASS" in gate.text() and "Step 2: PASS" in gate.text()


def test_step_1_fails_clearly_when_you_say_the_answer_is_wrong(brain, web, providers):
    gate = Answering(answer=False)
    gate.step_1()
    assert not gate.results[1][0] and "Step 1: FAIL" in gate.text()


def test_step_1_fails_clearly_when_the_search_fails(brain, web, providers):
    web.search_status = 500
    gate = Answering()
    gate.step_1()
    assert not gate.results[1][0] and "the search failed" in gate.text()


def test_step_2_fails_clearly_with_no_sources(brain, web, providers):
    gate = Answering()
    gate.step_2()
    assert not gate.results[2][0] and "Step 2: FAIL" in gate.text()


def test_step_3_passes_when_you_type_no_and_nothing_is_searched(brain, web, providers, tmp_path):
    answers = tmp_path / "typed.txt"
    answers.write_text("no\n")
    with open(answers) as typed:
        gate = Answering(stdin=typed)
        gate.step_3()
    assert gate.results[3][0], gate.text()
    assert web.queries == [] and providers.heard() == []


def test_steps_4_and_6_restart_guardian_with_the_stand_in_and_put_it_back(brain, providers, monkeypatch):
    """The real page reader, Guardian and stop; the stand-in web is the tool's own."""
    monkeypatch.delenv(TEST_SEARCH, raising=False)
    gate = Answering()
    first = gate.client.status()["pid"]
    gate.with_the_stand_in([4, 6])
    assert gate.results[4][0] and gate.results[6][0], gate.text()
    assert TEST_SEARCH not in os.environ
    state = gate.client.status()
    assert state["mode"] == "normal" and state["pid"] != first
    sent = providers.heard()[-1]["body"]["messages"][-1]["content"]
    assert research_gate.FACT in sent and research_gate.ORDER not in sent and f"> {research_gate.SNEAKY}" in sent
    brain.pid = state["pid"]


def test_step_4_is_not_run_if_you_say_no_to_the_restart(brain, providers):
    gate = Answering(answer=False)
    first = gate.client.status()["pid"]
    gate.with_the_stand_in([4, 6])
    assert not gate.results[4][0] and not gate.results[6][0] and gate.client.status()["pid"] == first


def test_step_5_passes_when_the_phones_question_is_searched_and_answered(brain, tmp_path, web, providers):
    gate = Answering()
    gate.phone = pair_phone(brain, tmp_path)
    gate.step_5()
    assert gate.results[5][0], gate.text()
    assert web.queries and web.read


@pytest.mark.parametrize("research_on", [False])
def test_with_research_off_it_says_what_to_do_and_runs_nothing(brain, web, providers):
    gate = Answering()
    assert gate.run() == 1
    assert "research: enabled: true" in gate.text() and "NOT RUN" in gate.text() and web.queries == []


def test_the_whole_run_gives_one_clear_result(brain, tmp_path, web, providers, monkeypatch):
    answers = tmp_path / "typed.txt"
    answers.write_text("no\n")
    with open(answers) as typed:
        gate = Answering(stdin=typed)
        gate.phone = pair_phone(brain, tmp_path)
        code = gate.run()
    assert code == 0, gate.text()
    assert "Result: PASSED  6 of 6" in gate.text() and PAGE_WORDS not in gate.text().split("The gate test:")[1]
    brain.pid = gate.client.status()["pid"]
    assert kairu("status").returncode == 0
