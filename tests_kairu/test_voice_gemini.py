"""Gemini hearing (voice.hearing: gemini, VOICE.md): each utterance goes once to Gemini; its words are only words; the offline
Whisper hears whenever Gemini can't. No network here: the requests go to a stand-in."""

import base64
import io
import json
import wave

import pytest

from kairu import config, executors
from kairu.voice import gemini
from kairu.voice.whisper import Heard

SOUND = bytes(16000 * 2)  # one second of 16-bit silence at 16 kHz


def answer(text: str) -> bytes:
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()


class Gate:
    def __init__(self, *replies):
        self.replies, self.asked = list(replies), []

    def __call__(self, url, key, data, timeout):
        self.asked.append((url, key, json.loads(data)))
        return self.replies.pop(0)


class Offline:
    def __init__(self):
        self.heard = 0

    def __call__(self, sound):
        self.heard += 1
        return Heard("open notepad", True, -0.3)


def test_one_utterance_goes_to_gemini_as_a_wav_with_the_key_in_its_header_and_comes_back_as_words():
    post = Gate((200, answer('"Kairu, what\'s the weather in Hyderabad?"')))
    heard = gemini.GeminiHearing("unused", post=post, key="AIza" + "x" * 35)(SOUND)
    assert heard == Heard("Kairu, what's the weather in Hyderabad?", True)
    url, key, body = post.asked[0]
    assert url == f"https://{gemini.HOST}/v1beta/models/{gemini.MODELS[0]}:generateContent" and key.startswith("AIza")
    sent = body["contents"][0]["parts"][1]["inline_data"]
    assert sent["mime_type"] == "audio/wav"
    with wave.open(io.BytesIO(base64.b64decode(sent["data"]))) as file:
        assert (file.getframerate(), file.getnchannels(), file.getsampwidth(), file.getnframes()) == (16000, 1, 2, 16000)
    assert "Kairu" in body["contents"][0]["parts"][0]["text"] and "background" in body["contents"][0]["parts"][0]["text"]


def test_nothing_said_is_no_words_and_never_sure():
    for said in ("", "Nothing", "(no speech)", "  "):
        assert gemini.GeminiHearing("unused", post=Gate((200, answer(said))), key="k" * 39)(SOUND) == Heard("", False)


def test_a_model_name_that_is_not_served_moves_on_to_the_next_and_is_remembered():
    post = Gate((404, b"{}"), (200, answer("open edge")), (200, answer("open chrome")))
    hearing = gemini.GeminiHearing("unused", post=post, key="k" * 39)
    assert hearing(SOUND).text == "open edge"
    assert hearing(SOUND).text == "open chrome"
    used = [url.split("/models/")[1].split(":")[0] for url, _, _ in post.asked]
    assert used == [gemini.MODELS[0], gemini.MODELS[1], gemini.MODELS[1]]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_when_gemini_refuses_the_offline_whisper_hears_and_gemini_rests_a_minute(status):
    now, offline = [0.0], Offline()
    post = Gate((status, b"{}"), (200, answer("open edge")))
    hearing = gemini.GeminiHearing("unused", post=post, key="k" * 39, fallback=lambda: offline, clock=lambda: now[0])
    assert hearing(SOUND).text == "open notepad" and offline.heard == 1  # this utterance is still heard
    assert hearing(SOUND).text == "open notepad" and len(post.asked) == 1  # resting: not asked again
    now[0] += gemini.REST_SECONDS
    assert hearing(SOUND).text == "open edge"


def test_gemini_out_of_reach_or_no_key_is_the_offline_whisper_too(tmp_path):
    def gone(*args):
        raise OSError("no network")
    offline = Offline()
    assert gemini.GeminiHearing("unused", post=gone, key="k" * 39, fallback=lambda: offline)(SOUND).text == "open notepad"
    no_key = gemini.GeminiHearing(tmp_path, post=Gate(), fallback=lambda: offline)
    assert no_key(SOUND).text == "open notepad" and "kairu provider add gemini" in no_key.last_problem


def test_the_offline_whisper_is_loaded_only_when_it_is_needed():
    made = []
    hearing = gemini.GeminiHearing("unused", post=Gate((200, answer("hi"))), key="k" * 39,
                                   fallback=lambda: made.append(1) or Offline())
    hearing(SOUND)
    assert made == []


def test_voice_hearing_in_config_yaml(tmp_path):
    def load(voice: str):
        path = tmp_path / "config.yaml"
        path.write_text("voice:\n" + voice, encoding="utf-8")
        return config.load(path)
    assert load("  enabled: false\n").voice_hearing == "local"
    cfg = load("  hearing: gemini\n  gemini_model: gemini-flash-lite-latest\n")
    assert (cfg.voice_hearing, cfg.voice_gemini_model) == ("gemini", "gemini-flash-lite-latest")
    for bad in ("  hearing: cloud\n", "  gemini_model: gpt-4o\n", "  hearing: true\n"):
        with pytest.raises(config.ConfigError):
            load(bad)


def test_the_listener_gets_the_setting_only_from_guardian():
    assert {"voice_hearing", "voice_gemini_model"} <= set(executors.EXECUTORS["voice.listen"].supplied)


def test_the_listener_hears_with_gemini_and_keeps_whisper_for_when_it_cannot(monkeypatch, tmp_path):
    from kairu.voice import listen, whisper
    loaded, warmed = [], []
    monkeypatch.setattr(whisper, "transcriber", lambda place: loaded.append(place) or Offline())
    monkeypatch.setattr(gemini.Connection, "warm", lambda self: warmed.append(1))
    hearing = listen._gemini_hearing(tmp_path / "model", str(tmp_path), "gemini-flash-latest")
    assert isinstance(hearing, whisper.WhisperHearing) and isinstance(hearing.hear, gemini.GeminiHearing)
    assert hearing.hear.models[0] == "gemini-flash-latest" and loaded == []  # Whisper not loaded until it is needed
    assert warmed == [1]  # the connection to Gemini is opened before the first sentence
    hearing.close()


def test_a_gemini_key_can_be_added_but_the_brain_asks_gemini_only_if_you_list_it(tmp_path):
    from kairu.brain.providers import PROVIDERS
    assert "gemini" in config.PROVIDER_NAMES and "gemini" in PROVIDERS
    path = tmp_path / "config.yaml"
    path.write_text("voice:\n  hearing: gemini\n", encoding="utf-8")
    assert "gemini" not in config.load(path).brain_providers


def test_one_connection_is_kept_for_every_sentence_and_opened_again_if_google_closed_it(monkeypatch):
    made = []

    class Response:
        status = 200

        def read(self):
            return answer("hi")

    class Fake:
        def __init__(self, host, timeout):
            self.host, self.timeout, self.sent, self.fail_next = host, timeout, 0, len(made) == 0 and False
            made.append(self)

        def connect(self):
            pass

        def request(self, method, path, body, headers):
            assert method == "POST" and path.startswith("/v1beta/models/") and headers["x-goog-api-key"] == "k" * 39
            if getattr(self, "broken", False):
                raise ConnectionResetError()
            self.sent += 1

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(gemini.http.client, "HTTPSConnection", Fake)
    hearing = gemini.GeminiHearing("unused", key="k" * 39)
    hearing.warm()
    assert hearing(SOUND).text == "hi" and hearing(SOUND).text == "hi"
    assert len(made) == 1 and made[0].sent == 2  # one handshake for both sentences
    made[0].broken = True
    assert hearing(SOUND).text == "hi" and len(made) == 2  # closed by Google while idle: one fresh connection, same sentence
