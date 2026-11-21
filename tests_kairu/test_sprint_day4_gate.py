"""tools/sprint_day4_gate.py works through the real Guardian program, on a pretend PC and a pretend Recycle Bin.

What you would type or press is done by the Owner below, through the same TaskCore the bar uses. The free AI is a stand-in.
"""

import importlib.util
import json
import re
import threading

import pytest
import yaml

from kairu import safemode
from kairu.brain import keys
from kairu.config import ROOT
from kairu.guardian import Refused
from kairu.store import Store
from kairu.tasks import pc
from kairu.tasks.core import TaskCore
from tests_kairu.fake_provider import FakeProviders
from tests_kairu.helpers import PIN, POLICY
from tests_kairu.program import program, program_with_pin  # noqa: F401 (fixtures)

spec = importlib.util.spec_from_file_location("sprint_day4_gate", ROOT / "tools" / "sprint_day4_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
GROQ_KEY = "gsk_" + "k" * 40
gate.day1.ORDER_SECONDS = 20  # an order that never reaches Guardian fails the step quickly here


@pytest.fixture
def providers(monkeypatch):
    fake = FakeProviders()
    monkeypatch.setenv("KAIRU_TEST_PROVIDERS", fake.url)
    yield fake
    fake.close()


@pytest.fixture
def desk(tmp_path, monkeypatch):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "pc.json").write_text(json.dumps({"windows": [{"app": "notepad", "title": "Untitled"}], "apps": {},
                                                "browsers": {"chrome": "C:/apps/chrome.exe"}, "volume": 8, "brightness": 56}))
    monkeypatch.setenv(pc.TEST_PC, str(folder))
    return folder


@pytest.fixture
def config_path(tmp_path, monkeypatch, desk, providers):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "brain": {"public_to_cloud": True, "providers": ["groq"]},
                                    "tasks": {"work_folder": str(tmp_path / "Kairu-files"), "bar_key": "Q"},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


class Owner(gate.Gate):
    """You, at the bar: yes and your PIN for a delete, Refuse for the personal search, yes to a plan, Ctrl+Alt+K when asked."""

    def __init__(self, providers, answer=True):
        super().__init__()
        self.providers, self.answer, self.said, self.threads = providers, answer, [], []
        self.core = TaskCore(self.cfg, self.client, approver=self.card, confirmer=lambda text: self.said.append(f"card: {text}") or True)

    def card(self, decision):
        self.said.append(f"card: {decision.action.name}")
        if decision.action.name == "web.search_private":
            try:
                return self.client.approve(decision.request_id, "", "")
            except Refused:
                return None
        return self.client.approve(decision.request_id, "yes", PIN)

    def say(self, text=""):
        self.said.append(text)
        print(text)

    def ask_here(self, question):
        return "y" if self.answer else "n"

    def typed_here(self):
        return ""

    def wait_until(self, what, seconds=10):
        return super().wait_until(what, min(seconds, 10))

    def type_in_the_bar(self, *orders):
        for order in orders:
            found = re.fullmatch(r"put all the pdfs in Kairu-files into a folder called (\S+)", order)
            if found:  # what a free AI would answer
                self.providers.answers["groq"] = json.dumps({"steps": [
                    {"action": "files.find", "details": {"what": "*.pdf", "when": ""}},
                    {"action": "files.move", "details": {"name": "*.pdf", "to": found.group(1)}}]})
            if order.startswith("wait "):  # this one runs while the gate waits to ask for Ctrl+Alt+K
                thread = threading.Thread(target=lambda: self.said.append(f"reply: {self.core.handle(order)}"), daemon=True)
                thread.start()
                self.threads.append(thread)
            else:
                self.said.append(f"reply: {self.core.handle(order)}")

    def press_the_key(self, what):
        safemode.emergency_stop(Store(self.cfg.data_dir), "Ctrl+Alt+K")

    def leave_safe_mode(self):
        for thread in self.threads:
            thread.join(10)
        self.client.resume("yes", PIN)

    def text(self):
        return "\n".join(self.said)


@pytest.fixture
def owner(program_with_pin, providers):
    keys.save(program_with_pin.data_dir, "groq", GROQ_KEY)
    return Owner(providers)


def test_the_tool_lists_the_new_skills_with_their_tiers(owner):
    assert owner.list_skills()
    text = owner.text()
    for line in ("Low     files.find", "Medium  files.move", "High    files.delete", "Medium  web.open", "Medium  web.search",
                 "Low     task.wait", "No Critical skill exists."):
        assert line in text, line


def test_a_whole_run_passes_and_leaves_no_test_file_behind(owner, desk):
    assert owner.run() == 0, owner.text()
    text = owner.text()
    assert "Result: PASSED  11 of 11" in text and "log PASS" in text and "voice  NOT YET" in text
    assert "kairu guardian quit" in text and "kairu guardian run" in text
    assert not list(owner.folder.rglob(f"{owner.tag}*")) and not list(owner.folder.parent.glob(f"{owner.tag}*"))
    assert owner.pc.volume()[0] == 8  # the plan's volume step never ran
    assert "card: web.search_private" in text and "card: files.delete" in text and "card: Plan: 1) find *.pdf" in text


def test_the_gate_never_takes_away_a_file_that_is_not_its_own(owner):
    mine = owner.folder / "my-own.pdf"
    mine.write_text("the owner's")
    owner.run(9)
    owner_file = list(owner.folder.rglob("my-own.pdf"))
    assert owner_file and owner_file[0].read_text() == "the owner's"
    assert "Kairu-files already has other PDFs (my-own.pdf)" in owner.text()


def test_an_outside_delete_refused_before_guardian_passes_and_one_that_went_through_would_fail(owner, monkeypatch):
    owner.step_5()
    assert owner.results[5][0] and "Guardian asked: False" in owner.text() and "card: files.delete" not in owner.text()
    real = owner.type_in_the_bar

    def careless(*orders):
        for order in orders:
            if "-outside.txt" in order:
                owner.folder.parent.joinpath(f"{owner.tag}-outside.txt").unlink()
            real(order)

    owner.type_in_the_bar = careless
    owner.step_5()
    assert not owner.results[5][0]


def test_saying_no_fails_a_step_and_the_result_is_failed(owner):
    owner.answer = False
    assert owner.run(11) == 1 and "Step 11: FAIL" in owner.text() and "Result: FAILED" in owner.text()


def test_when_guardian_does_not_know_the_new_skills_it_says_how_to_restart_it(owner, monkeypatch):
    real = owner.client.check

    def old_guardian(action, *args):
        decision = real(action, *args)
        name = action if isinstance(action, str) else action.name
        if name in gate.NEW_SKILLS:
            from kairu.guardian import Decision, Verdict
            return Decision(Verdict.DENY, decision.action, None, "this action is not in the policy, and unknown actions are refused")
        return decision

    monkeypatch.setattr(owner.client, "check", old_guardian)
    assert owner.run() == 1 and "NOT RUN" in owner.text() and "kairu guardian quit" in owner.text()
