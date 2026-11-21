"""Mission Mode (Phase C2): only while charging, the lid setting saved first and ALWAYS put back, and the limits.

These use a stand-in for the PC's power (KAIRU_TEST_POWER, kairu/mission.py), so they never touch your real lid
setting. Two Windows tests read the real setting and write the same value back, which changes nothing.
The paths through the real Guardian program (off, a stop, Guardian ending, a crash) are in test_link_program.py.
"""

import json
import sys
import threading
import time

import pytest

from kairu import mission
from tests_kairu.helpers import kairu, wait_for


@pytest.fixture
def pc(tmp_path, monkeypatch):
    """The stand-in power: plugged in, lid "Sleep" on mains, cool and quiet."""
    folder = tmp_path / "power"
    folder.mkdir()
    power = mission.StandIn(folder)
    for name, value in (("ac", True), ("scheme", "stand-in-plan"), ("lid_ac", 1), ("awake", False), ("celsius", None),
                        ("cpu", 5)):
        power._put(name, value)
    monkeypatch.setenv("KAIRU_TEST_POWER", str(folder))
    monkeypatch.setattr(mission, "CHECK_SECONDS", 0.05)
    return power


def start(data_dir, **limits):
    thread = threading.Thread(target=mission.run, args=(str(data_dir),), kwargs=limits, daemon=True)
    thread.start()
    return thread


def test_it_starts_only_while_charging_and_then_changes_nothing(tmp_path, pc):
    pc._put("ac", False)
    with pytest.raises(SystemExit) as ended:
        mission.run(str(tmp_path))
    assert ended.value.code == 1 and pc.lid_of("x") == 1 and not pc._get("awake")
    assert mission.saved(tmp_path) is None


def test_on_mains_the_old_value_is_saved_before_the_lid_is_changed_and_unplugging_puts_it_back(tmp_path, pc, monkeypatch):
    seen = []
    real = pc.set_lid
    monkeypatch.setattr(mission.StandIn, "set_lid", lambda self, scheme, value: (
        seen.append((value, mission.saved(tmp_path))), real(scheme, value)))
    thread = start(tmp_path)
    wait_for(lambda: pc._get("awake") is True)
    assert seen[0][0] == 0 and seen[0][1]["lid_ac"] == 1 and seen[0][1]["scheme"] == "stand-in-plan"  # saved first
    assert pc.lid_of("x") == 0
    pc._put("ac", False)  # unplugged
    thread.join(5)
    assert not thread.is_alive() and pc.lid_of("x") == 1 and pc._get("awake") is False
    assert mission.saved(tmp_path) is None and mission.last_ending(tmp_path)["reason"] == "unplugged"


@pytest.mark.parametrize("change, limits, reason", [
    ({}, {"max_hours": 0.0002}, "time"),
    ({"celsius": 91.5}, {"max_celsius": 85}, "heat"),
    ({"cpu": 99}, {"cpu_percent": 85, "cpu_minutes": 0.003}, "cpu"),
], ids=["time cap", "temperature", "CPU cap"])
def test_it_ends_by_itself_at_each_limit_and_puts_the_lid_back(tmp_path, pc, change, limits, reason):
    thread = start(tmp_path, **limits)
    wait_for(lambda: pc._get("awake") is True)
    for name, value in change.items():
        pc._put(name, value)
    thread.join(10)
    ending = mission.last_ending(tmp_path)
    assert not thread.is_alive() and ending["reason"] == reason and "Sleep" in ending["put_back"]
    assert pc.lid_of("x") == 1 and pc._get("awake") is False


def test_a_busy_moment_is_not_the_cpu_cap(tmp_path, pc):
    thread = start(tmp_path, cpu_percent=85, cpu_minutes=0.01, max_hours=0.0004)
    wait_for(lambda: pc._get("awake") is True)
    for _ in range(5):
        pc._put("cpu", 99)
        time.sleep(0.1)
        pc._put("cpu", 10)  # comes back down within the 0.6 s
        time.sleep(0.1)
    thread.join(10)
    assert mission.last_ending(tmp_path)["reason"] == "time"


def test_restore_can_run_any_number_of_times_and_a_crashed_leftover_goes_back_first(tmp_path, pc):
    (tmp_path / mission.STATE_NAME).write_text(json.dumps({"scheme": "stand-in-plan", "lid_ac": 2}))  # left by a crash
    pc._put("lid_ac", 0)
    assert "Hibernate" in mission.restore(tmp_path) and pc.lid_of("x") == 2
    assert mission.restore(tmp_path) is None and mission.restore(tmp_path) is None
    (tmp_path / mission.STATE_NAME).write_text(json.dumps({"scheme": "stand-in-plan", "lid_ac": 3}))
    pc._put("lid_ac", 0)
    thread = start(tmp_path)  # a new Mission Mode first puts the crash's change back, then saves the real old value
    wait_for(lambda: pc._get("awake") is True)
    assert mission.saved(tmp_path)["lid_ac"] == 3
    pc._put("ac", False)
    thread.join(5)
    assert pc.lid_of("x") == 3


def test_an_unreadable_saved_value_puts_windows_default_back(tmp_path, pc):
    (tmp_path / mission.STATE_NAME).write_text("{ broken")
    pc._put("lid_ac", 0)
    assert "default" in mission.restore(tmp_path) and pc.lid_of("x") == 1


def test_when_windows_refuses_the_saved_value_is_kept_for_the_next_try(tmp_path, pc):
    (tmp_path / mission.STATE_NAME).write_text(json.dumps({"scheme": "stand-in-plan", "lid_ac": 1}))
    pc._put("broken", True)
    with pytest.raises(mission.MissionError):
        mission.restore(tmp_path)
    assert mission.saved(tmp_path) == {"scheme": "stand-in-plan", "lid_ac": 1}
    pc._put("broken", False)
    assert mission.restore(tmp_path) and mission.saved(tmp_path) is None


def test_kairu_stop_puts_the_lid_back_itself_when_guardian_is_not_running(tmp_path, pc, config_path, config):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / mission.STATE_NAME).write_text(json.dumps({"scheme": "stand-in-plan", "lid_ac": 1}))
    pc._put("lid_ac", 0)
    stopped = kairu("stop")
    assert stopped.returncode == 0 and "lid setting on mains power is back" in stopped.stdout, stopped.stdout + stopped.stderr
    assert pc.lid_of("x") == 1 and mission.saved(config.data_dir) is None


def test_powercfg_output_is_read_by_its_numbers_in_any_language(monkeypatch):
    german = """Energieschema-GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Ausbalanciert)
  GUID-Alias: SCHEME_BALANCED
  Untergruppen-GUID: 4f971e89-eebd-4455-a8de-9e59040e7347  (Netzschalter und Zuklappen)
    Energieeinstellungs-GUID: 5ca83367-6e45-459f-a27b-476b1d01c936  (Zuklappen)
      Mögliche Einstellung - Index: 000
      Mögliche Einstellung - Anzeigename: Nichts unternehmen
      Mögliche Einstellung - Index: 001
      Mögliche Einstellung - Anzeigename: Energie sparen
    Index der aktuellen Wechselstromeinstellung: 0x00000002
    Index der aktuellen Gleichstromeinstellung: 0x00000001
"""
    monkeypatch.setattr(mission, "_powercfg", lambda *args: german)
    power = mission.WindowsPower.__new__(mission.WindowsPower)
    assert power.lid() == ("381b4222-f694-41f0-9685-ff5bb260df2e", 2)


windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@windows
def test_the_real_lid_setting_can_be_read_and_written_without_administrator_rights():
    """Writes back the value it read: nothing changes on this PC."""
    power = mission.WindowsPower()
    try:
        scheme, value = power.lid()
    except mission.MissionError as error:
        pytest.skip(f"this PC has no lid setting ({error})")
    power.set_lid(scheme, value)
    assert power.lid() == (scheme, value)
    print(f"\n  lid on mains: {mission.LID_ACTIONS.get(value)}; charging: {power.on_mains()}; "
          f"temperature: {power.celsius()}")


@windows
def test_windows_power_readings_never_fail():
    power = mission.WindowsPower()
    assert power.on_mains() in (True, False, None)
    reading = power.celsius()
    assert reading is None or 0 < reading < 150
    power.cpu_percent()
    time.sleep(0.2)
    busy = power.cpu_percent()
    assert busy is None or 0 <= busy <= 100


# --- Windows: a file another process is replacing or deleting is busy for a moment ---------------------------------

@pytest.fixture
def busy_once(monkeypatch):
    """Path.read_text, Path.unlink and os.replace each say "busy" (PermissionError) the first time, as Windows does
    while another process replaces or deletes the file; then they work."""
    from pathlib import Path
    refused = []

    def once(name, real):
        def patched(*args, **kwargs):
            if name not in refused:
                refused.append(name)
                raise PermissionError(13, "Permission denied")
            return real(*args, **kwargs)
        return patched
    monkeypatch.setattr(Path, "read_text", once("read", Path.read_text))
    monkeypatch.setattr(Path, "unlink", once("unlink", Path.unlink))
    monkeypatch.setattr(mission.os, "replace", once("replace", mission.os.replace))
    return refused


def test_the_saved_value_and_the_last_ending_are_read_again_while_windows_says_busy(tmp_path, busy_once):
    """CI, 10 Nov 2026: a test read mission-mode.json just as Guardian deleted it, and got PermissionError."""
    (tmp_path / mission.STATE_NAME).write_bytes(json.dumps({"scheme": "s", "lid_ac": 2}).encode())
    assert mission.saved(tmp_path) == {"scheme": "s", "lid_ac": 2} and busy_once == ["read"]
    (tmp_path / mission.LAST_NAME).write_bytes(json.dumps({"reason": "time"}).encode())
    busy_once.remove("read")
    assert mission.last_ending(tmp_path) == {"reason": "time"} and busy_once == ["read"]


def test_writing_and_putting_back_are_tried_again_while_windows_says_busy(tmp_path, pc, busy_once):
    busy_once.append("read")  # reads work at once here: this one is about the write and the delete
    mission._write(tmp_path / mission.STATE_NAME, {"scheme": "stand-in-plan", "lid_ac": 1})
    assert "replace" in busy_once and mission.saved(tmp_path)["lid_ac"] == 1
    pc.set_lid("stand-in-plan", 0)
    assert mission.restore(tmp_path, pc) and "unlink" in busy_once
    assert mission.saved(tmp_path) is None and pc.lid_of("x") == 1


def test_a_file_that_stays_busy_is_still_an_error_never_a_wrong_answer(tmp_path, monkeypatch):
    """Busy for longer than a moment: the PermissionError is raised, never "nothing is changed" (None)."""
    from pathlib import Path
    (tmp_path / mission.STATE_NAME).write_bytes(b"{}")
    tries = []
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: tries.append(1) or (_ for _ in ()).throw(PermissionError(13, "busy")))
    began = time.monotonic()
    with pytest.raises(PermissionError):
        mission.saved(tmp_path)
    assert len(tries) == mission.BUSY_TRIES + 1 and time.monotonic() - began < 2


@windows
def test_reading_while_another_thread_writes_and_deletes_the_file_never_fails(tmp_path):
    """The real race on Windows: one thread writes and deletes mission-mode.json as Mission Mode and restore() do;
    two others read it as Guardian and the tests do (every 1 ms here; the tests' wait_for every 10 ms). Without the tries
    again, a reader failed within about 30 reads (10 Nov 2026). Nobody may ever get PermissionError."""
    path = tmp_path / mission.STATE_NAME
    stop, failures, reads, changes = threading.Event(), [], [0], [0]

    def change():
        try:
            while not stop.is_set():
                mission._write(path, {"scheme": "s", "lid_ac": 0})
                mission._patiently(lambda: path.unlink(missing_ok=True))  # as restore() does
                changes[0] += 1
        except OSError as error:
            failures.append(f"writer: {error!r}")

    def read():
        try:
            while not stop.is_set():
                assert mission.saved(tmp_path) in (None, {}, {"scheme": "s", "lid_ac": 0})
                mission.last_ending(tmp_path)
                reads[0] += 1
                time.sleep(0.001)
        except OSError as error:
            failures.append(f"reader: {error!r}")

    threads = [threading.Thread(target=change), threading.Thread(target=read), threading.Thread(target=read)]
    for thread in threads:
        thread.start()
    time.sleep(3)
    stop.set()
    for thread in threads:
        thread.join(5)
    assert failures == [] and reads[0] > 100 and changes[0] > 100
