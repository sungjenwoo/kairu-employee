"""Live words in the Kairu bar (voice.live_caption_every, your GO of 15 Nov 2026: 0.20 s): while you speak, the bar shows
what Whisper has heard so far, in grey, the way Google shows your words as you speak; the whole sentence replaces them.

A pretend Whisper "hears" more words the longer the sound it is given, and the real speech gate runs on made-up sound, so
nothing here opens a microphone or a model.
"""

import threading
import time

import numpy
import pytest

from kairu import config as kairu_config
from kairu import executors
from kairu.bar import voice as bar_voice
from kairu.config import ROOT
from kairu.voice import words as w
from kairu.voice import whisper as kw

RATE, CHUNK = 16000, 3200  # 0.1 s


class Growing:
    """A pretend Whisper: of `said`, one more word for each `per_word` seconds of sound it is given."""

    def __init__(self, said: str, per_word: float = 0.5, sure: bool = True, slow: float = 0.0):
        self.words, self.per_word, self.sure, self.slow = said.split(), per_word, sure, slow
        self.calls: list[float] = []
        self.lock = threading.Lock()

    def __call__(self, sound: bytes) -> kw.Heard:
        assert sound and len(sound) % 2 == 0
        seconds = len(sound) / (2 * RATE)
        with self.lock:
            self.calls.append(seconds)
        time.sleep(self.slow)
        return kw.Heard(" ".join(self.words[:int(seconds / self.per_word)]), self.sure)


def speech(seconds: float, seed: int = 3) -> bytes:
    """Loud enough for the speech gate (a voice at the microphone), in memory only."""
    return numpy.random.default_rng(seed).normal(0, 3000, int(RATE * seconds)).clip(-32000, 32000).astype(numpy.int16).tobytes()


def silence(seconds: float) -> bytes:
    return bytes(int(RATE * seconds) * 2)


def feed(hearing, audio: bytes) -> list[dict]:
    events = []
    for start in range(0, len(audio), CHUNK):
        events += hearing.feed(audio[start:start + CHUNK])
    return events


def say(hearing, seconds: float = 2.0) -> list[dict]:
    return feed(hearing, silence(1.0) + speech(seconds) + silence(1.5))


def live(events) -> list[str]:
    return [event["hearing"] for event in events if "hearing" in event]


# --- the words appear while you speak ----------------------------------------------------------------------------------

def test_your_words_appear_while_you_speak_and_the_whole_sentence_replaces_them():
    hear = Growing("Kairu, open Notepad")
    hearing = kw.WhisperHearing(hear, background=False, live_every=0.2)
    events = say(hearing)
    assert live(events) == ["open", "open notepad"]  # grey, growing, before you stop
    heard = [event for event in events if "heard" in event]
    assert heard == [{"heard": w.clean(["open", "notepad"])}]
    assert events.index({"hearing": "open notepad"}) < events.index(heard[0])  # shown before the end
    assert events.count({"order": "open notepad", "breath": 1}) == 1  # once, never twice
    assert hearing.whisper_runs == 0 and hearing.live_runs >= 5  # the closing look was the whole sentence: heard once


def test_it_looks_every_fifth_of_a_second_of_your_speech():
    hear = Growing("Kairu, open Notepad")
    hearing = kw.WhisperHearing(hear, background=False, live_every=0.2)
    say(hearing, seconds=2.0)
    looks = hear.calls[:-1]  # the last call is the closing look, once you stop
    steps = numpy.diff(looks)
    assert len(looks) >= 8 and numpy.allclose(steps, 0.2, atol=0.01)  # 5 looks a second, each 0.2 s more sound


def test_off_unless_you_set_it():
    hear = Growing("Kairu, open Notepad")
    hearing = kw.WhisperHearing(hear, background=False)
    events = say(hearing)
    assert live(events) == [] and len(hear.calls) == 1  # as before: Whisper hears the whole sentence once
    assert {"order": "open notepad", "breath": 1} in events


def test_live_words_are_never_an_order_a_stop_or_a_wake():
    hear = Growing("Kairu, stop", per_word=0.3)
    hearing = kw.WhisperHearing(hear, background=False, live_every=0.2)
    events = feed(hearing, silence(1.0) + speech(1.5))  # still speaking: only live looks so far
    assert not hearing.stopped and not any({"stop", "order", "wake"} & set(event) for event in events)
    assert live(events) == ["stop"]  # shown, and nothing more
    events = feed(hearing, silence(1.5))  # now the whole sentence is heard: that is the stop
    assert {"stop": True} in events and hearing.stopped


# --- quick orders: they start as you finish speaking ----------------------------------------------------------------

def _order_at(events, order):
    """Where the order is among the events, and where the utterance ended (the 0.6 s pause)."""
    return events.index({"order": order, "breath": 1}), events.index({"talking": False})


def test_a_quick_order_starts_after_0_2_s_of_quiet_not_after_the_whole_pause():
    hearing = kw.WhisperHearing(Growing("Kairu, open Edge"), background=False, live_every=0.2)
    events = say(hearing)
    sent, ended = _order_at(events, "open edge")
    assert sent < ended  # before the 0.6 s pause had even finished
    assert {"wake": True, "alone": False} in events[:sent]
    assert events.count({"order": "open edge", "breath": 1}) == 1 and hearing.whisper_runs == 0


@pytest.mark.parametrize("order", ["close notepad", "delete report", "open report file", "restart the pc",
                                   "type hello in notepad", "search the weather today"])
def test_every_other_order_still_waits_for_the_whole_sentence(order):
    hearing = kw.WhisperHearing(Growing("Kairu, " + order, per_word=0.3), background=False, live_every=0.2)
    events = say(hearing, seconds=2.5)
    orders = [event for event in events if "order" in event]
    assert len(orders) == 1 and events.index(orders[0]) > events.index({"talking": False})


def test_quick_is_only_short_harmless_orders():
    for text in ("open edge", "open microsoft edge", "launch notepad", "set the volume to 30", "volume up", "mute",
                 "brightness 40", "what's open"):
        assert kw.WhisperHearing.quick(text), text
    for text in ("open edge and close notepad", "open the report file", "close edge", "delete edge", "open",
                 "open my files folder", "shut down", "open edge then chrome", "type hi"):
        assert not kw.WhisperHearing.quick(text), text


def test_an_order_whisper_is_unsure_of_never_starts_early():
    hearing = kw.WhisperHearing(Growing("open Edge", sure=False), background=False, live_every=0.2)
    hearing.start_session()
    events = say(hearing)
    assert not any("order" in event for event in events[:events.index({"talking": False})])


def test_if_you_say_more_after_a_short_pause_only_the_rest_is_sent():
    class TwoParts:
        calls = 0

        def __call__(self, sound):
            self.calls += 1
            seconds = len(sound) / (2 * RATE)
            return kw.Heard("Kairu, open Edge" if seconds < 2.0 else "Kairu, open Edge and close Notepad", True)

    hearing = kw.WhisperHearing(TwoParts(), background=False, live_every=0.2)
    events = feed(hearing, silence(1.0) + speech(1.0) + silence(0.3) + speech(1.2) + silence(1.5))
    orders = [event["order"] for event in events if "order" in event]
    assert orders == ["open edge", "close notepad"]  # Edge once, then only what you added


def test_without_live_words_nothing_starts_early():
    hearing = kw.WhisperHearing(Growing("Kairu, open Edge"), background=False)
    events = say(hearing)
    sent, ended = _order_at(events, "open edge")
    assert sent > ended and hearing.whisper_runs == 1


def test_a_slow_whisper_uses_the_closing_look_as_the_whole_sentence():
    hear = Growing("Kairu, open Edge", slow=0.5)
    hearing = kw.WhisperHearing(hear, live_every=0.2)
    try:
        events, audio = [], silence(1.0) + speech(2.0) + silence(1.5)
        for start in range(0, len(audio), CHUNK):
            events += hearing.feed(audio[start:start + CHUNK])
            time.sleep(0.1)
        deadline = time.monotonic() + 5
        while (hearing._waiting or hearing._live_busy) and time.monotonic() < deadline:
            events += hearing.feed(silence(0.1))
            time.sleep(0.05)
        assert events.count({"order": "open edge", "breath": 1}) == 1
        assert hearing.whisper_runs == 0  # the pause came while the closing look was still with Whisper: it was used
    finally:
        hearing.close()


# --- the same rules as the whole sentence --------------------------------------------------------------------------------

def test_outside_a_session_nothing_is_shown_without_kairu():
    hear = Growing("so what are we having for dinner")
    events = say(kw.WhisperHearing(hear, background=False, live_every=0.2), seconds=3.0)
    assert live(events) == [] and not any("heard" in event for event in events)


def test_outside_a_session_nothing_is_shown_while_whisper_is_unsure_of_kairu():
    hear = Growing("Kairu, open Notepad", sure=False)
    events = say(kw.WhisperHearing(hear, background=False, live_every=0.2))
    assert live(events) == []


def test_in_a_session_your_words_show_without_kairu():
    hearing = kw.WhisperHearing(Growing("what time is it"), background=False, live_every=0.2)
    hearing.start_session()
    events = say(hearing, seconds=2.5)
    assert live(events)[-1] == "what time is it" and {"heard": "what time is it"} in events


def test_a_spoken_pin_is_never_shown_even_live():
    hearing = kw.WhisperHearing(Growing("four seven one nine two", per_word=0.3), background=False, live_every=0.2)
    hearing.start_session()
    events = say(hearing, seconds=2.0)
    assert live(events) == [] and not any("heard" in event for event in events)


def test_kairus_own_voice_is_never_shown():
    hearing = kw.WhisperHearing(Growing("Kairu, the weather in Hyderabad is sunny"), background=False, live_every=0.2)
    hearing.start_session()
    events, audio = [], silence(1.0) + speech(2.5) + silence(1.5)
    for start in range(0, len(audio), CHUNK):
        hearing.set_echo("the weather in Hyderabad is sunny")  # voice.barge_in: the listener says so with every tenth
        events += hearing.feed(audio[start:start + CHUNK])
    assert live(events) == []


def test_grey_words_go_when_the_whole_sentence_shows_nothing():
    class ThenNothing(Growing):
        def __call__(self, sound):
            heard = super().__call__(sound)
            return kw.Heard("", False) if len(sound) / (2 * RATE) > 2.2 else heard  # the whole sentence: noise after all

    events = say(kw.WhisperHearing(ThenNothing("Kairu, open Notepad"), background=False, live_every=0.2))
    assert live(events)[:1] == ["open"] and live(events)[-1] == ""  # cleared, never left in the bar
    assert not any("order" in event for event in events)


# --- never piled up: a slow PC shows the words as fast as it can -------------------------------------------------------

def test_a_slow_whisper_is_never_asked_again_before_it_answers():
    hear = Growing("Kairu, open Notepad", slow=0.35)
    hearing = kw.WhisperHearing(hear, live_every=0.2)
    try:
        events = []
        for start in range(0, len(audio := silence(1.0) + speech(2.0) + silence(1.5)), CHUNK):
            events += hearing.feed(audio[start:start + CHUNK])
            time.sleep(0.1)  # in real time, as the microphone gives it
        deadline = time.monotonic() + 5
        while hearing._waiting and time.monotonic() < deadline:
            events += hearing.feed(silence(0.1))
            time.sleep(0.05)
        assert {"order": "open notepad", "breath": 1} in events
        spoken = 2.0 / 0.2
        assert hearing.live_runs < spoken  # it skipped looks while Whisper was busy
        gaps = numpy.diff(hear.calls[:-1])
        assert len(gaps) and gaps.min() >= 0.2 - 0.01  # never two looks at once, never a queue
    finally:
        hearing.close()


# --- your setting, supplied by Guardian ----------------------------------------------------------------------------------

def _config(tmp_path, voice: str):
    path = tmp_path / "config.yaml"
    path.write_text(f"voice:\n  enabled: true\n{voice}guardian:\n  data_dir: data\n", encoding="utf-8")
    return kairu_config.load(path)


def test_the_setting_is_off_by_default_and_takes_a_fifth_of_a_second(tmp_path):
    assert _config(tmp_path, "").voice_live_every == 0.0
    assert _config(tmp_path, "  live_caption_every: 0.20\n").voice_live_every == 0.2
    assert _config(tmp_path, "  live_caption_every: 1\n").voice_live_every == 1.0


@pytest.mark.parametrize("value", ["0.05", "5", "-1", "fast", "true"])
def test_a_wrong_setting_is_refused(tmp_path, value):
    with pytest.raises(kairu_config.ConfigError, match="live_caption_every"):
        _config(tmp_path, f"  live_caption_every: {value}\n")


def test_guardian_supplies_it_from_its_own_config_never_a_request():
    listen = executors.EXECUTORS["voice.listen"]
    assert "voice_live_every" in listen.supplied and "voice_live_every" not in listen.arguments
    assert '"voice_live_every": cfg.voice_live_every' in (ROOT / "kairu" / "guardian_program.py").read_text(encoding="utf-8")
    listen_py = (ROOT / "kairu" / "voice" / "listen.py").read_text(encoding="utf-8")
    assert "WhisperHearing(hear, live_every=live_every)" in listen_py


# --- the bar shows them in grey ------------------------------------------------------------------------------------------

class Shown:
    def __init__(self, live: bool = True):
        self.lines: list[tuple[str, str]] = []
        if live:
            self.hearing = lambda text: self.lines.append(("grey", text))

    def heard(self, text):
        self.lines.append(("white", text))


def _control(ui):
    control = object.__new__(bar_voice.VoiceControl)
    control.ui = ui
    return control


def test_the_bar_shows_live_words_grey_then_the_sentence_white():
    ui = Shown()
    control = _control(ui)
    for event in ({"hearing": "open"}, {"hearing": "open notepad"}, {"heard": "open notepad"}):
        control._event(event)
    assert ui.lines == [("grey", "open"), ("grey", "open notepad"), ("white", "open notepad")]


def test_a_window_without_grey_words_shows_them_plainly():
    ui = Shown(live=False)
    _control(ui)._event({"hearing": "open"})
    assert ui.lines == [("white", "open")]


def test_the_bar_window_draws_live_words_grey_with_dots():
    app = (ROOT / "kairu" / "bar" / "app.py").read_text(encoding="utf-8")
    assert "fg=QUIET if live else TEXT" in app and "{' …' if live else ''}" in app
    assert 'self._post("_show_heard", text, True)' in app
