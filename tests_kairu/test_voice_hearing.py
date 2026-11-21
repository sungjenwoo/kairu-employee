"""Hearing with the real small model, from recorded sounds (tests_kairu/voice/), so no microphone is needed.

The sounds are Windows' own voices (tests_kairu/voice/make.ps1), not yours: VOICE.md has what that does and does not show.
"""

import array

import pytest

from kairu.voice.hearing import Hearing
from tests_kairu.voice_helpers import CHUNK, hear, silence, sound, vosk_model  # noqa: F401 (a fixture)


@pytest.fixture
def hearing(vosk_model):
    return Hearing(vosk_model)


def kinds(events, *names):
    return [event for event in events if any(name in event for name in names)]


def test_kairu_wakes_it(hearing):
    events = hear(hearing, "kairu")
    assert kinds(events, "wake") == [{"wake": True, "alone": True}] and hearing.session
    assert not kinds(events, "order", "stop")


def test_the_hotkey_and_the_mic_button_start_a_session_without_kairu(hearing):
    assert hearing.start_session() == [{"wake": True, "alone": True}] and hearing.session
    assert kinds(hear(hearing, "open_notepad"), "order") == [{"order": "open notepad", "breath": 1}]


def test_speech_without_kairu_does_nothing_and_is_never_shown(hearing):
    events = hear(hearing, "no_kairu", "open_notepad", "set_volume_twenty")
    assert kinds(events, "wake", "order", "heard", "unclear", "stop", "thanks") == [] and not hearing.session


def test_two_orders_in_one_breath_are_one_order_for_the_task_core_in_the_order_said(hearing):
    events = hear(hearing, "kairu_open_chrome_and_volume")
    assert kinds(events, "wake", "order") == [{"wake": True, "alone": False}, {"order": "open chrome and set volume to 30", "breath": 1}]


def test_each_order_is_handed_on_as_soon_as_it_is_said_while_you_keep_talking(hearing):
    """Two orders with a pause between: the first is out before the second has been said."""
    audio = sound("kairu_two_breaths") + silence(2)
    orders, said_at = [], []
    for start in range(0, len(audio), CHUNK):
        for event in hearing.feed(audio[start:start + CHUNK]):
            if "order" in event:
                orders.append(event["order"])
                said_at.append(start / 32000)
    assert orders == ["open notepad", "set volume to 20"]
    last_loud = max(i for i, sample in enumerate(array.array("h", sound("kairu_two_breaths"))) if abs(sample) > 500) / 16000
    assert said_at[0] < last_loud - 1.0  # the first order was out while the second was still being said


def test_the_words_appear_live_as_you_say_them(hearing):
    hearing.start_session()
    live = [event["heard"] for event in hear(hearing, "kairu_open_chrome_and_volume") if "heard" in event]
    assert len(live) >= 3 and live[0] == "open" and live[-1] == "open chrome and set volume to 30"
    assert [len(text.split()) for text in live] == sorted(len(text.split()) for text in live)  # word by word


def test_filler_words_are_ignored(hearing):
    assert kinds(hear(hearing, "kairu_filler"), "order") == [{"order": "open notepad", "breath": 1}]


def test_an_unclear_order_gets_one_short_question_and_nothing_is_guessed(hearing):
    events = hear(hearing, "kairu_open")
    assert kinds(events, "unclear", "order") == [{"unclear": "Open what?"}]


def test_thank_you_ends_the_session_and_kairu_goes_quiet_until_woken(hearing):
    events = hear(hearing, "kairu", "thank_you", "open_notepad")
    assert kinds(events, "thanks") == [{"thanks": True}] and not hearing.session
    assert kinds(events, "order") == []  # after "thank you", an order without "Kairu" does nothing


def test_kairu_stop_is_heard_and_nothing_is_heard_after_it(hearing):
    events = hear(hearing, "kairu_stop", "kairu_open_chrome_and_volume")
    assert kinds(events, "stop") == [{"stop": True}] and kinds(events, "order", "wake") == [] and hearing.stopped


def test_how_soon_kairu_stop_is_heard(hearing):
    audio = sound("kairu_stop")
    ended = max(i for i, sample in enumerate(array.array("h", audio)) if abs(sample) > 300) / 16000
    audio += silence(2)
    for start in range(0, len(audio), CHUNK):
        if kinds(hearing.feed(audio[start:start + CHUNK]), "stop"):
            took = (start + CHUNK) / 32000 - ended
            break
    print(f"\n  'Kairu, stop' heard {took:.2f} s after the word ended (sound time)")
    assert took < 1.5


def test_a_spoken_yes_or_pin_is_never_an_order(hearing):
    hearing.start_session()
    events = hear(hearing, "yes", "pin")
    assert kinds(events, "ignored") == [{"ignored": "yes or digits"}] * 2 and kinds(events, "order") == []


def test_kairus_own_voice_is_never_heard_while_it_speaks(hearing):
    """The listener feeds silence while Kairu speaks: its own words, "Kairu, open Notepad" among them, never reach the model."""
    hearing.start_session()
    spoken = sound("kairus_own_voice")
    events = hear(hearing, bytes(len(spoken)))  # what the listener gives the model while paused
    assert kinds(events, "order", "wake", "heard", "unclear") == []


def test_unpaused_kairus_own_words_would_be_orders_which_is_why_the_mic_pauses(hearing):
    hearing.start_session()
    assert kinds(hear(hearing, "kairus_own_voice"), "order")


def test_someone_elses_voice_is_heard_like_yours(hearing):
    """There is no your-voice-only check yet: what another person says is an order like yours, decided by Guardian."""
    assert kinds(hear(hearing, "someone_else"), "order") == [{"order": "open notepad", "breath": 1}]


def test_the_session_ends_quietly_after_30_seconds_without_a_word(hearing, monkeypatch):
    monkeypatch.setattr("kairu.voice.hearing.SESSION_SECONDS", 3.0)
    hearing.start_session()
    assert kinds(hear(hearing, silence(4), pause=0), "quiet") == [{"quiet": True}] and not hearing.session
