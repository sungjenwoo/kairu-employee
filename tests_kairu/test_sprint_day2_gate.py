"""tools/sprint_day2_gate.py: its checks, from audit rows; the spoken steps themselves are yours, on your PC."""

import importlib.util
import subprocess
import sys

from kairu.config import ROOT

spec = importlib.util.spec_from_file_location("sprint_day2_gate", ROOT / "tools" / "sprint_day2_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def row(number, kind, action, decision="allow", **details):
    return {"id": number, "kind": kind, "action": action, "decision": decision, "details": details}


def test_both_steps_must_run_in_the_order_said():
    rows = [row(1, "check", "apps.open"), row(2, "run", "apps.open", "started"), row(3, "check", "system.volume"),
            row(4, "run", "system.volume", "started")]
    assert gate.in_order(rows, "apps.open", "system.volume")
    assert not gate.in_order(list(reversed(rows)), "apps.open", "system.volume")
    assert not gate.in_order(rows[:2], "apps.open", "system.volume")


def test_kairus_own_listening_and_speaking_are_not_orders():
    rows = [row(1, "check", "voice.speak"), row(2, "run", "voice.speak", "started"), row(3, "check", "voice.listen")]
    assert gate.orders_reaching_guardian(rows) == []
    assert gate.orders_reaching_guardian(rows + [row(4, "check", "apps.open")]) == ["apps.open"]


def test_an_answer_counts_as_spoken_only_when_voice_speak_ran_after_the_question():
    asked = [row(1, "check", "brain.ask"), row(2, "run", "brain.ask", "started")]
    assert not gate.spoken_after(asked, "brain.ask")
    assert gate.spoken_after(asked + [row(3, "run", "voice.speak", "started")], "brain.ask")
    assert not gate.spoken_after([row(1, "run", "voice.speak", "started"), *asked], "brain.ask")


def test_your_voice_pick_is_saved_as_voice_voice_and_nothing_else_in_config_changes():
    text = "# mine\nvoice:\n  enabled: true   # on\n  # voice: indian-svbi  # a note\nresearch:\n  enabled: false\n"
    saved = gate.with_voice(text, "uk-jenny")
    assert saved.splitlines()[:3] == text.splitlines()[:3] and saved.splitlines()[4:] == text.splitlines()[4:]
    assert saved.splitlines()[3].startswith("  voice: uk-jenny")
    again = gate.with_voice(saved, "us-hfc-female")
    assert again.count("voice: ") == 1 + 0 and "  voice: us-hfc-female" in again and "uk-jenny" not in again
    assert "  voice: indian-svbi" in gate.with_voice("voice:\n  enabled: true\n", "indian-svbi")
    from kairu import config
    for key in ("uk-jenny", "us-hfc-female"):
        assert key in config.VOICE_VOICES


def test_it_has_the_eleven_steps_and_never_types_into_the_bar_or_hears_you_itself():
    assert all(hasattr(gate.Gate, f"step_{number}") for number in range(1, gate.STEPS + 1)) and gate.STEPS == 11
    assert gate.TENMIN_QUESTIONS[0] == "who is the prime minister of India?" and len(gate.TENMIN_QUESTIONS) == 3
    assert (gate.AT_REST_MB, gate.SPEAKING_MB) == (200, 400)
    code = (ROOT / "tools" / "sprint_day2_gate.py").read_text(encoding="utf-8")
    for word in ("SendInput", "keybd_event", "open_mic", "WaveIn", "yes_box", "pin_box", ".approve("):
        assert word not in code, word
    shown = subprocess.run([sys.executable, str(ROOT / "tools" / "sprint_day2_gate.py"), "--help"], cwd=ROOT, capture_output=True, text=True)
    assert "--step" in shown.stdout, shown.stderr


def test_after_the_pick_only_the_picked_voices_file_stays(tmp_path):
    """indian-tni shares en_US-l2arctic-medium with indian-svbi: that one file stays; every other voice's three files go."""
    from kairu.voice import models
    place = tmp_path / models.FOLDER / models.VOICE_FOLDER
    place.mkdir(parents=True)
    for name in ("en_US-l2arctic-medium", "en_GB-jenny_dioco-medium", "en_US-libritts_r-medium"):
        for end in (".onnx", ".onnx.json", ".kairu.json"):
            (place / f"{name}{end}").write_text("x")
    (place / "my-notes.txt").write_text("not a voice")
    said = gate.keep_only(tmp_path, "indian-tni")
    assert sorted(path.name for path in place.iterdir()) == [
        "en_US-l2arctic-medium.kairu.json", "en_US-l2arctic-medium.onnx", "en_US-l2arctic-medium.onnx.json", "my-notes.txt"]
    assert said == "en_GB-jenny_dioco-medium, en_US-libritts_r-medium"


def test_a_voice_is_picked_by_number_and_r_hears_again():
    class Asked(gate.Gate):
        def __init__(self, answer):
            self.answer = answer

        def ask_here(self, question):
            return self.answer

    assert Asked("3").ask_choice("?", 16) == 3 and Asked(" r ").ask_choice("?", 16) == "r"
    assert Asked("r 12").ask_choice("?", 16) == "r12" and Asked("r17").ask_choice("?", 16) is None
    assert Asked("17").ask_choice("?", 16) is None and Asked("").ask_choice("?", 16) is None
