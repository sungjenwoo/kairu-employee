"""The light voice through the real Guardian program: the bar's voice side (kairu/bar/voice.py) with a stand-in window,
the real listener (voice.listen) and the real small model, a pretend microphone that plays the recorded sounds in real time
(KAIRU_TEST_MIC), a pretend speaker (KAIRU_TEST_VOICE) and the pretend PC (KAIRU_TEST_PC), so no app opens and nothing
restarts. The card stand-in is answered only by the test, as the bar's card is only answered by your typing.
"""

import json
import os
import shutil
import tempfile
import threading
import time

import pytest
import yaml

from kairu import audit, safemode
from kairu.bar.voice import GREETING, NO_VOICE_APPROVALS, WELCOME, VoiceControl
from kairu.brain import keys
from kairu.guardian import Action, Refused
from kairu.store import Store
from kairu.tasks import pc
from kairu.tasks.core import TaskCore
from kairu.voice import mic as microphone, speak
from tests_kairu.fake_provider import FakeProviders
from tests_kairu.helpers import POLICY, wait_for
from tests_kairu.program import family_memory_mib, program, program_with_pin  # noqa: F401 (fixtures)
from tests_kairu.voice_helpers import SOUNDS, PretendMic, PretendVoice, link_model, model_copy, unlink_model  # noqa: F401

GROQ_KEY = "gsk_" + "v" * 40


@pytest.fixture
def providers(monkeypatch):
    fake = FakeProviders()
    fake.answers["groq"] = "It is sunny and 31 degrees in Hyderabad today. Want tomorrow's too?"
    monkeypatch.setenv("KAIRU_TEST_PROVIDERS", fake.url)
    yield fake
    fake.close()


@pytest.fixture
def desk(tmp_path, monkeypatch):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "pc.json").write_text(json.dumps({
        "windows": [], "apps": {"chrome": "C:/apps/chrome.exe", "notepad": "C:/Windows/notepad.exe"}, "volume": 50, "brightness": 70}))
    monkeypatch.setenv(pc.TEST_PC, str(folder))
    return folder


@pytest.fixture
def mic(tmp_path, monkeypatch):
    folder = tmp_path / "mic"
    folder.mkdir()
    monkeypatch.setenv(microphone.TEST_MIC, str(folder))
    return PretendMic(folder)


@pytest.fixture
def speaker(tmp_path, monkeypatch):
    folder = tmp_path / "speaker"
    folder.mkdir()
    monkeypatch.setenv(speak.TEST_VOICE, str(folder))
    return PretendVoice(folder)


@pytest.fixture
def config_path(tmp_path, monkeypatch, desk, mic, speaker, providers, model_copy):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": True, "engine": "vosk"}, "research": {"enabled": False},  # Vosk, the fallback
                                    "brain": {"public_to_cloud": True, "providers": ["groq"]},
                                    "tasks": {"work_folder": str(tmp_path / "Kairu-files")},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    place = link_model(tmp_path / "data", model_copy)
    yield path
    unlink_model(place)


class Screen:
    """The bar's window, as the voice sees it."""

    def __init__(self):
        self.said, self.live, self.mic, self.card, self.shown = [], [], [], False, 0

    def say(self, text):
        self.said.append(text)

    def heard(self, text):
        self.live.append(text)

    def show(self):
        self.shown += 1

    def mic_shown(self, on):
        self.mic.append(on)

    def card_open(self):
        return self.card

    def busy(self):
        return False


class Card:
    """The approval card. Only the test answers it, as only your own typing answers the bar's: here, always "refuse"."""

    def __init__(self, screen):
        self.screen, self.asked, self.refused = screen, [], threading.Event()

    def approve(self, decision):
        self.asked.append(decision.action.name)
        self.screen.card = True
        self.refused.wait(60)
        self.screen.card = False
        return None


@pytest.fixture
def bar(program_with_pin):
    keys.save(program_with_pin.data_dir, "groq", GROQ_KEY)
    screen = Screen()
    card = Card(screen)
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=card.approve)
    voice = VoiceControl(program_with_pin.config, program_with_pin.client, core, screen)
    voice.card_stand_in = card
    yield voice
    card.refused.set()
    voice.close()


def listening(program) -> list[dict]:
    return [run for run in program.client.status()["running"] if run["action"] == "voice.listen"]


def calls(desk) -> list[str]:
    log = desk / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def started(program, action=None) -> list[str]:
    return [row["action"] for row in audit.tail(Store(program.data_dir), 3000, kind="run")
            if row["decision"] == "started" and action in (None, row["action"])]


def logged(program) -> str:
    with Store(program.data_dir).connect() as db:
        return " ".join(str(row) for row in db.execute("SELECT * FROM audit"))


def switch_on(voice, speaker, how="button"):
    """Your click (or Ctrl+Alt+V), then the greeting is said and the mic is listening again."""
    voice.mic_button() if how == "button" else voice.listen_key()
    wait_for(lambda: voice.state == "on", timeout=30)
    wait_for(lambda: GREETING in speaker.lines(), timeout=20)
    assert settled(voice), "the voice never calmed down"


def settled(voice, seconds=0.6, most=15.0):
    """Nothing in hand for a while: no order, no answer being spoken. False if it never calms down (Kairu answering itself)."""
    calm_since = given_up = time.monotonic()
    while time.monotonic() - calm_since < seconds:
        if time.monotonic() - given_up > most:
            return False
        if voice.working or voice.paused or not voice._orders.empty():
            calm_since = time.monotonic()
        time.sleep(0.05)
    return True


def say(mic, voice, name, timeout=40):
    """One recorded order into the pretend mic; waits until it has been heard, handled and answered."""
    file = mic.say(name)
    wait_for(lambda: file in mic.played(), timeout=timeout)
    time.sleep(seconds_of(name) + 1.2)  # it is heard in real time, and the pause after it ends the utterance
    assert settled(voice, most=timeout), "the voice never calmed down"


def seconds_of(name) -> float:
    import wave
    with wave.open(str(SOUNDS / f"{name}.wav")) as recorded:
        return recorded.getnframes() / recorded.getframerate()


# --- the mic: off at first; only your click or keystroke --------------------------------------------------------

def test_the_mic_starts_off_and_only_your_click_switches_it_on_and_off(bar, program_with_pin, mic, speaker):
    time.sleep(1)
    assert bar.state == "off" and not listening(program_with_pin) and mic.played() == [] and started(program_with_pin) == []
    switch_on(bar, speaker)
    assert listening(program_with_pin) and bar.ui.mic[0] is True and GREETING in bar.ui.said
    bar.mic_button()
    wait_for(lambda: not listening(program_with_pin), timeout=5)
    assert bar.state == "off" and bar.ui.mic[-1] is False


def test_ctrl_alt_v_starts_listening_with_go_ahead(bar, program_with_pin, speaker):
    switch_on(bar, speaker, how="key")
    assert speaker.lines() == [GREETING] and bar.session


def test_a_voice_listen_nobody_switched_on_never_opens_the_mic(bar, program_with_pin, mic):
    """Your phone, a mission or anything else may ask Guardian for voice.listen: without the token of a mic you switched on
    in the bar, the listener is refused by the bar and ends before it opens the microphone."""
    mic.say("kairu_open_chrome_and_volume")
    run = program_with_pin.client.run(Action("voice.listen", {"session": "f" * 32}))
    wait_for(lambda: program_with_pin.client.run_status(run["run"])["outcome"] is not None, timeout=20)
    assert program_with_pin.client.run_status(run["run"])["outcome"] == "refused" and mic.played() == [] and bar.state == "off"


def test_safe_mode_keeps_the_mic_off(bar, program_with_pin, mic):
    safemode.enter(Store(program_with_pin.data_dir), "a test")
    bar.mic_button()
    wait_for(lambda: bar.state == "off" and any("Safe Mode" in line for line in bar.ui.said), timeout=10)
    assert not listening(program_with_pin) and mic.played() == []


# --- the flow ---------------------------------------------------------------------------------------------------

def test_kairu_open_chrome_and_set_volume_to_30_runs_both_steps_through_guardian_in_order(bar, program_with_pin, mic, speaker, desk):
    switch_on(bar, speaker)
    say(mic, bar, "kairu_open_chrome_and_volume")
    assert calls(desk) == ["launch C:/apps/chrome.exe", "volume 30 None"]
    assert [name for name in started(program_with_pin) if name in ("apps.open", "system.volume")] == ["apps.open", "system.volume"]
    assert "Opened chrome. Volume 30." in bar.ui.said
    assert speaker.lines() == [GREETING]  # Tenmin, K-7: finished tasks stay quiet, a line in the bar and no speech


def test_the_words_appear_live_in_the_bar(bar, program_with_pin, mic, speaker):
    switch_on(bar, speaker)
    say(mic, bar, "set_volume_twenty")
    live = [text for text in bar.ui.live if text]
    assert len(live) >= 2 and live[-1] == "set volume to 20"


def test_search_the_weather_goes_to_the_brain_and_the_short_answer_is_spoken_and_shown(bar, program_with_pin, mic, speaker, providers):
    switch_on(bar, speaker)
    say(mic, bar, "kairu_search_weather")
    tenmin_line = "It is sunny and 31 degrees in Hyderabad today. Want tomorrow's too?"  # the answer, then one follow-up
    wait_for(lambda: speaker.lines()[-1] == tenmin_line, timeout=30)
    assert "brain.ask" in started(program_with_pin) and any(line.startswith("It is sunny") and "tomorrow" in line for line in bar.ui.said)
    assert "search the weather" in providers.text_heard()


def test_thank_you_ends_the_session_and_an_order_without_kairu_then_does_nothing(bar, program_with_pin, mic, speaker, desk):
    switch_on(bar, speaker)
    say(mic, bar, "thank_you")
    assert speaker.lines()[-1] == WELCOME and not bar.session
    say(mic, bar, "open_notepad")
    say(mic, bar, "no_kairu")
    assert calls(desk) == [] and "apps.open" not in started(program_with_pin)


def test_kairus_own_voice_never_wakes_it_or_gives_an_order(bar, program_with_pin, mic, speaker, desk):
    """While Kairu says its greeting, the room's sound (here: Kairu saying "Kairu, open Notepad") reaches the mic."""
    (speaker.folder / "echo.cue").write_text(str(SOUNDS / "kairus_own_voice.wav"), encoding="utf-8")
    switch_on(bar, speaker)
    wait_for(lambda: any(name.startswith("zz") for name in mic.played()), timeout=10)
    time.sleep(3)
    assert calls(desk) == [] and "apps.open" not in started(program_with_pin) and speaker.lines() == [GREETING]


# --- Guardian still decides -------------------------------------------------------------------------------------

def test_kairu_restart_waits_for_the_card_a_spoken_yes_or_pin_is_ignored_and_refusing_restarts_nothing(bar, program_with_pin, mic, speaker, desk):
    switch_on(bar, speaker)
    mic.say("kairu_restart")
    wait_for(lambda: bar.card_stand_in.asked == ["system.restart"], timeout=30)
    file = mic.say("yes")
    wait_for(lambda: file in mic.played(), timeout=20)
    file = mic.say("pin")
    wait_for(lambda: file in mic.played(), timeout=20)
    time.sleep(3)
    assert NO_VOICE_APPROVALS in bar.ui.said and calls(desk) == []
    assert "approval" not in [row["kind"] for row in audit.tail(Store(program_with_pin.data_dir), 200)]  # nothing was approved
    bar.card_stand_in.refused.set()
    wait_for(lambda: any("you refused it" in line for line in bar.ui.said), timeout=20)
    assert calls(desk) == [] and "system.restart" not in started(program_with_pin)


# --- the stop ---------------------------------------------------------------------------------------------------

def test_kairu_stop_halts_a_running_task_in_under_1_second_and_the_mic_goes_off(bar, program_with_pin, mic, speaker):
    switch_on(bar, speaker)
    demo = program_with_pin.client.run(Action("demo.count", {"seconds": 60, "quiet": True}))
    file = mic.say("kairu_stop")
    wait_for(lambda: program_with_pin.client.run_status(demo["run"])["outcome"] == "halted", timeout=20)

    def halted():
        return [row for row in audit.tail(Store(program_with_pin.data_dir), 100, kind="run")
                if row["decision"] == "halted" and row["action"] == "demo.count"]

    wait_for(halted, timeout=5)  # the row is written just after the programs are gone
    took = halted()[0]["details"]["seconds_since_stop"]
    print(f"\n  'Kairu, stop' -> `kairu demo` inside Guardian halted in {took:.3f} s; mic off")
    assert took < 1.0 and file in mic.played()
    wait_for(lambda: bar.state == "off" and not listening(program_with_pin), timeout=10)
    store = Store(program_with_pin.data_dir)
    assert safemode.is_safe(store) and "voice" in safemode.reason(store)
    assert any("Safe Mode" in line for line in bar.ui.said)


def test_every_emergency_stop_turns_the_mic_off(bar, program_with_pin, speaker):
    switch_on(bar, speaker)
    safemode.emergency_stop(Store(program_with_pin.data_dir), "kairu stop")  # as `kairu stop` or Ctrl+Alt+K do
    wait_for(lambda: bar.state == "off" and not listening(program_with_pin), timeout=10)


# --- what is kept: nothing but hashes -----------------------------------------------------------------------------

def test_no_sound_is_written_and_the_audit_log_keeps_only_hashes_of_your_words(bar, program_with_pin, mic, speaker, desk, tmp_path):
    began = time.time()
    switch_on(bar, speaker)
    token = bar._token
    say(mic, bar, "kairu_open_chrome_and_volume")
    everything = logged(program_with_pin)
    for words in ("chrome", "volume 30", "Go ahead", "listening", "Opened", token):
        assert words.lower() not in everything.lower(), words
    assert {"voice.listen", "voice.speak"} <= set(started(program_with_pin))
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
                if name.lower().endswith((".wav", ".pcm", ".raw", ".mp3", ".ogg", ".flac")) or head[:4] == b"RIFF":
                    made.append(path)
    assert made == []


AT_REST_MIB, SPEAKING_MIB = 190, 381  # 200 MB with the listener alone; 400 MB while Kairu speaks (proposed ADR, VOICE.md)
PIPER_SPEAKS = """import sys, time
from pathlib import Path
from kairu.voice import models, speak
data = Path(sys.argv[1])
piper, (onnx, config, speaker) = models.piper_ready(data), models.voice_ready(data, models.DEFAULT_VOICE)
line = ("Rain forms when the sun warms water and it rises as vapour. High up, the vapour cools and joins into tiny drops that "
        "make clouds. For example, steam from a kettle turns into drops on a cold plate. Isn't that neat?")  # Explain Mode: the longest
for _ in range(2):
    for piece in speak.synthesize(line, piper, onnx, speaker):
        pass
"""


def tree_mib(pid: int) -> float:
    """Working set of a process and every process under it, however deep (voice.speak's Python, then piper.exe)."""
    from tests_kairu.program import children, memory_mib
    total, waiting = 0.0, [pid]
    while waiting:
        member = waiting.pop()
        try:
            total += memory_mib(member)[0]
        except (AssertionError, OSError, FileNotFoundError):
            continue
        waiting += children(member)
    return total


def piper_peak_mib() -> float:
    """voice.speak's family while Piper speaks: its Python and piper.exe, with the voice the owner starts with (not played)."""
    import subprocess
    import sys
    from kairu.config import ROOT
    from kairu.voice import models
    try:
        models.piper_ready(ROOT / "data")
        models.voice_ready(ROOT / "data", models.DEFAULT_VOICE)
    except models.NotSetUp:
        pytest.skip("Piper is not set up in this folder: run `kairu voice setup` (tools/check_guardian.py does it)")
    speaking = subprocess.Popen([sys.executable, "-c", PIPER_SPEAKS, str(ROOT / "data")], cwd=ROOT)
    most = 0.0
    try:
        while speaking.poll() is None:
            try:
                most = max(most, tree_mib(speaking.pid))
            except (AssertionError, OSError, LookupError):
                pass
            time.sleep(0.05)
    finally:
        if speaking.poll() is None:
            speaking.kill()
    assert speaking.returncode == 0
    return most


def listener_peak(bar, program, mic, speaker) -> float:
    switch_on(bar, speaker)
    say(mic, bar, "kairu_open_chrome_and_volume")
    [run] = listening(program)
    return max(family_memory_mib(run["pid"])[1], tree_mib(run["pid"]))


def test_the_voice_stays_under_200_mb_at_rest(bar, program_with_pin, mic, speaker):
    peak = listener_peak(bar, program_with_pin, mic, speaker)
    print(f"\n  Voice process memory at rest (voice.listen, the small model, two recognizers): peak {peak:.0f} MiB; limit 200 MB")
    assert peak < AT_REST_MIB


@pytest.mark.skipif(os.name != "nt", reason="the Piper build Kairu uses (rhasspy/piper 2023.11.14-2) is for Windows")
def test_the_whole_voice_stays_under_400_mb_while_kairu_speaks(bar, program_with_pin, mic, speaker):
    peak = listener_peak(bar, program_with_pin, mic, speaker)
    speaking = piper_peak_mib()
    print(f"\n  Voice process memory while Kairu speaks (listener {peak:.0f} MiB + voice.speak with Piper {speaking:.0f} MiB): "
          f"{peak + speaking:.0f} MiB; limit 400 MB")
    assert peak + speaking < SPEAKING_MIB
