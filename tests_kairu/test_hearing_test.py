"""tools/hearing_test.py: what each engine heard, scored the same way for all; the sound only ever in memory and a pipe."""

import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import wave

import pytest

from kairu.config import ROOT
from kairu.voice import models

spec = importlib.util.spec_from_file_location("hearing_test", ROOT / "tools" / "hearing_test.py")
hearing_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hearing_test)
SOUNDS = ROOT / "tests_kairu" / "voice"


@pytest.mark.parametrize("text,wake,order", [
    ("Kairu, set the volume to 30.", True, "set the volume to 30"),
    ("Kai ru, open Chrome", True, "open chrome"),
    ("Cairo, what's open?", True, "what's open"),
    ("Kairu.", True, "wake"),
    ("Kairu, stop.", True, "stop"),
    ("Kairu, thank you.", True, "thanks"),
    ("Open Chrome", False, ""),
    ("Set the volume to 30", False, ""),  # "set" is never taken for the end of "Kairu"
])
def test_whisper_sentences_are_split_into_kairu_and_the_order_kairu_would_act_on(text, wake, order):
    woke, words = hearing_test.split_wake(text)
    assert woke is wake and hearing_test.outcome(woke, words) == order


def test_the_word_error_score_counts_wrong_missing_and_extra_words():
    assert hearing_test.word_errors("set the volume to 30", "set the volume to 30") == (0, 5)
    assert hearing_test.word_errors("set the volume to 30", "said the volume to 13") == (2, 5)
    assert hearing_test.word_errors("open chrome", "open") == (1, 2)
    assert hearing_test.word_errors("open chrome", "please open chrome now") == (2, 2)


def test_every_engines_model_is_pinned_to_its_source_by_sha256():
    for name, (kind, model) in hearing_test.ENGINES.items():
        if kind == "vosk":
            assert model.url.startswith("https://alphacephei.com/vosk/models/") and re.fullmatch(r"[0-9a-f]{64}", model.sha256)
        else:
            assert re.fullmatch(r"[0-9a-f]{40}", model.commit) and model.repo.startswith("Systran/faster-whisper-")
            assert all(re.fullmatch(r"[0-9a-f]{64}", sha) and size > 0 for _, sha, size in model.files)
    assert hearing_test.FASTER_WHISPER == "faster-whisper==1.2.1"


def test_the_tool_writes_no_sound_anywhere():
    """It records into memory and hands the sound to each engine through a pipe; the only files it writes are models."""
    code = (ROOT / "tools" / "hearing_test.py").read_text(encoding="utf-8")
    assert "wave.open" not in code and "write_bytes" not in code and "tofile" not in code
    assert re.findall(r"""open\([^)]*["']wb?["']""", code) == []
    assert code.count(".write_text(") == 2 and "kairu-whisper.json" in code  # the two marks written after a model checks out


def test_an_engine_hears_through_a_pipe_and_answers_what_kairu_would_do(tmp_path):
    """The Vosk engine, in its own process, on two of the test recordings: the listener's own hearing decides."""
    try:
        models.ready(ROOT / "data", "small-en-us")
    except models.NotSetUp:
        pytest.skip("the small model is not set up here (tools/check_guardian.py sets it up)")
    clips = []
    for name in ("kairu_stop", "kairu_search_weather"):
        with wave.open(str(SOUNDS / f"{name}.wav")) as sound:
            clips.append(sound.readframes(sound.getnframes()))
    feed = b"".join(struct.pack("<I", len(clip)) + clip for clip in clips) + struct.pack("<I", 0) + b"m"
    before = set(os.listdir(tmp_path))
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "hearing_test.py"), "--engine", "vosk-small-en-us",
                           "--data", str(ROOT / "data")], input=feed, capture_output=True, cwd=tmp_path, timeout=120)
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    loaded, stop, weather, measure, stop_words, weather_words, end = [json.loads(line) for line in done.stdout.decode().splitlines()]
    assert "loaded" in loaded and measure == {"measure": True} and end == {"done": True}
    assert stop["events"] == "stop" and "weather" in weather["events"]  # what Kairu would do: the listener's own hearing
    assert "stop" in stop_words["raw"] and "weather" in weather_words["raw"]  # what the model heard, only after "measure"
    assert set(os.listdir(tmp_path)) == before  # nothing written where it ran


def test_the_hint_engines_hear_through_the_listeners_own_whisper_hearing(tmp_path):
    """whisper-tiny.en+hint: Kairu's own speech gate, Whisper with the hint, and the words rules, in its own process."""
    pytest.importorskip("faster_whisper")
    try:
        models.whisper_ready(ROOT / "data")
    except models.NotSetUp:
        pytest.skip("Whisper tiny.en is not set up here (`kairu voice setup`)")
    assert hearing_test.ENGINES["whisper-tiny.en+hint"] == ("whisper+hint", models.WHISPERS["tiny.en"])
    assert hearing_test.ENGINES["whisper-base.en+hint"] == ("whisper+hint", models.WHISPERS["base.en"])
    clips = []
    for name in ("kairu_stop", "kairu_search_weather"):
        with wave.open(str(SOUNDS / f"{name}.wav")) as sound:
            clips.append(sound.readframes(sound.getnframes()))
    feed = b"".join(struct.pack("<I", len(clip)) + clip for clip in clips) + struct.pack("<I", 0) + b"m"
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "hearing_test.py"), "--engine", "whisper-tiny.en+hint",
                           "--data", str(ROOT / "data")], input=feed, capture_output=True, cwd=tmp_path, timeout=180)
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    loaded, stop, weather, *_ = [json.loads(line) for line in done.stdout.decode().splitlines()]
    assert "loaded" in loaded and stop["events"] == "stop" and weather["events"] == "search the weather"
    assert "stop" in stop["raw"].lower() and weather["gated"] is True
