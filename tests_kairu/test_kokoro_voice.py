"""Kokoro, the human-sounding voice (VOICE.md "Kokoro", 15 Nov 2026), and listening for your reply after Kairu asks.

Kokoro's own program is a stand-in here, except in the last test, which runs the real one only where its model and
packages are (KAIRU_TEST_KOKORO: the folder with the two files; KAIRU_TEST_KOKORO_PYTHON: a Python with `.[kokoro]`)."""

import json
import os
import re
import struct
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest
import yaml

from kairu import config, executors
from kairu.config import ROOT
from kairu.voice import models, speak
from kairu.voice.whisper import REPLY_SECONDS, SESSION_SECONDS
from tests_kairu.test_voice_whisper import hearing_of, kinds
from tests_kairu.voice_helpers import CHUNK, hear, silence

LINE = "The capital of Japan is Tokyo. Want to know more about it?"
WORKER = ROOT / "kairu" / "voice" / "kokoro_worker.py"
GPL = ("kokoro_onnx", "phonemizer", "espeakng_loader")


# --- the pinned files and the voices ------------------------------------------------------------------------

def test_kokoro_comes_only_from_its_official_release_each_file_pinned():
    for piece in (models.KOKORO_MODEL, models.KOKORO_VOICES):
        assert piece.url.startswith("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/")
        assert re.fullmatch(r"[0-9a-f]{64}", piece.sha256) and piece.size > 10_000_000 and piece.hosts == models.PIPER_HOSTS
    assert models.KOKORO_MODEL.name == "kokoro-v1.0.int8.onnx"  # the int8 model: about 300 MB while speaking, not 420


def test_the_voices_are_the_same_in_the_config_and_the_default_is_first():
    assert tuple(models.KOKORO_SPEAKERS) == config.KOKORO_VOICES and config.KOKORO_VOICES[0] == models.DEFAULT_KOKORO
    assert all(lang == ("en-gb" if key.startswith("b") else "en-us") for key, (_, lang) in models.KOKORO_SPEAKERS.items())


def test_kokoro_is_ready_only_with_both_files_and_their_checked_mark(tmp_path):
    place = tmp_path / models.FOLDER / models.KOKORO_FOLDER
    place.mkdir(parents=True)
    with pytest.raises(models.NotSetUp):
        models.kokoro_ready(tmp_path)
    for piece in (models.KOKORO_MODEL, models.KOKORO_VOICES):
        (place / piece.name).write_bytes(b"x")
    (place / models.KOKORO_MARK).write_text(json.dumps({"sha256": ["0" * 64, "1" * 64]}))
    with pytest.raises(models.NotSetUp):
        models.kokoro_ready(tmp_path)
    (place / models.KOKORO_MARK).write_text(json.dumps({"sha256": [models.KOKORO_MODEL.sha256, models.KOKORO_VOICES.sha256]}))
    assert models.kokoro_ready(tmp_path) == (place / models.KOKORO_MODEL.name, place / models.KOKORO_VOICES.name)


# --- the settings -------------------------------------------------------------------------------------------

def write(tmp_path, voice):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": voice}))
    return path


def test_kokoro_speaks_by_default_with_af_heart_and_only_known_values_are_taken(tmp_path):
    cfg = config.load(write(tmp_path, {"enabled": False}))
    assert (cfg.voice_tts, cfg.voice_kokoro) == ("kokoro", "af_heart")
    cfg = config.load(write(tmp_path, {"tts": "piper", "kokoro_voice": "bf_emma"}))
    assert (cfg.voice_tts, cfg.voice_kokoro) == ("piper", "bf_emma")
    for bad in ({"tts": "elevenlabs"}, {"kokoro_voice": "af_unknown"}):
        with pytest.raises(config.ConfigError):
            config.load(write(tmp_path, bad))


def test_guardian_supplies_the_engine_and_the_voice_and_a_request_never_can():
    spoken = executors.EXECUTORS["voice.speak"]
    assert {"voice_tts", "voice_kokoro"} <= set(spoken.supplied) and set(spoken.arguments) == {"text"}
    assert executors.argument_problem("voice.speak", spoken, {"text": "hi", "voice_tts": "piper"})
    code = (ROOT / "kairu" / "guardian_program.py").read_text(encoding="utf-8")
    assert '"voice_tts": cfg.voice_tts' in code and '"voice_kokoro": cfg.voice_kokoro' in code


# --- Kokoro's own program, kept apart -----------------------------------------------------------------------

def test_the_gpl_parts_are_loaded_only_by_kokoros_own_program():
    for path in (ROOT / "kairu").rglob("*.py"):
        if path == WORKER:
            continue
        text = path.read_text(encoding="utf-8")
        for module in GPL:
            assert not re.search(rf"^\s*(?:from|import)\s+{module}\b", text, re.MULTILINE), f"{path.name} imports {module}"


def test_kokoros_program_imports_nothing_of_kairu_writes_nothing_and_reaches_no_network():
    text = WORKER.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:from|import)\s+kairu\b", text, re.MULTILINE)
    for module in ("urllib", "http", "socket", "requests"):
        assert not re.search(rf"^\s*(?:from|import)\s+{module}\b", text, re.MULTILINE)
    assert "open(" not in text and ".write_" not in text


def test_it_runs_isolated_by_its_own_path():
    command = speak.kokoro_command(Path("m.onnx"), Path("v.bin"), "af_heart")
    assert command[:3] == [sys.executable, "-I", str(WORKER)] and command[3:] == ["m.onnx", "v.bin", "af_heart"]


@pytest.mark.parametrize("style", list(speak.STYLES))
def test_kokoro_says_the_answer_a_little_quicker_and_the_question_a_little_slower(style):
    (answer, quick), (question, slow) = speak.kokoro_parts(LINE, style)
    assert answer == "The capital of Japan is Tokyo." and question == "Want to know more about it?"
    assert slow < quick and 0.8 <= slow and quick <= 1.2
    assert speak.kokoro_parts(LINE, speak.PLAIN) == [(LINE, 1.0)]


# --- voice.speak: Kokoro first, Piper if Kokoro cannot ------------------------------------------------------

@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.delenv(speak.TEST_VOICE, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    said = []
    monkeypatch.setattr(speak, "say_with_piper", lambda line, *args, **kwargs: said.append(("piper", line)))
    monkeypatch.setattr(models, "piper_ready", lambda data_dir: Path("piper.exe"))
    monkeypatch.setattr(models, "voice_ready", lambda data_dir, key: (Path("v.onnx"), Path("v.json"), None))
    return said


def test_kokoro_not_set_up_means_piper_speaks(windows, tmp_path):
    speak.main(LINE, str(tmp_path), "us-hfc-female", "warm", "kokoro", "af_heart")
    assert windows == [("piper", LINE)]


def test_kokoro_set_up_speaks_and_piper_does_not(windows, tmp_path, monkeypatch):
    monkeypatch.setattr(models, "kokoro_ready", lambda data_dir: (Path("m.onnx"), Path("v.bin")))
    asked = []
    monkeypatch.setattr(speak, "say_with_kokoro", lambda *args: asked.append(args))
    speak.main(LINE, str(tmp_path), "us-hfc-female", "warm", "kokoro", "bf_emma")
    assert asked == [(LINE, Path("m.onnx"), Path("v.bin"), "bf_emma", "warm")] and windows == []


def test_kokoros_program_not_starting_means_piper_speaks(windows, tmp_path, monkeypatch):
    monkeypatch.setattr(models, "kokoro_ready", lambda data_dir: (Path("m.onnx"), Path("v.bin")))
    monkeypatch.setattr(speak, "say_with_kokoro", lambda *args: speak.NOT_STARTED)
    speak.main(LINE, str(tmp_path), "us-hfc-female", "warm", "kokoro", "af_heart")
    assert windows == [("piper", LINE)]


def test_voice_tts_piper_never_starts_kokoro(windows, tmp_path, monkeypatch):
    monkeypatch.setattr(speak, "say_with_kokoro", lambda *args: pytest.fail("Kokoro started"))
    speak.main(LINE, str(tmp_path), "us-hfc-female", "warm", "piper", "af_heart")
    assert windows == [("piper", LINE)]


# --- reading Kokoro's sound, from a stand-in of its program ---------------------------------------------------

STAND_IN = r'''
import json, struct, sys
request = json.loads(sys.stdin.readline())
out = sys.stdout.buffer
out.write(struct.pack("<I", 24000))
for number, (text, speed) in enumerate(request["parts"]):
    piece = bytes([number + 1]) * 100
    out.write(struct.pack("<I", len(piece)) + piece + struct.pack("<I", 0))
'''


def stand_in(tmp_path, monkeypatch, code):
    script = tmp_path / "worker.py"
    script.write_text(code)
    monkeypatch.setattr(speak, "kokoro_command", lambda model, voices, voice: [sys.executable, "-I", str(script)])


def test_the_sound_comes_part_by_part_and_a_breath_goes_between(tmp_path, monkeypatch):
    stand_in(tmp_path, monkeypatch, STAND_IN)
    played = []

    class Speakers:
        def __init__(self, rate):
            played.append(("rate", rate))

        def play(self, sound):
            played.append(sound)

        def wait(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(speak, "WaveOut", Speakers)
    assert speak.say_with_kokoro(LINE, Path("m"), Path("v"), "af_heart", "warm") is None
    breath = bytes(int(24000 * speak.STYLES["warm"][2]) * 2)
    assert played == [("rate", 24000), b"\x01" * 100, breath, b"\x02" * 100]


def test_a_program_that_ends_before_any_sound_lets_piper_speak(tmp_path, monkeypatch):
    stand_in(tmp_path, monkeypatch, "import sys; sys.exit(1)")
    monkeypatch.setattr(speak, "WaveOut", lambda rate: pytest.fail("the speakers were opened"))
    assert speak.say_with_kokoro(LINE, Path("m"), Path("v"), "af_heart", "warm") == speak.NOT_STARTED


def test_the_real_program_without_its_packages_says_it_could_not_start(tmp_path):
    result = subprocess.run([sys.executable, "-I", str(WORKER), "m.onnx", "v.bin", "af_heart"], input='{"parts": [["Hi.", 1.0]]}\n',
                            capture_output=True, text=True, timeout=60)
    if "could not start" not in result.stderr:
        pytest.skip("kokoro-onnx is installed here, and the files named do not exist")
    assert result.returncode == 1 and result.stdout == ""


@pytest.mark.skipif(not (os.environ.get("KAIRU_TEST_KOKORO") and os.environ.get("KAIRU_TEST_KOKORO_PYTHON")),
                    reason="the real Kokoro: set KAIRU_TEST_KOKORO and KAIRU_TEST_KOKORO_PYTHON")
def test_the_real_kokoro_says_the_answer_and_the_question_as_two_parts():
    folder = Path(os.environ["KAIRU_TEST_KOKORO"])
    command = [os.environ["KAIRU_TEST_KOKORO_PYTHON"], "-I", str(WORKER), str(folder / models.KOKORO_MODEL.name),
               str(folder / models.KOKORO_VOICES.name), "af_heart"]
    request = json.dumps({"parts": speak.kokoro_parts(LINE, "warm"), "lang": "en-us"}) + "\n"
    started = time.monotonic()
    out = subprocess.run(command, input=request.encode(), capture_output=True, timeout=180).stdout
    rate, place, parts, sizes = struct.unpack("<I", out[:4])[0], 4, 0, [0]
    while place < len(out):
        length = struct.unpack("<I", out[place:place + 4])[0]
        place += 4 + length
        if length:
            sizes[-1] += length
        else:
            parts += 1
            sizes.append(0)
    assert rate == 24000 and parts == 2 and all(size > 24000 for size in sizes[:2])  # each part longer than half a second
    print(f"real Kokoro: {time.monotonic() - started:.1f} s for {sum(sizes) / 2 / rate:.1f} s of sound")


# --- listening for your reply after Kairu asks --------------------------------------------------------------

def test_after_kairu_asks_it_listens_for_your_answer_without_kairu_for_a_few_seconds():
    hearing = hearing_of()
    assert hearing.listen_for_reply() == [{"reply": True}] and hearing.session
    assert kinds(hear(hearing, silence(REPLY_SECONDS - 1), pause=0), "quiet") == []
    assert kinds(hear(hearing, silence(2), pause=0), "quiet") == [{"quiet": True}] and not hearing.session


def test_your_answer_is_an_order_and_then_the_session_runs_as_usual():
    hearing = hearing_of("Yes, tell me about its history.")
    hearing.listen_for_reply()
    events = hear(hearing, "open_notepad", pause=1.0)
    assert kinds(events, "order") == [{"order": "yes tell me about its history", "breath": 1}]
    assert kinds(hear(hearing, silence(REPLY_SECONDS + 5), pause=0), "quiet") == [] and hearing.session
    assert kinds(hear(hearing, silence(SESSION_SECONDS), pause=0), "quiet") == [{"quiet": True}]


def test_a_reply_window_is_never_longer_than_8_seconds_and_never_after_stop():
    hearing = hearing_of()
    hearing.listen_for_reply(600)
    assert kinds(hear(hearing, silence(REPLY_SECONDS + 1), pause=0), "quiet") == [{"quiet": True}]
    hearing.stopped = True
    assert hearing.listen_for_reply() == [] and not hearing.session


def test_the_vosk_engine_listens_for_the_reply_the_same_way():
    from kairu.voice import hearing as vosk_hearing
    assert vosk_hearing.REPLY_SECONDS == REPLY_SECONDS
    assert "def listen_for_reply" in (ROOT / "kairu" / "voice" / "hearing.py").read_text(encoding="utf-8")


def test_the_listener_opens_the_reply_window_only_when_the_bar_asks_and_not_while_kairu_speaks():
    code = (ROOT / "kairu" / "voice" / "listen.py").read_text(encoding="utf-8")
    assert 'if reply.get("reply") and not paused:' in code


class Client:
    def __init__(self):
        self.runs = []

    def run(self, action):
        self.runs.append(action)
        return {"run": 1}

    def run_status(self, run):
        return {"outcome": "finished"}


def voice_control(monkeypatch, state="on"):
    from kairu.bar import voice
    monkeypatch.setattr(voice, "ECHO_TAIL", 0)
    control = voice.VoiceControl.__new__(voice.VoiceControl)
    control.state, control.talking, control._last_talk, control.paused, control._want_reply = state, False, 0.0, False, 0
    control.client = Client()
    return control


def test_the_bar_asks_for_the_reply_window_only_after_kairu_asked_aloud_with_the_mic_on(monkeypatch):
    from kairu.bar import voice
    control = voice_control(monkeypatch)
    control.speak("Tokyo. Want to know more about it?")
    assert control._want_reply == voice.REPLY_SECONDS == REPLY_SECONDS and not control.paused
    control._want_reply = 0
    control.speak("Done, I opened Notepad.")
    assert control._want_reply == 0
    off = voice_control(monkeypatch, state="off")
    off.speak("Want to know more?")
    assert off._want_reply == 0 and off.client.runs == []  # with the mic off, nothing is said and nothing opens


def test_the_bar_switches_nothing_on_for_the_reply():
    code = (ROOT / "kairu" / "bar" / "voice.py").read_text(encoding="utf-8")
    reply = code[code.index("self._want_reply = REPLY_SECONDS"):][:200]
    assert "_switch_on" not in reply and "mic_button" not in reply and "listen_key" not in reply
