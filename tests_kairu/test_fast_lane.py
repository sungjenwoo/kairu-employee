"""The fast lane (voice.fast_orders) and your-voice-only (voice.only_my_voice), your GO of 15 Nov 2026: "it must work fast,
like Claude's mic" and the last item of the Tenmin voice list. Pretend Vosk recognizers and a pretend Whisper, with the real
speech gate on made-up sound: nothing here opens a microphone, a model or the network.
"""

import io
import json

import numpy
import pytest

from kairu import config as kairu_config
from kairu import executors
from kairu.bar import voice as bar_voice
from kairu.config import ROOT
from kairu.voice import fastlane, listen, models, myvoice
from kairu.voice import whisper as kw

RATE, CHUNK = 16000, 3200
MINE = [1.0] * 64 + [0.0] * 64
SOMEONE = [0.0] * 64 + [1.0] * 64


class PretendVosk:
    """A pretend KaldiRecognizer: one more of `words` per `per_word` seconds fed; a voice print of `voice` if given."""

    def __init__(self, words, per_word=0.3, voice=None):
        self.words = [(word, 1.0) if isinstance(word, str) else word for word in words]
        self.per_word, self.voice = per_word, voice
        self.fed, self.taken = 0.0, 0

    def AcceptWaveform(self, sound):
        self.fed += len(sound) / (2 * RATE)
        return False

    def _now(self):
        return self.words[:min(len(self.words), int(self.fed / self.per_word))]

    def PartialResult(self):
        return json.dumps({"partial": " ".join(word for word, _ in self._now()[self.taken:])})

    def FinalResult(self):
        new = self._now()[self.taken:]
        self.taken += len(new)
        result = {"text": " ".join(word for word, _ in new),
                  "result": [{"word": word, "conf": conf, "start": 0, "end": 0} for word, conf in new]}
        if self.voice is not None:
            result.update(spk=self.voice, spk_frames=int(self.fed * 100))
        return json.dumps(result)

    def Result(self):
        return self.FinalResult()

    def Reset(self):
        self.fed, self.taken = 0.0, 0


class Whisper:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def __call__(self, sound):
        self.calls += 1
        return kw.Heard(self.text, True)


def speech(seconds):
    return numpy.random.default_rng(5).normal(0, 3000, int(RATE * seconds)).clip(-32000, 32000).astype(numpy.int16).tobytes()


def silence(seconds):
    return bytes(int(RATE * seconds) * 2)


def say(hearing, seconds=1.5):
    audio, events = silence(1.0) + speech(seconds) + silence(1.5), []
    for start in range(0, len(audio), CHUNK):
        events += hearing.feed(audio[start:start + CHUNK])
    return events


def hearing_with(said, quick=None, whisper=None, voice=None, mine=None, live_every=0.2):
    words = said.split()
    hearing = kw.WhisperHearing(Whisper(whisper or said), background=False, live_every=live_every)
    hearing.attach_fast(fastlane.FastLane(PretendVosk(words, voice=voice), PretendVosk(quick or words), mine))
    return hearing


def orders(events):
    return [event["order"] for event in events if "order" in event]


def before_the_end(events, order):
    return events.index({"order": order, "breath": 1}) < events.index({"talking": False})


# --- quick orders, from the fast lane ------------------------------------------------------------------------------------

def test_open_edge_starts_0_2_s_after_you_stop_without_waiting_for_whisper():
    hearing = hearing_with("cairo open edge", whisper="Kairu, open Edge.")
    events = say(hearing)
    assert orders(events) == ["open edge"] and before_the_end(events, "open edge")  # once, before the pause is over
    assert hearing.live_runs == 0 and hearing.hear.calls == 1  # Whisper only for the whole sentence, after


def test_the_live_words_come_from_vosk_word_by_word():
    events = say(hearing_with("cairo open microsoft edge", whisper="Kairu, open Microsoft Edge."), seconds=2.0)
    shown = [event["hearing"] for event in events if "hearing" in event]
    assert shown[:3] == ["open", "open microsoft", "open microsoft edge"]


@pytest.mark.parametrize("quick", [["cairo", "open", "[unk]", "edge"],  # something else was said too
                                   ["cairo", "open", ("edge", 0.6)],  # Vosk not sure of a word
                                   ["open", "edge"]])  # no "Kairu", no session
def test_no_quick_order_unless_every_word_is_sure_and_it_began_with_kairu(quick):
    events = say(hearing_with("cairo open edge", quick=quick, whisper="Kairu, open Edge."))
    sent = orders(events)
    assert sent == ["open edge"] and not before_the_end(events, "open edge")  # it waited for Whisper's whole sentence


def test_other_orders_wait_for_whisper():
    events = say(hearing_with("cairo close notepad", quick=["cairo", "[unk]", "notepad"], whisper="Kairu, close Notepad."))
    assert orders(events) == ["close notepad"] and not before_the_end(events, "close notepad")


@pytest.mark.parametrize("words, order", [("cairo open edge", "open edge"), ("hey cairo open google chrome", "open google chrome"),
                                          ("cairo set the volume to thirty", "set the volume to 30"), ("cairo mute", "mute")])
def test_quick_order_reads_the_grammar_words(words, order):
    found = [{"word": word, "conf": 1.0} for word in words.split()]
    assert fastlane.quick_order(found, session=False) == order


def test_quick_order_refuses_what_is_not_quick():
    def found(words):
        return [{"word": word, "conf": 1.0} for word in words.split()]
    assert fastlane.quick_order(found("cairo set the volume to two hundred"), False) is None  # asked about, never guessed
    assert fastlane.quick_order(found("open edge"), True) == "open edge"  # in a session, no "Kairu" needed
    assert fastlane.quick_order([], True) is None


def test_the_grammar_is_only_quick_words_and_unk():
    assert fastlane.QUICK_GRAMMAR[-1] == "[unk]" and "delete" not in fastlane.QUICK_GRAMMAR and "close" not in fastlane.QUICK_GRAMMAR


# --- only your voice -----------------------------------------------------------------------------------------------------

def test_your_voice_opens_edge_at_once():
    events = say(hearing_with("cairo open edge", whisper="Kairu, open Edge.", voice=MINE, mine=MINE))
    assert orders(events) == ["open edge"] and before_the_end(events, "open edge")


def test_someone_elses_voice_is_never_an_order():
    events = say(hearing_with("cairo open edge", whisper="Kairu, open Edge.", voice=SOMEONE, mine=MINE))
    assert orders(events) == [] and {"not_you": "not yours"} in events
    assert not any("wake" in event for event in events)


def test_kairu_stop_works_from_anyone():
    hearing = hearing_with("cairo stop", whisper="Kairu, stop.", voice=SOMEONE, mine=MINE)
    events = say(hearing)
    assert {"stop": True} in events and hearing.stopped


def test_too_short_to_tell_is_not_yours():
    lane = fastlane.FastLane(PretendVosk([]), PretendVosk([]), MINE)
    lane._prints = [(MINE, 10)]  # a tenth of a second of voice print: too little to tell
    assert lane.voice() == "too short"
    assert fastlane.FastLane(None, None, None).voice() == "unchecked"


def test_a_short_order_is_compared_not_called_too_short():
    """Laptop test, 16 Nov 2026: "Kairu, open Notepad" often had fewer than 60 voice-print frames, so it was never compared."""
    lane = fastlane.FastLane(PretendVosk([]), PretendVosk([]), MINE)
    lane._prints = [(MINE, fastlane.LEAST_FRAMES)]
    assert lane.voice() == "yours"
    lane._prints = [(MINE, fastlane.LEAST_FRAMES - 1)]
    assert lane.voice() == "too short"
    lane._prints = [(SOMEONE, 50)]
    assert lane.voice() == "not yours"  # a short order in someone else's voice is still not yours


def test_a_short_order_has_its_own_line_and_a_long_one_keeps_the_old_one():
    import math
    unit = [value / math.sqrt(sum(v * v for v in MINE)) for value in MINE]
    other = [value / math.sqrt(sum(v * v for v in SOMEONE)) for value in SOMEONE]
    # a voice print at cosine 0.46 to yours: between the short line (0.42) and the long one (0.50)
    side = [o - sum(a * b for a, b in zip(other, unit)) * u for o, u in zip(other, unit)]
    side = [value / math.sqrt(sum(v * v for v in side)) for value in side]
    halfway = [0.46 * u + math.sqrt(1 - 0.46 ** 2) * w for u, w in zip(unit, side)]
    assert fastlane.cosine(halfway, MINE) == pytest.approx(0.46, abs=1e-6)
    lane = fastlane.FastLane(PretendVosk([]), PretendVosk([]), MINE)
    lane._prints = [(halfway, fastlane.SHORT_FRAMES - 1)]
    assert lane.voice() == "yours"
    lane._prints = [(halfway, fastlane.SHORT_FRAMES)]
    assert lane.voice() == "not yours"
    assert fastlane.LEAST_FRAMES < fastlane.SHORT_FRAMES and fastlane.MATCH_SHORT < fastlane.MATCH


def test_enroll_asks_for_short_orders_too_and_each_sentence_counts_the_same():
    assert {"Kairu, open Notepad.", "Kairu, volume fifty.", "Kairu, what's open?"} <= myvoice.SHORT_SENTENCES
    assert myvoice.SHORT_SENTENCES < set(myvoice.SENTENCES) and myvoice.SHORTEST_SECONDS < myvoice.LEAST_SECONDS
    long_one, short_one = [1.0] + [0.0] * (myvoice.SIZE - 1), [0.0, 2.0] + [0.0] * (myvoice.SIZE - 2)
    blended = myvoice.blend([(long_one, 500), (short_one, 40)])
    assert blended[0] == pytest.approx(blended[1])  # each sentence the same weight: not 500:40, not by loudness


def test_close_is_yours_far_is_not():
    near = [value + 0.1 for value in MINE]
    assert fastlane.cosine(near, MINE) > fastlane.MATCH > fastlane.cosine(SOMEONE, MINE)


# --- the voice print -----------------------------------------------------------------------------------------------------

def test_the_voice_print_is_numbers_only_and_can_be_forgotten(tmp_path):
    assert myvoice.load(tmp_path) is None
    place = myvoice.save(tmp_path, MINE, 5)
    kept = json.loads(place.read_text(encoding="utf-8"))
    assert set(kept) == {"vector", "sentences", "model", "made"} and myvoice.load(tmp_path) == MINE
    place.write_text(json.dumps({"vector": [1, 2]}), encoding="utf-8")
    assert myvoice.load(tmp_path) is None  # not a voice print: as if there were none
    assert myvoice.forget(tmp_path) and not place.exists() and not myvoice.forget(tmp_path)


class PretendMic:
    def __init__(self, sentences):
        audio = b"".join(silence(1.0) + speech(2.0) + silence(1.0) for _ in range(sentences))
        self.chunks = [audio[start:start + CHUNK] for start in range(0, len(audio), CHUNK)]
        self.closed = False

    def read(self):
        return self.chunks.pop(0) if self.chunks else silence(0.1)

    def close(self):
        self.closed = True


def test_enroll_keeps_the_average_of_your_sentences_and_no_sound(tmp_path):
    cfg = kairu_config.Config(voice_enabled=True, research_enabled=False, policy_path=tmp_path / "p", data_dir=tmp_path)
    mic, lines, ticks = PretendMic(len(myvoice.SENTENCES)), [], iter(range(10**6))
    code = myvoice.enroll(cfg, say=lines.append, clock=lambda: next(ticks) * 0.01,
                          opened=(mic, PretendVosk(["a"] * 20, voice=MINE), PretendVosk(["a"])))
    assert code == 0 and mic.closed and myvoice.load(tmp_path) == pytest.approx(MINE)
    assert any("1.00" in line for line in lines)
    assert [path.name for path in (tmp_path / "voice").iterdir()] == ["my-voice.json"]  # nothing else written


# --- setup, settings and the listener ------------------------------------------------------------------------------------

def test_the_speaker_model_comes_only_from_alphacephei_and_is_pinned(tmp_path):
    assert models.SPEAKER.url == "https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip" and len(models.SPEAKER.sha256) == 64
    with pytest.raises(models.NotSetUp):
        models.speaker_ready(tmp_path)

    class Wrong(io.BytesIO):
        def geturl(self):
            return models.SPEAKER.url

    with pytest.raises(models.SetupError, match="SHA-256"):
        models.setup_speaker(tmp_path, say=lambda line: None, opener=lambda url, timeout: Wrong(b"not the model"))
    assert not any((tmp_path / "voice").glob("*.zip.part"))


def _config(tmp_path, voice):
    path = tmp_path / "config.yaml"
    path.write_text(f"voice:\n  enabled: true\n{voice}guardian:\n  data_dir: data\n", encoding="utf-8")
    return kairu_config.load(path)


def test_both_are_off_unless_you_set_them(tmp_path):
    plain = _config(tmp_path, "")
    assert (plain.voice_fast, plain.voice_only_mine) == (False, False)
    on = _config(tmp_path, "  fast_orders: true\n  only_my_voice: true\n")
    assert (on.voice_fast, on.voice_only_mine) == (True, True)
    with pytest.raises(kairu_config.ConfigError, match="only_my_voice"):
        _config(tmp_path, "  only_my_voice: maybe\n")


def test_guardian_supplies_both_never_a_request():
    listen_action = executors.EXECUTORS["voice.listen"]
    for name in ("voice_fast", "voice_only_mine"):
        assert name in listen_action.supplied and name not in listen_action.arguments
    program = (ROOT / "kairu" / "guardian_program.py").read_text(encoding="utf-8")
    assert '"voice_fast": cfg.voice_fast' in program and '"voice_only_mine": cfg.voice_only_mine' in program


def test_your_voice_only_fails_closed(tmp_path):
    lane, problem, hard = listen._fast_lane("whisper-small.en", str(tmp_path), "small-en-us", False, True)
    assert lane is None and hard and "kairu voice enroll" in problem  # no voice print: the mic stays off
    myvoice.save(tmp_path, MINE, 5)
    lane, problem, hard = listen._fast_lane("whisper-small.en", str(tmp_path), "small-en-us", False, True)
    assert lane is None and hard and "not set up" in problem  # no models: the mic stays off
    lane, problem, hard = listen._fast_lane("vosk", str(tmp_path), "small-en-us", False, True)
    assert lane is None and hard


def test_fast_orders_without_the_vosk_model_only_say_so(tmp_path):
    lane, problem, hard = listen._fast_lane("whisper-small.en", str(tmp_path), "small-en-us", True, False)
    assert lane is None and not hard and "Fast orders are off" in problem


def test_the_bar_says_why_it_did_nothing():
    lines = []

    class Ui:
        def heard(self, text):
            pass

        def say(self, text):
            lines.append(text)

    control = object.__new__(bar_voice.VoiceControl)
    control.ui = Ui()
    control._event({"not_you": "not yours"})
    control._event({"not_you": "too short"})
    assert lines == [bar_voice.NOT_YOU["not yours"], bar_voice.NOT_YOU["too short"]]


def test_the_fast_lane_writes_nothing_and_the_voice_print_is_its_only_file():
    from tests_kairu.test_voice_rules import WRITES
    lane_code = (ROOT / "kairu" / "voice" / "fastlane.py").read_text(encoding="utf-8")
    assert not WRITES.search(lane_code)
    print_code = (ROOT / "kairu" / "voice" / "myvoice.py").read_text(encoding="utf-8")
    assert WRITES.findall(print_code) == [".write_text("] and "part.write_text(json.dumps({\"vector\"" in print_code
