"""The light voice's safety rules, read from the code and the policy: no model, no microphone, no Guardian needed."""

import ast
import re
import sys
import time

import pytest

from kairu import policy
from kairu.config import ROOT
from kairu.guardian import Guardian, Verdict
from kairu.policy import Tier
from kairu.voice import mic as microphone
from tests_kairu.helpers import POLICY

VOICE = ROOT / "kairu" / "voice"
KAIRU_CODE = {path: path.read_text(encoding="utf-8") for path in (ROOT / "kairu").rglob("*.py")}


def code_of(*names) -> str:
    return "\n".join(KAIRU_CODE[ROOT / "kairu" / name] for name in names)


# --- the policy: nothing about Guardian's decisions changes -----------------------------------------------------

def test_voice_listen_and_speak_are_low_switched_by_voice_and_keep_only_hashes():
    rules = policy.load(POLICY).rules
    for name in ("voice.listen", "voice.speak"):
        rule = rules[name]
        assert rule.tier is Tier.LOW and rule.feature == "voice" and rule.private and rule.read_only
    assert [name for name in rules if name.startswith("voice.")] == ["voice.listen", "voice.speak"]


def test_any_other_voice_action_is_denied_even_with_voice_on(write_config):
    from kairu import config
    guardian = Guardian(config.load(write_config(voice=True)))
    for name in ("voice.record", "voice.approve", "voice.mic_on", "voice.setup"):
        assert guardian.check(name).verdict is Verdict.DENY
    assert guardian.check("voice.listen").verdict is Verdict.ALLOW


def test_voice_off_in_the_shipped_config_and_guardian_refuses_both(guardian):
    from kairu import config
    assert config.load(ROOT / "config.yaml").voice_enabled is False
    assert all(guardian.check(name).verdict is Verdict.DENY for name in ("voice.listen", "voice.speak"))


# --- only your own click or keystroke switches the mic on ----------------------------------------------------------

def test_only_the_mic_buttons_command_and_the_keys_handler_can_switch_the_mic_on():
    """mic_button() and listen_key() are called in one place each: the button's own command and Ctrl+Alt+V's own handler."""
    callers = {path.relative_to(ROOT).as_posix(): len(re.findall(r"\.(?:mic_button|listen_key)\(", text))
               for path, text in KAIRU_CODE.items() if re.search(r"\.(?:mic_button|listen_key)\(", text)}
    assert callers == {"kairu/bar/app.py": 2, "kairu/workspace/server.py": 2}  # the bar, and the workspace (W2)
    app = KAIRU_CODE[ROOT / "kairu" / "bar" / "app.py"]
    tree = ast.parse(app)
    owners = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
              and re.search(r"\.(?:mic_button|listen_key)\(", ast.get_source_segment(app, node))}
    assert owners == {"_mic_clicked", "listen_key_pressed"}
    assert re.findall(r"\b_mic_clicked\b", app).count("_mic_clicked") == 2  # its definition and command=self._mic_clicked
    assert "command=self._mic_clicked" in app
    assert re.findall(r"\blisten_key_pressed\b", app).count("listen_key_pressed") == 2  # its definition, and the hotkey
    assert "ShowHideKey(bar.listen_key_pressed, cfg.voice_key, LISTEN_ID)" in app
    assert "_switch_on(" in code_of("bar/voice.py") and code_of("bar/voice.py").count("self._switch_on()") == 2


def test_in_the_workspace_only_the_pages_mic_button_and_ctrl_m_switch_the_mic_on():
    """W2 (ADR-036): mic_button() and listen_key() are called in Workspace.mic_pressed only, which only the /api/mic request
    calls; the page sends /api/mic from micPressed only, and calls micPressed only from the mic's click and Ctrl+M."""
    server = KAIRU_CODE[ROOT / "kairu" / "workspace" / "server.py"]
    tree = ast.parse(server)
    owners = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
              and re.search(r"\.(?:mic_button|listen_key)\(", ast.get_source_segment(server, node))}
    assert owners == {"mic_pressed"}
    assert len(re.findall(r"\.mic_pressed\(", server)) == 1 and 'path == "/api/mic"' in server
    page = (ROOT / "kairu" / "workspace" / "page.html").read_text(encoding="utf-8")
    assert page.count('"/api/mic"') == 1 and page.index('"/api/mic"') > page.index("async function micPressed(")
    calls = re.findall(r"micPressed\(([^)]*)\)", page)
    assert sorted(calls) == ['"button"', '"key"', "how"]  # the click, Ctrl+M, and its own definition
    assert '$("mic").addEventListener("click", () => micPressed("button"))' in page
    assert re.search(r'event\.ctrlKey && !event\.altKey && !event\.shiftKey && event\.key\.toLowerCase\(\) === "m"[^\n]*micPressed\("key"\)', page)
    workspace_code = server + KAIRU_CODE[ROOT / "kairu" / "workspace" / "app.py"]
    assert "start_voice()" in workspace_code and "mic_button()" in server  # the voice is made off; switching it on is yours


def test_nothing_in_the_voice_can_fill_or_press_the_card_or_the_mic_button():
    code = code_of("bar/voice.py", *[f"voice/{path.name}" for path in VOICE.glob("*.py")])
    for name in ("yes_box", "pin_box", "approve_button", "refuse_button", "mic_button.", "order_box", ".approve(", "link_approve"):
        assert name not in code, name
    assert ".invoke(" not in code and "event_generate" not in code and "SendInput" not in code and "keybd_event" not in code


def imported(code: str) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_the_listener_never_runs_anything_itself():
    for name in ("listen.py", "hearing.py", "words.py", "mic.py", "link.py"):
        code = KAIRU_CODE[VOICE / name]
        uses = imported(code)
        assert not {use for use in uses if use.split(".")[1:2] in (["client"], ["tasks"], ["executors"], ["runner"])}, (name, uses)
        assert "subprocess" not in uses and "GuardianClient(" not in code and ".run(" not in code, name
    assert "safemode.emergency_stop(" in code_of("voice/listen.py")  # its one deed: "Kairu, stop"


LOADS_VOSK = """import sys
from kairu.voice import listen
vosk = listen.load_vosk()
assert vosk.Model and vosk.KaldiRecognizer and vosk.SetLogLevel
print(sorted(name for name in ("requests", "urllib3", "ssl", "tqdm", "srt", "urllib.request") if name in sys.modules))
import urllib.request
print(urllib.request.urlopen.__module__)
"""


def test_the_listener_loads_vosk_without_its_downloader_and_so_without_a_way_to_the_network():
    """About 9 MiB less (CI, 7 Nov 2026: the listener was 195.5 MiB on Linux against 190): requests, urllib3 and ssl stay out."""
    import subprocess
    done = subprocess.run([sys.executable, "-c", LOADS_VOSK], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split("\n")[:2] == ["[]", "urllib.request"]  # none loaded; the real one still loads afterwards
    code = code_of("voice/listen.py")
    assert "import vosk" not in code.split("def load_vosk")[0] and "vosk = load_vosk()" in code


# --- no sound is ever written; words stay in memory ---------------------------------------------------------------

WRITES = re.compile(r"""open\([^)]*["'](?:w|a|x)b?\+?["']|wave\.open\([^)]*["']w|\.write_bytes\(|\.write_text\(|tofile\(|"""
                    r"""shutil\.copy""")


def test_no_voice_code_writes_sound_or_words_to_disk():
    for name in ("listen.py", "hearing.py", "words.py", "link.py"):
        assert not WRITES.search(KAIRU_CODE[VOICE / name]), name
    assert not WRITES.search(code_of("bar/voice.py"))
    mic_code = KAIRU_CODE[VOICE / "mic.py"]
    assert WRITES.findall(mic_code) == ['open(self.folder / "played.log", "a"']  # the tests' pretend mic: names it played
    speak_code = KAIRU_CODE[VOICE / "speak.py"]
    assert WRITES.findall(speak_code) == ['open(folder / "spoken.log", "a"']  # the tests' pretend speaker only
    assert speak_code.index('open(folder / "spoken.log"') > speak_code.index("def _stand_in")


def test_the_real_microphone_keeps_nothing_after_closing():
    code = KAIRU_CODE[VOICE / "mic.py"]
    assert "memset(buffer, 0" in code  # what was heard does not linger in memory either


# --- Windows' privacy setting: read, never worked around -------------------------------------------------------------

@pytest.mark.parametrize("values,says", [
    ({("HKCU", microphone.PRIVACY): "Deny"}, "blocks the microphone"),
    ({("HKCU", microphone.PRIVACY + r"\NonPackaged"): "Deny"}, "for desktop apps"),
    ({("HKLM", microphone.PRIVACY): "Deny"}, "turned off for this PC"),
    ({("HKCU", microphone.PRIVACY): "Allow"}, ""),
    ({}, ""),
])
def test_windows_microphone_privacy_setting_is_read_and_said_plainly(values, says):
    found = microphone.privacy_problem(lambda hive, key: values.get((hive, key)))
    assert (says in found and "Settings > Privacy & security > Microphone" in found) if says else found == ""


def test_a_blocked_microphone_is_never_opened_another_way(monkeypatch):
    monkeypatch.delenv(microphone.TEST_MIC, raising=False)
    monkeypatch.setattr(microphone, "privacy_problem", lambda read=None: "Windows' privacy setting blocks the microphone.")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(microphone, "WaveIn", lambda: pytest.fail("the microphone was opened anyway"))
    with pytest.raises(microphone.MicProblem, match="privacy setting"):
        microphone.open_mic()
    assert "winreg" in KAIRU_CODE[VOICE / "mic.py"] and "SetValue" not in KAIRU_CODE[VOICE / "mic.py"]


def test_on_other_systems_there_is_no_microphone(monkeypatch):
    monkeypatch.delenv(microphone.TEST_MIC, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(microphone.MicProblem, match="built for Windows"):
        microphone.open_mic()


# --- the mic goes off when the PC locks or sleeps ------------------------------------------------------------------

def test_a_pc_that_slept_turns_the_mic_off(monkeypatch):
    from kairu.bar import session_watch
    monkeypatch.setattr(session_watch, "TICK_SECONDS", 0.05)
    told, now = [], [time.time()]
    monkeypatch.setattr(session_watch.time, "time", lambda: now[0])
    watch = session_watch.SessionWatch(told.append)
    try:
        time.sleep(0.2)
        now[0] += 60  # an hour of sleep looks like this to a clock that ticks every second
        deadline = time.monotonic() + 3
        while not told and time.monotonic() < deadline:
            time.sleep(0.05)
        assert told and "asleep" in told[0]
    finally:
        watch.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows tells a window of its own about locking and sleep")
def test_windows_tells_the_bar_about_lock_sign_out_and_sleep():
    from kairu.bar import session_watch
    told = []
    watch = session_watch.SessionWatch(told.append)
    try:
        deadline = time.monotonic() + 3
        while not watch._thread_id and time.monotonic() < deadline:
            time.sleep(0.05)
        assert watch._thread_id  # its window is made and registered for session and power changes
        assert {0x7: "the PC locked", 0x6: "you signed out"}.items() <= session_watch.LOCK_EVENTS.items()
    finally:
        watch.close()
    code = KAIRU_CODE[ROOT / "kairu" / "bar" / "session_watch.py"]
    assert "WTSRegisterSessionNotification" in code and "RegisterSuspendResumeNotification" in code


# --- the key -----------------------------------------------------------------------------------------------------------

def test_ctrl_alt_v_is_its_own_key_never_k():
    from kairu import hotkey as guardians_key
    from kairu.bar import hotkey
    assert len({hotkey.LISTEN_ID, hotkey.HOTKEY_ID, guardians_key.HOTKEY_ID}) == 3
    assert hotkey.ShowHideKey(print, "V", hotkey.LISTEN_ID).name == "Ctrl+Alt+V" and hotkey._virtual_key("V") == 0x56
