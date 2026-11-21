"""Catching "Kairu" better (15 Nov 2026: the owner said Kairu often did not catch it), and `kairu voice check`.

Whisper is a stand-in (tests_kairu/test_voice_whisper.py Pretend); the sounds are the recorded ones; no microphone."""

import re
import types

import pytest

from kairu.config import ROOT
from kairu.voice import check
from kairu.voice import whisper as kw
from tests_kairu.test_voice_rules import WRITES
from tests_kairu.test_voice_whisper import hearing_of, kinds
from tests_kairu.voice_helpers import CHUNK, hear, silence, sound


@pytest.mark.parametrize("text, woke, rest", [
    ("Hey Kairu, open Chrome.", True, ["open", "chrome"]),
    ("Okay, Kairu.", True, []),
    ("Hi Kyra, what time is it?", True, ["what", "time", "is", "it"]),
    ("Kaira, close Notepad.", True, ["close", "notepad"]),
    ("Kairi.", True, []),
    ("OK Kai Ru close notepad", True, ["close", "notepad"]),
    ("Hey there, how are you?", False, ["hey", "there", "how", "are", "you"]),
    ("Hello.", False, ["hello"]),
    ("Okay.", False, ["okay"]),
])
def test_a_greeting_before_kairu_and_more_of_whispers_spellings_wake_it(text, woke, rest):
    assert kw.split_wake(text) == (woke, rest)


def test_hey_kairu_and_an_order():
    events = hear(hearing_of("Hey Kairu, open Notepad."), "kairu_open")
    assert kinds(events, "wake", "order") == [{"wake": True, "alone": False}, {"order": "open notepad", "breath": 1}]


def test_kairu_alone_heard_unsure_opens_a_short_window_and_says_go_ahead():
    hearing = hearing_of("Kairu.", sure=False)
    events = hear(hearing, "kairu_filler", pause=0.8)
    assert kinds(events, "wake") == [{"wake": True, "alone": True}] and hearing.session
    assert kinds(hear(hearing, silence(kw.REPLY_SECONDS + 1), pause=0), "quiet") == [{"quiet": True}] and not hearing.session


def test_after_an_unsure_kairu_what_you_say_next_is_heard_as_an_order():
    hearing = hearing_of("Kairu.", "Open Notepad.", sure=False)
    hear(hearing, "kairu_filler", pause=0.8)
    events = hear(hearing, "open_notepad")
    assert kinds(events, "order", "unclear") == [{"unclear": "Sorry, I didn't catch that. Could you say it again?"}]
    sure = hearing_of("Kairu.")
    hear(sure, "kairu_filler", pause=0.8)
    sure.hear.said.append("Open Notepad.")
    assert kinds(hear(sure, "open_notepad"), "order") == [{"order": "open notepad", "breath": 2}]


def test_an_order_heard_unsure_after_kairu_still_never_wakes_it():
    hearing = hearing_of("Hey Kairu, open Notepad.", sure=False)
    assert kinds(hear(hearing, "kairu_filler"), "wake", "heard", "order", "unclear") == [] and not hearing.session


# --- kairu voice check ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("heard, says", [
    (kw.Heard("Kairu.", True), "WAKES Kairu"),
    (kw.Heard("Hey Kairu, open Chrome.", True), "WAKES Kairu, order: open chrome"),
    (kw.Heard("Kairu.", False, -1.4), "WAKES Kairu (not sure"),
    (kw.Heard("Kairu, open Chrome.", False), "would NOT wake Kairu: Whisper was not sure"),
    (kw.Heard("Cyrus.", True), "would NOT wake Kairu: the first word is not"),
    (kw.Heard("", False, 0.0, 1), "no words: Whisper dropped it as noise"),
])
def test_the_check_says_why_it_would_or_would_not_wake(heard, says):
    assert check.verdict(heard).startswith(says)


def test_the_check_listens_says_what_it_heard_and_closes_the_mic(monkeypatch, tmp_path):
    audio = sound("kairu_filler") + silence(1.5) + sound("open_notepad") + silence(1.5)
    chunks = [audio[start:start + CHUNK] for start in range(0, len(audio), CHUNK)]

    class Mic:
        closed = False

        def read(self):
            return chunks.pop(0) if chunks else bytes(CHUNK)

        def close(self):
            Mic.closed = True

    ticks = iter(range(10_000))
    monkeypatch.setattr(check.microphone, "open_mic", Mic)
    monkeypatch.setattr(check.models, "hearing_ready", lambda data_dir, engine, model: tmp_path)
    said = iter(["Kairu.", "Open Notepad."])
    monkeypatch.setattr(check.kw, "transcriber", lambda place: lambda utterance: kw.Heard(next(said), True, -0.3))
    lines = []
    cfg = types.SimpleNamespace(voice_engine="whisper-base.en", voice_model="", data_dir=tmp_path)
    assert check.run(cfg, 20, lines.append, clock=lambda: next(ticks) * 0.05) == 0
    heard = [line for line in lines if line.startswith("- ")]
    assert len(heard) == 2 and "'Kairu.'" in heard[0] and "WAKES Kairu" in heard[0] and "dB" in heard[0]
    assert "would NOT wake" in heard[1] and lines[-1].startswith("Room noise:") and Mic.closed


def test_the_check_is_only_for_whisper_and_says_when_voice_is_not_ready(tmp_path):
    lines = []
    assert check.run(types.SimpleNamespace(voice_engine="small-en-us", voice_model="", data_dir=tmp_path), 5, lines.append) == 1
    assert "for Whisper" in lines[0]


def test_the_check_writes_nothing_sends_nothing_and_runs_nothing():
    code = (ROOT / "kairu" / "voice" / "check.py").read_text(encoding="utf-8")
    assert not WRITES.search(code)
    for module in ("urllib", "http", "socket", "requests", "kairu.client", "kairu.channel", "subprocess"):
        assert not re.search(rf"^\s*(?:from|import)\s+{re.escape(module)}\b", code, re.MULTILINE), module
    assert check.LONGEST_SECONDS == 60
