"""Protection (Phase J, part J2): folders, devices and Windows Security, watched read-only."""

import os
import sys
import time
from pathlib import Path

import pytest

from kairu.protect import actions, devices, folders, security, watch
from kairu.protect.devices import Device, DeviceMonitor
from kairu.protect.folders import FolderMonitor, FolderProblem
from kairu.protect.security import SecurityMonitor, Unsupported
from kairu.protect.store import ACTIVE, DEGRADED, ProtectStore

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """A stand-in home folder: on Windows, test folders live under AppData, which Kairu refuses to watch."""
    fake = tmp_path / "home"
    (fake / "AppData").mkdir(parents=True)
    (fake / ".ssh").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


@pytest.fixture
def data(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def downloads(tmp_path, data):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "notes.txt").write_text("old")
    (folder / "old-setup.exe").write_bytes(b"")  # already there before Kairu watched: never an alert
    actions.add_folder(str(data), str(folder))
    return folder


def check(data):
    findings, note = FolderMonitor(ProtectStore(data), data).check()
    return findings


# --- folders -----------------------------------------------------------------------------------------

def test_the_first_look_only_learns_what_is_there(data, downloads):
    assert check(data) == []
    assert check(data) == []


def test_a_new_program_in_downloads_is_reported_and_never_opened(data, downloads):
    check(data)
    (downloads / "setup.exe").write_bytes(b"MZ")
    (downloads / "photo.jpg").write_bytes(b"x")
    found = check(data)
    assert [(f.kind, f.severity, f.title) for f in found] == [("risky_download", "warning", "A program was downloaded: setup.exe")]
    assert ("Size", "2 bytes") in found[0].lines and found[0].you_can.endswith("Kairu changed nothing.")
    assert (downloads / "setup.exe").read_bytes() == b"MZ"  # untouched
    assert check(data) == []  # once only


@pytest.mark.parametrize("name,why", [("test.pdf.exe", "looks like a .pdf file but is a program"),
                                      ("invoice.docx.scr", "looks like a .docx file"),
                                      ("photo‮gnp.exe", "reverses its letters")])
def test_a_disguised_file_is_high(data, downloads, name, why):
    check(data)
    (downloads / name).write_bytes(b"")
    found = check(data)
    assert len(found) == 1 and found[0].kind == "disguised_file" and found[0].severity == "high"
    assert why in found[0].why[0]


def test_a_file_still_downloading_is_checked_when_it_is_complete(data, downloads):
    check(data)
    part = downloads / "tool.exe.crdownload"
    part.write_bytes(b"half")
    assert check(data) == []
    part.rename(downloads / "tool.exe")
    assert [f.title for f in check(data)] == ["A program was downloaded: tool.exe"]


def test_many_files_changing_at_once_is_high(data, downloads):
    victims = downloads / "work"
    victims.mkdir()
    for number in range(folders.MANY_CHANGED):
        (victims / f"report{number}.docx").write_text("text")
    check(data)
    time.sleep(0.05)
    for number in range(folders.MANY_CHANGED):
        source = victims / f"report{number}.docx"
        source.rename(victims / f"report{number}.docx.locked")
    found = [f for f in check(data) if f.kind == "many_files_changed"]
    assert len(found) == 1 and found[0].severity == "high"
    assert ("Gone or renamed", str(folders.MANY_CHANGED)) in found[0].lines


def test_a_few_changes_are_not_many(data, downloads):
    check(data)
    (downloads / "notes.txt").write_text("edited, and longer")
    assert check(data) == []


def test_system_private_and_too_broad_folders_are_refused(tmp_path, data, home):
    inside = home / "AppData" / "Local"
    inside.mkdir()
    for refused in (home, Path(home.anchor), data, home / ".ssh", inside):
        with pytest.raises(FolderProblem):
            folders.fence(str(refused), data)
    if sys.platform == "win32":
        with pytest.raises(FolderProblem):
            folders.fence(os.environ["SystemRoot"], data)
    else:
        with pytest.raises(FolderProblem):
            folders.fence("/etc", data)
    with pytest.raises(FolderProblem, match="no folder"):
        folders.fence(str(tmp_path / "missing"), data)
    plain = tmp_path / "a.txt"
    plain.write_text("x")
    with pytest.raises(FolderProblem, match="not a folder"):
        folders.fence(str(plain), data)


def test_at_most_five_folders_and_removing_one_forgets_it(tmp_path, data):
    made = []
    for number in range(folders.MOST_FOLDERS + 1):
        folder = tmp_path / f"f{number}"
        folder.mkdir()
        made.append(folder)
    for folder in made[:-1]:
        actions.add_folder(str(data), str(folder))
    with pytest.raises(SystemExit):
        actions.add_folder(str(data), str(made[-1]))
    actions.remove_folder(str(data), str(made[0].resolve()))
    assert str(made[0].resolve()) not in folders.approved(ProtectStore(data))
    with pytest.raises(SystemExit):
        actions.remove_folder(str(data), str(made[0].resolve()))


@windows_only
def test_on_windows_the_website_a_file_came_from_is_read_from_its_zone_note(data, downloads):
    check(data)
    file = downloads / "setup.exe"
    file.write_bytes(b"MZ")
    with open(str(file) + ":Zone.Identifier", "w") as note:
        note.write("[ZoneTransfer]\nZoneId=3\nReferrerUrl=https://example.com/\nHostUrl=https://example.com/setup.exe\n")
    found = check(data)
    assert ("From", "https://example.com/setup.exe") in found[0].lines


@windows_only
def test_on_windows_downloads_is_found_where_windows_keeps_it():
    assert folders.downloads_folder().is_dir()


# --- devices -------------------------------------------------------------------------------------------

MOUSE = Device("USB\\VID_046D&PID_C077\\5&1", "USB Optical Mouse", "Mouse")
STICK = Device("USBSTOR\\DISK&VEN_SANDISK&PROD_CRUZER\\4C53", "SanDisk Cruzer USB Device", "DiskDrive")
GADGET = Device("HID\\VID_16C0&PID_27DB\\7&2", "HID Keyboard Device", "Keyboard")


def device_round(data, listing):
    return DeviceMonitor(ProtectStore(data), lambda: listing).check()[0]


def test_devices_already_there_are_learned_and_a_new_one_is_reported_once(data):
    assert device_round(data, [MOUSE]) == []
    found = device_round(data, [MOUSE, STICK])
    assert [(f.kind, f.severity, f.title) for f in found] == [("new_device", "warning",
                                                              "New device connected: SanDisk Cruzer USB Device")]
    assert device_round(data, [MOUSE, STICK]) == []
    assert device_round(data, [MOUSE]) == []  # unplugging is never an alert
    assert device_round(data, [MOUSE, STICK]) == []  # seen before


def test_a_new_keyboard_is_high(data):
    device_round(data, [MOUSE])
    found = device_round(data, [MOUSE, GADGET])
    assert found[0].kind == "new_keyboard" and found[0].severity == "high" and "type commands" in found[0].why[1]


def test_the_devices_present_can_be_listed_on_this_system():
    listed = devices.present()
    assert all(isinstance(device, Device) and device.id for device in listed)
    print(f"\n  devices present: {len(listed)}")


# --- Windows Security ----------------------------------------------------------------------------------

def test_protection_turned_off_is_high_once_and_its_return_is_noted(data):
    state = {security.PROVIDERS["firewall"]: security.GOOD, security.PROVIDERS["antivirus"]: security.GOOD}
    monitor = SecurityMonitor(ProtectStore(data), lambda provider: state[provider])
    assert monitor.check()[0] == []
    state[security.PROVIDERS["antivirus"]] = security.POOR
    found = monitor.check()[0]
    assert [(f.kind, f.severity) for f in found] == [("security_off", "high")] and "antivirus" in found[0].title
    assert monitor.check()[0] == []
    state[security.PROVIDERS["antivirus"]] = security.GOOD
    assert [f.kind for f in monitor.check()[0]] == ["security_restored"]


def test_protection_already_off_at_the_first_look_is_reported(data):
    monitor = SecurityMonitor(ProtectStore(data), lambda provider: security.POOR)
    assert len(monitor.check()[0]) == 2


def test_when_windows_cannot_tell_the_source_is_unsupported_not_safe(data):
    def unknown(provider):
        raise Unsupported("no Security Center")
    with pytest.raises(Unsupported):
        SecurityMonitor(ProtectStore(data), unknown).check()


def test_the_security_center_answers_or_says_it_cannot():
    try:
        state = security.health(security.PROVIDERS["firewall"])
    except Unsupported as why:
        print(f"\n  Windows Security Center: {why}")
        return
    assert state in security.WORDS
    print(f"\n  firewall: {security.WORDS[state]}")


# --- the watcher -----------------------------------------------------------------------------------------

def test_watch_pc_turns_on_the_three_and_the_watcher_shows_each(data, tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    actions.watch_pc(str(data), str(folder), devices=True, security=True)
    w = watch.Watcher(str(data), check_seconds=1, gmail_seconds=60,
                      devices=lambda: [MOUSE], security=lambda provider: security.GOOD)
    assert set(w.watching()) == {"folders", "devices", "security"}
    assert w.round()
    store = ProtectStore(data)
    assert store.source("folders")["state"] == ACTIVE and store.source("folders")["detail"] == "Downloads: 0 files"
    assert store.source("devices")["state"] == ACTIVE and store.source("security")["state"] == ACTIVE
    actions.pause(str(data), "devices")
    assert set(w.watching()) == {"folders", "security"}


def test_one_failing_monitor_never_stops_the_others(data, tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    actions.watch_pc(str(data), str(folder), devices=True, security=True)

    def broken():
        raise OSError("SetupAPI went away")

    w = watch.Watcher(str(data), check_seconds=1, gmail_seconds=60, devices=broken, security=lambda p: security.GOOD)
    for _ in range(3):
        assert w.round()
    store = ProtectStore(data)
    assert store.source("devices")["state"] == DEGRADED and store.source("folders")["state"] == ACTIVE
    assert [a.kind for a in store.alerts()] == ["protection_degraded"]


def test_unsupported_security_shows_as_unsupported(data):
    actions.watch_pc(str(data), "", devices=False, security=True)

    def unknown(provider):
        raise Unsupported("Windows only")

    w = watch.Watcher(str(data), check_seconds=1, gmail_seconds=60, security=unknown)
    w.round()
    assert ProtectStore(data).source("security")["state"] == watch.UNSUPPORTED


def test_watch_pc_needs_something_to_watch(data):
    with pytest.raises(SystemExit):
        actions.watch_pc(str(data), "", devices=False, security=False)


def test_watching_the_pc_or_another_folder_needs_yes_and_the_pin(guardian):
    from kairu.guardian import Verdict
    for name in ("protect.watch_pc", "protect.add_folder"):
        assert guardian.check(name).verdict is Verdict.NEEDS_APPROVAL
    assert guardian.check("protect.remove_folder").verdict is Verdict.ALLOW
