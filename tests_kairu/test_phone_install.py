"""`kairu phone` (PHONE.md): finding adb and the app, unpacking GitHub's artifact safely, and what adb's answers mean.
adb itself is a stand-in: these tests never touch a phone."""

import subprocess
import zipfile

import pytest

from kairu import phone


class StandInAdb:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, adb, *arguments, seconds=60):
        self.calls.append(arguments)
        out = self.answers.get(arguments[0] if arguments[0] != "-s" else arguments[2], "")
        return subprocess.CompletedProcess([adb, *arguments], 0, out, "")


def test_the_newest_kairu_file_in_downloads_is_found(tmp_path):
    import os
    import time
    (tmp_path / "holiday.apk").write_bytes(b"x")
    old, new = tmp_path / "kairu-phone-0.1.3.apk", tmp_path / "kairu-phone.zip"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert phone.newest_app(tmp_path) == new
    assert phone.newest_app(tmp_path / "missing") is None


def test_a_browsers_second_copy_is_found_when_it_is_the_newest(tmp_path):
    import os
    import time
    old, new = tmp_path / "kairu-phone.zip", tmp_path / "kairu-phone (1).zip"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert phone.newest_app(tmp_path) == new
    (tmp_path / "kairu-phone (1).exe").write_bytes(b"x")
    os.utime(new, (time.time() - 50, time.time() - 50))
    assert phone.newest_app(tmp_path) == new


def test_the_one_apk_inside_githubs_zip_is_unpacked_by_its_name_only(tmp_path):
    archive = tmp_path / "kairu-phone.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../../evil/kairu-phone-0.1.7.apk", b"APK")
    app = phone.app_from(archive, tmp_path / "data")
    assert app == tmp_path / "data" / "phone" / "kairu-phone-0.1.7.apk" and app.read_bytes() == b"APK"
    assert not (tmp_path / "evil").exists()


@pytest.mark.parametrize("names", [[], ["a.apk", "b.apk"]])
def test_a_zip_must_hold_exactly_one_apk(tmp_path, names):
    archive = tmp_path / "kairu-phone.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("readme.txt", b"x")
        for name in names:
            z.writestr(name, b"x")
    with pytest.raises(phone.PhoneError, match="exactly one"):
        phone.app_from(archive, tmp_path)


def test_other_files_are_refused(tmp_path):
    (tmp_path / "kairu-phone.exe").write_bytes(b"x")
    (tmp_path / "broken.zip").write_bytes(b"not a zip")
    with pytest.raises(phone.PhoneError, match="neither"):
        phone.app_from(tmp_path / "kairu-phone.exe", tmp_path)
    with pytest.raises(phone.PhoneError, match="whole"):
        phone.app_from(tmp_path / "broken.zip", tmp_path)
    with pytest.raises(phone.PhoneError, match="isn't there"):
        phone.app_from(tmp_path / "nothing.apk", tmp_path)


def test_install_needs_exactly_one_phone_and_says_success(monkeypatch, tmp_path):
    adb = StandInAdb({"devices": "List of devices attached\n", "install": "Performing Streamed Install\nSuccess\n"})
    monkeypatch.setattr(phone, "run", adb)
    with pytest.raises(phone.PhoneError, match="No phone"):
        phone.install(tmp_path / "a.apk", adb="adb")
    adb.answers["devices"] = "List of devices attached\n192.168.1.5:41823\tdevice\nemulator-5554\toffline\n"
    assert phone.install(tmp_path / "a.apk", adb="adb") == "192.168.1.5:41823"
    assert adb.calls[-1] == ("-s", "192.168.1.5:41823", "install", "-r", str(tmp_path / "a.apk"))
    adb.answers["devices"] += "R58N\tdevice\n"
    with pytest.raises(phone.PhoneError, match="2 phones"):
        phone.install(tmp_path / "a.apk", adb="adb")


def test_a_different_signing_key_is_explained(monkeypatch, tmp_path):
    adb = StandInAdb({"devices": "List\nR58N\tdevice\n", "install": "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: ...]"})
    monkeypatch.setattr(phone, "run", adb)
    with pytest.raises(phone.PhoneError, match="different key"):
        phone.install(tmp_path / "a.apk", adb="adb")


def test_pair_and_connect_check_what_they_are_given(monkeypatch):
    adb = StandInAdb({"pair": "Successfully paired to 192.168.1.5:37145", "connect": "connected to 192.168.1.5:41823"})
    monkeypatch.setattr(phone, "run", adb)
    for address, code in (("192.168.1.5", "123456"), ("192.168.1.5:37145", "12345"), ("a b:1", "123456"), ("x;rm:1", "123456")):
        with pytest.raises(phone.PhoneError):
            phone.pair(address, code, adb="adb")
    assert adb.calls == []
    phone.pair("192.168.1.5:37145", "123456", adb="adb")
    phone.connect("192.168.1.5:41823", adb="adb")
    assert adb.calls == [("pair", "192.168.1.5:37145", "123456"), ("connect", "192.168.1.5:41823")]


def test_no_adb_says_where_to_get_it(monkeypatch, tmp_path):
    monkeypatch.setattr(phone, "adb_places", lambda: [tmp_path / "adb.exe"])
    monkeypatch.setattr(phone.shutil, "which", lambda name: None)
    with pytest.raises(phone.PhoneError, match="platform-tools"):
        phone.find_adb()
