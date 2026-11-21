"""Hearing with Whisper (voice.engine: whisper-base.en, the default, or whisper-tiny.en): sound in, the same events as
kairu/voice/hearing.py out.

    the speech gate   decides, a tenth of a second at a time, whether someone is speaking: the sound's level against the
                      room's own noise (numpy, no model). Whisper runs only on what it lets through: in a silent room, never.
    Whisper base.en   (or tiny.en) hears each utterance whole, once it has ended (a pause of 0.6 s), with Kairu's own words as a hint,
                      in a thread of its own so the microphone is never kept waiting. faster-whisper, int8, on the CPU.
    the words         the same rules as for Vosk (kairu/voice/words.py): "Kairu" first, then the order; fillers out, levels
                      as digits, the usual mishearings put right, one short question instead of a guess.

The hint is words only (VOCABULARY): how Kairu's names and order words are spelled. Never a whole example order, which made
Whisper "hear" that order when it was not said (8 Nov 2026), and the tests check it does not invent one.

An utterance is what you say between pauses. When Whisper has heard it, it must begin with "Kairu" (or be said within a
session), as with Vosk: outside a session, an utterance without "Kairu" is dropped at once, nothing shown, kept or sent.
"Kairu, stop" (or "stop" in a session) is the emergency stop; the listener writes it as soon as Whisper's words are ready.

Sound is only ever in memory: each utterance is handed to Whisper as numbers and dropped after it; nothing is written.

Live words (voice.live_caption_every, your setting of 15 Nov 2026: 0.20 s): while you are still speaking, Whisper also hears
what you have said so far, this often, and the bar shows it in grey ("hearing"), the way Google shows your words as you
speak; when you stop, the whole utterance is heard once more and its words ("heard") replace the grey ones. The live words
are only shown: never a stop or an answer, and never an order except a quick one on the closing look (below). They follow the same
rules as "heard": outside a session they show only once Whisper is sure they began with "Kairu", a spoken yes or PIN is
never shown, Kairu's own voice is never shown, and nothing is kept or written. If Whisper is still busy with the last look
(a big model on a laptop CPU), the next one waits: the bar shows the words as fast as the PC can, and they never pile up.

Quick orders (your "it must work fast", 15 Nov 2026; needs the live words on): when you stop for 0.2 s, Whisper takes one
closing look at the whole of what you said. If that is a short, harmless order (QUICK_ORDER: open an app, the volume, the
brightness, mute, what's open) and Whisper is sure of it, it goes to the bar at once, without waiting for the 0.6 s pause
and a second hearing. When the pause comes, that same closing look is used as the whole utterance (the sound is the same),
so Whisper never hears it twice; if you said more after all ("open Edge and close Notepad"), only the rest is sent. Every
other order (close, delete, files, typing, restart, anything with a card) still waits for the whole utterance, as before,
and Guardian decides every step either way.

With the fast lane (voice.fast_orders, kairu/voice/fastlane.py) the small Vosk model hears beside Whisper: the live words
come from it, word by word, and the quick order is decided by its grammar recognizer 0.2 s after you stop, in a few
milliseconds, instead of by a Whisper look (about a second each on a laptop CPU). Whisper then takes no live looks at all,
so it is free for the whole utterance. With your-voice-only (voice.only_my_voice) an utterance that is not in your voice is
never an order, a wake or an answer; "Kairu, stop" always is the stop.
"""

import difflib
import os
import queue
import re
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from kairu.voice import fastlane
from kairu.voice import words as w

RATE = 16000
FRAME = 320  # samples: 20 ms
SPEECH_LEVEL = 300  # a voice at the microphone is always louder than this (16-bit RMS, about -40 dBFS)
OVER_NOISE = 3.0  # and this many times louder than the room's own steady noise
VOICED_FRAMES = 2  # of the 20 ms frames in a tenth of a second, this many loud ones make it speech
END_CHUNKS = 6  # a pause of 0.6 s ends an utterance
BEFORE_CHUNKS = 3  # 0.3 s from before the first loud frame, so the first sound of "Kairu" is not cut off
LEAST_SPEECH_FRAMES = 12  # 0.24 s of loud frames at least, or it was a click, a tap or a cough, and Whisper never hears it
MOST_SECONDS = 12.0  # an utterance longer than this is heard in parts
NOISE_FRAMES = 150  # the room's noise: the quietest tenth of the last 3 s
# Your voice over the room (laptop test, 16 Nov 2026: "it hears me but at the same time the sound of my surroundings, so it
# mixes and captures wrong"). You talk close to the microphone, so your words are much louder than people, a TV or traffic
# further away. The gate learns how loud you are and leaves quieter sound out; Whisper hears a cleaned copy (clean below).
NEAR_SHARE = 0.3  # within an utterance: a frame quieter than this share of your own words (about -10 dB) is the room, not you
START_SHARE = 0.25  # once your level is known: sound quieter than this share of it (about -12 dB) never starts an utterance
VOICE_MEMORY = 0.3  # each utterance moves your level this far towards its own
VOICE_LEARNED = 2  # utterances heard before your level is used to start one
VOICE_FADE = 0.998  # a tenth of a second of quiet lowers it this much (halves in about 35 s), so moving away never locks you out
ROOM_DOWN = 0.1  # the room between your words is turned down this far (-20 dB) in what Whisper hears
HANG_FRAMES = 3  # 60 ms kept on each side of your loud frames, so the edges of words are never cut
NOISE_OVER = 1.5  # steady noise (a fan, AC, traffic hum) taken out: this many times the room's own spectrum
NOISE_FLOOR = 0.08  # never below this share of the sound, so words never come out hollow
NOISE_MEMORY = 0.1  # each quiet tenth of a second moves the room's spectrum this far
FFT = 512  # samples (32 ms) for the room's spectrum; half of it is the step
SESSION_SECONDS = 30.0
REPLY_SECONDS = 8.0  # after Kairu asks its follow-up question: this long for your answer, then quiet
ECHO_GRACE = 1.5  # voice.barge_in: an utterance that ends this soon after Kairu stopped speaking may still be its echo
ECHO_SHARE = 0.6  # of the words heard, this share or more are words Kairu was saying: it is Kairu's own voice, left out
BARGE_WORDS = frozenset({"wait", "stop", "enough", "quiet", "hold", "pause", "shush", "sorry", "no", "excuse", "hey", "listen", "on", "me", "a", "sec", "second", "minute"})
ASKED_SECONDS = 20.0  # an answer to "Did you mean 30?" this soon after it
LIVE_EVERY = 0.0  # voice.live_caption_every: how often the live words are heard while you speak (0: never; 0.20 for you)
LIVE_FASTEST = 0.1  # the microphone gives a tenth of a second at a time: no faster than that
QUICK_QUIET = 2  # 0.2 s of quiet after your words: Whisper's closing look at the whole of what you said
QUICK_ORDER = re.compile(  # short, harmless orders that start on the closing look (Low or read-only skills only)
    r"(?:open|launch|start) [a-z][a-z0-9+']*(?: [a-z][a-z0-9+']*)?"
    r"|(?:set |turn )?(?:the )?(?:volume|brightness)(?: to)? \d{1,3}"
    r"|(?:turn )?(?:the )?(?:volume|brightness) (?:up|down)"
    r"|(?:mute|unmute)(?: the volume)?"
    r"|what's open")
NOT_QUICK = frozenset({"and", "then", "also", "file", "files", "folder", "folders", "document", "page", "tab", "website"})

PROMPT = "Kairu, Notepad, Chrome."  # Whisper's prompt: how the names are spelled (the only hint before 10 Nov 2026)
VOCABULARY = ("Kairu, volume, brightness, open, close, Chrome, Notepad, what's open, search, weather, Google, find, move, "
              "rename, delete, undo, thank you, stop, yes, no, Hyderabad, Claude, remember.")  # its hotwords: Kairu's order words, never a whole order
# On Piper's four Indian English voices (72 orders and sentences, 10 Nov 2026), tiny.en got 41 right with the prompt alone,
# 53 with these words as its prompt, 56 with them as hotwords beside the prompt; none of the three invented an order. In
# the owner's own voice (10 Nov 2026), base.en with this hint got 10 of 10 orders right, tiny.en with it 8 of 10.
SURE_LOGPROB = -1.0  # Whisper's own average log-probability below which it was not sure what it heard
NO_SPEECH = 0.6  # Whisper's own score that a piece was not speech at all: above it, it is noise, dropped unheard
NO_SPEECH_UNSURE = 0.3  # and above this when Whisper was not sure of the words either. Measured 10 Nov 2026: the recorded
# orders 0.00-0.07; keyboard taps that base.en wrote as "Pup, pup, pup" 0.84, a loud hiss it wrote as "I'm sorry." 0.53
# (log-probability -1.88), one tiny.en wrote as "Okay." 0.43. Whisper's own rule is the same shape (0.6 with -1.0).
MOST_TOKENS = 48  # an order is short; more than this is Whisper running on
THREADS = 2  # as fast as 4 on the owner's PC, and less memory (tiny.en and base.en)
BIG_THREADS = 4  # the bigger models (small.en up to large-v3-turbo) are much faster with 4

# faster-whisper's package loads these for decoding sound files (PyAV) and downloading models (huggingface_hub), which the
# listener never does: the sound comes from memory, and `kairu voice setup` downloads. Stood in for while it loads.
NOT_IN_THE_LISTENER = ("av", "huggingface_hub")
TEST_WHISPER = "KAIRU_TEST_WHISPER"


# --- the speech gate --------------------------------------------------------------------------------------------------

class SpeechGate:
    """A tenth of a second at a time: is someone speaking? When an utterance ends, its sound (16-bit, in memory)."""

    def __init__(self, rate: int = RATE):
        import numpy
        self.numpy = numpy
        self.rate = rate
        self.levels: deque = deque(maxlen=NOISE_FRAMES)
        self.speaking = False
        self.before: deque = deque(maxlen=BEFORE_CHUNKS)
        self.kept: list[bytes] = []
        self.quiet = 0
        self.loud_frames = 0
        self.gated = 0  # tenths of a second the gate kept from Whisper (for the idle measure)
        self.ended_by_pause, self.ended_loud = False, 0  # how the last utterance ended: by a pause? its loud frames
        self.voice_level, self.voices = 0.0, 0  # how loud you are at the microphone, and from how many utterances
        self.loud_levels: list[float] = []  # this utterance's loud frames: how loud you are in it
        self.graced = False  # this utterance already had its one extra tenth of a second (feed)
        self.room_spectrum = None  # the room's own steady noise, from quiet moments (numbers only, never sound)
        self.room_line = float(SPEECH_LEVEL)  # the speech line of the last tenth of a second: what clean() reads, from Whisper's
        # own thread, so it never looks into `levels` while the microphone's thread is adding to it
        window = numpy.hanning(FFT + 1)[:-1].astype(numpy.float32)  # periodic: at half steps the windows add up to 1
        self.window = window

    def noise(self) -> float:
        if len(self.levels) < 10:
            return 0.0
        return float(self.numpy.percentile(self.numpy.fromiter(self.levels, float), 10))

    def you(self) -> float:
        """How loud your words are in this utterance so far (0 until there are enough of them)."""
        if len(self.loud_levels) < 5:
            return 0.0
        return float(self.numpy.percentile(self.numpy.asarray(self.loud_levels, dtype=float), 75))

    def _start_line(self, line: float) -> float:
        return max(line, START_SHARE * self.voice_level) if self.voices >= VOICE_LEARNED else line

    def _learn_room(self, samples) -> None:
        np = self.numpy
        if samples.size < FFT:
            return
        steps = range(0, samples.size - FFT + 1, FFT // 2)
        spectrum = np.mean([np.abs(np.fft.rfft(samples[at:at + FFT] * self.window)) for at in steps], axis=0)
        self.room_spectrum = spectrum if self.room_spectrum is None else \
            (1 - NOISE_MEMORY) * self.room_spectrum + NOISE_MEMORY * spectrum

    def clean(self, sound: bytes) -> bytes:
        """What Whisper hears: the utterance with the room turned down between your words (frames much quieter than your own
        words, kept 60 ms around them) and the room's steady noise taken out of every moment. In memory only, like the sound
        itself; nothing is written. Sound too short or with nothing loud in it comes back as it was."""
        np = self.numpy
        samples = np.frombuffer(sound[:len(sound) - len(sound) % 2], np.int16).astype(np.float32)
        count = samples.size // FRAME
        if count < 3:
            return sound
        frames = samples[:count * FRAME].reshape(count, FRAME)
        levels = np.sqrt(np.mean((frames - frames.mean(axis=1, keepdims=True)) ** 2, axis=1))
        line, room_spectrum = self.room_line, self.room_spectrum  # read once: both are replaced whole, never changed in place
        loud = levels[levels > line]
        if loud.size < 3:
            return sound
        loud_now = levels >= max(line, NEAR_SHARE * float(np.percentile(loud, 75)))
        near = np.convolve(loud_now.astype(np.float32), np.ones(2 * HANG_FRAMES + 1, np.float32), mode="same") > 0
        gains = np.where(near, 1.0, ROOM_DOWN).astype(np.float32)
        gain = np.repeat(gains, FRAME)
        gain = np.convolve(gain, np.ones(80, np.float32) / 80, mode="same")  # 5 ms ramps: no clicks where it turns down
        out = samples.copy()
        out[:gain.size] *= gain
        if room_spectrum is not None and float(room_spectrum.max()) > 1.0:  # a silent room has no noise to take out
            out = self._without_room(out, room_spectrum)
        return np.clip(out, -32768, 32767).astype(np.int16).tobytes()

    def _without_room(self, samples, room_spectrum):
        """The room's steady noise taken out (spectral subtraction, half-overlapping 32 ms windows, all in one numpy call)."""
        np = self.numpy
        step = FFT // 2
        padded = np.concatenate([np.zeros(FFT, np.float32), samples, np.zeros(FFT + step, np.float32)])
        count = (padded.size - FFT) // step + 1
        starts = np.arange(count) * step
        pieces = padded[starts[:, None] + np.arange(FFT)] * self.window
        spectra = np.fft.rfft(pieces, axis=1)
        size = np.abs(spectra)
        kept = np.maximum(size - NOISE_OVER * room_spectrum, NOISE_FLOOR * size) / np.maximum(size, 1e-9)
        back = np.fft.irfft(spectra * kept, FFT, axis=1).astype(np.float32)
        out = np.zeros(padded.size, np.float32)
        np.add.at(out, (starts[:, None] + np.arange(FFT)).ravel(), back.ravel())
        return out[FFT:FFT + samples.size]

    def feed(self, sound: bytes) -> tuple[str | None, bytes]:
        """("start", b""), ("end", the utterance), ("dropped", b"") or (None, b"")."""
        np = self.numpy
        samples = np.frombuffer(sound[:len(sound) - len(sound) % (2 * FRAME)], np.int16).astype(np.float32)
        frames = samples.reshape(-1, FRAME) if samples.size else samples.reshape(0, FRAME)
        levels = np.sqrt(np.mean((frames - frames.mean(axis=1, keepdims=True)) ** 2, axis=1)) if len(frames) else np.zeros(0)
        line = max(SPEECH_LEVEL, OVER_NOISE * self.noise())
        self.room_line = line
        if self.speaking:  # the room is not you: only frames near your own loudness keep the utterance going
            line = max(line, NEAR_SHARE * self.you())
        else:
            line = self._start_line(line)
        hits = levels > line
        loud = int(np.count_nonzero(hits))
        self.levels.extend(float(level) for level in levels)
        voiced = loud >= min(VOICED_FRAMES, max(len(levels), 1))
        if not self.speaking:
            self.before.append(sound)
            if not voiced:
                self.gated += 1
                self.voice_level *= VOICE_FADE
                if not loud:
                    self._learn_room(samples)
                return None, b""
            self.speaking, self.kept, self.quiet, self.loud_frames = True, list(self.before), 0, loud
            self.loud_levels = [float(level) for level in levels[hits]]
            self.before.clear()
            return "start", b""
        self.kept.append(sound)
        self.loud_frames += loud
        self.loud_levels.extend(float(level) for level in levels[hits])
        self.quiet = 0 if voiced else self.quiet + 1
        if voiced:
            self.graced = False
        elif self.quiet >= END_CHUNKS and not self.graced and np.count_nonzero(levels > self.room_line) >= VOICED_FRAMES:
            # the pause would end it, but there is soft sound right now (the "s" of "stop" after "Kairu" and a breath): one
            # more tenth of a second, once, to hear whether a word follows (16 Nov 2026: "Kairu, stop" lost its "stop")
            self.graced = True
            return None, b""
        if self.quiet < END_CHUNKS and len(self.kept) * len(sound) < MOST_SECONDS * self.rate * 2:
            return None, b""
        utterance, enough = b"".join(self.kept[:len(self.kept) - max(self.quiet - 2, 0)]), self.loud_frames >= LEAST_SPEECH_FRAMES
        self.ended_by_pause, self.ended_loud = self.quiet >= END_CHUNKS, self.loud_frames
        if enough and self.you():
            level = self.you()
            self.voice_level = level if not self.voices else (1 - VOICE_MEMORY) * self.voice_level + VOICE_MEMORY * level
            self.voices += 1
        self.speaking, self.kept, self.quiet, self.loud_frames, self.loud_levels, self.graced = False, [], 0, 0, [], False
        return ("end", utterance) if enough else ("dropped", b"")


# --- Whisper ----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Heard:
    text: str
    sure: bool
    score: float = field(default=0.0, compare=False)  # Whisper's lowest average log-probability (for `kairu voice check`)
    dropped: int = field(default=0, compare=False)  # pieces dropped as noise (no_speech_prob), for `kairu voice check`


def load_faster_whisper():
    """faster-whisper without PyAV or the Hugging Face downloader: stand-ins while its package loads, gone from sys.modules
    after it, so the real ones still load if anything asks for them. What faster-whisper took from them refuses to run."""
    import types

    def not_here(*args, **kwargs):
        raise RuntimeError("not loaded in the listener: the sound comes from memory, and `kairu voice setup` downloads models")

    stand_ins = {}
    for name in NOT_IN_THE_LISTENER:
        if name not in sys.modules:
            stand_ins[name] = module = types.ModuleType(name)
            module.__getattr__ = lambda attribute, name=name: not_here
    sys.modules.update(stand_ins)
    try:
        import faster_whisper
    finally:
        for name, stand_in in stand_ins.items():
            if sys.modules.get(name) is stand_in:
                del sys.modules[name]
    return faster_whisper


def noise(segment) -> bool:
    """Whisper wrote words for this piece, but by its own score it was not speech: taps, a hiss, a fan."""
    return segment.no_speech_prob > NO_SPEECH or (segment.no_speech_prob > NO_SPEECH_UNSURE and segment.avg_logprob < SURE_LOGPROB)


class Whisper:
    """Whisper from its folder (data/voice/faster-whisper-base.en, or -tiny.en), hearing one utterance at a time."""

    def __init__(self, folder, hint: str = PROMPT, threads: int = THREADS, beam: int = 5, hotwords: str | None = VOCABULARY):
        self.hint, self.beam, self.hotwords = hint, beam, hotwords
        self.model = load_faster_whisper().WhisperModel(str(folder), device="cpu", compute_type="int8", cpu_threads=threads)

    def __call__(self, sound: bytes) -> Heard:
        import numpy
        samples = numpy.frombuffer(sound, numpy.int16).astype(numpy.float32) / 32768
        segments, _ = self.model.transcribe(
            samples, language="en", beam_size=self.beam, temperature=0.0, initial_prompt=self.hint or None, vad_filter=False,
            condition_on_previous_text=False, without_timestamps=True, max_new_tokens=MOST_TOKENS, hotwords=self.hotwords)
        segments = list(segments)
        heard = [segment for segment in segments if not noise(segment)]
        text = " ".join(segment.text.strip() for segment in heard).strip()
        score = min((segment.avg_logprob for segment in heard), default=0.0)
        sure = bool(heard) and score >= SURE_LOGPROB and all(segment.compression_ratio < 2.4 for segment in heard)
        return Heard(text, sure, round(score, 2), len(segments) - len(heard))


class StandInWhisper:
    """The tests' pretend Whisper (KAIRU_TEST_WHISPER names a JSON file: {recording: [what Whisper hears, ...]}). It "hears"
    the recording the pretend mic (KAIRU_TEST_MIC) played last, so the tests run the real speech gate with no model. Each
    time it hears, it adds the time and the recording's name to heard.log beside the pretend mic (never the words)."""

    def __init__(self, script: str, mic_folder: str):
        import json
        from pathlib import Path
        self.script = {name: list(said) for name, said in json.loads(Path(script).read_text(encoding="utf-8")).items()}
        self.mic = Path(mic_folder)

    def __call__(self, sound: bytes) -> Heard:
        log = self.mic / "played.log"
        played = log.read_text(encoding="utf-8").split() if log.exists() else []
        name = re.sub(r"^(?:zz)?\d+_|\.cue$", "", played[-1]) if played else ""
        said = self.script.get(name) or [""]
        text = said.pop(0) if len(said) > 1 else said[0]
        with open(self.mic / "heard.log", "a", encoding="utf-8") as heard:
            heard.write(f"{time.time():.6f} {name}\n")
        return Heard(text, True)


def warm(hear) -> None:
    """Whisper's first sentence pays for setting itself up (several seconds with a big model on a laptop CPU): this pays
    it with half a second of silence while the model loads, never on your first real sentence (laptop test, 15 Nov 2026)."""
    if isinstance(hear, StandInWhisper):
        return  # the tests' pretend Whisper has nothing to set up, and would count it as a sentence
    try:
        hear(bytes(RATE))  # 0.5 s of 16-bit silence
    except Exception:  # only a warm-up: a real problem shows on the first real sentence, as before
        pass


def transcriber(folder):
    """The real Whisper, or the tests' pretend one."""
    if os.environ.get(TEST_WHISPER):
        from kairu.voice import mic
        return StandInWhisper(os.environ[TEST_WHISPER], os.environ.get(mic.TEST_MIC, "."))
    name = str(folder).lower()
    big = any(size in name for size in ("large", "medium", "small"))
    if not big:
        return Whisper(folder)
    # the bigger models: 4 threads, and one best guess instead of five (beam 1): they hear well enough without the beam,
    # and it takes about a third off each sentence on a laptop CPU (the owner's "it must answer quickly", 15 Nov 2026)
    return Whisper(folder, threads=min(BIG_THREADS, os.cpu_count() or 2), beam=1)


# --- "Kairu" in Whisper's words ---------------------------------------------------------------------------------------

KAIRU_HEARD = frozenset({"kairu", "kyru", "kairo", "cairo", "kiru", "karu", "kyro", "kairou", "kyrou", "carew", "cairu",
                         "kairoo", "kyroo", "kaeru", "kaoru", "kayru", "kiro", "kyle", "kai",
                         # more of Whisper's spellings of it (15 Nov 2026: the owner said "Kairu" was often not caught)
                         "kaira", "kairi", "kaiyu", "kairos", "karoo", "kyra", "kira", "kyrie", "kayro", "kairoh", "cairou"})
GREETINGS = frozenset({"hey", "hi", "hello", "ok", "okay", "oh", "o", "yo", "hay"})  # "Hey Kairu", "Okay Kairu"
KAIRU_END = frozenset({"ru", "roo", "rue", "rou", "ro"})


def tokens(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower().replace("-", " ")).split()


def split_wake(text: str) -> tuple[bool, list[str]]:
    """(did it begin with "Kairu", the words after it), for Whisper's whole sentences."""
    said = tokens(text)
    if len(said) >= 2 and said[0] in GREETINGS:  # "hey Kairu ...": the greeting goes, never into an order
        woke, rest = split_wake(" ".join(said[1:]))
        if woke:
            return True, rest
    if said and (said[0] in KAIRU_HEARD or difflib.SequenceMatcher(None, said[0], "kairu").ratio() >= 0.75):
        rest = said[1:]
        return True, rest[1:] if rest[:1] and rest[0] in KAIRU_END else rest  # "kai ru", "ky roo"
    if len(said) >= 2 and difflib.SequenceMatcher(None, said[0] + said[1], "kairu").ratio() >= 0.8:
        return True, said[2:]  # "car ooh"
    return False, said


# --- the hearing ------------------------------------------------------------------------------------------------------

class WhisperHearing:
    """Sound in, events out, as kairu/voice/hearing.py's Hearing: the listener uses either. `hear` is a Whisper (or the
    tests' stand-in); with background=True it hears in its own thread, so the microphone is read on time meanwhile."""

    def __init__(self, hear, rate: int = RATE, background: bool = True, live_every: float = LIVE_EVERY):
        self.hear, self.rate = hear, rate
        self.live_every = max(float(live_every), LIVE_FASTEST) if live_every and live_every > 0 else 0.0
        self.gate = SpeechGate(rate)
        self.session = False
        self.stopped = False
        self.talking = False
        self.clock = 0.0
        self.last_word = 0.0
        self._reply_from, self._reply_seconds = None, REPLY_SECONDS
        self.breath = 0
        self.heard_at = None  # when Whisper's words for the last utterance were ready (time.time())
        self.whisper_runs = 0
        self._asked = None  # (the order to say instead, when) after "Did you mean 30?"
        self._echo: tuple[set, float] | None = None  # voice.barge_in: (the words Kairu is saying, until when)
        self._waiting = 0  # utterances handed to Whisper and not heard yet
        self._utterance_no = 0  # counts utterances, so live words that come back late are never shown for the next one
        self._live_at = 0.0  # when Whisper was last asked for the live words
        self._live_busy = False  # a look at the live words is with Whisper: the next waits (never piled up)
        self._shown_live = ""  # the grey words in the bar now
        self.live_runs = 0
        self._closing: list | None = None  # [utterance, its loud frames then, what Whisper heard (None while it hears)]
        self._final_from_look: int | None = None  # this utterance's whole sound is the closing look still with Whisper
        self._early: tuple[int, str] | None = None  # (utterance, the quick order sent on its closing look)
        self.fast: fastlane.FastLane | None = None  # voice.fast_orders / voice.only_my_voice (attach_fast)
        self._fast_closed: tuple[int, int] | None = None  # (utterance, loud frames) of the fast lane's last closing look
        self._voices: dict[int, str] = {}  # utterance -> whose voice it was (fastlane.FastLane.voice)
        self.lips = None  # voice.camera (attach_lips): kairu/voice/lips.py's LipWatch
        self._lips: dict[int, str] = {}  # utterance -> what the camera saw (LipWatch.verdict)
        self.soft_problem = ""
        self._results: queue.SimpleQueue = queue.SimpleQueue()
        self._work: queue.SimpleQueue | None = None
        if background:
            self._work = queue.SimpleQueue()
            threading.Thread(target=self._hearing, name="kairu-whisper", daemon=True).start()

    # --- what the listener asks ----------------------------------------------------------------------

    def start_session(self) -> list[dict]:
        if self.stopped:
            return []
        self.session = True
        self.last_word = self.clock
        self._reply_from = None
        return [{"wake": True, "alone": True}]

    def listen_for_reply(self, seconds: float = REPLY_SECONDS) -> list[dict]:
        """Kairu has just asked its follow-up question, with the mic already on: listen for your answer, without "Kairu",
        for this long (at most REPLY_SECONDS); once you speak, the session runs as usual. Never switches the mic on."""
        if self.stopped:
            return []
        self.session = True
        self.last_word = self.clock
        self._reply_from, self._reply_seconds = self.clock, min(float(seconds), REPLY_SECONDS)
        return [{"reply": True}]

    def _quiet_after(self) -> float:
        """SESSION_SECONDS, or the reply window's length while you have not spoken since Kairu asked."""
        if self._reply_from is not None and self.last_word <= self._reply_from:
            return self._reply_seconds
        return SESSION_SECONDS

    def feed(self, sound: bytes) -> list[dict]:
        if self.stopped or not sound:
            return []
        self.clock += len(sound) / (2 * self.rate)
        events: list[dict] = []
        self._collect(events)
        if self.stopped:
            return events
        happened, utterance = self.gate.feed(sound)
        caption = None
        if happened == "start":
            self.talking = True
            self._utterance_no += 1
            self._live_at = self.clock
            if self.fast is not None:
                caption = self.fast.begin(self.gate.kept)
            events.append({"talking": True})
        elif happened in ("end", "dropped"):
            self.talking = False
            events.append({"talking": False})
            if happened == "dropped":
                if self.fast is not None:
                    self.fast.drop()
                self._clear_live(events)  # a click or a cough: no grey words left behind
            if happened == "end":
                number = self._utterance_no
                if self.fast is not None:
                    self._voices[number] = self.fast.end()  # whose voice, before Whisper's words are used
                if self.lips is not None:  # voice.camera: were your lips moving while this was said?
                    ended = time.monotonic()
                    self._lips[number] = self.lips.verdict(ended - len(utterance) / (2 * self.rate), ended)
                self._waiting += 1
                same = self._closing_is_whole(number)
                if same and self._closing[2] is not None:  # the closing look heard exactly this: never heard twice
                    self._results.put(("heard", self._closing[2], (time.time(), number)))
                    self._collect(events)
                elif same and self._live_busy:
                    self._final_from_look = number  # the closing look, still with Whisper, is the whole utterance
                else:
                    self.whisper_runs += 1
                    if self._work is None:
                        self._results.put(("heard", self._heard(utterance), (time.time(), number)))
                        self._collect(events)
                    else:
                        self._work.put(("heard", utterance, number))
        elif self.fast is not None and self.gate.speaking:
            caption = self.fast.feed(sound)
            if self.gate.quiet >= QUICK_QUIET:
                self._fast_closing(events)
        elif self._live_due():
            closing = self.gate.quiet >= QUICK_QUIET
            self._live_busy, self._live_at = True, self.clock
            self.live_runs += 1
            number = self._utterance_no
            if closing:
                self._closing = [number, self.gate.loud_frames, None]
            so_far = b"".join(self.gate.kept)  # a copy, in memory only, like the utterance itself
            if self._work is None:
                self._results.put(("live", (number, closing), self._heard(so_far)))
                self._collect(events)
            else:
                self._work.put(("live", number, so_far, closing))
        if caption is not None and self.live_every and self.gate.speaking and self.clock - self._live_at >= self.live_every - 1e-6:
            self._live_at = self.clock
            self._caption(caption, events)
        if self.session and not self.talking and not self._waiting and self.clock - self.last_word > self._quiet_after():
            self.session = False
            events.append({"quiet": True})
        return events

    def set_echo(self, speaking: str) -> None:
        """voice.barge_in: what Kairu is saying now ("" when it is quiet). Its words are left out for ECHO_GRACE after."""
        if speaking:
            self._echo = (set(tokens(speaking)), self.clock + ECHO_GRACE)
        elif self._echo:
            self._echo = (self._echo[0], min(self._echo[1], self.clock + ECHO_GRACE))

    def _echoing(self) -> set | None:
        if self._echo and self.clock <= self._echo[1] + END_CHUNKS * 0.1:
            return self._echo[0]
        self._echo = None
        return None

    def close(self) -> None:
        if self._work is not None:
            self._work.put(None)

    def attach_lips(self, lips) -> None:
        """voice.camera (kairu/voice/lips.py): an utterance your lips didn't say is never yours."""
        self.lips = lips

    def attach_fast(self, lane: "fastlane.FastLane") -> None:
        """The fast lane (voice.fast_orders / voice.only_my_voice): Vosk beside Whisper, on the same sound."""
        self.fast = lane

    # --- the fast lane: live words from Vosk, quick orders from its grammar --------------------------

    def _caption(self, said: str, events: list[dict]) -> None:
        """Vosk's words so far, shown in grey: the same rules as Whisper's live words."""
        if self._echo_near() or self.stopped:
            return
        woke, rest = split_wake(said)
        if not woke and rest and rest[0] in w.KAIRU_LIKE:  # the small model's own spellings of "Kairu"
            woke, rest = True, [word for word in rest[1:] if word not in fastlane.WAKE_WORDS]
        if not self.session and not woke:
            return  # outside a session, nothing is shown until it begins with "Kairu"
        text = w.clean(rest)
        if not text or w.is_yes_or_digits(text):
            return
        if text != self._shown_live:
            self._shown_live = text
            events.append({"hearing": text})

    def _fast_closing(self, events: list[dict]) -> None:
        """0.2 s of quiet: the grammar recognizer's words. A quick order, sure, and (with your-voice-only) yours: sent now."""
        marker = (self._utterance_no, self.gate.loud_frames)
        if self._fast_closed == marker:
            return  # once per pause; again only if you speak again
        self._fast_closed = marker
        found = self.fast.closing_words()
        if self._echo_near() or self.stopped:
            return
        text = fastlane.quick_order(found, self.session)
        if not text or (self.fast.voiceprint is not None and self.fast.voice() != "yours"):
            return  # not quick, not sure, or not your voice: the whole utterance decides, as before
        self._send_early(self._utterance_no, text, events)

    def _send_early(self, number: int, text: str, events: list[dict]) -> None:
        if not self.session:
            self.session = True
            events.append({"wake": True, "alone": False})
        self.breath += 1
        self.last_word = self.clock
        self._early = (number, text)
        events.append({"order": text, "breath": self.breath})  # quick: it starts as you finish speaking

    # --- live words, while you speak (voice.live_caption_every) --------------------------------------

    def _live_due(self) -> bool:
        """Time for another look at what you have said so far: you are speaking, long enough to be a word, the last look is
        back, no whole utterance is waiting for Whisper (it always goes first), and Kairu is not speaking. While you speak,
        every live_every; once you have been quiet QUICK_QUIET, one closing look at once (again only if you speak again)."""
        if self.fast is not None:
            return False  # the fast lane gives the live words; Whisper stays free for the whole utterance
        if not (self.live_every and self.gate.speaking and not self._live_busy and not self._waiting
                and self.gate.loud_frames >= LEAST_SPEECH_FRAMES and not self._echo_near()):
            return False
        if self.gate.quiet >= QUICK_QUIET:
            return not (self._closing and self._closing[:2] == [self._utterance_no, self.gate.loud_frames])
        return self.gate.quiet == 0 and self.clock - self._live_at >= self.live_every - 1e-6  # Whisper free for the closing look

    def _closing_is_whole(self, number: int) -> bool:
        """The closing look had all of this utterance's words: it ended by a pause and nothing loud came after the look."""
        return bool(self._closing) and self._closing[0] == number and self.gate.ended_by_pause \
            and self._closing[1] == self.gate.ended_loud

    @staticmethod
    def quick(text: str) -> bool:
        """A short, harmless order that may start on the closing look (QUICK_ORDER), never one with more after it."""
        return bool(QUICK_ORDER.fullmatch(text)) and not NOT_QUICK & set(text.split())

    def _echo_near(self) -> bool:
        """voice.barge_in: Kairu is speaking, or stopped only moments ago (what is heard may still be its echo)."""
        return bool(self._echo) and self.clock <= self._echo[1] + END_CHUNKS * 0.1

    def _live(self, number: int, closing: bool, heard: Heard, events: list[dict]) -> None:
        """Whisper's words for what you have said so far: shown in grey. Only on the closing look, and only a quick order
        Whisper is sure of, is it sent at once; anything else waits for the whole utterance."""
        if number != self._utterance_no or not self.gate.speaking or self._echo_near() or self.stopped:
            return  # it came back after you stopped (the whole utterance is with Whisper now), or Kairu is speaking
        woke, said = split_wake(heard.text)
        if not self.session and not (woke and heard.sure):
            return  # outside a session, nothing is shown until Whisper is sure it began with "Kairu"
        text = w.clean(said)
        if not text or w.is_yes_or_digits(text):
            return  # nothing yet, or a spoken yes or PIN: never shown
        if text != self._shown_live:
            self._shown_live = text
            events.append({"hearing": text})
        if closing and heard.sure and self.quick(text) and not w.unclear(text, 1.0) and not w.is_stop(text):
            self._send_early(number, text, events)

    def _clear_live(self, events: list[dict]) -> None:
        if self._shown_live:
            self._shown_live = ""
            events.append({"hearing": ""})

    # --- Whisper, in its own thread ------------------------------------------------------------------

    def _hearing(self) -> None:
        while (work := self._work.get()) is not None:
            if work[0] == "live":
                self._results.put(("live", (work[1], work[3]), self._heard(work[2])))
            else:
                self._results.put(("heard", self._heard(work[1]), (time.time(), work[2])))

    def _heard(self, utterance: bytes) -> Heard:
        try:
            return self.hear(self.gate.clean(utterance))  # your words, with the room turned down (SpeechGate.clean)
        except Exception as error:  # Whisper failing on one utterance must not end the listener
            print(f"voice.listen: Whisper could not hear that ({type(error).__name__})", file=sys.stderr, flush=True)
            return Heard("", False)

    def _collect(self, events: list[dict]) -> None:
        while not self.stopped:
            try:
                kind, first, second = self._results.get_nowait()
            except queue.Empty:
                return
            if kind == "live":
                self._live_busy = False
                (number, closing), heard = first, second
                if closing and self._closing and self._closing[0] == number:
                    self._closing[2] = heard
                if self._final_from_look == number:  # you had stopped: this look was the whole utterance
                    self._final_from_look = None
                    self._final(heard, time.time(), number, events)
                else:
                    self._live(number, closing, heard, events)
                continue
            self._final(first, *second, events)

    def _final(self, heard: Heard, at: float, number: int, events: list[dict]) -> None:
        self._waiting -= 1
        self.heard_at = at
        early, self._early = (self._early[1] if self._early and self._early[0] == number else None), None
        voice = self._voices.pop(number, "unchecked")
        lips = self._lips.pop(number, "unchecked")
        if lips in ("lips still", "no face") and not (self.fast is not None and self.fast.voiceprint is not None):
            voice = lips  # the camera decides when your voice print doesn't
        elif lips in ("lips still", "no face") and voice == "yours":
            voice = lips  # your voice, but your lips didn't move: a recording, or someone who sounds like you
        if voice in ("lips still", "no face") or (self.fast is not None and self.fast.voiceprint is not None and voice != "yours"):
            woke, said = split_wake(heard.text)
            if not (w.is_stop(w.clean(said)) and (self.session or woke)):  # "Kairu, stop" works from anyone
                if woke or self.session:
                    events.append({"not_you": voice})  # never an order, a wake or an answer
                self._clear_live(events)
                self._shown_live = ""
                return
        before = len(events)
        self._utterance(heard, events, early)
        if not any("heard" in event for event in events[before:]):
            self._clear_live(events)  # the whole utterance showed nothing (no "Kairu", Kairu's echo, a PIN): grey words go
        self._shown_live = ""  # "heard" has replaced them

    # --- what was heard, made into events, the same way as Vosk's ----------------------------------------

    def _utterance(self, heard: Heard, events: list[dict], early: str | None = None) -> None:
        spoken = self._echoing()
        if spoken is not None:  # Kairu was speaking (voice.barge_in)
            words = tokens(heard.text)
            if not words or sum(word in spoken for word in words) >= ECHO_SHARE * len(words):
                return  # Kairu's own voice from the speakers: never an order, never shown
            first, _ = split_wake(heard.text)
            if heard.sure and (first or len(words) >= 2 or words[0] in BARGE_WORDS):
                events.append({"barge": True})  # you talked over Kairu: the bar ends voice.speak
                if len(words) <= 3 and set(words) <= BARGE_WORDS - {"stop", "no"}:
                    return  # "wait", "hold on": only to stop Kairu talking, never an order ("stop" is still the stop)
        woke, said = split_wake(heard.text)
        if not said and not woke:
            return
        self.breath += 1
        self.last_word = self.clock
        if not self.session and woke and not heard.sure and not said:
            # "Kairu" alone, and Whisper not quite sure: open a short window (REPLY_SECONDS) and say "Go ahead". Nothing it
            # half-heard ever becomes an order: only what you say next does, and silence closes it again.
            self.session = True
            self._reply_from, self._reply_seconds = self.clock, REPLY_SECONDS
            events.append({"wake": True, "alone": True})
            return
        if not self.session and (not woke or not heard.sure):
            return  # no "Kairu" (or Whisper not sure it heard one), no session: dropped, never shown or kept
        if woke and not self.session:
            self.session = True
            events.append({"wake": True, "alone": not w.clean(said)})
        text = w.clean(said)
        if not text:
            return
        if not w.is_yes_or_digits(text):
            events.append({"heard": text})  # what you said, in the bar's words line; never a PIN said aloud
        if early is not None:  # its quick order went at the closing look
            if text == early:
                return  # already started: never twice
            if text.startswith(early + " "):  # you said more after all: only the rest
                text = re.sub(r"^(?:and then|and|then)\s+", "", text[len(early):].strip())
                if not text:
                    return
        asked, self._asked = self._asked, None
        if w.is_stop(text):
            self.stopped, self.session = True, False
            events.append({"stop": True})
        elif w.is_thanks(text):
            self.session = False
            events.append({"thanks": True})
        elif w.is_yes_or_digits(text):
            if asked and self.clock - asked[1] < ASKED_SECONDS and text.split()[0] not in ("no", "nope"):
                events.append({"unclear": w.say_it_again(asked[0])})  # a spoken yes is still never an order
            else:
                events.append({"ignored": "yes or digits"})
        elif question := w.unclear(text, 1.0 if heard.sure else 0.0):
            instead = w.asked_instead(text)  # "Did you mean 30?", "Did you mean set the volume to 30?"
            if instead and question == instead[0]:
                self._asked = (instead[1], self.clock)
            events.append({"unclear": question})
        else:
            events.append({"order": text, "breath": self.breath})
