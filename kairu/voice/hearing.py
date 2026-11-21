"""Hearing: sound in, events out. Two recognizers on the same sound, both from one small offline model (Vosk).

    words    the whole vocabulary: what you say, word by word, with a time and a confidence for each word
    wake     a tiny grammar: the words the model hears for "Kairu" ("cairo", "carew", "kai", "kai ru"), "stop", and [unk]
             for everything else. "Kairu" is not in the model's vocabulary, so this is how it is recognized.

An utterance is what you say between pauses (about half a second). When one ends, the wake recognizer says whether it began
with "Kairu", and where "Kairu" ended; the words after that are the order. Outside a session, an utterance without "Kairu"
is dropped at once: nothing is shown, kept or sent. "Kairu" starts a session; in a session every utterance is an order,
until "thank you", or 30 seconds without a word.

Events, in order (each a small dict): {"heard": live words}, {"talking": bool}, {"wake": True, "alone": no order with it},
{"order": text, "breath": utterance number}, {"unclear": the one short question}, {"ignored": "yes or digits"},
{"thanks": True}, {"quiet": True}, {"stop": True}. "Kairu, stop" (or "stop" in a session) is heard by the wake
recognizer at the end of the utterance; after it, nothing more is heard.

While Kairu speaks, the listener feeds silence instead of the sound from the mic, so Kairu never hears itself, and the two
recognizers keep the same clock (resetting one would put its word times out of step with the other's).

Sound is only ever in memory, a tenth of a second at a time, and is never kept: not here, not on disk.
"""

import json

from kairu.voice import words as w

RATE = 16000
SESSION_SECONDS = 30.0
REPLY_SECONDS = 8.0  # after Kairu asks its follow-up question: this long for your answer, then quiet  # a session with no words for this long ends quietly
WAKE_GAP = 0.1  # seconds between the parts of "Kairu" that still count as one word
KAIRU_SECONDS = 2.0  # "Kairu", said slowly, is never longer than this
LATE_STOP = 2.0  # "stop" this soon after a lone "Kairu" is "Kairu, stop", said with a pause
TAIL_SECONDS = 0.35  # words this close after "Kairu" may be the end of "Kairu" itself ("... to you")
ECHO_SECONDS = 1.5  # a short utterance this soon after "Kairu", made only of such words, is the rest of "Kairu"


def recognizers(model, rate: int = RATE):
    """The two recognizers for a vosk.Model: (words, wake)."""
    import vosk
    heard = vosk.KaldiRecognizer(model, rate)
    wake = vosk.KaldiRecognizer(model, rate, json.dumps(w.WAKE_GRAMMAR))
    for recognizer in (heard, wake):
        recognizer.SetWords(True)
    return heard, wake


def _mid(word: dict) -> float:
    return (word["start"] + word["end"]) / 2


def wake_end(wake_words: list[dict], starts_at: float) -> float | None:
    """Where "Kairu" ends, if the utterance that starts at `starts_at` begins with it; otherwise None."""
    lead = sorted((word for word in wake_words if word["end"] > starts_at - 0.3), key=lambda word: word["start"])
    if not lead or lead[0]["word"] not in w.WAKE_START or lead[0]["start"] > starts_at + 0.5:
        return None
    first, end = lead[0], lead[0]["end"]
    for index in range(1, len(lead)):
        word = lead[index]
        if word["start"] - end > WAKE_GAP or word["end"] - first["start"] > KAIRU_SECONDS:
            break
        if word["word"] in w.WAKE_PARTS:
            end = word["end"]
            continue
        if word["word"] != "[unk]":
            break
        later = lead[index + 1] if index + 1 < len(lead) else None
        if later and later["word"] in w.WAKE_PARTS and later["start"] - word["end"] <= WAKE_GAP:
            end = word["end"]
            continue  # "kai [unk] carew": all of it is "Kairu"
        if first["word"] == "kai" and word["end"] - word["start"] <= 0.7 and (later is None or later["start"] - word["end"] >= 0.2):
            end = word["end"]  # "kai" and a short sound after it, then a pause: the rest of "Kairu"
        break
    return end


def _after_kairu(said: list[dict], ends: float) -> list[dict]:
    """The words after "Kairu", without what may still be the end of it."""
    order = [word for word in said if _mid(word) > ends]
    for _ in range(2):
        if order and order[0]["word"] in w.KAIRU_TAIL and order[0]["start"] - ends < TAIL_SECONDS:
            ends = order.pop(0)["end"]
    return order


class Hearing:
    def __init__(self, model=None, rate: int = RATE, made=None):
        self.heard, self.wake = made or recognizers(model, rate)
        self.rate = rate
        self.session = False
        self.stopped = False
        self.clock = 0.0  # seconds of sound heard since this started (pauses not counted)
        self.last_word = 0.0
        self._reply_from, self._reply_seconds = None, REPLY_SECONDS
        self.breath = 0
        self.talking = False
        self._wake_words: list[dict] = []  # the wake recognizer's words for the utterance going on
        self._lone_kairu_at = None
        self._kairu_ended = None  # where the last "Kairu" ended, on the recognizers' clock
        self._shown = ""

    # --- what the listener asks ----------------------------------------------------------------------

    def start_session(self) -> list[dict]:
        """Ctrl+Alt+V or the mic button: listen now, without "Kairu"."""
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
        """A piece of sound (16-bit mono at RATE), and what it led to."""
        if self.stopped or not sound:
            return []
        self.clock += len(sound) / (2 * self.rate)
        events: list[dict] = []
        if self.wake.AcceptWaveform(sound):
            self._wake_result(json.loads(self.wake.Result()), events)
        if self.stopped:
            return events
        if self.heard.AcceptWaveform(sound):
            self._utterance(json.loads(self.heard.Result()), events)
        else:
            self._partial(json.loads(self.heard.PartialResult()).get("partial", ""), events)
        if self.session and not self.talking and self.clock - self.last_word > self._quiet_after():
            self.session = False
            events.append({"quiet": True})
        return events

    # --- the wake recognizer -------------------------------------------------------------------------

    def _wake_result(self, result: dict, events: list[dict]) -> None:
        found = result.get("result", [])
        self._wake_words += found
        tokens = [word["word"] for word in found]
        if not tokens:
            return
        if tokens[-1] == "stop" and len(tokens) > 1 and tokens[0] in w.WAKE_START and all(t in w.WAKE_PARTS or t == "[unk]" for t in tokens[:-1]):
            self._stop(events)  # "Kairu, stop"
        elif tokens == ["stop"] and (self.session or (self._lone_kairu_at is not None and found[0]["start"] - self._lone_kairu_at < LATE_STOP)):
            self._stop(events)  # "stop" in a session, or "Kairu ... stop"
        elif tokens[0] in w.WAKE_START and all(t in w.WAKE_PARTS or t == "[unk]" for t in tokens) and len(tokens) <= 3:
            self._lone_kairu_at = found[-1]["end"]

    def _stop(self, events: list[dict]) -> None:
        self.stopped, self.session = True, False
        events.append({"stop": True})

    # --- the word recognizer -------------------------------------------------------------------------

    def _partial(self, text: str, events: list[dict]) -> None:
        talking = bool(text)
        if talking != self.talking:
            self.talking = talking
            events.append({"talking": talking})
        if not talking:
            return
        self.last_word = self.clock
        waking = False
        if not self.session:
            tokens = json.loads(self.wake.PartialResult()).get("partial", "").split() or [word["word"] for word in self._wake_words[-3:]]
            waking = bool(tokens) and tokens[0] in w.WAKE_START
        if self.session or waking:
            shown = w.shown(text.split(), strip_kairu=True)
            if shown != self._shown:
                self._shown = shown
                events.append({"heard": shown})

    def _utterance(self, result: dict, events: list[dict]) -> None:
        said = result.get("result", [])
        if self.talking:
            self.talking = False
            events.append({"talking": False})
        self._shown = ""
        closing = json.loads(self.wake.FinalResult())  # the wake recognizer ends its utterance here too, so the two agree
        self._wake_result(closing, events)
        wake_words, self._wake_words = self._wake_words, []
        if self.stopped or not said:
            return
        self.breath += 1
        self.last_word = self.clock
        ends = wake_end(wake_words, said[0]["start"])
        order = said if ends is None else _after_kairu(said, ends)
        if ends is None and self._kairu_ended is not None and said[0]["start"] - self._kairu_ended < ECHO_SECONDS                 and len(said) <= 3 and all(word["word"] in w.KAIRU_TAIL or word["word"] in w.KAIRU_LIKE for word in said):
            return  # the rest of "Kairu", heard as words of its own ("to you")
        if ends is not None:
            self._kairu_ended = ends
        if ends is None and not self.session:
            return  # no "Kairu", no session: dropped, never shown or kept
        if ends is not None and not self.session:
            self.session = True
            events.append({"wake": True, "alone": not order})
        if not order:
            return
        text = w.clean([word["word"] for word in order])
        if not text:
            return
        sure = sum(word.get("conf", 1.0) for word in order) / len(order)
        if w.is_stop(text):
            self._stop(events)
        elif w.is_thanks(text):
            self.session = False
            events.append({"thanks": True})
        elif w.is_yes_or_digits(text):
            events.append({"ignored": "yes or digits"})
        elif question := w.unclear(text, sure):
            events.append({"unclear": question})
        else:
            events.append({"order": text, "breath": self.breath})
