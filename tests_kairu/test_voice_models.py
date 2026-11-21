"""`kairu voice setup`: from alphacephei.com only, the SHA-256 pinned in the code is checked, and it is never a Kairu action."""

import hashlib
import io
import re
import subprocess
import sys
import zipfile

import pytest

from kairu import config, executors
from kairu.config import ROOT
from kairu.tasks import skills
from kairu.voice import models


class Download(io.BytesIO):
    def __init__(self, data: bytes, url: str):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


def archive(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as packed:
        for name, data in files.items():
            packed.writestr(name, data)
    return out.getvalue()


@pytest.fixture
def small(monkeypatch):
    """A stand-in model whose pinned SHA-256 is that of a small archive made here."""
    def make(files=None, pin=None, url=None):
        name = "vosk-model-test-0.1"
        data = archive(files or {f"{name}/am/final.mdl": b"m" * 100, f"{name}/conf/model.conf": b"--beam=10\n"})
        model = models.Model("test", name, pin or hashlib.sha256(data).hexdigest(), len(data), "Test")
        monkeypatch.setitem(models.MODELS, "test", model)
        asked = []

        def opener(address, timeout):
            asked.append(address)
            return Download(data, url or address)
        return model, opener, asked
    return make


def test_it_downloads_from_alphacephei_only_checks_the_sha_and_unpacks_into_the_data_folder(tmp_path, small):
    model, opener, asked = small()
    place = models.setup(tmp_path, "test", say=lambda text: None, opener=opener)
    assert asked == [f"https://alphacephei.com/vosk/models/{model.name}.zip"]
    assert place == tmp_path / "voice" / model.name and (place / "am" / "final.mdl").read_bytes() == b"m" * 100
    assert models.ready(tmp_path, "test") == place
    assert sorted(p.name for p in (tmp_path / "voice").iterdir()) == [model.name]  # the download itself is gone


def test_a_download_with_the_wrong_sha_256_is_deleted_and_nothing_is_unpacked(tmp_path, small):
    _, opener, _ = small(pin="0" * 64)
    with pytest.raises(models.SetupError, match="SHA-256"):
        models.setup(tmp_path, "test", say=lambda text: None, opener=opener)
    assert list((tmp_path / "voice").iterdir()) == []
    with pytest.raises(models.NotSetUp):
        models.ready(tmp_path, "test")


def test_a_download_sent_to_another_host_is_refused(tmp_path, small):
    _, opener, _ = small(url="https://elsewhere.example/model.zip")
    with pytest.raises(models.SetupError, match="elsewhere"):
        models.setup(tmp_path, "test", say=lambda text: None, opener=opener)
    assert list((tmp_path / "voice").iterdir()) == []


@pytest.mark.parametrize("bad", ["../evil.txt", "vosk-model-test-0.1/../../evil.txt", "/etc/evil", "other-folder/a.txt",
                                 "vosk-model-test-0.1/C:evil"])
def test_an_archive_with_a_file_outside_the_models_folder_is_refused(tmp_path, small, bad):
    model, opener, _ = small(files={"vosk-model-test-0.1/am/final.mdl": b"m", bad: b"x"})
    with pytest.raises(models.SetupError, match="outside|nothing was kept"):
        models.setup(tmp_path, "test", say=lambda text: None, opener=opener)
    assert not (tmp_path / "voice" / model.name).exists() and not (tmp_path / "evil.txt").exists()


def test_a_model_without_its_mark_is_not_ready(tmp_path):
    (tmp_path / "voice" / models.MODELS[models.DEFAULT].name).mkdir(parents=True)
    with pytest.raises(models.NotSetUp, match="kairu voice setup"):
        models.ready(tmp_path, models.DEFAULT)


def test_the_pinned_models_are_the_two_small_english_ones_from_alphacephei():
    assert set(models.MODELS) == set(config.VOICE_MODELS) and models.DEFAULT == config.VOICE_MODELS[0]
    for model in models.MODELS.values():
        assert re.fullmatch(r"[0-9a-f]{64}", model.sha256) and model.url.startswith("https://alphacephei.com/vosk/models/")
        assert model.mib < 60  # about 50 MB, as planned
    assert models.MODELS["small-en-us"].sha256 == "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"
    assert models.MODELS["small-en-in"].sha256 == "20663dcac4d5cb783a579c54d98339344a688e4ec6e1b4a4b059fd1235454cc7"


def test_setup_is_never_a_kairu_action():
    assert all(not executor.target.startswith("kairu.voice.models") for executor in executors.EXECUTORS.values())
    assert all(not skill.executor.startswith("kairu.voice.models") for skill in skills.SKILLS)
    assert "voice.setup" not in (ROOT / "policy.yaml").read_text(encoding="utf-8")


def test_the_models_never_go_into_the_repository():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/" in ignored and "vosk-model-*/" in ignored
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout
    assert "vosk-model" not in tracked and "final.mdl" not in tracked


def test_voice_model_and_key_settings(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("voice:\n  enabled: true\n  model: small-en-in\n  key: b\n")
    loaded = config.load(path)
    assert (loaded.voice_model, loaded.voice_key) == ("small-en-in", "B")
    assert (config.load(tmp_path / "none.yaml").voice_model, config.load(tmp_path / "none.yaml").voice_key) == ("small-en-us", "V")
    for text in ("voice:\n  model: big-en\n", "voice:\n  key: K\n", "voice:\n  key: VV\n", "voice:\n  loud: true\n",
                 "voice:\n  key: Q\ntasks:\n  bar_key: Q\n"):
        path.write_text(text)
        with pytest.raises(config.ConfigError):
            config.load(path)


def test_the_cli_runs_setup_itself_never_through_guardian():
    code = (ROOT / "kairu" / "cli.py").read_text(encoding="utf-8")
    body = code[code.index("def _voice("):code.index("def _usage(")]
    assert "models.setup(" in body and "GuardianClient" not in body and "client." not in body
    shown = subprocess.run([sys.executable, "-m", "kairu", "voice", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert "setup" in shown.stdout and "status" in shown.stdout
