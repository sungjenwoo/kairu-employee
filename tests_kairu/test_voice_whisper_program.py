"""The light voice with Whisper (voice.engine: whisper-base.en, the default) through the real Guardian program: the bar's voice side
with a stand-in window, the real listener and its speech gate, the pretend microphone playing the recorded sounds in real
time, the pretend speaker and the pretend PC, as in test_voice_program.py (which keeps Vosk, the fallback).

Whisper is the tests' pretend one (KAIRU_TEST_WHISPER: what it "hears" for each recording is written below), so these run
everywhere with nothing downloaded. Where Whisper base.en and tiny.en are set up in this folder (the owner's PC), the tests
marked "real" run with each of them instead (voice.engine: whisper-base.en, whisper-tiny.en), through the same Guardian, and
measure them.
"""

import json
import os
import shutil
import tempfile
import time

import pytest
import yaml

from kairu import audit, safemode
from kairu.guardian import Action
from kairu.store import Store
from kairu.voice import models, whisper as kw
from tests_kairu.helpers import POLICY, wait_for
from tests_kairu.program import family_memory_mib, program, program_with_pin  # noqa: F401 (fixtures)
from tests_kairu.test_voice_program import (AT_REST_MIB, SPEAKING_MIB, bar, calls, desk, listening, logged, mic,  # noqa: F401
                                            piper_peak_mib, providers, say, seconds_of, speaker, started, switch_on, tree_mib)
from tests_kairu.voice_helpers import link_model, unlink_model

WHAT_WHISPER_HEARS = {  # recording -> what the pretend Whisper hears, an utterance at a time
    "kairu_open_chrome_and_volume": ["Kairu, open Chrome and set volume to 30."],
    "kairu_stop": ["Kairu, stop."],
    "kairu_open": ["Kairu, set the volume to 230."],  # Whisper heard "to 30" as "230"
    "yes": ["Yes."],
    "set_volume_twenty": ["Set volume to 20."],
    "kairu_search_weather": ["Kairu, search the weather."],
    "kairu_filler": ["Kairu, search the volume to 30."],  # tiny.en heard the owner's "set the volume" so (10 Nov 2026)
}
LOAD_PEAK_MIB = {  # the short peak the owner allows, at load and with each sentence (10 Nov 2026)
    "base.en": 315,  # about 307 MiB
    "tiny.en": 215,  # about 211 MiB
}


@pytest.fixture(params=["pretend", "base.en", "tiny.en"])
def hearing(request, tmp_path_factory, monkeypatch, tmp_path):
    """The pretend Whisper everywhere; Whisper base.en (the default) and tiny.en where they are set up here (a copy of each,
    linked into the test's data). (kind, the model's folder, the engine in config.yaml)."""
    if request.param == "pretend":
        script = tmp_path / "whisper.json"
        script.write_text(json.dumps(WHAT_WHISPER_HEARS), encoding="utf-8")
        monkeypatch.setenv(kw.TEST_WHISPER, str(script))
        default = models.WHISPERS[models.WHISPER]  # a stand-in folder with setup's mark: the pretend Whisper reads no model
        folder = tmp_path / "pretend-model" / default.folder(".").name
        folder.mkdir(parents=True)
        for name, *_ in default.files:
            (folder / name).write_bytes(b"")
        (folder / models.WHISPER_MARK).write_text(json.dumps(models.whisper_mark(default)), encoding="utf-8")
        return "pretend", folder, None
    pytest.importorskip("faster_whisper")
    from kairu.config import ROOT
    try:
        place = models.whisper_ready(ROOT / "data", request.param)
    except models.NotSetUp:
        pytest.skip(f"Whisper {request.param} is not set up in this folder (`kairu voice setup`)")
    monkeypatch.delenv(kw.TEST_WHISPER, raising=False)
    copy = tmp_path_factory.getbasetemp() / "whisper-model" / place.name
    if not copy.exists():
        shutil.copytree(place, copy)
    return "real", copy, f"whisper-{request.param}"


@pytest.fixture
def config_path(tmp_path, monkeypatch, desk, mic, speaker, providers, hearing):
    path = tmp_path / "config.yaml"
    voice = {"enabled": True, "engine": hearing[2]} if hearing[2] else {"enabled": True}  # pretend: the default engine
    path.write_text(yaml.safe_dump({"voice": voice, "research": {"enabled": False},
                                    "brain": {"public_to_cloud": True, "providers": ["groq"]},
                                    "tasks": {"work_folder": str(tmp_path / "Kairu-files")},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    place = link_model(tmp_path / "data", hearing[1]) if hearing[1] else None
    yield path
    if place:
        unlink_model(place)


def pretend_only(hearing):
    if hearing[0] != "pretend":
        pytest.skip("this one needs words the recordings do not say: the pretend Whisper only")


def real_only(hearing):
    if hearing[0] != "real":
        pytest.skip("a measure of Whisper base.en or tiny.en itself")


def whisper_key(hearing) -> str:
    return models.WHISPER_ENGINES[hearing[2] or models.ENGINES[0]]


# --- the flow ----------------------------------------------------------------------------------------------------

def test_the_default_engine_is_whisper_and_runs_both_steps_through_guardian(bar, program_with_pin, mic, speaker, desk, hearing):
    assert program_with_pin.config.voice_engine == (hearing[2] or "whisper-base.en")
    switch_on(bar, speaker)
    say(mic, bar, "kairu_open_chrome_and_volume")
    wait_for(lambda: len(calls(desk)) == 2, timeout=20)
    assert calls(desk) == ["launch C:/apps/chrome.exe", "volume 30 None"]
    assert "Opened chrome. Volume 30." in bar.ui.said and "open chrome and set volume to 30" in bar.ui.live
    assert speaker.lines() == ["Go ahead, I'm listening."]  # finished tasks stay quiet


def test_volume_230_asks_did_you_mean_30_and_changes_nothing_a_spoken_yes_included(bar, program_with_pin, mic, speaker, desk, hearing):
    pretend_only(hearing)
    switch_on(bar, speaker)
    say(mic, bar, "kairu_open")
    wait_for(lambda: "Did you mean 30?" in speaker.lines(), timeout=20)
    say(mic, bar, "yes")
    wait_for(lambda: any("say it again with the number" in line for line in speaker.lines()), timeout=20)
    time.sleep(1)
    assert calls(desk) == [] and "system.volume" not in started(program_with_pin)
    say(mic, bar, "set_volume_twenty")  # said again, with the number: now it is an order
    wait_for(lambda: calls(desk) == ["volume 20 None"], timeout=20)


def test_search_the_volume_is_never_a_search_it_asks_and_waits_for_the_order_again(bar, program_with_pin, mic, speaker, desk, hearing):
    """Whisper heard "set the volume to 30" as "search the volume to 30": no search (no brain.ask, nothing to the web), no
    volume change, one question; a spoken yes changes nothing; the order said again runs."""
    pretend_only(hearing)
    switch_on(bar, speaker)
    say(mic, bar, "kairu_filler")
    wait_for(lambda: "Did you mean set the volume to 30?" in speaker.lines(), timeout=20)
    say(mic, bar, "yes")
    wait_for(lambda: any("say it again with the number" in line for line in speaker.lines()), timeout=20)
    time.sleep(1)
    assert calls(desk) == [] and not {"brain.ask", "system.volume", "web.search"} & set(started(program_with_pin))
    say(mic, bar, "set_volume_twenty")
    wait_for(lambda: calls(desk) == ["volume 20 None"], timeout=20)
    assert "brain.ask" not in started(program_with_pin)


def test_with_the_mic_on_and_you_silent_whisper_never_runs(bar, program_with_pin, mic, speaker, hearing):
    pretend_only(hearing)
    switch_on(bar, speaker)
    time.sleep(20)
    heard = mic.folder / "heard.log"
    assert not heard.exists() and listening(program_with_pin)


# --- the stop ----------------------------------------------------------------------------------------------------

def test_kairu_stop_heard_by_whisper_halts_everything_within_1_second_of_the_words(bar, program_with_pin, mic, speaker, hearing):
    switch_on(bar, speaker)
    demo = program_with_pin.client.run(Action("demo.count", {"seconds": 60, "quiet": True}))
    file = mic.say("kairu_stop")
    wait_for(lambda: file in mic.played(), timeout=20, every=0.005)
    import array
    from tests_kairu.voice_helpers import sound
    loud = [i for i, sample in enumerate(array.array("h", sound("kairu_stop"))) if abs(sample) > 500]
    words_end = time.time() + loud[-1] / 16000  # heard in real time from now; the words end at its last loud sound
    assert loud[-1] / 16000 <= seconds_of("kairu_stop")
    wait_for(lambda: program_with_pin.client.run_status(demo["run"])["outcome"] == "halted", timeout=30)
    store = Store(program_with_pin.data_dir)

    def halted():
        return [row for row in audit.tail(store, 100, kind="run") if row["decision"] == "halted" and row["action"] == "demo.count"]

    wait_for(halted, timeout=5)
    gone = halted()[0]["details"]["seconds_since_stop"]
    after_words = safemode.stop_requested_at(store) - words_end
    if hearing[0] == "pretend":  # the pretend Whisper wrote down when it heard the words
        heard_at = float((mic.folder / "heard.log").read_text(encoding="utf-8").split()[-2])
        written = safemode.stop_requested_at(store) - heard_at
        print(f"\n  'Kairu, stop' (pretend Whisper): the stop written {written:.3f} s after the words were heard; "
              f"`kairu demo` gone {gone:.3f} s after that: {written + gone:.3f} s in all (limit 1 s)")
        assert written + gone < 1.0
    else:  # the real Whisper: the pause that ends the utterance (0.6 s), Whisper's own time (tiny.en 0.4 s on an idle PC,
        # up to 1.5 s while the PC is busy), then the stop: from Whisper's words to the halt is the pretend run's measure above
        print(f"\n  'Kairu, stop' (Whisper {whisper_key(hearing)}): the stop written {after_words:.3f} s after the words ended "
              f"(a 0.6 s pause, then Whisper); `kairu demo` gone {gone:.3f} s after that")
        assert after_words < 3.0 and gone < 1.0
    assert file in mic.played()
    wait_for(lambda: bar.state == "off" and not listening(program_with_pin), timeout=10)
    assert safemode.is_safe(store) and "voice" in safemode.reason(store)


# --- what is kept: nothing but hashes ------------------------------------------------------------------------------

def test_no_sound_is_written_and_the_audit_log_keeps_only_hashes(bar, program_with_pin, mic, speaker, desk, tmp_path, hearing):
    began = time.time()
    switch_on(bar, speaker)
    say(mic, bar, "kairu_open_chrome_and_volume")
    wait_for(lambda: len(calls(desk)) == 2, timeout=20)
    everything = logged(program_with_pin) + (program_with_pin.data_dir / "guardian.log").read_text(errors="replace")
    for words in ("chrome", "volume 30", "Go ahead", "Opened", bar._token or "-"):
        assert words.lower() not in everything.lower(), words
    made = []
    for folder in (tmp_path, tempfile.gettempdir()):
        for root, _, files in os.walk(folder):
            for name in files:
                path = os.path.join(root, name)
                try:
                    if os.path.getmtime(path) < began:
                        continue
                    with open(path, "rb") as file:
                        head = file.read(12)
                except OSError:
                    continue
                if name.lower().endswith((".wav", ".pcm", ".raw", ".mp3", ".ogg", ".flac", ".npy")) or head[:4] == b"RIFF":
                    made.append(path)
    assert made == []


# --- memory, with Whisper base.en and tiny.en themselves -----------------------------------------------------------

def listener_after_an_order(bar, program, mic, speaker) -> tuple[float, float]:
    switch_on(bar, speaker)
    say(mic, bar, "kairu_open_chrome_and_volume")
    time.sleep(2)
    [run] = listening(program)
    now, peak = family_memory_mib(run["pid"])
    return max(now, tree_mib(run["pid"])), peak


def test_whisper_stays_under_200_mb_at_rest_with_only_a_short_peak(bar, program_with_pin, mic, speaker, hearing):
    real_only(hearing)
    steady, peak = listener_after_an_order(bar, program_with_pin, mic, speaker)
    key = whisper_key(hearing)
    print(f"\n  The listener with Whisper {key} after an order: {steady:.0f} MiB (limit {AT_REST_MIB} MiB = 200 MB); "
          f"its peak {peak:.0f} MiB (while it loads and hears; under {LOAD_PEAK_MIB[key]} allowed)")
    assert steady < AT_REST_MIB and peak < LOAD_PEAK_MIB[key]


@pytest.mark.skipif(os.name != "nt", reason="the Piper build Kairu uses (rhasspy/piper 2023.11.14-2) is for Windows")
def test_whisper_and_piper_stay_under_400_mb_while_kairu_speaks(bar, program_with_pin, mic, speaker, hearing):
    real_only(hearing)
    steady, _ = listener_after_an_order(bar, program_with_pin, mic, speaker)
    speaking = piper_peak_mib()
    print(f"\n  While Kairu speaks: the listener {steady:.0f} MiB + voice.speak with Piper {speaking:.0f} MiB = "
          f"{steady + speaking:.0f} MiB (limit {SPEAKING_MIB} MiB = 400 MB)")
    assert steady + speaking < SPEAKING_MIB
