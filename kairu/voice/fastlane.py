"""The fast lane (voice.fast_orders, the owner's "it must work fast, like Claude's mic", 15 Nov 2026), and your-voice-only
(voice.only_my_voice): the small offline Vosk model, beside Whisper, on the same sound.

Whisper hears well but slowly on a laptop CPU: it always works on a 30-second window, so each look takes about a second
with small.en, however short the order. Vosk hears as the sound comes, a tenth of a second at a time, for almost no CPU. So:

    words    Vosk with its whole vocabulary: the grey live words in the bar, word by word as you speak (instant), and,
             with the speaker model, a voice print of who is speaking (an x-vector: 128 numbers, never sound).
    quick    Vosk with a tiny grammar (QUICK_GRAMMAR): only "Kairu", the quick order words, app names and numbers, and
             [unk] for anything else. After 0.2 s of quiet its words decide whether this is a quick order.

A quick order (kairu/voice/whisper.py QUICK_ORDER: open an app, volume, brightness, mute, what's open) goes at once when
every word is in the grammar (no [unk]: nothing else was said), Vosk is sure of each word (SURE_WORD), outside a session it
began with "Kairu", and, with your-voice-only on, the voice is yours. Whisper still hears the whole utterance as before, for
everything else and to put right what Vosk heard; the order is never sent twice (whisper.py "early").

Your voice (kairu/voice/myvoice.py): `kairu voice enroll` keeps the average voice print of a few sentences you say, in
data/voice/my-voice.json. With voice.only_my_voice on, an utterance whose voice print is not close enough to it (MATCH) is
never an order, a wake or an answer; "Kairu, stop" always works, from anyone. Too short to tell is not yours.

Nothing here writes, keeps or sends sound or words; the recognizers live in the listener's memory only.
"""

import json
import math

from kairu.voice import words as w

SURE_WORD = 0.85  # Vosk's own confidence for each word of a quick order
MATCH = 0.5  # cosine similarity of an utterance's voice print to yours, from which it is yours (`kairu voice enroll` shows yours)
# Laptop test, 16 Nov 2026: "most of the time it says I couldn't tell it was you". Vosk counts only the frames it is sure are
# speech, so a short order ("Kairu, open Notepad") often had fewer than the 60 asked for, and was never even compared.
LEAST_FRAMES = 30  # voice-print frames (10 ms each) below which the voice is too short to tell (was 60)
SHORT_FRAMES = 80  # under this, the voice print comes from little sound and wavers more, even for you:
MATCH_SHORT = 0.42  # so a short order is yours from this line (someone else's voice is usually far below both)

WAKE_WORDS = ("cairo", "carew", "kai", "ru", "rue")  # how the small model hears "Kairu" (kairu/voice/words.py)
GREETINGS = ("hey", "okay")
QUICK_VERBS = ("open", "launch", "start", "set", "turn", "the", "volume", "brightness", "to", "up", "down", "mute", "unmute",
               "what's")
QUICK_APPS = ("edge", "microsoft", "chrome", "google", "firefox", "notepad", "calculator", "explorer", "file", "word",
              "excel", "powerpoint", "outlook", "teams", "spotify", "paint", "camera", "photos", "calendar", "mail", "store",
              "zoom", "discord", "telegram", "whatsapp", "code", "visual", "studio", "music", "maps", "clock", "terminal",
              "media", "player", "snipping", "tool", "settings", "brave", "opera", "vlc", "steam", "obs", "notion", "slack")
NUMBERS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty",
           "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "percent")
QUICK_GRAMMAR = sorted(set(WAKE_WORDS + GREETINGS + QUICK_VERBS + QUICK_APPS + NUMBERS)) + ["[unk]"]


def recognizers(model, speaker=None, rate: int = 16000):
    """(words, quick) for a vosk.Model; with a vosk.SpkModel, `words` also gives a voice print."""
    import vosk
    heard = vosk.KaldiRecognizer(model, rate)
    quick = vosk.KaldiRecognizer(model, rate, json.dumps(QUICK_GRAMMAR))
    for recognizer in (heard, quick):
        recognizer.SetWords(True)
    if speaker is not None:
        heard.SetSpkModel(speaker)
    return heard, quick


def cosine(one, other) -> float:
    top = sum(a * b for a, b in zip(one, other))
    size = math.sqrt(sum(a * a for a in one)) * math.sqrt(sum(b * b for b in other))
    return top / size if size else 0.0


def quick_order(found: list[dict], session: bool) -> str | None:
    """The quick order in the grammar recognizer's words, or None. Strict: every word sure, nothing else said."""
    if not found or any(word.get("word") == "[unk]" or float(word.get("conf", 0)) < SURE_WORD for word in found):
        return None
    said = [word["word"] for word in found]
    while said and said[0] in GREETINGS:
        said.pop(0)
    woke = bool(said) and said[0] in ("cairo", "carew", "kai")
    while said and said[0] in WAKE_WORDS:
        said.pop(0)
    if not session and not woke:
        return None  # outside a session, an order must begin with "Kairu"
    text = w.clean(said)
    from kairu.voice.whisper import WhisperHearing
    return text if text and WhisperHearing.quick(text) and not w.unclear(text, 1.0) else None


class FastLane:
    """The two Vosk recognizers for one utterance at a time, driven by the speech gate (kairu/voice/whisper.py)."""

    def __init__(self, words, quick, voiceprint: list[float] | None = None):
        self.words, self.quick, self.voiceprint = words, quick, voiceprint
        self._said = ""  # words of the pieces of this utterance Vosk has already closed
        self._quick_words: list[dict] = []
        self._prints: list[tuple[list[float], int]] = []

    def begin(self, sounds) -> str:
        """A new utterance: from its first sound (the gate keeps 0.3 s from before it, so "Kairu" is not cut)."""
        self.words.Reset()
        self.quick.Reset()
        self._said, self._quick_words, self._prints = "", [], []
        caption = ""
        for sound in sounds:
            caption = self.feed(sound)
        return caption

    def feed(self, sound: bytes) -> str:
        """More of the utterance; what Vosk has heard of it so far (the grey live words)."""
        if self.quick.AcceptWaveform(sound):  # Vosk's own end of a piece: kept, the closing look adds the rest
            self._quick_words += json.loads(self.quick.Result()).get("result", [])
        if self.words.AcceptWaveform(sound):
            self._piece(json.loads(self.words.Result()))
            return self._said
        partial = json.loads(self.words.PartialResult()).get("partial", "")
        return f"{self._said} {partial}".strip()

    def closing_words(self) -> list[dict]:
        """After 0.2 s of quiet: everything the grammar recognizer heard of this utterance, with Vosk's confidence."""
        found = self._quick_words + json.loads(self.quick.FinalResult()).get("result", [])
        self._quick_words = found  # if you speak on, these stay the start of the utterance
        self._piece(json.loads(self.words.FinalResult()))  # its voice print so far
        return found

    def end(self) -> str:
        """The utterance ended: who spoke it (voice())."""
        self._piece(json.loads(self.words.FinalResult()))
        verdict = self.voice()
        self.words.Reset()
        self.quick.Reset()
        self._said, self._quick_words, self._prints = "", [], []
        return verdict

    def drop(self) -> None:
        self.words.Reset()
        self.quick.Reset()
        self._said, self._quick_words, self._prints = "", [], []

    def _piece(self, result: dict) -> None:
        text = str(result.get("text", "")).strip()
        if text:
            self._said = f"{self._said} {text}".strip()
        vector, frames = result.get("spk"), int(result.get("spk_frames", 0) or 0)
        if isinstance(vector, list) and vector and frames > 0:
            self._prints.append(([float(value) for value in vector], frames))

    def voice(self) -> str:
        """"yours", "not yours", "too short" (to tell), or "unchecked" (your-voice-only is off)."""
        if self.voiceprint is None:
            return "unchecked"
        frames = sum(count for _, count in self._prints)
        if frames < LEAST_FRAMES:
            return "too short"
        size = len(self._prints[0][0])
        mean = [sum(vector[i] * count for vector, count in self._prints) / frames for i in range(size)]
        line = MATCH if frames >= SHORT_FRAMES else MATCH_SHORT
        return "yours" if cosine(mean, self.voiceprint) >= line else "not yours"
