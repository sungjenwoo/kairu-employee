"""A sealed file is read safely while Windows is still putting it in place."""

import threading
from pathlib import Path

import pytest

from kairu.protect import sealed

SECRET = {"code": "123456"}


def test_a_moment_of_permission_denied_is_waited_out(tmp_path, monkeypatch):
    key = tmp_path / "key"
    sealed.write(key, SECRET)
    real, refused = Path.read_bytes, []

    def busy(path):
        if len(refused) < 3:
            refused.append(path)
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", busy)
    assert sealed.read(key) == SECRET
    assert len(refused) == 3


def test_a_lasting_refusal_is_still_raised_not_taken_for_no_file(tmp_path, monkeypatch):
    key = tmp_path / "key"
    sealed.write(key, SECRET)

    def refused(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(Path, "read_bytes", refused)
    monkeypatch.setattr(sealed.time, "sleep", lambda seconds: None)
    with pytest.raises(PermissionError):
        sealed.read(key)


def test_a_file_that_does_not_exist_is_none_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(sealed.time, "sleep", lambda seconds: pytest.fail("it waited"))
    assert sealed.read(tmp_path / "no-such-key") is None


def test_reading_a_file_while_it_first_appears_never_fails(tmp_path):
    key = tmp_path / "link-pair.offer"
    for _ in range(100):
        writer = threading.Thread(target=sealed.write, args=(key, SECRET))
        writer.start()
        while (found := sealed.read(key)) is None:
            assert writer.is_alive() or key.exists()
        writer.join()
        assert found == SECRET
        key.unlink()
