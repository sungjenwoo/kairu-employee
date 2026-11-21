"""Handling a task through the real Guardian program, on the pretend PC: every step is decided and run by Guardian.

"Open Chrome, then in the search bar type Instagram" is two Guardian actions (apps.open, screen.type); a careful step waits
for the card ("yes" and the PIN); refusing it does nothing; your words stay out of the audit log.
"""

import json
import time

import pytest
import yaml

from kairu import audit, safemode
from kairu.guardian import Refused
from kairu.store import Store
from kairu.tasks import pc, screen
from kairu.tasks.core import TaskCore
from tests_kairu.helpers import PIN, POLICY, alive, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "pc.json").write_text(json.dumps({
        "windows": [{"app": "pythonw", "title": "Kairu bar"}, {"app": "notepad", "title": "Untitled - Notepad"},
                    {"app": "whatsapp", "title": "WhatsApp"}],
        "apps": {"chrome": "C:/apps/chrome.exe", "notepad": "C:/Windows/notepad.exe"},
        "controls": {"chrome": [["box", "Search Google or type a URL"], ["button", "Send"], ["button", "Next"]]},
        "volume": 50, "brightness": 70}))
    monkeypatch.setenv(pc.TEST_PC, str(folder))
    return folder


@pytest.fixture
def config_path(tmp_path, monkeypatch, desk):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "tasks": {"work_folder": str(tmp_path / "Kairu-files")},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


def state(desk) -> dict:
    return json.loads((desk / "pc.json").read_text())


def open_chrome(desk):
    """What apps.open does on a real PC, a moment later: Chrome's window comes to the front."""
    data = state(desk)
    data["windows"] = [{"app": "chrome", "title": "New Tab - Google Chrome"}, *data["windows"]]
    (desk / "pc.json").write_text(json.dumps(data))


def calls(desk):
    log = desk / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def started(data_dir):
    return [row["action"] for row in audit.tail(Store(data_dir), 3000, kind="run") if row["decision"] == "started"]


def logged(data_dir) -> str:
    with Store(data_dir).connect() as db:
        return " ".join(str(row) for row in db.execute("SELECT * FROM audit"))


def core_for(program, approver=None):
    options = {"approver": approver} if approver else {}
    return TaskCore(program.config, program.client, **options)


def test_open_chrome_then_type_instagram_in_the_search_bar(program_with_pin, desk):
    open_chrome(desk)  # on the pretend PC, the window is already there for the step after apps.open
    reply = core_for(program_with_pin).handle("open Chrome, then in the search bar type Instagram")
    assert reply == 'Opened Chrome. Typed "Instagram" in Chrome in the search bar.'
    assert started(program_with_pin.data_dir)[-2:] == ["apps.open", "screen.type"]
    assert calls(desk)[-3:] == ["front chrome", "field chrome search", "type chrome Instagram"]
    assert "Instagram" not in logged(program_with_pin.data_dir)


def test_type_and_press_enter_is_one_step_in_the_address_bar(program_with_pin, desk):
    open_chrome(desk)
    reply = core_for(program_with_pin).handle("in the address bar of chrome type instagram.com and press enter")
    assert reply == 'Typed "instagram.com" in Chrome in the search bar and pressed Enter.'
    assert started(program_with_pin.data_dir)[-1:] == ["screen.type"]


def test_a_careful_click_waits_for_the_card_and_no_means_nothing_happens(program_with_pin, desk):
    open_chrome(desk)
    seen = []

    def refuse(decision):
        seen.append(decision)
        return None

    reply = core_for(program_with_pin, refuse).handle("click send in chrome")
    assert reply == "Not done: you refused it." and seen[0].action.name == "screen.confirm"
    assert not any(line.startswith("click") for line in calls(desk))


def test_a_careful_click_runs_once_after_yes_and_the_pin(program_with_pin, desk):
    open_chrome(desk)
    client = program_with_pin.client
    reply = core_for(program_with_pin, lambda decision: client.approve(decision.request_id, "yes", PIN)).handle("click send in chrome")
    assert reply == 'Clicked "Send" in Chrome.' and calls(desk).count("click chrome Send") == 1


def test_an_app_not_on_the_safe_list_is_tried_then_asks_for_the_card(program_with_pin, desk):
    client, asked = program_with_pin.client, []

    def approve(decision):
        asked.append(decision.action.name)
        return client.approve(decision.request_id, "yes", PIN)

    reply = core_for(program_with_pin, approve).handle("type hello in whatsapp")
    assert reply == 'Typed "hello" in Whatsapp.' and asked == ["screen.confirm"]
    assert started(program_with_pin.data_dir)[-2:] == ["screen.type", "screen.confirm"]
    assert state(desk)["typed"] == {"whatsapp": "hello"}


def test_a_wrong_pin_types_nothing(program_with_pin, desk):
    client = program_with_pin.client
    reply = core_for(program_with_pin, lambda decision: client.approve(decision.request_id, "yes", "000000")).handle(
        "type hello in whatsapp")
    assert reply.startswith("Not done") and "typed" not in state(desk)


def test_screen_confirm_cannot_run_without_an_approval_even_if_asked_directly(program_with_pin, desk):
    from kairu.guardian import Action
    with pytest.raises(Refused):
        program_with_pin.client.run(Action("screen.confirm", {"verb": "type", "app": "whatsapp", "what": "hi", "job": "c" * 16}))
    assert "typed" not in state(desk)


def test_kairus_own_bar_is_never_typed_into(program_with_pin, desk):
    reply = core_for(program_with_pin).handle("type yes in pythonw")
    assert reply.startswith("Refused") and "typed" not in state(desk)


def test_a_stop_ends_typing_within_a_second_and_the_rest_never_runs(program_with_pin, desk):
    open_chrome(desk)
    data = state(desk)
    data["slow"] = 20
    (desk / "pc.json").write_text(json.dumps(data))
    core = core_for(program_with_pin)
    import threading
    said = []
    worker = threading.Thread(target=lambda: said.append(core.handle("type hello in notepad, then press ctrl s")))
    worker.start()
    wait_for(lambda: "screen.type" in started(program_with_pin.data_dir), timeout=10)
    time.sleep(0.3)
    stopped_at = time.monotonic()
    safemode.emergency_stop(Store(program_with_pin.data_dir), "test")
    worker.join(timeout=10)
    assert time.monotonic() - stopped_at < 5 and said and "stopped" in said[0].lower()
    assert "press notepad ctrl+s" not in calls(desk) and "typed" not in state(desk)


def test_open_chrome_then_type_then_search_as_three_orders(program_with_pin, desk):
    """Omesh's way: one order at a time, each carrying on from the last."""
    core = core_for(program_with_pin)
    assert core.handle("open Chrome") == "Opened Chrome."
    open_chrome(desk)  # Chrome's window comes up; the bar is still in front of it, as it is while you type the next order
    data = state(desk)
    data["windows"] = [data["windows"][1], data["windows"][0], *data["windows"][2:]]
    (desk / "pc.json").write_text(json.dumps(data))
    assert core.handle("on search bar type Instagram") == 'Typed "Instagram" in Chrome in the search bar.'
    assert core.handle("search") == "Searched in Chrome."
    assert calls(desk)[-1] == "press chrome enter"
    assert started(program_with_pin.data_dir)[-3:] == ["apps.open", "screen.type", "screen.press"]  # no card, no PIN
