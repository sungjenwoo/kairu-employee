"""What was left of the Tenmin use case (handover of 15 Nov 2026), built on your GO of 15 Nov 2026:
the top hearing models (pinned), listening from the start, barge-in. Memory and "ask, then summarise" have their tests in
test_memory.py and test_ask_ai.py. Nothing here opens a microphone, a model or the network."""

import json

import pytest

from kairu import config as kairu_config
from kairu.voice import models
from kairu.voice.whisper import Heard, WhisperHearing

SHA = "a" * 64
COMMIT = "b" * 40


# --- the top hearing models: pinned like the others, never downloaded unpinned ----------------------------------------

def test_the_big_models_are_engines_but_not_set_up_until_pinned(tmp_path):
    for engine in ("whisper-large-v3-turbo", "whisper-distil-large-v3", "whisper-medium.en", "whisper-small.en"):
        assert engine in kairu_config.VOICE_ENGINES and engine in models.ENGINES
        key = models.WHISPER_ENGINES[engine]
        if key not in models.WHISPERS:
            assert "pin_whisper.py" in models.not_pinned(key)
            with pytest.raises(models.NotSetUp):
                models.whisper_ready(tmp_path, key)
            with pytest.raises(models.SetupError):
                models.setup_whisper(tmp_path, key, say=lambda line: None, opener=lambda *a, **k: 1 / 0)
    assert kairu_config.VOICE_ENGINES == models.ENGINES and models.ENGINES[0] == "whisper-base.en"


def _pins(tmp_path, **changes):
    entry = {"repo": models.BIG_REPOS["large-v3-turbo"], "commit": COMMIT,
             "files": [["config.json", SHA, 2000], ["model.bin", SHA, 1_600_000_000], ["preprocessor_config.json", SHA, 340]]}
    entry.update(changes)
    path = tmp_path / "whisper_pins.json"
    path.write_text(json.dumps({"large-v3-turbo": entry}), encoding="utf-8")
    return models._pinned(path)


def test_a_good_pin_makes_a_model_that_downloads_only_from_its_commit(tmp_path):
    whisper = _pins(tmp_path)["large-v3-turbo"]
    assert (whisper.repo, whisper.commit, whisper.mib > 1000) == ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", COMMIT, True)
    assert "preprocessor_config.json" in {name for name, *_ in whisper.files}  # large-v3 needs its 128 mel bins


@pytest.mark.parametrize("changes", [{"repo": "someone/else"}, {"commit": "main"}, {"files": [["model.bin", SHA, 5]]},
                                     {"files": [["config.json", "x" * 64, 1], ["model.bin", SHA, 1]]},
                                     {"files": [["config.json", SHA, 1], ["model.bin", SHA, 1], ["../evil", SHA, 1]]},
                                     {"files": [["config.json", SHA, 0], ["model.bin", SHA, 1]]}])
def test_a_wrong_pin_is_left_out(tmp_path, changes):
    assert _pins(tmp_path, **changes) == {}


def test_the_pin_tool_reads_hugging_face_only_and_hashes_the_small_files():
    import hashlib
    import io
    from tools import pin_whisper
    small = b'{"feature_size": 128}'
    answers = {
        "https://huggingface.co/api/models/Systran/faster-whisper-small.en/revision/main": json.dumps({"sha": COMMIT}).encode(),
        f"https://huggingface.co/api/models/Systran/faster-whisper-small.en/tree/{COMMIT}": json.dumps([
            {"type": "file", "path": "model.bin", "lfs": {"oid": SHA, "size": 483_000_000}},
            {"type": "file", "path": "config.json"}, {"type": "file", "path": ".gitattributes"},
            {"type": "file", "path": "README.md"}]).encode(),
        f"https://huggingface.co/Systran/faster-whisper-small.en/resolve/{COMMIT}/config.json": small,
    }

    class Response(io.BytesIO):
        def __init__(self, url):
            super().__init__(answers[url])
            self.url = url

        def geturl(self):
            return self.url

    pinned = pin_whisper.pin("small.en", opener=lambda url, timeout: Response(url))
    assert pinned == {"repo": "Systran/faster-whisper-small.en", "commit": COMMIT,
                      "files": [["config.json", hashlib.sha256(small).hexdigest(), len(small)], ["model.bin", SHA, 483_000_000]]}

    class Elsewhere(Response):
        def geturl(self):
            return "https://evil.example/x"

    with pytest.raises(SystemExit):
        pin_whisper.pin("small.en", opener=lambda url, timeout: Elsewhere(url))


# --- your two new voice settings ---------------------------------------------------------------------------------------

def _config(tmp_path, voice: str):
    path = tmp_path / "config.yaml"
    path.write_text(f"voice:\n  enabled: true\n{voice}guardian:\n  data_dir: data\n", encoding="utf-8")
    return kairu_config.load(path)


def test_listening_at_start_and_barge_in_are_off_unless_you_set_them(tmp_path):
    plain = _config(tmp_path, "")
    assert (plain.voice_listen_at_start, plain.voice_barge_in) == (False, False)
    on = _config(tmp_path, "  listen_at_start: true\n  barge_in: true\n  engine: whisper-large-v3-turbo\n")
    assert (on.voice_listen_at_start, on.voice_barge_in, on.voice_engine) == (True, True, "whisper-large-v3-turbo")
    with pytest.raises(kairu_config.ConfigError):
        _config(tmp_path, "  listen_at_start: yes please\n")


# --- barge-in: Kairu's own voice is left out, yours stops it -----------------------------------------------------------

@pytest.fixture
def hearing():
    heard = WhisperHearing(lambda sound: Heard("", False), background=False)
    heard.session = True
    heard.set_echo("Photosynthesis is how plants make food from sunlight. Want an example?")
    return heard


def _said(hearing, text, sure=True):
    events = []
    hearing._utterance(Heard(text, sure), events)
    return events


def test_kairus_own_voice_is_never_heard_as_an_order(hearing):
    assert _said(hearing, "photosynthesis is how plants make food") == []
    assert _said(hearing, "plants make food from sunlight want an example") == []


def test_talking_over_kairu_stops_it_and_a_real_order_still_goes_on(hearing):
    assert _said(hearing, "wait") == [{"barge": True}]
    assert _said(hearing, "hold on") == [{"barge": True}]
    events = _said(hearing, "Kairu what time is it")
    assert events[0] == {"barge": True} and {"order": "what time is it", "breath": 1} in events


def test_kairu_stop_while_it_speaks_is_still_the_emergency_stop(hearing):
    assert {"stop": True} in _said(hearing, "Kairu stop") and hearing.stopped


def test_an_unsure_word_does_not_stop_kairu(hearing):
    assert {"barge": True} not in _said(hearing, "hmm", sure=False)


def test_after_kairu_is_quiet_the_echo_rule_ends(hearing):
    hearing.set_echo("")
    hearing.clock += 5
    assert {"order": "photosynthesis is how plants make food", "breath": 1} in _said(hearing, "photosynthesis is how plants make food")


def test_the_listener_hears_the_mic_while_kairu_speaks_only_with_barge_in():
    from kairu.config import ROOT
    text = (ROOT / "kairu" / "voice" / "listen.py").read_text(encoding="utf-8")
    assert 'if paused and not barge:' in text and 'hasattr(hearing, "set_echo")' in text


# --- listening from the start: only your setting, and never a session by itself ----------------------------------------

class _UI:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def show(self):
        self.said.append("<shown>")

    def mic_shown(self, on):
        pass

    def heard(self, text):
        pass


class _Client:
    def __init__(self, up=True, mode="normal"):
        self.up, self.mode, self.ran = up, mode, []

    def status(self):
        from kairu import channel
        if not self.up:
            raise channel.ChannelError("down")
        return {"mode": self.mode}

    def run(self, action, granted=None):
        self.ran.append(action.name)
        return {"run": 1}

    def run_status(self, run):
        return {"outcome": None}

    def end(self, run):
        pass


def _voice(tmp_path, monkeypatch, at_start, client):
    from kairu.bar import voice
    from kairu.voice import link

    class Server:
        def __init__(self, data_dir):
            pass

        def accept(self, poll):
            import time
            time.sleep(poll)

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(link, "Server", Server)
    monkeypatch.setattr(voice, "AT_START_WAIT", 0.01)
    monkeypatch.setattr(voice, "START_SECONDS", 0.3)
    cfg = _config(tmp_path, "  listen_at_start: true\n" if at_start else "")
    return voice.VoiceControl(cfg, client, object(), _UI())


def _wait(condition):
    import time
    for _ in range(200):
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_without_the_setting_the_mic_stays_off_at_start(tmp_path, monkeypatch):
    client = _Client()
    control = _voice(tmp_path, monkeypatch, False, client)
    control.listen_at_start("the bar started")
    assert not _wait(lambda: client.ran) and control.state == "off"
    control.close()


def test_with_the_setting_the_mic_listens_for_kairu_without_a_session_or_showing_the_bar(tmp_path, monkeypatch):
    client = _Client()
    control = _voice(tmp_path, monkeypatch, True, client)
    control.listen_at_start("the bar started")
    assert _wait(lambda: client.ran == ["voice.listen"])
    assert control._want_session is False and "<shown>" not in control.ui.said
    control.close()


def test_it_waits_for_guardian_and_never_starts_after_an_emergency_stop(tmp_path, monkeypatch):
    late = _Client(up=False)
    control = _voice(tmp_path, monkeypatch, True, late)
    control.listen_at_start("the bar started")
    late.up = True
    assert _wait(lambda: late.ran == ["voice.listen"])
    control.close()
    stopped = _Client(mode="safe")
    control = _voice(tmp_path, monkeypatch, True, stopped)
    control.listen_at_start("you unlocked the PC")
    assert not _wait(lambda: stopped.ran) and control.state == "off"
    control.close()


def test_only_the_bar_start_and_your_unlock_call_it():
    import re
    from kairu.config import ROOT
    callers = [path.relative_to(ROOT).as_posix() for path in (ROOT / "kairu").rglob("*.py")
               if re.search(r"\blisten_at_start\(", path.read_text(encoding="utf-8")) and path.name != "voice.py"]
    assert callers == ["kairu/bar/app.py"]
    app = (ROOT / "kairu" / "bar" / "app.py").read_text(encoding="utf-8")
    assert "SessionWatch(lambda why: voice.mic_off(f\"Mic off: {why}.\"), voice.listen_at_start)" in app


def test_unlocking_tells_the_bar_and_locking_still_turns_the_mic_off():
    from kairu.bar import session_watch
    told, back = [], []
    watch = session_watch.SessionWatch.__new__(session_watch.SessionWatch)
    watch.on_change, watch.on_back = told.append, back.append
    watch._tell("the PC locked")
    watch._tell(session_watch.BACK_EVENTS[0x8], back=True)
    assert told == ["the PC locked"] and back == ["you unlocked the PC"]
    watch.on_back = None
    watch._tell("you signed in", back=True)  # without listen_at_start nothing is called


# --- fixes for the first real run on Windows (found by reading, before the laptop test) --------------------------------

def test_kairus_browser_opens_its_pages_to_ui_automation():
    from pathlib import Path
    from kairu.tasks import web
    given = web.arguments(Path("C:/k/data/browser-profile"), "https://claude.ai/new")
    assert "--force-renderer-accessibility" in given and given[-1] == "https://claude.ai/new"


def test_ui_automation_answers_in_utf8_both_ways():
    from kairu import hands
    from kairu.config import ROOT
    assert "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false" in hands.UIA_SCRIPT
    assert 'encoding="utf-8"' in (ROOT / "kairu" / "hands.py").read_text(encoding="utf-8")


# --- found on the laptop, 15 Nov 2026: a big model's load must not end the listener --------------------------------

class _Line:
    def __init__(self, replies=None):
        self.sent, self.replies = [], list(replies or [])

    def send(self, message, timeout=5.0):
        self.sent.append(message)

    def receive(self, timeout=5.0):
        return self.replies.pop(0) if self.replies else {"paused": False, "session": False, "end": False}


def _slow(monkeypatch, seconds, result=None, error=None):
    import time
    from kairu.voice import listen

    def hearing(place, engine):
        time.sleep(seconds)
        if error:
            raise error
        return result

    monkeypatch.setattr(listen, "_hearing", hearing)
    monkeypatch.setattr(listen, "LOADING_TICK", 0.05)
    return listen


def test_while_a_big_model_loads_the_bar_is_told_the_listener_is_still_here(monkeypatch):
    listen = _slow(monkeypatch, 0.4, result="whisper")
    line = _Line([{}, {"session": True}])
    assert listen._load(line, "place", "whisper-large-v3-turbo") == ("whisper", "", True)
    assert len(line.sent) >= 4 and all(message == {"events": [], "talking": False, "session": False} for message in line.sent)


def test_the_bar_can_end_it_while_it_loads_and_a_model_that_cant_load_says_so(monkeypatch):
    listen = _slow(monkeypatch, 0.3, result="whisper")
    assert listen._load(_Line([{"end": True}]), "place", "whisper-large-v3-turbo") == (None, "", False)
    listen = _slow(monkeypatch, 0.1, error=MemoryError("not enough memory"))
    hearing, problem, _ = listen._load(_Line(), "place", "whisper-large-v3-turbo")
    assert hearing is None and "MemoryError" in problem and "not enough memory" in problem


# --- "whats the weather in hyd" answered in about a second (laptop test, 15 Nov 2026: "it must respond quick") ---------

@pytest.mark.parametrize("said, where", [
    ("whats the weather in hyd", "Hyderabad"), ("Kairu, what's the weather in Hyderabad today", "Hyderabad"),
    ("how is the weather in bangalore", "Bengaluru"), ("weather in Chennai", "Chennai"), ("hyderabad weather", "Hyderabad"),
    ("is it raining in vizag", "Visakhapatnam"), ("temperature in New Delhi now", "New Delhi"),
    ("what is the temperature in warangal right now", "Warangal")])
def test_a_weather_question_names_its_place(said, where):
    from kairu.research import weather
    assert weather.place(said) == where


@pytest.mark.parametrize("said", ["what is the weather like tomorrow", "weather this week in hyd", "how is my weather app",
                                  "what is weather", "who is the prime minister", "remember that the weather was nice"])
def test_other_questions_are_not_taken(said):
    from kairu.research import weather
    assert weather.place(said) == ""


def test_the_router_sends_it_to_open_meteo_and_the_gateway_never_to_an_ai():
    from kairu.brain import router
    route = router.route("whats the weather in hyd")
    assert (route.kind, route.name, route.query, route.research) == ("cloud", "weather", "Hyderabad", True)


FORECAST = {"place": {"name": "Hyderabad", "admin1": "Telangana", "latitude": 17.38, "longitude": 78.46},
            "forecast": {"current": {"temperature_2m": 27.4, "apparent_temperature": 30.1, "relative_humidity_2m": 61,
                                     "weather_code": 2, "wind_speed_10m": 9.2},
                         "daily": {"temperature_2m_max": [31.2], "temperature_2m_min": [19.6],
                                   "precipitation_probability_max": [10]}}}


def test_the_action_keeps_only_numbers_and_names_and_the_answer_is_tenmins(tmp_path, monkeypatch):
    from kairu.research import weather
    from kairu.research.store import ResearchStore
    pretend = tmp_path / "weather.json"
    pretend.write_text(json.dumps(FORECAST), encoding="utf-8")
    monkeypatch.setenv(weather.TEST_WEATHER, str(pretend))
    weather.main(str(tmp_path), "Hyderabad", "a" * 16)
    found = ResearchStore(str(tmp_path)).take("a" * 16, "weather")
    assert found == {"name": "Hyderabad", "region": "Telangana", "temp": 27, "feels": 30, "humidity": 61, "wind": 9,
                     "sky": "partly cloudy", "high": 31, "low": 20, "rain": 10}
    said = weather.answer(found)
    assert said == ("It's 27°C and partly cloudy in Hyderabad right now, feels like 30. Today: 20 to 31°C, 10% chance of rain."
                    "\nWant tomorrow's forecast too?")


def test_an_unknown_place_or_a_bad_request_gives_no_answer_and_the_web_is_asked(tmp_path, monkeypatch):
    from kairu.research import weather
    from kairu.research.store import ResearchStore
    pretend = tmp_path / "weather.json"
    pretend.write_text(json.dumps({"place": None}), encoding="utf-8")
    monkeypatch.setenv(weather.TEST_WEATHER, str(pretend))
    weather.main(str(tmp_path), "Nowhereville", "b" * 16)
    assert weather.answer(ResearchStore(str(tmp_path)).take("b" * 16, "weather")) == ""
    with pytest.raises(SystemExit):
        weather.main(str(tmp_path), "https://evil.example", "c" * 16)


def test_weather_is_a_medium_research_action_that_only_reaches_open_meteo():
    from kairu import executors, policy
    from kairu.config import ROOT
    from kairu.research import weather
    from tests_kairu.helpers import POLICY
    rule = policy.load(POLICY).rules["research.weather"]
    assert rule.tier.name == "MEDIUM" and "research.weather" in executors.EXECUTORS
    assert weather.HOSTS == ("geocoding-api.open-meteo.com", "api.open-meteo.com")
    text = (ROOT / "kairu" / "research" / "weather.py").read_text(encoding="utf-8")
    assert text.count("urlopen(") == 1 and "not in HOSTS" in text


def test_the_bigger_hearing_models_take_one_best_guess(monkeypatch):
    from kairu.voice import whisper
    made = []
    monkeypatch.setattr(whisper, "Whisper", lambda folder, **kw: made.append((str(folder), kw)) or "w")
    monkeypatch.delenv(whisper.TEST_WHISPER, raising=False)
    whisper.transcriber("data/voice/faster-whisper-large-v3-turbo")
    whisper.transcriber("data/voice/faster-whisper-base.en")
    assert made[0][1]["beam"] == 1 and made[1][1] == {}


def test_whisper_sets_itself_up_on_silence_while_it_loads_and_never_on_the_stand_in():
    from kairu.voice import whisper
    heard = []
    whisper.warm(lambda sound: heard.append(len(sound)))
    assert heard == [whisper.RATE]  # half a second of 16-bit silence
    whisper.warm(lambda sound: 1 / 0)  # a warm-up never fails the listener
    stand_in = whisper.StandInWhisper.__new__(whisper.StandInWhisper)
    whisper.warm(stand_in)  # returns at once: nothing is "heard"
    from kairu.config import ROOT
    assert "warm(hear)" in (ROOT / "kairu" / "voice" / "listen.py").read_text(encoding="utf-8")
    assert "kw.warm(hear)" in (ROOT / "kairu" / "voice" / "check.py").read_text(encoding="utf-8")
