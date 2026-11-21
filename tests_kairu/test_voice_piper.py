"""Piper, Kairu's offline voice: pinned downloads from the official sources only, run as a separate program, the voice from
Guardian's own config.yaml. The real voice is tried where `kairu voice setup` put it (Windows); nothing is played aloud here.
"""

import hashlib
import io
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import pytest

from kairu import config, executors
from kairu.config import ROOT
from kairu.voice import models, speak


class Download(io.BytesIO):
    def __init__(self, data: bytes, url: str):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


def opener_for(data: bytes, final: str | None = None):
    asked = []

    def opener(address, timeout):
        asked.append(address)
        return Download(data, final or address)
    return opener, asked


def piper_zip(exe: bytes = b"MZ stand-in") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as packed:
        packed.writestr(zipfile.ZipInfo("piper/piper.exe", (2026, 11, 7, 0, 0, 0)), exe)
        packed.writestr(zipfile.ZipInfo("piper/espeak-ng-data/phontab", (2026, 11, 7, 0, 0, 0)), b"x")
    return out.getvalue()


@pytest.fixture
def pinned(monkeypatch):
    """The Piper build and one voice pinned to stand-in files made here, at their real addresses."""
    build = piper_zip()
    monkeypatch.setattr(models, "PIPER", models.Piece(models.PIPER.name, models.PIPER.url, hashlib.sha256(build).hexdigest(),
                                                      len(build), models.PIPER_HOSTS))
    onnx, cfg = b"onnx stand-in", b'{"audio": {"sample_rate": 22050}}'
    real = models.VOICES["indian-svbi"]
    monkeypatch.setitem(models.VOICES, "indian-svbi", models.Voice(
        real.key, real.name, real.path, real.label,
        models.Piece(real.onnx.name, real.onnx.url, hashlib.sha256(onnx).hexdigest(), len(onnx), models.VOICE_HOSTS),
        models.Piece(real.config.name, real.config.url, hashlib.sha256(cfg).hexdigest(), len(cfg), models.VOICE_HOSTS), real.speaker))
    return build, onnx, cfg


def test_the_voices_and_the_piper_build_are_pinned_to_the_official_sources():
    assert models.PIPER.url == "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
    assert models.PIPER.sha256 == "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea"
    assert set(models.VOICES) == set(config.VOICE_VOICES) == {
        "indian-svbi", "uk-jenny", "us-hfc-female", "indian-tni", "indian-asi", "indian-rrbi", "us-kristin", "us-ryan", "us-joe",
        "uk-alba", "uk-cori", "uk-northern-male", "us-libritts-1093", "us-libritts-3905", "us-libritts-6694", "us-libritts-3490"}
    assert not {"us-amy", "us-lessac", "uk-alan"} & set(models.VOICES)  # their recordings' licences don't allow it
    assert models.DEFAULT_VOICE == config.VOICE_VOICES[0]
    for voice in models.VOICES.values():
        for piece in (voice.onnx, voice.config):
            assert piece.url.startswith("https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/"), piece.url
            assert re.fullmatch(r"[0-9a-f]{64}", piece.sha256)
    assert models.VOICES["indian-svbi"].name == "en_US-l2arctic-medium" and models.VOICES["indian-svbi"].speaker == 2  # SVBI
    assert models.VOICES["uk-jenny"].name == "en_GB-jenny_dioco-medium" and models.VOICES["us-hfc-female"].name == "en_US-hfc_female-medium"
    speakers = {key: (voice.name, voice.speaker) for key, voice in models.VOICES.items() if voice.speaker is not None}
    assert speakers == {  # L2-ARCTIC's own ids (TNI 9, ASI 10, RRBI 19) and LibriTTS-R's, from each voice's .onnx.json
        "indian-svbi": ("en_US-l2arctic-medium", 2), "indian-tni": ("en_US-l2arctic-medium", 9),
        "indian-asi": ("en_US-l2arctic-medium", 10), "indian-rrbi": ("en_US-l2arctic-medium", 19),
        "us-libritts-1093": ("en_US-libritts_r-medium", 120), "us-libritts-3905": ("en_US-libritts_r-medium", 450),
        "us-libritts-6694": ("en_US-libritts_r-medium", 90), "us-libritts-3490": ("en_US-libritts_r-medium", 435)}
    for voice in models.VOICES.values():  # every voice of one file has that file's one pin
        twin = next(other for other in models.VOICES.values() if other.name == voice.name)
        assert (voice.onnx, voice.config) == (twin.onnx, twin.config)


def test_piper_comes_from_github_its_sha_checked_and_is_unpacked_into_the_data_folder(tmp_path, pinned):
    build, _, _ = pinned
    opener, asked = opener_for(build, "https://release-assets.githubusercontent.com/github-production-release-asset/x")
    exe = models.setup_piper(tmp_path, say=lambda text: None, opener=opener)
    assert asked == [models.PIPER.url] and exe == tmp_path / "voice" / "piper-2023.11.14-2" / "piper.exe" and exe.read_bytes() == b"MZ stand-in"
    assert models.piper_ready(tmp_path) == exe


def test_a_piper_build_with_the_wrong_sha_256_is_deleted_and_nothing_is_unpacked(tmp_path, pinned):
    changed = piper_zip(b"MZ standXin")  # a working archive of the very same size: only its SHA-256 tells it apart
    assert len(changed) == models.PIPER.size and changed != piper_zip()
    opener, _ = opener_for(changed, "https://release-assets.githubusercontent.com/x")
    with pytest.raises(models.SetupError, match="SHA-256"):
        models.setup_piper(tmp_path, say=lambda text: None, opener=opener)
    assert list((tmp_path / "voice").iterdir()) == []
    with pytest.raises(models.NotSetUp):
        models.piper_ready(tmp_path)


@pytest.mark.parametrize("final", ["https://evil.example/piper.zip", "http://release-assets.githubusercontent.com/x",
                                   "https://githubusercontent.com.evil.example/x", "https://huggingface.co/x"])
def test_piper_sent_anywhere_but_github_is_refused(tmp_path, pinned, final):
    build, _, _ = pinned
    opener, _ = opener_for(build, final)
    with pytest.raises(models.SetupError, match="sent elsewhere"):
        models.setup_piper(tmp_path, say=lambda text: None, opener=opener)
    assert list((tmp_path / "voice").iterdir()) == []


def test_a_voice_comes_from_hugging_face_only_with_both_files_sha_checked(tmp_path, pinned, monkeypatch):
    _, onnx, cfg = pinned
    files = {models.VOICES["indian-svbi"].onnx.url: onnx, models.VOICES["indian-svbi"].config.url: cfg}
    asked = []

    def opener(address, timeout):
        asked.append(address)
        return Download(files[address], "https://us.aws.cdn.hf.co/xet-bridge-us/abc")
    place = models.setup_voice(tmp_path, "indian-svbi", say=lambda text: None, opener=opener)
    assert asked == list(files) and place.read_bytes() == onnx
    assert models.voice_ready(tmp_path, "indian-svbi")[2] == 2
    bad = tmp_path / "other"
    with pytest.raises(models.SetupError, match="sent elsewhere"):
        models.setup_voice(bad, "indian-svbi", say=lambda text: None,
                           opener=lambda address, timeout: Download(files[address], "https://objects.githubusercontent.com/x"))
    with pytest.raises(models.SetupError, match="SHA-256|larger"):
        models.setup_voice(bad, "indian-svbi", say=lambda text: None,
                           opener=lambda address, timeout: Download(files[address] + b"!", "https://huggingface.co/x"))
    assert [path.name for path in (bad / "voice" / "piper-voices").iterdir()] == []


def test_the_voice_is_chosen_by_guardians_config_never_by_a_request():
    spoken = executors.EXECUTORS["voice.speak"]
    assert set(spoken.arguments) == {"text"} and spoken.supplied == ("data_dir", "voice_voice", "voice_style", "voice_tts",
                                                                          "voice_kokoro") and spoken.single
    assert executors.argument_problem("voice.speak", spoken, {"text": "hi", "voice_voice": "uk-jenny"})


def test_piper_runs_as_its_own_program_with_the_voice_its_speaker_and_pauses_between_sentences():
    command = speak.piper_command(Path("C:/k/piper.exe"), Path("C:/k/en_US-l2arctic-medium.onnx"), 2)
    assert command[0].endswith("piper.exe") and "--output-raw" in command and command[command.index("--speaker") + 1] == "2"
    assert float(command[command.index("--sentence_silence") + 1]) == speak.SENTENCE_PAUSE > 0
    assert "--speaker" not in speak.piper_command(Path("piper.exe"), Path("jenny.onnx"), None)


def test_without_piper_set_up_windows_own_voice_speaks_and_with_it_piper_does(tmp_path, monkeypatch, pinned):
    monkeypatch.delenv(speak.TEST_VOICE, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    said = []
    monkeypatch.setattr(speak, "speak", lambda line: said.append(("windows", line)))
    monkeypatch.setattr(speak, "say_with_piper", lambda line, piper, onnx, cfg, speaker: said.append(("piper", line, speaker)))
    speak.main("Hello there.", str(tmp_path), "indian-svbi")
    build, onnx, cfg = pinned
    models.setup_piper(tmp_path, say=lambda text: None, opener=opener_for(build, "https://objects.githubusercontent.com/x")[0])
    files = {models.VOICES["indian-svbi"].onnx.url: onnx, models.VOICES["indian-svbi"].config.url: cfg}
    models.setup_voice(tmp_path, "indian-svbi", say=lambda text: None,
                       opener=lambda address, timeout: Download(files[address], "https://huggingface.co/x"))
    speak.main("Hello there.", str(tmp_path), "indian-svbi")
    assert said == [("windows", "Hello there."), ("piper", "Hello there.", 2)]


def test_kairu_never_imports_or_links_the_gpl_piper_package_and_says_what_piper_bundles():
    code = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "kairu").rglob("*.py"))
    assert not re.search(r"^\s*(?:import|from)\s+piper\b", code, re.MULTILINE)
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = project.split("dependencies = [")[1].split("]")[0]
    assert not re.search(r'^\s*"(?:piper|onnxruntime)', dependencies, re.MULTILINE)  # no Piper package is installed at all
    assert "espeak-ng" in project and "GPL-3.0" in project
    voice_doc = (ROOT / "VOICE.md").read_text(encoding="utf-8")
    assert "espeak-ng" in voice_doc and "GPL-3.0" in voice_doc


def real_piper():
    if sys.platform != "win32":
        pytest.skip("the Piper build Kairu uses (rhasspy/piper 2023.11.14-2) is for Windows")
    try:
        return models.piper_ready(ROOT / "data"), models.voice_ready(ROOT / "data", models.DEFAULT_VOICE)
    except models.NotSetUp:
        pytest.skip("Piper is not set up in this folder: run `kairu voice setup` (tools/check_guardian.py does it)")


def test_the_real_piper_voice_starts_speaking_within_about_a_second():
    piper, (onnx, cfg, speaker) = real_piper()
    for _ in speak.synthesize("Hello.", piper, onnx, speaker):  # the first time reads the voice from disk
        pass
    started, first, sound = time.monotonic(), None, b""
    for piece in speak.synthesize("Narendra Modi. Want to know more about him?", piper, onnx, speaker):
        first = first or time.monotonic() - started
        sound += piece
    seconds = len(sound) / 2 / speak.sample_rate(cfg)
    print(f"\n  Piper ({models.DEFAULT_VOICE}): first sound {first:.2f} s after the line; {seconds:.1f} s of speech")
    assert first < 1.5 and 1.5 < seconds < 8 and max(sound[1::2]) > 0


def test_nothing_of_the_voice_is_written_while_piper_speaks(tmp_path):
    piper, (onnx, cfg, speaker) = real_piper()
    before = {path for path in Path(piper).parent.rglob("*")} | {path for path in onnx.parent.rglob("*")}
    for _ in speak.synthesize("A short line.", piper, onnx, speaker):
        pass
    after = {path for path in Path(piper).parent.rglob("*")} | {path for path in onnx.parent.rglob("*")}
    assert after == before and not list(Path(os.getcwd()).glob("*.wav"))
