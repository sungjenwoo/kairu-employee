"""tools/sprint_day1_gate.py works through the real Guardian program, on a pretend PC, with its pass and fail lines.

What you would type or press is done by the Gate below, through the same TaskCore the bar uses.
"""

import importlib.util
import json
import os
import time

import pytest
import yaml

from kairu import safemode
from kairu.brain import keys
from kairu.config import ROOT
from kairu.guardian import Refused
from kairu.store import Store
from kairu.tasks import pc
from kairu.tasks.core import TaskCore
from tests_kairu.helpers import PIN, POLICY
from tests_kairu.program import program, program_with_pin  # noqa: F401 (fixtures)
from tests_kairu.test_tasks_program import GROQ_KEY, calls

spec = importlib.util.spec_from_file_location("sprint_day1_gate", ROOT / "tools" / "sprint_day1_gate.py")
sprint_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sprint_gate)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "pc.json").write_text(json.dumps({"windows": [], "apps": {"chrome": "C:/apps/chrome.exe", "notepad": "C:/Windows/notepad.exe"},
                                                "volume": 8, "brightness": 56}))
    monkeypatch.setenv(pc.TEST_PC, str(folder))
    return folder


@pytest.fixture
def config_path(tmp_path, monkeypatch, desk):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "tasks": {"work_folder": str(tmp_path / "Kairu-files"), "bar_key": "Q"},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


class Owner(sprint_gate.Gate):
    """You, at the bar: orders go through the task core; opening and closing a pretend window shows in the pretend PC.

    `misses`: orders you first type into the gate's own window by mistake, then again in the bar once it says so.
    `slow`: orders you type only `delay` seconds after the gate asks. `terminal`: what waits in the gate's window, the
    way Windows' console keeps typed lines until a question reads them.
    """

    def __init__(self, answer=True):
        super().__init__()
        self.answer, self.said, self.showing, self.chrome_on_left = answer, [], False, False
        self.misses, self.slow, self.delay = set(), set(), 0.0
        self.terminal, self._later = [], []
        self.core = TaskCore(self.cfg, self.client, approver=self.refuse_the_card)

    def refuse_the_card(self, decision):
        try:
            return self.client.approve(decision.request_id, "", "")
        except Refused:
            return None

    def say(self, text=""):
        self.said.append(text)
        print(text)

    def ask_here(self, question):
        if self.terminal:  # as input() does: the first line waiting in the window is the answer
            return self.terminal.pop(0)
        return "y" if self.answer else "n"

    def typed_here(self):
        typed = "".join(self.terminal)
        self.terminal.clear()
        now = time.monotonic()
        for due, order in [item for item in self._later if item[0] <= now]:
            self._later.remove((due, order))
            self._in_the_bar(order)
        return typed

    def wait_until(self, what, seconds=10):
        return super().wait_until(what, min(seconds, 10))

    def type_in_the_bar(self, *orders):
        for order in orders:
            if order in self.misses:  # into the gate's own window; again in the bar once the gate says so
                self.misses.discard(order)
                self.terminal.append(order + "\r")
                self._later.append((time.monotonic(), order))
            elif order in self.slow:
                self.slow.discard(order)
                self._later.append((time.monotonic() + self.delay, order))
            else:
                self._in_the_bar(order)

    def _in_the_bar(self, *orders):
        for order in orders:
            seen = len(calls(self.pc.folder))
            self.said.append(f"reply: {self.core.handle(order)}")
            for call in calls(self.pc.folder)[seen:]:
                state = self.pc.state()
                if call.startswith("launch"):
                    app = "chrome" if "chrome" in call else "notepad"
                    if not any(item["app"] == app for item in state["windows"]):
                        self.pc._change("window", windows=state["windows"] + [{"app": app, "title": app}])
                if call == "arrange chrome left":
                    self.chrome_on_left = True

    def window_rect(self, window):
        return (0, 0, 960, 1000) if self.chrome_on_left else (100, 100, 400, 400)

    def screen_width(self):
        return 1920

    def bar_window(self):
        return self.showing

    def press_the_key(self, what):
        self.showing = not self.showing

    def press_stop(self):
        safemode.emergency_stop(Store(self.cfg.data_dir), "the Kairu bar")

    def leave_safe_mode(self):
        self.client.resume("yes", PIN)

    def text(self):
        return "\n".join(self.said)


@pytest.fixture
def owner(program_with_pin):
    keys.save(program_with_pin.data_dir, "groq", GROQ_KEY)
    return Owner()


def test_the_tool_lists_every_skill_with_its_tier_and_no_critical_one(owner):
    assert owner.list_skills()
    text = owner.text()
    assert "Low     apps.open" in text and "High    system.restart" in text and "No Critical skill exists." in text


def test_a_whole_run_gives_one_clear_result_and_puts_things_back(owner, desk):
    assert owner.run() == 0, owner.text()
    assert "Result: PASSED  8 of 8" in owner.text()
    assert owner.pc.volume()[0] == 8 and owner.pc.brightness() == 56  # as they were
    assert "restart" not in calls(desk)  # refused on the card


def test_an_order_typed_into_the_gates_own_window_is_caught_and_then_counted_from_the_bar(owner):
    """Gate step 2, 6 Nov: "open Chrome" never reached Guardian. The gate now says where it went, and waits for the bar."""
    owner.misses = {"open Chrome"}
    assert owner.run(2) == 0, owner.text()
    assert "That went into this window, not the bar: 'open Chrome'" in owner.text() and owner.results[2][0]


def test_an_order_typed_late_is_waited_for(owner, monkeypatch):
    """Gate step 4, 6 Nov: the gate stopped waiting for "volume 30" before it was typed, and said nothing."""
    monkeypatch.setattr(sprint_gate, "WAIT_SECONDS", 0.5)
    owner.slow, owner.delay = {"volume 30"}, 2.0
    assert owner.run(4) == 0, owner.text()
    assert owner.results[4][0] and "(read 30)" in owner.text()


def test_what_was_typed_into_the_gates_window_never_answers_a_question(owner):
    owner.terminal = ["open Chrome\r"]
    assert owner.yes("Did it work?") is True
    assert "not the bar: 'open Chrome'" in owner.text()


def test_each_order_of_step_2_must_reach_guardian_on_its_own(owner, desk):
    """Chrome already open, and only "open Notepad" typed: the old gate could pass a step with one order missing."""
    owner.misses = {"open Chrome"}
    owner._later.clear()

    def forgets_to_retype():
        typed = "".join(owner.terminal)
        owner.terminal.clear()
        return typed

    owner.typed_here = forgets_to_retype
    monkeypatch_order = sprint_gate.ORDER_SECONDS
    sprint_gate.ORDER_SECONDS = 2
    try:
        owner.step_2()
    finally:
        sprint_gate.ORDER_SECONDS = monkeypatch_order
    assert not owner.results[2][0] and "Chrome: order reached Guardian False" in owner.text()


def test_one_step_can_be_run_again(owner):
    assert owner.run(4) == 0, owner.text()
    assert "PART PASSED  1 of 1" in owner.text() and "the gate needs all 8" in owner.text()


def test_a_failed_step_says_fail_and_the_result_is_failed(owner, desk):
    owner.answer = False
    assert owner.run(4) == 1
    assert "Step 4: FAIL" in owner.text() and "Result: FAILED" in owner.text()


def test_the_rename_outside_must_end_as_a_refusal(owner):
    owner.step_7()
    assert owner.results[7][0] and "the rename outside ended as: refused" in owner.text()


def test_a_rename_outside_that_went_through_would_fail_the_step(owner, monkeypatch):
    """If the fence ever let it through, the outside file would be gone, and the step must say so."""
    real_rename = owner.type_in_the_bar

    def careless(*orders):
        for order in orders:
            if " outside" in order or "-outside" in order:
                outside = order.split("rename ", 1)[1].split(" to ")[0]
                os.remove(outside)
            real_rename(order)

    owner.type_in_the_bar = careless
    owner.step_7()
    assert not owner.results[7][0] and "Step 7: FAIL" in owner.text()


def test_in_safe_mode_it_says_what_to_do_and_runs_nothing(owner):
    safemode.emergency_stop(Store(owner.cfg.data_dir), "test")
    assert owner.run() == 1
    assert "Safe Mode" in owner.text() and "NOT RUN" in owner.text()


def test_the_tool_names_your_chosen_key(owner):
    owner.step_1()
    assert "Ctrl+Alt+Q" in owner.text() and owner.results[1][0]
