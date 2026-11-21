"""Protection (Phase J) through the real Guardian program: the monitors start, report, stop and come back.

These start Guardian with protect.enabled, as the shipped config.yaml does, and use the kairu command as you would.
"""

import json
import sys
import time
from datetime import timedelta

import pytest
import yaml

from kairu import audit, channel, safemode
from kairu.guardian import Action, Refused, Verdict
from kairu.guardian_program import Protector
from kairu.protect.store import ProtectStore
from kairu.store import Store
from tests_kairu.helpers import PIN, POLICY, alive, kairu, wait_for
from tests_kairu.program import program, program_with_pin  # noqa: F401 (fixtures)

LIMIT = 1.0


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Like conftest's, with protection on and quick rounds."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "protect": {"enabled": True, "check_seconds": 1, "gmail_seconds": 60},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


def watching(program):
    return [run for run in program.client.status()["running"] if run["action"] == "protect.watch"]


def rows(program, kind):
    return audit.tail(Store(program.config.data_dir), 1000, kind=kind)


def add_deadline_soon(hours=20):
    from kairu.protect.deadlines import local_now
    due = local_now() + timedelta(hours=hours)
    added = kairu("deadline", "add", "Hackathon submission", due.strftime("%Y-%m-%d"), due.strftime("%H:%M"))
    assert added.returncode == 0, added.stdout + added.stderr
    return added.stdout


def test_with_nothing_to_watch_guardian_starts_the_monitors_and_they_end_by_themselves(program):
    wait_for(lambda: any(row["action"] == "protect.watch" and row["decision"] in ("finished", "failed")
                         for row in rows(program, "run")), timeout=20)
    outcomes = [row["decision"] for row in rows(program, "run") if row["action"] == "protect.watch"]
    assert outcomes == ["started", "finished"]
    time.sleep(2)  # and Guardian does not start them again and again
    assert [row["decision"] for row in rows(program, "run") if row["action"] == "protect.watch"] == outcomes
    assert "nothing connected yet" in kairu("status").stdout or "monitors not running" in kairu("status").stdout


def test_a_deadline_tomorrow_gives_a_clear_alert_recorded_without_its_words(program):
    said = add_deadline_soon()
    assert "Added deadline 1: Hackathon submission" in said and "Reminders come 3 days" in said
    store = ProtectStore(program.data_dir)
    wait_for(lambda: store.alerts(), timeout=20)
    alert = store.alerts()[0]
    assert alert.kind == "deadline_soon" and alert.title.startswith("Due ") and alert.title.endswith(": Hackathon submission")
    assert alert.classification == "Confirmed fact"
    wait_for(lambda: rows(program, "alert"), timeout=10)
    row = rows(program, "alert")[0]
    assert (row["action"], row["decision"]) == ("protect.deadlines", "deadline_soon")
    assert set(row["details"]) == {"alert", "severity", "fingerprint"} and "Hackathon" not in json.dumps(row)
    assert program.client.status()["last_popup"][0] == "Kairu: Deadline coming up"
    if sys.platform == "win32" and program.client.status()["tray"] == "shown":  # the taskbar may not be ready on a CI machine
        wait_for(lambda: program.client.status()["tray_popup"] == program.client.status()["last_popup"], timeout=5)
        print(f"\n  tray pop-up shown: {program.client.status()['tray_popup'][0]}")

    listed = kairu("alerts").stdout
    assert f"#{alert.id}" in listed and "Hackathon submission" in listed
    shown = kairu("alerts", "show", str(alert.id)).stdout
    assert "Confirmed fact" in shown and "Due:" in shown and "kairu deadline remove 1" in shown
    assert kairu("alerts", "dismiss", str(alert.id)).returncode == 0
    assert store.alert(alert.id).status == "dismissed" and "No new alerts" in kairu("alerts").stdout
    assert "it never means everything is safe" in kairu("alerts").stdout
    status = kairu("protect", "status").stdout
    assert "running inside Guardian" in status and "deadlines: Active: 1 open" in status


def test_kairu_stop_ends_the_monitors_within_1_second_and_they_come_back_after_resume(program_with_pin):
    add_deadline_soon(hours=100)  # something to watch, with no reminder yet
    wait_for(lambda: watching(program_with_pin), timeout=20)
    pid = watching(program_with_pin)[0]["pid"]
    started = time.monotonic()
    assert kairu("stop").returncode == 0
    wait_for(lambda: not alive(pid), timeout=5, every=0.01)
    elapsed = time.monotonic() - started
    assert elapsed < LIMIT + 0.5, f"took {elapsed:.3f} s"  # includes starting Python for `kairu stop`
    print(f"\n  `kairu stop` -> protect.watch gone in {elapsed:.3f} s")
    time.sleep(3)
    assert watching(program_with_pin) == []  # Safe Mode: Guardian starts nothing
    program_with_pin.client.resume("yes", PIN)
    wait_for(lambda: watching(program_with_pin), timeout=10)
    gap_free = ProtectStore(program_with_pin.data_dir).alerts()
    assert all(alert.kind != "deadline_soon" for alert in gap_free)


def test_only_one_monitor_program_runs_and_no_request_can_point_it_elsewhere(program, tmp_path):
    add_deadline_soon(hours=100)
    wait_for(lambda: watching(program), timeout=20)
    with pytest.raises(Refused, match="already running"):
        program.client.run(Action("protect.watch"))
    for name, details in [("protect.watch", {"data_dir": str(tmp_path)}), ("deadline.add", {"title": "x", "due": "2030-01-01T00:00+00:00",
                                                                                         "data_dir": str(tmp_path)}),
                          ("protect.watch", {"check_seconds": 0.001})]:
        with pytest.raises(Refused, match="takes only"):
            program.client.run(Action(name, details))
    assert not (tmp_path / "protection.db").exists()


def test_connecting_gmail_needs_yes_and_the_pin(program):
    decision = program.client.check(Action("protect.connect_email", {"client_file": "C:/x.json"}))
    assert decision.verdict is Verdict.NEEDS_APPROVAL and "read-only access to your Gmail" in decision.description
    with pytest.raises(Refused, match="not approved"):
        program.client.run(Action("protect.connect_email", {"client_file": "C:/x.json"}))


def test_a_wrong_client_file_is_refused_before_anything_is_approved(program, tmp_path):
    wrong = tmp_path / "client.json"
    wrong.write_text(json.dumps({"web": {"client_id": "x"}}))
    said = kairu("protect", "connect-gmail", str(wrong))
    assert said.returncode == 1 and "Desktop app" in said.stdout
    assert not [row for row in rows(program, "check") if row["action"] == "protect.connect_email"]


def test_guardian_takes_only_well_formed_reports(program):
    good = {"op": "report", "source": "gmail", "kind": "phishing", "severity": "high", "alert": 7, "fingerprint": "a" * 64}
    assert channel.request(program.data_dir, good)["verdict"] == "ok"
    for change in [{"kind": "run_this"}, {"source": "bank"}, {"severity": "critical"}, {"fingerprint": "zz"},
                   {"alert": "7"}, {"alert": 0}, {"text": "Your account is blocked"}, {"action": "files.delete"}]:
        message = {**good, **change}
        assert channel.request(program.data_dir, message)["verdict"] == "deny", change
    reported = [row for row in rows(program, "alert")]
    assert len(reported) == 1 and reported[0]["details"]["fingerprint"] == "a" * 64


def test_protection_changes_wait_while_in_safe_mode_but_the_read_only_monitors_may_be_started(program_with_pin):
    assert kairu("stop").returncode == 0
    said = kairu("deadline", "add", "Report", "2030-01-01")
    assert said.returncode == 1 and "Safe Mode" in said.stdout
    started = kairu("protect", "start").stdout
    assert "started" in started or "already running" in started


# --- the Protector, in this process -------------------------------------------------------------------

class FakeRun:
    def __init__(self, action="protect.watch"):
        self.action, self.outcome = action, None


class FakeRunner:
    def __init__(self):
        self.runs = []

    def running(self):
        return [run for run in self.runs if run.outcome is None]


class FakeService:
    """What the Protector uses of Guardian's Service: the store, the runner, _run and runs."""

    def __init__(self, store):
        self.store, self.quit_requested, self.runner, self.runs = store, False, FakeRunner(), {}

    @property
    def started(self):
        return self.runner.runs

    def _run(self, action):
        run = FakeRun(action)
        self.runner.runs.append(run)
        self.runs[len(self.runner.runs)] = run
        return {"verdict": "ok", "run": len(self.runner.runs), "pid": 1}


@pytest.fixture
def protector(guardian, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    service = FakeService(guardian.store)
    return Protector(service, log=lambda text: None), service, clock


def end(service, outcome):
    service.runner.runs[-1].outcome = outcome


def test_the_protector_restarts_a_failed_monitor_after_a_wait_that_grows(protector):
    keeper, service, clock = protector
    keeper.tick()
    assert len(service.started) == 1
    waits = []
    for _ in range(4):
        end(service, "failed")
        keeper.tick()
        before = len(service.started)
        moment = clock[0]
        while len(service.started) == before:
            clock[0] += 5
            keeper.tick()
        waits.append(clock[0] - moment)
    assert waits == [30, 120, 600, 1800]


def test_the_protector_waits_after_a_clean_end_and_starts_again_after_a_resume(protector, guardian, with_pin):
    keeper, service, clock = protector
    keeper.tick()
    end(service, "finished")  # nothing to watch
    for _ in range(10):
        clock[0] += 3600
        keeper.tick()
    assert len(service.started) == 1
    safemode.emergency_stop(guardian.store, "test")
    keeper.tick()
    guardian.resume("yes", PIN)
    keeper.tick()
    assert len(service.started) == 2


def test_the_protector_starts_nothing_in_safe_mode(protector, guardian):
    keeper, service, clock = protector
    safemode.enter(guardian.store, "test")
    for _ in range(5):
        clock[0] += 3600
        keeper.tick()
    assert service.started == []


def test_the_check_can_pause_guardian_while_its_monitors_run(program, config, config_path):
    from kairu import client
    add_deadline_soon(hours=100)
    wait_for(lambda: watching(program), timeout=20)
    assert client.pause_for_check(config) is True  # the monitors do not block the check
    wait_for(lambda: not alive(program.pid))
    client.resume_after_check(config, config_path, was_running=True)
    back = client.GuardianClient(config, start_if_down=False)
    program.pid = back.status()["pid"]
    wait_for(lambda: watching(program), timeout=20)  # and they come back with Guardian


def test_the_check_still_refuses_while_other_actions_run(program, config):
    from kairu import client
    program.client.run(Action("demo.count", {"seconds": 60, "quiet": True}))
    with pytest.raises(Refused, match="running actions"):
        client.pause_for_check(config)


def test_status_says_starting_until_the_first_check_of_a_newly_approved_source(program, tmp_path, monkeypatch):
    from pathlib import Path
    from kairu.protect import actions
    home = tmp_path / "home"  # on Windows tmp_path is inside AppData, which Kairu refuses to watch
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    folder = tmp_path / "Downloads"
    folder.mkdir()
    actions.watch_pc(str(program.data_dir), str(folder), devices=False, security=False)
    said = kairu("protect", "status").stdout
    assert "folders:   Starting" in said or "folders:   Active" in said, said
    assert "devices:   Not set up" in said
