"""Hearing with Whisper (voice.engine: whisper-base.en, the default, or whisper-tiny.en; kairu/voice/whisper.py).

Most tests run everywhere with a pretend Whisper (what it "hears" is written in the test) and the real speech gate on the
recorded sounds in tests_kairu/voice/, so nothing is downloaded. The tests marked "real" use Whisper base.en and tiny.en
themselves where `kairu voice setup` (or the hearing test) has put them in this folder's data/voice/, and are skipped
elsewhere (as in CI).
"""

import subprocess
import sys
import time

import numpy
import pytest

from kairu import config, executors
from kairu.config import ROOT
from kairu.voice import models, words as w
from kairu.voice import whisper as kw
from tests_kairu.voice_helpers import CHUNK, hear, silence, sound

RATE = 16000


class Pretend:
    """A pretend Whisper: hears the next of `said` for each utterance the speech gate lets through."""

    def __init__(self, *said, sure=True, slow=0.0):
        self.said, self.sure, self.slow, self.heard = list(said), sure, slow, 0

    def __call__(self, utterance: bytes) -> kw.Heard:
        assert utterance and len(utterance) % 2 == 0
        self.heard += 1
        time.sleep(self.slow)
        return kw.Heard(self.said.pop(0) if self.said else "", self.sure)


def hearing_of(*said, **options):
    return kw.WhisperHearing(Pretend(*said, **options), background=False)


def kinds(events, *names):
    return [event for event in events if any(name in event for name in names)]


def noise(seconds: float, level: float, seed: int = 1) -> bytes:
    return numpy.random.default_rng(seed).normal(0, level, int(RATE * seconds)).clip(-32000, 32000).astype(numpy.int16).tobytes()


def clicks(seconds: float) -> bytes:
    """Keyboard-like taps: 10 ms loud, then quiet, four times a second."""
    one = numpy.zeros(RATE // 4, numpy.int16)
    one[:160] = 9000
    return numpy.tile(one, int(seconds * 4)).tobytes()


# --- the speech gate: Whisper runs only when someone speaks ------------------------------------------------------

def test_in_silence_whisper_never_runs():
    """Two minutes of a silent room, a steady fan-like hiss and taps: the gate never hands Whisper anything."""
    pretend = Pretend()
    hearing = kw.WhisperHearing(pretend, background=False)
    hear(hearing, silence(40), noise(40, 150), clicks(40), pause=0)
    assert pretend.heard == 0 and hearing.whisper_runs == 0 and hearing.gate.gated > 1150


def test_a_steady_noise_louder_than_a_quiet_voice_is_learned_as_the_rooms_own():
    """A loud fan (RMS 500): after a short while it is the room's noise, and only a voice over it is heard."""
    pretend = Pretend("Kairu, open Notepad.")
    hearing = kw.WhisperHearing(pretend, background=False)
    fan = noise(30, 500, seed=2)
    hear(hearing, fan, pause=0)
    assert pretend.heard <= 1  # the first moment of the fan, before it is known, at most
    started = pretend.heard
    voice = numpy.frombuffer(sound("kairu_open"), numpy.int16).astype(numpy.int32) * 3
    mixed = (voice + numpy.frombuffer(noise(len(voice) / RATE, 500, seed=3), numpy.int16)).clip(-32000, 32000).astype(numpy.int16)
    hear(hearing, mixed.tobytes() + noise(1.5, 500, seed=4), pause=0)
    assert pretend.heard == started + 1


def test_each_utterance_is_handed_to_whisper_once_whole_after_a_short_pause():
    gate = kw.SpeechGate()
    audio = silence(0.5) + sound("kairu_open_chrome_and_volume") + silence(1.0)
    ends = []
    for start in range(0, len(audio), CHUNK):
        happened, utterance = gate.feed(audio[start:start + CHUNK])
        if happened == "end":
            ends.append((start, utterance))
    assert len(ends) == 1
    spoken = len(sound("kairu_open_chrome_and_volume"))
    assert spoken * 0.8 < len(ends[0][1]) < spoken + 0.6 * RATE * 2  # all of it, and not much of the pause
    assert ends[0][0] / 2 / RATE - 0.5 - spoken / 2 / RATE < kw.END_CHUNKS / 10 + 0.3  # heard about 0.6 s after you stop


def test_two_breaths_are_two_utterances():
    pretend = Pretend("Kairu, open Notepad.", "Set volume to 20.")
    events = hear(kw.WhisperHearing(pretend, background=False), "kairu_two_breaths")
    assert kinds(events, "order") == [{"order": "open notepad", "breath": 1}, {"order": "set volume to 20", "breath": 2}]


def test_whisper_hears_in_its_own_thread_so_the_microphone_is_never_kept_waiting():
    pretend = Pretend("Kairu, open Notepad.", slow=0.8)
    hearing = kw.WhisperHearing(pretend)
    audio = sound("kairu_filler") + silence(2.5)
    events, slowest = [], 0.0
    for start in range(0, len(audio), CHUNK):
        began = time.perf_counter()
        events += hearing.feed(audio[start:start + CHUNK])
        slowest = max(slowest, time.perf_counter() - began)
        time.sleep(0.1)  # as the microphone gives it: in real time
    hearing.close()
    assert slowest < 0.1 and kinds(events, "order") == [{"order": "open notepad", "breath": 1}]


# --- what Whisper heard, made into events as with Vosk ---------------------------------------------------------------

def test_kairu_alone_wakes_it_with_no_order():
    events = hear(hearing_of("Kairu."), "kairu")
    assert kinds(events, "wake", "order", "unclear") == [{"wake": True, "alone": True}]


def test_kairu_and_an_order():
    events = hear(hearing_of("Kairu, open Chrome and set volume to 30."), "kairu_open_chrome_and_volume")
    assert kinds(events, "wake", "heard", "order") == [{"wake": True, "alone": False}, {"heard": "open chrome and set volume to 30"},
                                                       {"order": "open chrome and set volume to 30", "breath": 1}]


def test_speech_without_kairu_outside_a_session_is_dropped_and_never_shown():
    hearing = hearing_of("Open Notepad.", "The weather was lovely yesterday.")
    events = hear(hearing, "open_notepad", "no_kairu")
    assert kinds(events, "wake", "heard", "order", "unclear", "stop", "thanks", "ignored") == [] and not hearing.session


def test_in_a_session_every_utterance_is_an_order_until_thank_you():
    hearing = hearing_of("Open Notepad.", "Thank you.", "Open Notepad.")
    hearing.start_session()
    events = hear(hearing, "open_notepad", "thank_you", "open_notepad")
    assert kinds(events, "order", "thanks") == [{"order": "open notepad", "breath": 1}, {"thanks": True}] and not hearing.session


def test_kairu_stop_is_the_stop_and_nothing_is_heard_after_it():
    hearing = hearing_of("Kairu, stop.", "Kairu, open Notepad.")
    events = hear(hearing, "kairu_stop", "kairu_filler")
    assert kinds(events, "stop", "order") == [{"stop": True}] and hearing.stopped and hearing.heard_at


def test_stop_alone_is_the_stop_only_in_a_session():
    outside = hearing_of("Stop.")
    assert kinds(hear(outside, "kairu_open"), "stop") == [] and not outside.stopped
    inside = hearing_of("Stop.")
    inside.start_session()
    assert kinds(hear(inside, "kairu_open"), "stop") == [{"stop": True}]


def test_a_spoken_yes_or_pin_is_never_an_order_and_a_pin_is_never_shown():
    hearing = hearing_of("Yes.", "4 8 2 9 1 6")
    hearing.start_session()
    events = hear(hearing, "yes", "pin")
    assert kinds(events, "order", "heard") == [] and kinds(events, "ignored") == [{"ignored": "yes or digits"}] * 2


def test_what_whisper_was_not_sure_of_gets_one_short_question():
    hearing = hearing_of("Open Notepad.", sure=False)
    hearing.start_session()
    events = hear(hearing, "kairu_filler")
    assert kinds(events, "order", "unclear") == [{"unclear": w.NOT_CAUGHT}]


def test_a_kairu_whisper_was_not_sure_of_never_wakes_it():
    """Room sound Whisper half-heard as "Kairu ..." must not open a session, where every utterance is an order."""
    hearing = hearing_of("Kairu, open Notepad.", sure=False)
    events = hear(hearing, "kairu_filler")
    assert kinds(events, "wake", "heard", "order", "unclear") == [] and not hearing.session


@pytest.mark.parametrize("heard,order", [
    ("Kairu, set the value to 30.", "set the volume to 30"),  # the owner's own misses, 10 Nov 2026
    ("Kairu, said the volume to 30.", "set the volume to 30"),
    ("Kairu, wants open?", "what's open"),
    ("Kairu, starts the weather today.", "search the weather today"),
    ("Kairu, set a volume to 80.", "set the volume to 80"),
    ("Kairu, set the volume to 30%.", "set the volume to 30"),
    ("Kairu, set the brightness to fifty.", "set the brightness to 50"),
    ("Kai Ru, close Notepad.", "close notepad"),
])
def test_whispers_near_misses_in_kairus_order_words_are_put_right(heard, order):
    assert kinds(hear(hearing_of(heard), "kairu_open"), "order") == [{"order": order, "breath": 1}]


def test_a_session_ends_after_30_seconds_without_a_word():
    hearing = hearing_of()
    hearing.start_session()
    assert kinds(hear(hearing, silence(31), pause=0), "quiet") == [{"quiet": True}] and not hearing.session


# --- numbers: never a guess out of range -----------------------------------------------------------------------------

@pytest.mark.parametrize("text,question", [
    ("set the volume to 230", "Did you mean 30?"), ("volume 230", "Did you mean 30?"), ("set volume to 2 30", "Did you mean 30?"),
    ("set the brightness to 450", "Did you mean 50?"), ("volume 230 percent", "Did you mean 30?"),
    ("set the volume to 999", "Volume goes from 0 to 100. What level?"), ("brightness 1000", "Brightness goes from 0 to 100. What level?"),
])
def test_a_level_out_of_range_is_asked_about_never_guessed(text, question):
    assert w.unclear(text, 1.0) == question


@pytest.mark.parametrize("text", ["set the volume to 30", "volume 100", "brightness to 0", "open chrome", "volume to 50 percent"])
def test_a_level_in_range_is_not_asked_about(text):
    assert w.unclear(text, 1.0) == "" and w.level_question(text) is None


def test_volume_230_asks_did_you_mean_30_and_does_nothing_until_you_say_it_again():
    hearing = hearing_of("Kairu, set the volume to 230.", "Yes.", "Volume 30.")
    events = hear(hearing, "kairu_open", "yes", "kairu_open")
    assert kinds(events, "order", "unclear") == [
        {"unclear": "Did you mean 30?"},
        {"unclear": w.say_it_again("volume 30")},  # a spoken yes is still never an order
        {"order": "volume 30", "breath": 3},
    ]


def test_no_after_did_you_mean_does_nothing():
    events = hear(hearing_of("Kairu, set the volume to 230.", "No."), "kairu_open", "yes")
    assert kinds(events, "order", "unclear", "ignored") == [{"unclear": "Did you mean 30?"}, {"ignored": "yes or digits"}]


# --- "search" with a setting word after it: never a search -----------------------------------------------------------

@pytest.mark.parametrize("text,question,instead", [
    ("search the volume to 30", "Did you mean set the volume to 30?", "set the volume to 30"),  # the owner's tiny.en miss
    ("search volume to 30", "Did you mean set the volume to 30?", "set the volume to 30"),
    ("search for the sound at 40", "Did you mean set the volume to 40?", "set the volume to 40"),
    ("search the brightness to 50", "Did you mean set the brightness to 50?", "set the brightness to 50"),
    ("search the volume to 230", "Did you mean set the volume to 30?", "set the volume to 30"),  # and never a guess
    ("search the brightness to 999", "Brightness goes from 0 to 100. What level?", "brightness 50"),
    ("search the volume up", "Did you mean turn the volume up?", "turn the volume up"),
    ("search the volume", "Did you mean set the volume?", "set the volume to 50"),
    ("search wifi off", "Did you mean turn Wi-Fi off?", "turn wifi off"),
    ("search for the wifi", "Did you mean turn Wi-Fi on or off?", "turn wifi on"),
    ("search for volume settings", "Did you mean set the volume?", "set the volume to 50"),
])
def test_a_heard_search_with_a_setting_word_after_it_is_asked_about_never_searched(text, question, instead):
    assert w.unclear(text, 1.0) == question and w.asked_instead(text) == (question, instead)


@pytest.mark.parametrize("text", ["search the weather", "search for chrome tips", "search google for the news", "set the volume to 30",
                                  "turn wifi off", "brightness 40"])
def test_a_search_without_a_setting_word_and_the_settings_themselves_are_not_asked_about(text):
    assert w.setting_question(text) is None and w.unclear(text, 1.0) == ""


@pytest.mark.parametrize("heard", ["Kairu, search the volume to 30.", "Kairu, starts the volume to 30.", "Kairu, search the volume 2 30."])
def test_search_the_volume_asks_and_does_nothing_until_you_say_the_order_again(heard):
    hearing = hearing_of(heard, "Yes.", "Set the volume to 30.")
    events = hear(hearing, "kairu_open", "yes", "kairu_open")
    assert kinds(events, "order", "unclear") == [
        {"unclear": "Did you mean set the volume to 30?"},
        {"unclear": w.say_it_again("set the volume to 30")},  # a spoken yes is still never an order
        {"order": "set the volume to 30", "breath": 3},
    ]


def test_search_wifi_asks_and_a_spoken_yes_asks_for_the_whole_order():
    events = hear(hearing_of("Kairu, search Wi-Fi off.", "Yes."), "kairu_open", "yes")
    assert kinds(events, "order", "unclear") == [{"unclear": "Did you mean turn Wi-Fi off?"},
                                                 {"unclear": 'Please say the whole order again, like "turn wifi off".'}]


def test_vosk_asks_about_search_the_volume_too():
    """The rule is in the words, so it holds for both engines (Vosk's Hearing asks with the same words.unclear)."""
    from kairu.voice import hearing as vosk_hearing
    assert "w.unclear(text, sure)" in (ROOT / "kairu" / "voice" / "hearing.py").read_text(encoding="utf-8")
    assert vosk_hearing.w is w


# --- the hint ----------------------------------------------------------------------------------------------------------

def test_the_hint_is_kairus_order_words_and_never_a_whole_order():
    """A whole example order in Whisper's prompt made it "hear" that order when it was not said (8 Nov 2026)."""
    for word in ("Kairu", "volume", "brightness", "open", "close", "Chrome", "Notepad", "what's open", "search", "weather",
                 "Google", "find", "move", "rename", "delete", "undo", "thank you", "stop", "yes", "no"):
        assert word in kw.VOCABULARY, word
    for hint in (kw.VOCABULARY, kw.PROMPT):
        pieces = [piece.strip(" .") for piece in hint.split(",")]
        assert all(len(piece.split()) <= 2 for piece in pieces), hint  # words and two-word names, never a sentence
        assert not any(character.isdigit() for character in hint)


class Segment:
    def __init__(self, text, logprob, no_speech, compression=0.7):
        self.text, self.avg_logprob, self.no_speech_prob, self.compression_ratio = text, logprob, no_speech, compression


@pytest.mark.parametrize("segments,heard", [
    ([Segment(" Kairu, open Notepad.", -0.13, 0.01)], kw.Heard("Kairu, open Notepad.", True)),  # the recordings: 0.00-0.07
    ([Segment(" Pup, pup, pup, pup, pup.", -0.59, 0.84)], kw.Heard("", False)),  # base.en on keyboard taps (10 Nov 2026)
    ([Segment(" I'm sorry.", -1.88, 0.53)], kw.Heard("", False)),  # base.en on a loud hiss
    ([Segment(" Okay.", -1.88, 0.43)], kw.Heard("", False)),  # tiny.en on it
    ([Segment(" Open Notepad.", -1.4, 0.1)], kw.Heard("Open Notepad.", False)),  # speech it was unsure of: asked again
    ([Segment(" Kairu,", -0.2, 0.02), Segment(" pup pup.", -0.6, 0.9)], kw.Heard("Kairu,", True)),
])
def test_what_whisper_itself_scores_as_not_speech_is_dropped_unheard(segments, heard):
    """Noise Whisper wrote words for is dropped, nothing said back; speech it was unsure of still gets "say it again"."""
    class Model:
        def transcribe(self, *args, **kwargs):
            return iter(segments), None
    whisper = kw.Whisper.__new__(kw.Whisper)
    whisper.hint, whisper.beam, whisper.hotwords, whisper.model = kw.PROMPT, 5, kw.VOCABULARY, Model()
    assert whisper(bytes(3200)) == heard


def test_whisper_is_asked_with_the_hint_and_no_way_to_guess():
    code = (ROOT / "kairu" / "voice" / "whisper.py").read_text(encoding="utf-8")
    call = code[code.index("self.model.transcribe("):code.index("heard = [segment")]
    for setting in ("initial_prompt=self.hint", "hotwords=self.hotwords", "temperature=0.0", "condition_on_previous_text=False",
                    "vad_filter=False", 'language="en"', "max_new_tokens=MOST_TOKENS"):
        assert setting in call, setting


# --- the settings, the model and what the listener loads ---------------------------------------------------------------

def test_whisper_is_the_default_engine_and_vosk_the_fallback(tmp_path):
    """Whisper base.en since the owner's hearing test (10 Nov 2026); tiny.en and Vosk stay choices in config.yaml."""
    assert config.load(tmp_path / "none.yaml").voice_engine == "whisper-base.en" == config.VOICE_ENGINES[0]
    assert config.VOICE_ENGINES == models.ENGINES == ("whisper-base.en", "whisper-tiny.en", "whisper-large-v3-turbo",
                                                      "whisper-distil-large-v3", "whisper-medium.en", "whisper-small.en", "vosk")
    assert models.WHISPER == "base.en" and models.WHISPER_ENGINES == {
        "whisper-base.en": "base.en", "whisper-tiny.en": "tiny.en", "whisper-large-v3-turbo": "large-v3-turbo",
        "whisper-distil-large-v3": "distil-large-v3", "whisper-medium.en": "medium.en", "whisper-small.en": "small.en"}
    # the bigger ones (your GO of 15 Nov 2026) are pinned in whisper_pins.json: test_tenmin_next.py
    path = tmp_path / "config.yaml"
    for written, engine in (("whisper", "whisper-base.en"), ("whisper-tiny.en", "whisper-tiny.en"), ("whisper-base.en", "whisper-base.en")):
        path.write_text(f"voice:\n  engine: {written}\n")
        assert config.load(path).voice_engine == engine
    models.WHISPERS["tiny.en"].folder(tmp_path / "data").mkdir(parents=True)
    with pytest.raises(models.NotSetUp, match="tiny.en"):
        models.hearing_ready(tmp_path / "data", "whisper-tiny.en", "small-en-us")
    with pytest.raises(models.NotSetUp, match="base.en"):
        models.hearing_ready(tmp_path / "data", "whisper-base.en", "small-en-us")
    with pytest.raises(models.NotSetUp, match="vosk-model-small-en-us"):
        models.hearing_ready(tmp_path / "data", "vosk", "small-en-us")
    path.write_text("voice:\n  enabled: true\n  engine: vosk\n  model: small-en-in\n")
    assert (config.load(path).voice_engine, config.load(path).voice_model) == ("vosk", "small-en-in")
    path.write_text("voice:\n  engine: google\n")
    with pytest.raises(config.ConfigError, match="voice.engine"):
        config.load(path)


def test_guardian_supplies_the_engine_from_its_own_config_never_a_request():
    listen = executors.EXECUTORS["voice.listen"]
    assert "voice_engine" in listen.supplied and "voice_engine" not in listen.arguments
    assert '"voice_engine": cfg.voice_engine' in (ROOT / "kairu" / "guardian_program.py").read_text(encoding="utf-8")


def test_tiny_en_is_pinned_to_its_source_by_sha256_and_needs_its_mark(tmp_path):
    tiny = models.WHISPERS["tiny.en"]
    assert tiny.repo == "Systran/faster-whisper-tiny.en" and len(tiny.commit) == 40
    assert {name for name, *_ in tiny.files} == {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}
    assert 70 < tiny.mib < 80
    tiny.folder(tmp_path).mkdir(parents=True)
    for name, *_ in tiny.files:
        (tiny.folder(tmp_path) / name).write_bytes(b"x")
    with pytest.raises(models.NotSetUp, match="kairu voice setup"):
        models.whisper_ready(tmp_path, "tiny.en")


def test_base_en_the_default_is_pinned_to_its_source_by_sha256_and_needs_its_mark(tmp_path):
    base = models.WHISPERS[models.WHISPER]
    assert base.key == "base.en" and base.repo == "Systran/faster-whisper-base.en" and len(base.commit) == 40
    assert {name for name, *_ in base.files} == {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}
    assert 140 < base.mib < 145
    base.folder(tmp_path).mkdir(parents=True)
    for name, *_ in base.files:
        (base.folder(tmp_path) / name).write_bytes(b"x")
    with pytest.raises(models.NotSetUp, match="kairu voice setup"):
        models.whisper_ready(tmp_path)  # the default: base.en
    (base.folder(tmp_path) / models.WHISPER_MARK).write_text(__import__("json").dumps(models.whisper_mark(base)))
    assert models.whisper_ready(tmp_path) == models.hearing_ready(tmp_path, "whisper-base.en", "small-en-us") == base.folder(tmp_path)


def test_setup_checks_each_whisper_file_and_deletes_a_wrong_one(tmp_path, monkeypatch):
    import hashlib
    from tests_kairu.test_voice_models import Download
    files = {"config.json": b"{}", "model.bin": b"m" * 50, "tokenizer.json": b"{}", "vocabulary.txt": b"a"}
    fake = models.Whisper("test", "Systran/faster-whisper-test", "c" * 40,
                          tuple((name, hashlib.sha256(data).hexdigest(), len(data)) for name, data in files.items()))
    monkeypatch.setitem(models.WHISPERS, "test", fake)
    asked = []

    def opener(address, timeout):
        asked.append(address)
        return Download(files[address.rsplit("/", 1)[1]], address)
    place = models.setup_whisper(tmp_path, "test", say=lambda text: None, opener=opener)
    assert place == models.whisper_ready(tmp_path, "test") and (place / "model.bin").read_bytes() == b"m" * 50
    assert asked[0] == f"https://huggingface.co/Systran/faster-whisper-test/resolve/{'c' * 40}/config.json"
    bad = models.Whisper("bad", fake.repo, fake.commit, (("model.bin", "0" * 64, 50),))
    monkeypatch.setitem(models.WHISPERS, "bad", bad)
    with pytest.raises(models.SetupError, match="SHA-256"):
        models.setup_whisper(tmp_path, "bad", say=lambda text: None, opener=opener)
    assert list(bad.folder(tmp_path).iterdir()) == []


LOADS_WHISPER = """import sys
from kairu.voice import whisper
faster_whisper = whisper.load_faster_whisper()
assert faster_whisper.WhisperModel
print(sorted(name for name in ("av", "huggingface_hub", "onnxruntime", "requests", "urllib3", "torch") if name in sys.modules))
"""


def test_the_listener_loads_faster_whisper_without_pyav_the_downloader_or_onnxruntime():
    pytest.importorskip("faster_whisper")
    done = subprocess.run([sys.executable, "-c", LOADS_WHISPER], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_only_the_tests_pretend_whisper_writes_anything_and_never_words():
    code = (ROOT / "kairu" / "voice" / "whisper.py").read_text(encoding="utf-8")
    from tests_kairu.test_voice_rules import WRITES
    assert WRITES.findall(code) == ['open(self.mic / "heard.log", "a"']  # the time and the recording's name, for the tests
    assert code.index('open(self.mic / "heard.log"') > code.index("class StandInWhisper")
    assert 'heard.write(f"{time.time():.6f} {name}\\n")' in code


# --- with Whisper base.en and tiny.en themselves, where they are set up (the owner's PC; skipped in CI) -----------------

@pytest.fixture(scope="module", params=["base.en", "tiny.en"])
def tiny(request):
    """The real Whisper: base.en (the default) and tiny.en (the other choice), each where it is set up."""
    pytest.importorskip("faster_whisper")
    try:
        place = models.whisper_ready(ROOT / "data", request.param)
    except models.NotSetUp:
        pytest.skip(f"Whisper {request.param} is not set up in this folder (`kairu voice setup`)")
    return kw.Whisper(place)


@pytest.mark.parametrize("name,said", [
    ("kairu", []), ("kairu_open_chrome_and_volume", ["open chrome and set volume to 30"]), ("kairu_stop", ["stop"]),
    ("kairu_search_weather", ["search the weather"]), ("kairu_two_breaths", ["open notepad", "set volume to 20"]),
    ("no_kairu", []),
])
def test_real_tiny_en_hears_the_recorded_orders(tiny, name, said):
    events = hear(kw.WhisperHearing(tiny, background=False), name)
    orders = [event.get("order") or ("stop" if event.get("stop") else None) for event in kinds(events, "order", "stop")]
    assert orders == said
    assert bool(kinds(events, "wake")) is (name != "no_kairu")


def test_real_tiny_en_invents_no_order_from_kairu_alone_noise_or_taps(tiny):
    hearing = kw.WhisperHearing(tiny, background=False)
    events = hear(hearing, "kairu", noise(3, 2500, seed=5), clicks(3), noise(2, 900, seed=6))
    assert kinds(events, "order", "unclear", "stop", "thanks") == []
