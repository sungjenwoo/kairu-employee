"""Phase D3 (PHONE.md): an order typed on the phone runs on the PC through the task core, step by step, with Guardian deciding
each step; a High step waits for the phone's fingerprint (or the PIN at the PC). The real Guardian program, the stand-in relay
and phone, and the pretend PC (KAIRU_TEST_PC): nothing really opens, closes or restarts.
"""

import time

import pytest
import yaml
from nacl.signing import SigningKey

from tests_kairu.helpers import PIN, POLICY, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_link_program import command, pair_phone, power, relay  # noqa: F401 (fixtures)
from tests_kairu.test_phone_approvals import card_of, enrolled, signed
from tests_kairu.test_tasks_program import calls, desk, providers, work  # noqa: F401 (fixtures)


@pytest.fixture
def config_path(tmp_path, monkeypatch, relay, power, desk, work, providers):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "link": {"enabled": True, "relay": relay.url},
                                    "brain": {"public_to_cloud": True, "providers": ["groq"]},
                                    "tasks": {"work_folder": str(work)},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


def order(phone, words: str, until, seconds: float = 45):
    since = int(time.time()) - 1
    phone.send("command", command("task.order", order=words, device="dev-0000000000000000"))
    return phone.replies(since, seconds, until=until)


def test_an_order_from_the_phone_runs_on_the_pc_and_the_answer_comes_back(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    told = order(phone, "open Notepad and set volume to 20", lambda got: any("Volume 20" in m["body"] for m in got))
    assert any(m["body"].startswith("On it: open Notepad → volume 20") for m in told)
    assert any(m["body"] == "Opened Notepad. Volume 20." for m in told)
    assert calls(desk) == ["launch C:/Windows/notepad.exe", "volume 20 None"]


def test_a_high_step_waits_for_the_phones_fingerprint(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    key = SigningKey.generate()
    enrolled(program_with_pin, phone, key)
    told = order(phone, "restart", lambda got: any("kairu_card" in m["body"] for m in got))
    card = card_of([m for m in told if "kairu_card" in m["body"]][-1])
    assert card["action"] == "system.restart"
    time.sleep(0.5)
    assert not any("restart" in line for line in calls(desk))  # nothing before the fingerprint
    since = int(time.time()) - 1
    phone.send("command", command("link.approve", number=card["number"], signature=signed(key, phone, card)))
    phone.replies(since, 30, until=lambda got: any("Approved system.restart with your fingerprint" in m["body"] for m in got))
    wait_for(lambda: any("restart" in line for line in calls(desk)), timeout=30)


def test_a_refused_step_does_nothing_and_says_so(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    enrolled(program_with_pin, phone, SigningKey.generate())
    told = order(phone, "restart", lambda got: any("kairu_card" in m["body"] for m in got))
    card = card_of([m for m in told if "kairu_card" in m["body"]][-1])
    since = int(time.time()) - 1
    phone.send("command", command("link.refuse", number=card["number"]))
    told = phone.replies(since, 30, until=lambda got: any("Not done" in m["body"] for m in got))
    assert any("Not done" in m["body"] for m in told) and not any("restart" in line for line in calls(desk))


def test_without_fingerprint_approval_the_pin_at_the_pc_approves_a_step(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    order(phone, "restart", lambda got: any("kairu link approve" in m["body"] for m in got))
    [waiting] = program_with_pin.client.link_waiting()
    assert waiting["action"] == "system.restart"
    program_with_pin.client.link_approve(waiting["number"], "yes", PIN)
    wait_for(lambda: any("restart" in line for line in calls(desk)), timeout=30)
