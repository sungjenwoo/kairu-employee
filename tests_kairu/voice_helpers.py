"""Helpers for the voice tests: the recorded sounds in tests_kairu/voice/, the real small model, and the pretend mic.

The model is the one `kairu voice setup` put in this folder's data/voice/ (tools/check_guardian.py sets it up first). A test
Guardian gets it through a link in its own data folder, to a copy made once per test run, so nothing a test does can touch
the model you use.
"""

import os
import shutil
import sys
import wave
from pathlib import Path

import pytest

from kairu.config import ROOT

SOUNDS = ROOT / "tests_kairu" / "voice"
RATE, CHUNK = 16000, 3200  # bytes: 0.1 s


def sound(name: str) -> bytes:
    with wave.open(str(SOUNDS / f"{name}.wav")) as recorded:
        assert (recorded.getframerate(), recorded.getsampwidth(), recorded.getnchannels()) == (RATE, 2, 1)
        return recorded.readframes(recorded.getnframes())


def silence(seconds: float) -> bytes:
    return bytes(int(RATE * seconds) * 2)


def hear(hearing, *parts, pause: float = 2.0) -> list[dict]:
    """Feed each recorded sound (a name) or raw bytes, each followed by `pause` seconds of silence; the events, in order."""
    events = []
    for part in parts:
        audio = (sound(part) if isinstance(part, str) else part) + silence(pause)
        for start in range(0, len(audio), CHUNK):
            events += hearing.feed(audio[start:start + CHUNK])
    return events


def real_model_folder() -> Path:
    """The model `kairu voice setup` put here, or a skip that says how to get it."""
    from kairu.voice import models
    try:
        return models.ready(ROOT / "data", models.DEFAULT)
    except models.NotSetUp:
        pytest.skip("the voice model is not set up in this folder: run `kairu voice setup` (tools/check_guardian.py does it)")


@pytest.fixture(scope="session")
def vosk_model():
    pytest.importorskip("vosk")
    import vosk
    vosk.SetLogLevel(-1)
    return vosk.Model(str(real_model_folder()))


@pytest.fixture(scope="session")
def model_copy(tmp_path_factory):
    """A copy of the model for test Guardians: their data folders link to this, never to yours."""
    from kairu.voice import models
    copy = tmp_path_factory.mktemp("voice-model") / models.MODELS[models.DEFAULT].name
    shutil.copytree(real_model_folder(), copy)
    return copy


def link_model(data_dir: Path, copy: Path) -> Path:
    """data_dir/voice/NAME, a junction (Windows) or symlink (Linux) to the copy. unlink_model() removes only the link."""
    place = Path(data_dir) / "voice" / copy.name
    place.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(copy), str(place))
    else:
        os.symlink(copy, place, target_is_directory=True)
    return place


def unlink_model(place: Path) -> None:
    if sys.platform == "win32":
        os.rmdir(place)  # a junction: removes the link, not what it points to
    else:
        place.unlink()


class PretendMic:
    """The folder KAIRU_TEST_MIC names: each cue put here names one of the recordings in tests_kairu/voice, heard once, in
    name order, in real time. The recordings are never copied: no sound is written anywhere, here or in the temp folder."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.count = 0

    def say(self, name: str) -> str:
        self.count += 1
        cue = f"{self.count:03}_{name}.cue"
        (self.folder / f"{cue}.part").write_text(str(SOUNDS / f"{name}.wav"), encoding="utf-8")
        os.replace(self.folder / f"{cue}.part", self.folder / cue)  # whole, never half-written
        return cue

    def played(self) -> list[str]:
        log = self.folder / "played.log"
        return log.read_text(encoding="utf-8").split() if log.exists() else []


class PretendVoice:
    """The folder KAIRU_TEST_VOICE names: voice.speak writes each line it would say to spoken.log."""

    def __init__(self, folder: Path):
        self.folder = folder

    def lines(self) -> list[str]:
        log = self.folder / "spoken.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []
