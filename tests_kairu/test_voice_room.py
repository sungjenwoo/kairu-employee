"""Your voice over the room (laptop test, 16 Nov 2026: "it hears me but at the same time the sound of my surroundings, so it
mixes and captures wrong"). The speech gate learns how loud you are at the microphone: quieter sound (people, a TV, traffic
further away) no longer starts an utterance or keeps yours going, and Whisper hears a copy with the room turned down and the
room's steady noise taken out. Made-up sound only: no microphone, nothing played aloud."""

import pytest

np = pytest.importorskip("numpy")

from kairu.voice import whisper as kw  # noqa: E402

RATE = kw.RATE
CHUNK = RATE // 10  # the microphone gives a tenth of a second at a time
rng = np.random.default_rng(16112026)


def tone(level: float, tenths: int, pitch: float = 220.0) -> np.ndarray:
    """A voice-like sound at this RMS level: a few harmonics, wavering."""
    t = np.arange(tenths * CHUNK) / RATE
    wave = sum(np.sin(2 * np.pi * pitch * k * t + k) / k for k in (1, 2, 3, 4))
    wave *= 1 + 0.3 * np.sin(2 * np.pi * 4 * t)
    return wave / np.sqrt(np.mean(wave ** 2)) * level


def hiss(level: float, tenths: int) -> np.ndarray:
    return rng.normal(0, level, tenths * CHUNK)


def pcm(samples: np.ndarray) -> bytes:
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


def feed(gate: kw.SpeechGate, samples: np.ndarray) -> list[tuple[str, bytes, int]]:
    """Every gate event, with the tenth of a second it happened in."""
    events = []
    data = pcm(samples)
    for at in range(0, len(data), CHUNK * 2):
        happened, utterance = gate.feed(data[at:at + CHUNK * 2])
        if happened:
            events.append((happened, utterance, at // (CHUNK * 2)))
    return events


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(samples, dtype=float) ** 2)))


def settled(gate: kw.SpeechGate, room: float = 40.0) -> None:
    feed(gate, hiss(room, 30))  # 3 s of the room: its noise level and spectrum


def you_said_two_things(gate: kw.SpeechGate, room: float = 40.0) -> None:
    for _ in range(kw.VOICE_LEARNED):
        events = feed(gate, np.concatenate([tone(5000, 10) + hiss(room, 10), hiss(room, 10)]))
        assert [kind for kind, _, _ in events] == ["start", "end"]


def test_your_level_is_learned_from_what_you_say():
    gate = kw.SpeechGate()
    settled(gate)
    assert gate.voices == 0
    you_said_two_things(gate)
    assert gate.voices == kw.VOICE_LEARNED and 3500 < gate.voice_level < 7500


def test_people_talking_further_away_no_longer_start_an_utterance():
    gate = kw.SpeechGate()
    settled(gate)
    you_said_two_things(gate)
    assert not gate.speaking
    assert feed(gate, tone(900, 20, 180) + hiss(40, 20)) == []  # a voice across the room (about -15 dB): nothing starts
    assert [kind for kind, _, _ in feed(gate, np.concatenate([tone(5000, 10) + hiss(40, 10), hiss(40, 10)]))] == ["start", "end"]


def test_the_room_does_not_keep_your_utterance_going():
    gate = kw.SpeechGate()
    settled(gate)
    you_said_two_things(gate)
    # you speak for a second, then people keep talking in the background for three seconds
    sound = np.concatenate([tone(5000, 10) + hiss(40, 10), tone(900, 30, 180) + hiss(40, 30)])
    events = feed(gate, sound)
    kinds = [kind for kind, _, _ in events]
    assert kinds[:2] == ["start", "end"]
    ended_at = events[1][2]
    assert ended_at <= 10 + kw.END_CHUNKS + 1  # it ends 0.6 s after your words, not when the room goes quiet
    assert len(events[1][1]) < (10 + kw.END_CHUNKS + 2) * CHUNK * 2


def test_before_the_fix_the_room_would_have_kept_it_going():
    """The same sound through a gate that never learns you (as before 16 Nov 2026): one long utterance, words mixed."""
    gate = kw.SpeechGate()
    gate.you = lambda: 0.0  # never knows how loud you are
    settled(gate)
    events = feed(gate, np.concatenate([tone(5000, 10) + hiss(40, 10), tone(900, 30, 180) + hiss(40, 30), hiss(40, 10)]))
    assert [kind for kind, _, _ in events] == ["start", "end"] and events[1][2] > 10 + kw.END_CHUNKS + 8


def test_whisper_hears_the_room_turned_down_and_your_words_kept():
    gate = kw.SpeechGate()
    settled(gate)
    you = tone(5000, 8)
    room = tone(900, 8, 180)
    sound = np.concatenate([you, room, you]) + hiss(40, 24)
    cleaned = np.frombuffer(gate.clean(pcm(sound)), np.int16).astype(float)
    part = 8 * CHUNK
    hang = (kw.HANG_FRAMES + 1) * kw.FRAME
    before = rms(sound[part + hang:2 * part - hang])
    after = rms(cleaned[part + hang:2 * part - hang])
    assert after < before / 6  # the people in the room: at least 15 dB quieter
    assert rms(cleaned[hang:part - hang]) > 0.8 * rms(sound[hang:part - hang])  # your words: as loud as they were


def test_the_rooms_steady_noise_is_taken_out():
    gate = kw.SpeechGate()
    fan = lambda tenths: hiss(400, tenths)  # noqa: E731  a loud fan, below the speech line's 3 times
    feed(gate, fan(30))
    assert gate.room_spectrum is not None
    sound = np.concatenate([fan(5), tone(5000, 10) + fan(10), fan(5)])
    cleaned = np.frombuffer(gate.clean(pcm(sound)), np.int16).astype(float)
    words = slice(5 * CHUNK + 800, 15 * CHUNK - 800)
    noise_in_words_before = rms(sound[words] - tone(5000, 10)[800:-800])
    noise_in_words_after = rms(cleaned[words] - tone(5000, 10)[800:-800])
    assert noise_in_words_after < noise_in_words_before  # less fan under your words


def test_moving_away_never_locks_you_out():
    gate = kw.SpeechGate()
    settled(gate)
    you_said_two_things(gate)
    assert feed(gate, tone(1100, 10) + hiss(40, 10)) == []  # right after: a quiet voice is the room
    feed(gate, hiss(40, 600))  # a minute of quiet
    assert [kind for kind, _, _ in feed(gate, np.concatenate([tone(1100, 10) + hiss(40, 10), hiss(40, 10)]))][:1] == ["start"]


def test_short_or_silent_sound_comes_back_as_it_was():
    gate = kw.SpeechGate()
    assert gate.clean(b"") == b""
    quiet = pcm(hiss(20, 5))
    assert gate.clean(quiet) == quiet


def test_the_listener_and_kairu_voice_check_hear_the_cleaned_copy_and_nothing_is_written():
    from kairu.config import ROOT
    source = (ROOT / "kairu" / "voice" / "whisper.py").read_text(encoding="utf-8")
    assert "return self.hear(self.gate.clean(utterance))" in source
    assert "hear(gate.clean(utterance))" in (ROOT / "kairu" / "voice" / "check.py").read_text(encoding="utf-8")
    gate_code = source[source.index("class SpeechGate"):source.index("# --- Whisper")]
    for never in ("open(", "write", "wave.", "tofile", "save"):
        assert never not in gate_code, never


def test_cleaning_on_whispers_thread_never_looks_into_what_the_microphones_thread_is_changing():
    """Whisper hears in its own thread while the microphone keeps feeding the gate: clean() reads only room_line and
    room_spectrum, each replaced whole, never the levels deque (found while building: "deque mutated during iteration"
    made an utterance heard as nothing)."""
    import threading
    gate = kw.SpeechGate()
    settled(gate)
    utterance = pcm(tone(5000, 20) + hiss(40, 20))
    problems, done = [], threading.Event()

    def listen():
        while not done.is_set():
            gate.feed(pcm(hiss(40, 1)))

    thread = threading.Thread(target=listen)
    thread.start()
    try:
        for _ in range(200):
            try:
                gate.clean(utterance)
            except RuntimeError as problem:
                problems.append(problem)
    finally:
        done.set()
        thread.join()
    assert problems == []
    source = kw.SpeechGate.clean.__code__.co_names
    assert "noise" not in source and "levels" not in source


def test_kairu_a_breath_and_stop_stays_one_utterance_even_after_the_gate_has_learned_you():
    """16 Nov 2026: the soft "s" of "stop" after "Kairu" and a breath counted as quiet, so "Kairu" ended alone and "stop"
    was dropped as too short. One extra tenth of a second, once, when soft sound is there right at the end."""
    import wave
    from pathlib import Path

    def recorded(name):
        with wave.open(str(Path(__file__).parent / "voice" / f"{name}.wav")) as found:
            return np.frombuffer(found.readframes(found.getnframes()), np.int16).astype(float)
    gate = kw.SpeechGate()
    quiet = np.zeros(RATE)
    sound = np.concatenate([quiet, recorded("open_notepad"), quiet, recorded("open_notepad"), quiet, recorded("kairu_stop"), quiet])
    ends = [kind for kind, _, _ in feed(gate, sound) if kind in ("end", "dropped")]
    assert ends == ["end", "end", "end"]  # two orders, then "Kairu, stop" whole: nothing dropped
