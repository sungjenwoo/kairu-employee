"""How Kairu sounds (VOICE.md "How Kairu sounds", 14 Nov 2026): voice.style, Tenmin's expressive delivery with Piper's own
dials. Nothing here plays a sound: the speakers and Piper are stand-ins."""

import json
import types
from pathlib import Path

import pytest
import yaml

from kairu import config, executors
from kairu.brain import tenmin
from kairu.config import ROOT
from kairu.voice import speak

LINE = "The capital of Japan is Tokyo. Want to know more about it?"


@pytest.mark.parametrize("style", list(speak.STYLES))
def test_the_answer_and_the_follow_up_question_are_said_in_their_own_delivery(style):
    answer, question, breath = speak.STYLES[style]
    assert speak.parts(LINE, style) == [("The capital of Japan is Tokyo.", answer), ("Want to know more about it?", question)]
    assert question[0] > answer[0]  # the question is said more slowly than the answer, as a teacher asks
    assert 0 < breath < 1


def test_every_delivery_stays_near_the_voices_own_so_words_stay_clear():
    for answer, question, _ in speak.STYLES.values():
        for length, noise, width in (answer, question):
            assert 0.85 <= length <= 1.2 and 0.5 <= noise <= 0.85 and 0.7 <= width <= 1.0


def test_plain_is_the_line_as_it_is_in_one_piece():
    assert speak.parts(LINE, speak.PLAIN) == [(LINE, None)]
    assert speak.parts(LINE, "unknown") == [(LINE, None)]


def test_a_line_with_no_follow_up_or_only_a_question_is_one_piece():
    answer, question, _ = speak.STYLES["warm"]
    assert speak.parts("Tokyo.", "warm") == [("Tokyo.", answer)]
    assert speak.parts("Did you mean Tokyo?", "warm") == [("Did you mean Tokyo?", question)]


def test_every_tenmin_answer_splits_into_the_answer_then_its_one_question():
    said = tenmin.spoken("Photosynthesis is how plants make food from light. It happens in leaves.\nWant an example?",
                         "what is photosynthesis")
    (first, _), (second, _) = speak.parts(said, "warm")
    assert not first.endswith("?") and second == "Want an example?"


def test_piper_gets_its_three_dials_only_with_a_delivery():
    command = speak.piper_command(Path("piper.exe"), Path("v.onnx"), 2, (0.95, 0.75, 0.9))
    assert command[command.index("--length_scale") + 1] == "0.95"
    assert command[command.index("--noise_scale") + 1] == "0.75" and command[command.index("--noise_w") + 1] == "0.90"
    assert "--length_scale" not in speak.piper_command(Path("piper.exe"), Path("v.onnx"), 2)


def test_with_a_style_piper_runs_once_for_each_part_one_at_a_time_with_a_breath_between(tmp_path, monkeypatch):
    played, made = [], []

    class Speakers:
        def __init__(self, rate):
            self.rate = rate

        def play(self, sound):
            played.append(sound)

        def wait(self):
            pass

        def close(self):
            pass

    def synthesize(text, piper, onnx, speaker, delivery=None):
        made.append((text, delivery))
        yield b"\x01\x01" * 10

    monkeypatch.setattr(speak, "WaveOut", Speakers)
    monkeypatch.setattr(speak, "synthesize", synthesize)
    config_file = tmp_path / "v.onnx.json"
    config_file.write_text(json.dumps({"audio": {"sample_rate": 22050}}))
    assert speak.say_with_piper(LINE, Path("piper.exe"), Path("v.onnx"), config_file, 2, style="warm") is None
    answer, question, breath = speak.STYLES["warm"]
    assert made == [("The capital of Japan is Tokyo.", answer), ("Want to know more about it?", question)]
    assert played[1] == bytes(int(22050 * breath) * 2) and set(played[1]) == {0}  # quiet between them
    made.clear(), played.clear()
    speak.say_with_piper(LINE, Path("piper.exe"), Path("v.onnx"), config_file, 2)
    assert made == [(LINE, None)] and len(played) == 1  # plain: as before


def test_the_style_reaches_the_speaker_and_only_the_line_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv(speak.TEST_VOICE, str(tmp_path))
    monkeypatch.setattr(speak.time, "sleep", lambda seconds: None)
    speak.main(LINE, str(tmp_path), "indian-svbi", "lively")
    assert (tmp_path / "spoken.log").read_text().splitlines() == [LINE]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["spoken.log"]  # voice rule: nothing else is written
    heard = []
    monkeypatch.setattr(speak, "_stand_in", lambda folder, line, style=speak.PLAIN: heard.append(style))
    speak.main(LINE, str(tmp_path), "indian-svbi", "lively")
    speak.main(LINE, str(tmp_path), "indian-svbi", "shouting")  # not a style: plain
    speak.main(LINE, str(tmp_path), "indian-svbi")
    assert heard == ["lively", speak.PLAIN, speak.PLAIN]


# --- the setting -----------------------------------------------------------------------------------------------

def write(tmp_path, voice):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": voice}))
    return path


def test_the_style_is_warm_by_default_and_only_one_of_four(tmp_path):
    assert config.load(write(tmp_path, {"enabled": False})).voice_style == "warm"
    assert config.load(write(tmp_path, {"style": "calm"})).voice_style == "calm"
    with pytest.raises(config.ConfigError, match="voice.style must be one of"):
        config.load(write(tmp_path, {"style": "shouting"}))
    assert set(config.VOICE_STYLES) == {*speak.STYLES, speak.PLAIN} and config.VOICE_STYLES[0] == speak.DEFAULT_STYLE


def test_guardian_supplies_the_style_and_a_request_never_can():
    spoken = executors.EXECUTORS["voice.speak"]
    assert "voice_style" in spoken.supplied and set(spoken.arguments) == {"text"}
    assert executors.argument_problem("voice.speak", spoken, {"text": "hi", "voice_style": "lively"})
    assert '"voice_style": cfg.voice_style' in (ROOT / "kairu" / "guardian_program.py").read_text(encoding="utf-8")


def test_kairu_voice_try_says_one_line_in_each_style(monkeypatch, tmp_path):
    from kairu import cli
    heard = []
    monkeypatch.setattr(speak, "main", lambda line, data_dir, voice, style, tts="piper", kokoro="": heard.append((line, voice, style)))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    cfg = types.SimpleNamespace(voice_tts="piper", voice_kokoro="af_heart", voice_voice="uk-jenny", voice_style="warm", data_dir=tmp_path)
    assert cli._voice_try(types.SimpleNamespace(style=None, voice=None, tts=None), cfg) == 0
    assert [style for _, _, style in heard] == ["warm", "lively", "calm", "plain"]
    assert {voice for _, voice, _ in heard} == {"uk-jenny"} and {line for line, _, _ in heard} == {cli.TRY_LINE}
    heard.clear()
    cli._voice_try(types.SimpleNamespace(style="calm", voice="us-ryan", tts=None), cfg)
    assert heard == [(cli.TRY_LINE, "us-ryan", "calm")]


def test_kairu_voice_try_voices_plays_every_voice_in_your_style(monkeypatch, tmp_path):
    from kairu import cli
    from kairu.voice import models
    heard = []
    monkeypatch.setattr(speak, "main", lambda line, data_dir, voice, style, tts="piper", kokoro="": heard.append((voice, style)))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    cfg = types.SimpleNamespace(voice_tts="piper", voice_kokoro="af_heart", voice_voice="uk-jenny", voice_style="lively", data_dir=tmp_path)
    assert cli._voice_try(types.SimpleNamespace(style=None, voice=None, voices=True, tts=None), cfg) == 0
    assert [voice for voice, _ in heard] == list(models.VOICES) and {style for _, style in heard} == {"lively"}


def test_the_default_voice_is_no_longer_the_one_the_owner_did_not_like():
    from kairu.voice import models
    assert models.DEFAULT_VOICE == config.VOICE_VOICES[0] == config.Config.__dataclass_fields__["voice_voice"].default == "uk-jenny"


def test_the_default_voice_is_now_uk_jenny_and_indian_svbi_is_still_there():
    from kairu.voice import models
    assert models.DEFAULT_VOICE == config.VOICE_VOICES[0] == config.Config.voice_voice == "uk-jenny"
    assert "indian-svbi" in models.VOICES


def test_kairu_voice_try_voices_says_the_line_in_every_voice(monkeypatch, tmp_path):
    from kairu import cli
    from kairu.voice import models
    heard = []
    monkeypatch.setattr(speak, "main", lambda line, data_dir, voice, style, tts="piper", kokoro="": heard.append((voice, style)))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    cfg = types.SimpleNamespace(voice_tts="piper", voice_kokoro="af_heart", voice_voice="uk-jenny", voice_style="calm", data_dir=tmp_path)
    assert cli._voice_try(types.SimpleNamespace(style=None, voice=None, voices=True, tts=None), cfg) == 0
    assert [voice for voice, _ in heard] == list(models.VOICES) and {style for _, style in heard} == {"calm"}
