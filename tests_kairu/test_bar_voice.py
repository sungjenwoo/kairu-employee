"""The bar's mic button and live words (Sprint Day 2). Skipped where there is no screen. Guardian is a stand-in here;
tests_kairu/test_voice_program.py runs the voice through the real Guardian.
"""

import subprocess
import sys
import time

import pytest
import yaml

from kairu import config as kairu_config
from kairu.config import ROOT
from kairu.guardian import Refused
from tests_kairu.helpers import POLICY
from tests_kairu.program import family_memory_mib
from tests_kairu.test_bar import StandInCore, StandInGuardian, make_bar, pump


class VoiceOffGuardian(StandInGuardian):
    """Guardian with voice switched off in its own config.yaml: it refuses voice.listen."""

    def run(self, action, approval=None):
        raise Refused(f"{action.name} is switched off in config.yaml")


@pytest.fixture
def voice_config(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": True}, "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


@pytest.fixture
def voice_bar(voice_config):
    pytest.importorskip("tkinter")
    from kairu.bar.app import WINDOW_TRIES, Bar
    import tkinter
    cfg = kairu_config.load(voice_config)
    for tries_left in range(WINDOW_TRIES - 1, -1, -1):
        try:
            made = Bar(cfg, core=StandInCore(), client=VoiceOffGuardian())
            break
        except tkinter.TclError as error:
            if not tries_left:
                pytest.skip(f"no screen here ({error})")
            time.sleep(0.5)
    yield made
    made.close()


def test_without_voice_there_is_no_mic_button(config):
    made = make_bar(config, core=StandInCore())
    try:
        assert made.mic_button is None and made.voice is None and made.heard_line is None
    finally:
        made.close()


def test_the_mic_button_is_there_and_off_at_every_start(voice_bar):
    assert voice_bar.mic_button.cget("text") == "Mic" and voice_bar.voice.state == "off"
    assert not voice_bar.heard_line.winfo_ismapped()


def test_your_click_asks_guardian_and_a_refusal_is_said_plainly_and_leaves_it_off(voice_bar):
    voice_bar.show()
    voice_bar.mic_button.invoke()  # your click, in the test
    pump(voice_bar, lambda: "refused voice.listen" in voice_bar.reply_line.cget("text"))
    assert voice_bar.voice.state == "off" and voice_bar.mic_button.cget("text") == "Mic"


def test_the_live_words_line_shows_what_you_say(voice_bar):
    voice_bar.show()
    voice_bar._mic_look(True)
    voice_bar._show_heard("open chrome and set")
    voice_bar.root.update()
    assert voice_bar.heard_line.winfo_ismapped() and "open chrome and set" in voice_bar.heard_line.cget("text")
    voice_bar._mic_look(False)
    voice_bar.root.update()
    assert not voice_bar.heard_line.winfo_ismapped() and voice_bar.mic_button.cget("text") == "Mic"


def test_stop_and_locking_the_pc_turn_the_mic_off(voice_bar, monkeypatch):
    off = []
    monkeypatch.setattr(voice_bar.voice, "mic_off", lambda why="": off.append(why))
    voice_bar.stop_button.invoke()
    pump(voice_bar, lambda: off)
    assert "Stopped everything" in off[0]
    voice_bar.watch.on_change("the PC locked")
    assert off[-1] == "Mic off: the PC locked."


class Kept(list):
    """Stands in for the voice's order queue: keeps what is put, hands nothing on."""

    def put(self, item):
        self.append(item)


def test_a_spoken_order_while_the_card_is_open_is_dropped_never_kept_for_later(voice_bar, monkeypatch):
    from kairu.bar.voice import NO_VOICE_APPROVALS
    kept = Kept()
    monkeypatch.setattr(voice_bar.voice, "_orders", kept)
    voice_bar._answer = {"done": None}  # a card is open
    voice_bar.voice._event({"order": "restart"})
    voice_bar.voice._event({"ignored": "yes or digits"})
    pump(voice_bar, lambda: voice_bar.reply_line.cget("text") == NO_VOICE_APPROVALS)
    assert kept == [] and voice_bar.core.orders == []
    voice_bar._answer = None
    voice_bar.voice._event({"order": "restart"})
    assert kept == [("order", "restart")]  # with no card open, the same order is handed on


class Line:
    """A listener at the other end of the voice link, as a test plays it."""

    def __init__(self, hello):
        self.waiting, self.answers = [hello], []

    def receive(self, timeout=5):
        from kairu.voice.link import LinkError
        if not self.waiting:
            raise LinkError("gone")
        return self.waiting.pop(0)

    def send(self, message, timeout=5):
        self.answers.append(message)

    last = send


def test_only_the_token_of_the_mic_you_switched_on_is_accepted(voice_bar):
    """Even while your own mic is starting, a listener with another token is refused, before it can open the microphone."""
    voice = voice_bar.voice
    voice.state, voice._token = "starting", "a" * 32  # as just after your click
    for other in ("b" * 32, "a" * 31, "", None):
        line = Line({"hello": other})
        voice._converse(line)
        assert line.answers == [{"ok": False}], other
    right = Line({"hello": "a" * 32})
    from kairu.voice.link import LinkError
    with pytest.raises(LinkError):  # accepted; then this listener goes away
        voice._converse(right)
    assert right.answers[0] == {"ok": True}
    voice.state, voice._token = "off", None
    late = Line({"hello": "a" * 32})
    voice._converse(late)
    assert late.answers == [{"ok": False}]  # and none at all while the mic is off


def test_the_bar_with_voice_stays_under_60_mb(voice_bar, voice_config):
    process = subprocess.Popen([sys.executable, "-m", "kairu.bar.app", "--config", str(voice_config)], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(3)
        assert process.poll() is None, process.stdout.read()
        now, peak = family_memory_mib(process.pid)
        print(f"\n  the Kairu bar's own process, with voice on: {now:.0f} MiB (peak {peak:.0f} MiB)")
        assert now < 57  # 60 MB
        from kairu.bar.app import QUIT_FILE
        (voice_config.parent / "data" / QUIT_FILE).write_text("")
        process.wait(15)
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
