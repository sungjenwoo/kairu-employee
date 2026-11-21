"""Phase D4 (PHONE.md): a mission from the phone is an order that may wait in the Gate while the PC is off (up to 12 hours,
as every queued Link message) and runs through the task core when Guardian next runs, each step decided by Guardian. A
plain-text mission is still kept as a request only, and a mission can carry no action but the order. The real Guardian
program, the stand-in relay and phone, and the pretend PC (KAIRU_TEST_PC): nothing really opens, closes or restarts.
"""

import json
import time

import pytest
import yaml

from kairu import client
from kairu.link import store as link_store
from tests_kairu.helpers import POLICY, alive, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_link_program import command, pair_phone, power, relay, rows  # noqa: F401 (fixtures)
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


def mission(phone, words: str, until, seconds: float = 45):
    since = int(time.time()) - 1
    phone.send("mission", command("task.order", order=words))
    return phone.replies(since, seconds, until=until)


def test_a_mission_runs_through_the_task_core_and_the_answer_comes_back(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    told = mission(phone, "open Notepad and set volume to 20", lambda got: any("Volume 20" in m["body"] for m in got))
    assert any(m["body"].startswith("Your mission reached the PC") for m in told)
    assert any(m["body"] == "Opened Notepad. Volume 20." for m in told)
    assert calls(desk) == ["launch C:/Windows/notepad.exe", "volume 20 None"]


def test_a_mission_that_waited_in_the_gate_while_guardian_was_off_runs_when_it_starts(program_with_pin, tmp_path, relay,
                                                                                    desk):
    phone = pair_phone(program_with_pin, tmp_path)
    config = program_with_pin.config
    client.quit_guardian(config)
    with link_store.LinkStore(config.data_dir).connect() as db:  # as if the phone had been paired three hours ago
        db.execute("UPDATE devices SET paired_at = ?", (time.time() - 3 * 3600,))
    wait_for(lambda: not alive(program_with_pin.pid), timeout=10)
    since = int(time.time()) - 1
    relay.publish(phone.state["topic"], phone.envelope("mission", command("task.order", order="open Notepad"), age=7200),
                  when=time.time() - 7200)  # sent two hours ago, while the PC was off
    relay.publish(phone.state["topic"], phone.envelope("command", command("task.order", order="set volume to 20"),
                                                       age=7200), when=time.time() - 7200)  # an order never runs late
    again = start(config)
    try:
        told = phone.replies(since, 45, until=lambda got: any("Opened Notepad" in m["body"] for m in got)
                             and any("too old" in m["body"] for m in got))
        assert any(m["body"].startswith("Your mission reached the PC") for m in told)
        assert calls(desk) == ["launch C:/Windows/notepad.exe"]
    finally:
        end(again)
        program_with_pin.pid = again.pid


def test_a_high_step_in_a_mission_still_waits_for_approval(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    mission(phone, "restart", lambda got: any("kairu link approve" in m["body"] for m in got))
    [waiting] = program_with_pin.client.link_waiting()
    assert waiting["action"] == "system.restart"
    time.sleep(0.5)
    assert not any("restart" in line for line in calls(desk))  # nothing before "yes" and the PIN (or the fingerprint)


def test_a_plain_mission_is_still_a_request_only_and_no_other_action_rides_on_a_mission(program_with_pin, tmp_path):
    phone = pair_phone(program_with_pin, tmp_path)
    since = int(time.time()) - 1
    phone.send("mission", "Book the train, my PIN is 482916")
    phone.send("mission", command("demo.count", seconds=0.1, quiet=True))
    told = phone.replies(since, 30, until=lambda got: sum("as a request only" in m["body"] for m in got) >= 2)
    assert sum("as a request only" in m["body"] for m in told) == 2
    started = {row["action"] for row in rows(program_with_pin.data_dir, "run") if row["decision"] == "started"}
    assert "demo.count" not in started and "task.order" not in started


def test_a_missions_words_never_reach_the_audit_log(program_with_pin, tmp_path, desk):
    phone = pair_phone(program_with_pin, tmp_path)
    told = mission(phone, "make a file called secretplan.txt saying launch at dawn",
                   lambda got: any("secretplan.txt" in m["body"] for m in got))
    assert any("secretplan.txt" in m["body"] for m in told)  # the step ran, and only the phone heard its name
    logged = json.dumps(rows(program_with_pin.data_dir))
    assert "secretplan" not in logged and "launch at dawn" not in logged
