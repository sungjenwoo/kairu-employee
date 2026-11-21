"""Gemini hearing (voice.hearing: gemini; the owner's GO of 16 Nov 2026, VOICE.md "Gemini hearing").

The laptop's Whisper took 6 s a sentence with little memory free and mixed in people talking nearby. With this on, each
utterance the speech gate ends (the room already turned down, SpeechGate.clean) is sent once to Google's Gemini API, which
writes down what the nearest speaker said; Kairu's own rules then decide what it means, exactly as with Whisper's words.

    GeminiHearing(data_dir, model, fallback)   a hear(sound) -> Heard, like kairu.voice.whisper.Whisper

What leaves the PC: that one utterance's sound (16-bit, 16 kHz, as a WAV in memory), to generativelanguage.googleapis.com
only, with the key from `kairu provider add gemini` (sealed on this PC). Nothing is written to disk. The words that come
back are only words: a spoken "yes" or PIN is still never an approval, and every order still goes to the task core and
Guardian. If Gemini can't be reached, refuses the key or is at its free limit, the utterance is heard by the offline
Whisper instead (loaded only then), and Gemini is left alone for a minute. Standard library only.
"""

import base64
import http.client
import io
import json
import sys
import time
import urllib.error
import urllib.request
import wave

from kairu.voice.whisper import RATE, Heard

HOST = "generativelanguage.googleapis.com"
MODELS = ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.5-flash")
SECONDS = 6.0  # one utterance's answer, at most
REST_SECONDS = 60.0  # after a failure, the offline Whisper hears for this long before Gemini is tried again
MOST_SECONDS_OF_SOUND = 15
PROMPT = ("Transcribe the speech in this audio exactly, in English. The person is talking to a laptop assistant called "
          "Kairu: write that name as \"Kairu\". Write only the words of the main speaker, the one closest to the microphone; "
          "leave out other people talking in the background, a TV, music and noise. If there is no clear speech, answer "
          "with nothing at all. Answer with the words only: no quotes, labels or notes.")


class GeminiProblem(Exception):
    pass


def wav(sound: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(sound[:MOST_SECONDS_OF_SOUND * RATE * 2])
    return out.getvalue()


def body(sound: bytes) -> dict:
    return {"contents": [{"role": "user", "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav(sound)).decode("ascii")}}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 120}}


def words_of(answer: dict) -> str:
    """The text Gemini wrote, tidied: one line, no quotes around it."""
    parts = ((answer.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = " ".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
    text = " ".join(text.split()).strip("\"'“”")
    return "" if text.lower() in ("nothing", "(nothing)", "[silence]", "silence", "no speech", "(no speech)") else text


class Connection:
    """One HTTPS connection to Gemini, kept open between sentences: a new one costs a TLS handshake (0.3-0.5 s from India)
    on every sentence. Opened again after any problem."""

    def __init__(self, host: str = HOST):
        self.host, self.connection = host, None

    def warm(self) -> None:
        """Open it now (when the mic comes on), so the first sentence doesn't pay for the handshake."""
        try:
            self._open(SECONDS).connect()
        except OSError:
            self.close()

    def _open(self, timeout: float):
        if self.connection is None:
            self.connection = http.client.HTTPSConnection(self.host, timeout=timeout)
        return self.connection

    def __call__(self, url: str, key: str, data: bytes, timeout: float) -> tuple[int, bytes]:
        path = url.split(self.host, 1)[1]
        headers = {"x-goog-api-key": key, "Content-Type": "application/json", "User-Agent": "kairu-voice/1"}
        for attempt in (1, 2):  # a connection Google closed while idle: once more on a fresh one
            try:
                connection = self._open(timeout)
                connection.timeout = timeout
                connection.request("POST", path, body=data, headers=headers)
                response = connection.getresponse()
                return response.status, response.read()
            except (http.client.HTTPException, OSError):
                self.close()
                if attempt == 2:
                    raise
        raise OSError("unreachable")

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None


def _post(url: str, key: str, data: bytes, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "x-goog-api-key": key, "Content-Type": "application/json", "User-Agent": "kairu-voice/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class GeminiHearing:
    def __init__(self, data_dir, model: str = "", fallback=None, post=None, clock=time.monotonic, key=None):
        self.data_dir, self.clock = data_dir, clock
        self.post = post if post is not None else Connection()
        self.models = tuple(dict.fromkeys(([model] if model else []) + list(MODELS)))
        self.fallback_maker, self.fallback = fallback, None
        self.rest_until = 0.0
        self._key = key
        self.last_problem = ""

    def key(self) -> str:
        if self._key is None:
            from kairu.brain import keys
            found = keys.load(self.data_dir, "gemini")
            if not found:
                raise GeminiProblem("no Gemini key yet: `kairu provider add gemini`")
            self._key = found[0]
        return self._key

    def _offline(self, sound: bytes) -> Heard:
        if self.fallback is None:
            if self.fallback_maker is None:
                return Heard("", False)
            self.fallback = self.fallback_maker()
        return self.fallback(sound)

    def gemini(self, sound: bytes) -> Heard:
        data = json.dumps(body(sound)).encode("utf-8")
        for model in self.models:
            status, raw = self.post(f"https://{HOST}/v1beta/models/{model}:generateContent", self.key(), data, SECONDS)
            if status == 404:  # this model name isn't served (any more): the next one
                continue
            if status != 200:
                why = {400: "Gemini refused the request", 401: "Gemini refused the key", 403: "Gemini refused the key",
                       429: "Gemini is at its free limit"}.get(status, f"Gemini answered {status}")
                try:  # Google's own reason, in words (never the key)
                    detail = str(json.loads(raw.decode("utf-8")).get("error", {}).get("message", ""))[:200]
                except (ValueError, AttributeError):
                    detail = ""
                raise GeminiProblem(f"{why} ({model}){': ' + detail if detail else ''}")
            self.models = (model,) + tuple(name for name in self.models if name != model)  # remember the one that works
            text = words_of(json.loads(raw.decode("utf-8")))
            return Heard(text, bool(text), -0.2 if text else 0.0)
        raise GeminiProblem("none of Gemini's models answered")

    def __call__(self, sound: bytes) -> Heard:
        if self.clock() >= self.rest_until:
            try:
                heard = self.gemini(sound)
                self.last_problem = ""
                return heard
            except (GeminiProblem, OSError, ValueError, KeyError, IndexError) as problem:
                self.last_problem = str(problem) if isinstance(problem, GeminiProblem) else f"Gemini can't be reached ({type(problem).__name__})"
                print(f"voice: {self.last_problem}; the offline Whisper hears for a minute", file=sys.stderr, flush=True)
                self.rest_until = self.clock() + REST_SECONDS
        return self._offline(sound)

    def warm(self) -> None:
        warm = getattr(self.post, "warm", None)
        if warm:
            warm()

    def close(self) -> None:
        for part in (self.fallback, self.post):
            close = getattr(part, "close", None)
            if close:
                close()
