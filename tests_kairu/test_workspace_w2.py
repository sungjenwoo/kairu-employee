"""W2, finishing the workspace (Plan v2.0 section 4b-2, ADR-036): the file skills, the Files panel, voice in the workspace,
one mic for the bar and the workspace, "open the workspace", and Ember Glow.

The skills run on the pretend PC (KAIRU_TEST_PC) and the pretend Recycle Bin; the voice uses stand-ins, never a microphone.
"""

import hashlib
import re
import sys
import threading
import time

import pytest

from kairu import policy
from kairu.config import ROOT
from kairu.policy import Tier
from kairu.tasks import actions, core
from kairu.tasks import plan
from kairu.tasks.store import TaskStore
from kairu.voice import link
from kairu.workspace import app
from kairu.workspace.server import WINDOW_GONE_SECONDS, YOU_ARE_IN_IT, Workspace
from kairu.workspace.store import WorkspaceStore
from tests_kairu.helpers import POLICY, wait_for
from tests_kairu.test_day4 import JOB, USABLE, calls, data, desk, said, steps_of, work  # noqa: F401 (fixtures)
from tests_kairu.test_workspace import PAGE, SERVER, StandInCore, StandInGuardian, call, served, workspace  # noqa: F401

RULES = policy.load(POLICY).rules


# --- the policy --------------------------------------------------------------------------------------------------------

def test_the_three_file_skills_have_their_tiers_and_keep_only_a_hash_of_your_words():
    for name, tier in (("files.write", Tier.MEDIUM), ("files.open", Tier.MEDIUM), ("files.show", Tier.LOW)):
        assert RULES[name].tier is tier and RULES[name].private and not RULES[name].read_only, name
    assert {skill.action for skill in USABLE} >= {"files.write", "files.open", "files.show"}


def test_their_work_folder_is_supplied_by_guardian_never_by_a_request():
    from kairu import executors
    for name in ("files.write", "files.open", "files.show"):
        assert executors.EXECUTORS[name].supplied == ("data_dir", "work_folder")
        assert "work_folder" not in executors.EXECUTORS[name].arguments


# --- understanding the orders ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("order,expected", [
    ("make a file called gate.txt saying hello", [("files.write", {"name": "gate.txt", "text": "hello"})]),
    ("Kairu, create a file notes.md with buy milk and eggs", [("files.write", {"name": "notes.md", "text": "buy milk and eggs"})]),
    ("make a file called empty.txt", [("files.write", {"name": "empty.txt", "text": ""})]),
    ("open file notepad.exe", [("files.open", {"name": "notepad.exe"})]),
    ('open the file "report final.pdf"', [("files.open", {"name": "report final.pdf"})]),
    ("open notes.txt", [("files.open", {"name": "notes.txt"})]),
    ('open the folder "Reports"', [("files.open", {"name": "Reports"})]),
    ('show "gate.txt" in its folder', [("files.show", {"name": "gate.txt"})]),
    ("show me report.pdf in explorer", [("files.show", {"name": "report.pdf"})]),
    ("open the folder of gate.txt", [("files.show", {"name": "gate.txt"})]),
    # the orders that worked before W2 still mean what they meant
    ("open youtube.com", [("web.open", {"url": "youtube.com"})]),
    ("open github", [("web.open", {"url": "github"})]),
    ("open Notepad", [("apps.open", {"name": "Notepad"})]),
    ("find pdfs from today", [("files.find", {"what": "pdfs", "when": "today"})]),
    ("make a file called a.txt saying hi and open Notepad", [("files.write", {"name": "a.txt", "text": "hi"}),
                                                             ("apps.open", {"name": "Notepad"})]),
])
def test_the_file_orders_are_understood(order, expected):
    assert steps_of(order) == expected


def test_a_step_names_its_files_from_its_own_details_never_a_pattern():
    assert core.files_of(core.Step("files.write", {"name": "gate.txt", "text": "x"})) == [{"name": "gate.txt", "how": "made"}]
    assert core.files_of(core.Step("files.rename", {"old": "a.txt", "new": "b.txt"})) == [{"name": "b.txt", "how": "renamed"}]
    assert core.files_of(core.Step("files.move", {"name": "*.pdf", "to": "pdfs/"})) == [{"name": "pdfs", "how": "moved into"}]
    assert core.files_of(core.Step("files.delete", {"name": "*.tmp"})) == []
    assert core.files_of(core.Step("apps.open", {"name": "Notepad"})) == []


def test_the_new_skills_are_fenced_before_guardian_is_asked(config):
    task = core.TaskCore(config, client=StandInGuardian())
    for action in ("files.write", "files.open", "files.show"):
        assert task.outside(core.Step(action, {"name": "../outside.txt"})).startswith("Refused"), action
        assert task.outside(core.Step(action, {"name": "inside.txt"})) == "", action


def test_a_plan_may_use_them_and_shows_each_in_a_few_words():
    assert {"files.write", "files.open", "files.show"} <= set(plan.PLANNABLE)
    assert plan.describe("files.write", {"name": "a.txt", "text": "hi"}) == "make a.txt"
    assert plan.describe("files.show", {"name": "a.txt"}) == "show a.txt in its folder"
    parsed = plan.parse('{"steps": [{"action": "files.write", "details": {"name": "a.txt"}}]}', {"files.write"})
    assert parsed == [("files.write", {"name": "a.txt", "text": ""})]


# --- files.write: a new text file, never over another; undo puts it in the Recycle Bin ------------------------------

def test_write_makes_a_new_text_file_and_undo_puts_it_in_the_bin(data, work, desk):
    assert actions.write_file(str(data), JOB, "gate.txt", "hello", str(work)) is None
    assert (work / "gate.txt").read_text(encoding="utf-8") == "hello\n" and said(data).text == "Made gate.txt (5 characters)."
    actions.undo(str(data), JOB, str(work))
    assert not (work / "gate.txt").exists() and said(data).text == "Undone: gate.txt is in the Recycle Bin."
    assert list((desk / "bin").rglob("*")), "it went to the pretend Recycle Bin, not deleted for good"


def test_write_never_overwrites_and_writes_text_kinds_only(data, work, desk):
    (work / "keep.txt").write_text("mine")
    for name, problem in (("keep.txt", "already there"), ("run.bat", "text files only"), ("tool.exe", "text files only"),
                          ("../out.txt", "outside your work folder"), ("*.txt", "never a pattern"), ("C:/x.txt", "outside")):
        assert actions.write_file(str(data), JOB, name, "echo hi", str(work)) == actions.REFUSED, name
        assert problem in said(data).text, name
    assert (work / "keep.txt").read_text() == "mine" and not (work / "run.bat").exists()
    assert TaskStore(data).undo_count() == 0


def test_undo_leaves_a_made_file_that_you_changed_since(data, work, desk):
    actions.write_file(str(data), JOB, "draft.md", "one", str(work))
    said(data)
    (work / "draft.md").write_text("one, and my own words")
    assert actions.undo(str(data), JOB, str(work)) == actions.REFUSED
    assert "changed since" in said(data).text and (work / "draft.md").exists()


def test_a_written_backslash_n_is_a_new_line(data, work, desk):
    actions.write_file(str(data), JOB, "list.txt", "milk\\neggs", str(work))
    assert (work / "list.txt").read_text() == "milk\neggs\n"
    entry = TaskStore(data).newest_undo()
    assert entry.kind == "write" and entry.detail["sha256"] == hashlib.sha256(b"milk\neggs\n").hexdigest()


# --- files.open and files.show: never a program, script or shortcut -----------------------------------------------

def test_open_opens_documents_and_folders_through_the_pc(data, work, desk):
    (work / "notes.txt").write_text("x")
    (work / "Reports").mkdir()
    assert actions.open_file(str(data), JOB, "notes.txt", str(work)) is None and said(data).text == "Opened notes.txt."
    assert actions.open_file(str(data), JOB, "Reports", str(work)) is None
    assert calls(desk) == ["open file notes.txt", "open file Reports"]


@pytest.mark.parametrize("name", ["tool.exe", "run.bat", "run.cmd", "go.ps1", "x.vbs", "x.js", "setup.msi", "link.lnk",
                                  "site.url", "app.hta", "x.scr", "macro.docm", "noext"])
def test_open_refuses_anything_that_could_run_code(data, work, desk, name):
    (work / name).write_text("x")
    assert actions.open_file(str(data), JOB, name, str(work)) == actions.REFUSED
    assert "never opens programs, scripts or shortcuts" in said(data).text and calls(desk) == []


def test_open_and_show_stay_inside_the_work_folder(data, work, desk, tmp_path):
    (tmp_path / "secret.txt").write_text("x")
    for skill in (actions.open_file, actions.show_file):
        assert skill(str(data), JOB, "../secret.txt", str(work)) == actions.REFUSED
        assert "outside your work folder" in said(data).text
        assert skill(str(data), JOB, "missing.txt", str(work)) == actions.REFUSED
        assert "no 'missing.txt'" in said(data).text
    assert calls(desk) == []


def test_show_shows_any_kind_without_opening_it(data, work, desk):
    (work / "tool.exe").write_text("x")
    assert actions.show_file(str(data), JOB, "tool.exe", str(work)) is None
    assert calls(desk) == ["show file tool.exe"] and said(data).text == "tool.exe is shown in its folder."


# --- the Files panel -----------------------------------------------------------------------------------------------

def test_a_finished_steps_files_are_kept_with_the_mission_and_not_shown_with_the_steps(workspace, served):
    def work(order):
        tell = workspace._progress
        tell({"kind": "steps", "steps": [
            {"action": "files.write", "label": "make gate.txt", "files": [{"name": "gate.txt", "how": "made"}]},
            {"action": "files.rename", "label": "rename", "files": [{"name": "b.txt", "how": "renamed"}]}]})
        tell({"kind": "step", "number": 1, "state": "running", "text": ""})
        seen["steps"] = call(served, "/api/state")[1]["run"]["steps"]
        tell({"kind": "step", "number": 1, "state": "done", "text": "Made gate.txt."})
        tell({"kind": "step", "number": 2, "state": "not done", "text": "Refused."})
        return "Made gate.txt. Refused."

    seen = {}
    workspace.core.then = work
    mission = call(served, "/api/order", {"text": "make a file called gate.txt and rename a.txt to b.txt"})[1]["mission"]
    wait_for(lambda: call(served, "/api/state")[1]["run"] is None)
    assert all(set(step) == {"label", "state", "text"} for step in seen["steps"])
    files = call(served, f"/api/missions/{mission}")[1]["files"]
    assert [(f["name"], f["how"]) for f in files] == [("gate.txt", "made")]  # the step that wasn't done names nothing


def test_the_files_list_shows_each_name_once_with_what_last_happened(tmp_path):
    store = WorkspaceStore(tmp_path)
    mission = store.add_mission("Files")["id"]
    for name, how in (("a.txt", "made"), ("b.txt", "made"), ("a.txt", "opened"), ("x", "deleted for good")):
        store.note_file(mission, name, how)
    assert [(f["name"], f["how"]) for f in store.files(mission)] == [("a.txt", "opened"), ("b.txt", "made")]
    store.delete_mission(mission)
    assert store.files(mission) == []


def test_the_panels_buttons_send_orders_and_show_names_as_text():
    panel = PAGE[PAGE.index("// Files (W2)"):PAGE.index('const needs = el("section");')]
    assert 'sendText("open the " + (folder ? "folder" : "file")' in panel and 'sendText("show \\"" + f.name' in panel
    assert "innerHTML" not in PAGE and "insertAdjacentHTML" not in PAGE
    helper = PAGE[PAGE.index("async function sendText("):PAGE.index("// --- the voice (W2)")]
    assert '"/api/order"' in helper and "/api/answer" not in helper  # a button is an order, never an answer to the card


# --- voice in the workspace ----------------------------------------------------------------------------------------------

class StandInVoice:
    def __init__(self):
        self.state, self.session, self.working, self.pressed, self.off = "off", False, False, [], []

    def mic_button(self):
        self.pressed.append("button")

    def listen_key(self):
        self.pressed.append("key")

    def mic_off(self, why="Mic off."):
        self.off.append(why)
        self.state = "off"

    def close(self):
        pass


def test_without_voice_enabled_there_is_no_mic(workspace, served):
    assert workspace.start_voice() is False and workspace.voice is None
    assert call(served, "/api/state")[1]["voice"] == {"enabled": False}
    status, reply = call(served, "/api/mic", {"how": "button"})
    assert status == 400 and "voice.enabled" in reply["error"]


def test_the_mic_requests_reach_the_switch_and_nothing_else_switches_it_on(workspace, served):
    workspace.voice = StandInVoice()
    assert call(served, "/api/mic", {"how": "button"})[0] == 200 and call(served, "/api/mic", {"how": "key"})[0] == 200
    assert call(served, "/api/mic", {"how": "anything"})[0] == 200
    assert workspace.voice.pressed == ["button", "key", "button"]
    assert call(served, "/api/mic", {"how": "button"}, key="wrong")[0] == 401 and len(workspace.voice.pressed) == 3


def test_a_spoken_order_goes_into_the_open_mission_and_a_new_one_when_none_is_open(workspace, served):
    workspace.voice = StandInVoice()
    first = call(served, "/api/order", {"text": "what's open?"})[1]["mission"]
    wait_for(lambda: workspace._run is None)
    call(served, "/api/voice-where", {"mission": first, "project": None})
    assert workspace.spoken("open Notepad") == "Done." and workspace.core.orders[-1] == "open Notepad"
    texts = [m["text"] for m in call(served, f"/api/missions/{first}")[1]["messages"]]
    assert texts[-2:] == ["open Notepad", "Done."]
    project = call(served, "/api/projects", {"name": "Voice"})[1]["project"]["id"]
    call(served, "/api/voice-where", {"mission": None, "project": project})
    workspace.spoken("set volume to 20")
    made = call(served, "/api/state")[1]["voice"]["mission"]
    assert made not in (None, first) and call(served, f"/api/missions/{made}")[1]["mission"]["project"] == project


def test_a_spoken_order_waits_its_turn_and_never_answers_the_card(workspace):
    workspace._run = {"mission": 1, "order": "x", "steps": [], "thinking": False, "started": time.time()}
    assert "still on the last order" in workspace.spoken("open Notepad") and workspace.core.orders == []
    workspace._run = None
    from kairu.workspace.server import _VoiceScreen
    screen = _VoiceScreen(workspace)
    workspace._card = {"id": "c"}
    assert screen.card_open() and not hasattr(screen, "answer") and not hasattr(screen, "approve")
    workspace._card = None


def test_the_mic_goes_off_when_no_window_has_been_open_for_a_while(workspace, monkeypatch):
    from kairu.workspace import server as workspace_server
    monkeypatch.setattr(workspace_server, "WINDOW_GONE_SECONDS", 0.5)
    workspace.voice = StandInVoice()
    workspace.voice.state = "on"
    threading.Thread(target=workspace._watch_windows, daemon=True).start()
    workspace.overview()
    wait_for(lambda: workspace.voice.state == "off", timeout=5)
    assert workspace.voice.off == ["Mic off: no workspace window is open."]
    workspace._voice_closed.set()
    assert WINDOW_GONE_SECONDS >= 10


def test_stop_switches_the_mic_off_too(workspace):
    workspace.voice = StandInVoice()
    workspace.voice.state = "on"
    workspace.stop()
    wait_for(lambda: workspace.voice.state == "off", timeout=5)
    assert "mic is off" in workspace.voice.off[0]


def test_the_voices_lines_name_the_windows_own_key(workspace):
    from kairu.workspace.server import _VoiceScreen
    _VoiceScreen(workspace).say('Mic on. Say "Kairu", or press Ctrl+Alt+V.')
    assert workspace._voice_line == 'Mic on. Say "Kairu", or press Ctrl+M.'


# --- one mic for the bar and the workspace ---------------------------------------------------------------------------------

class StartingGuardian:
    """voice.listen is started and keeps starting: the mic stays in "starting", holding the voice link."""

    def status(self):
        return {"mode": "normal"}

    def run(self, action, approval=None):
        return {"run": 7}

    def run_status(self, run):
        return {"outcome": None}

    def end(self, run):
        pass


class Screen:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def heard(self, text):
        pass

    def show(self):
        pass

    def mic_shown(self, on):
        pass

    def card_open(self):
        return False

    def busy(self):
        return False


@pytest.mark.skipif(sys.platform == "win32", reason="the socket file is Linux's voice link; Windows' pipe is the same rule")
def test_the_link_is_held_only_while_a_mic_is_on_and_the_other_window_is_told(config):
    from kairu.bar.voice import MIC_ELSEWHERE, VoiceControl
    bar_screen, workspace_screen = Screen(), Screen()
    bar = VoiceControl(config, StartingGuardian(), StandInCore(), bar_screen)
    in_workspace = VoiceControl(config, StartingGuardian(), StandInCore(), workspace_screen)
    try:
        assert bar.server is None and in_workspace.server is None  # nothing is held while both mics are off
        bar.mic_button()
        assert bar.state == "starting" and bar.server is not None
        in_workspace.mic_button()
        assert in_workspace.state == "off" and workspace_screen.said[-1] == MIC_ELSEWHERE
        bar.mic_off()
        wait_for(lambda: bar.server is None, timeout=5)
        in_workspace.mic_button()
        assert in_workspace.state == "starting"
    finally:
        bar.close()
        in_workspace.close()


@pytest.mark.skipif(sys.platform == "win32", reason="the socket file is Linux's voice link")
def test_a_second_claim_of_the_link_is_told_apart_from_other_problems(tmp_path):
    held = link.Server(tmp_path)
    try:
        with pytest.raises(link.LinkTaken):
            link.Server(tmp_path)
    finally:
        held.close()
    with pytest.raises(link.LinkError) as problem:
        link.Server(tmp_path / "missing")
    assert not isinstance(problem.value, link.LinkTaken)


# --- open the workspace ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("said_it", ["open the workspace", "Kairu, open the workspace", "open my kairu workspace please",
                                     "show the workspace", "launch the Kairu app"])
def test_open_the_workspace_is_heard(said_it):
    assert app.OPEN_WORKSPACE.fullmatch(said_it)


@pytest.mark.parametrize("not_it", ["open Notepad", "open the workspace folder and delete it", "workspace"])
def test_nothing_else_opens_it(not_it):
    assert not app.OPEN_WORKSPACE.fullmatch(not_it)


def test_in_the_workspace_it_is_already_open(workspace):
    mission = workspace.order(None, "open the workspace")["mission"]
    workspace.wait(5)
    assert workspace.core.orders == [] and workspace.store.messages(mission)[-1]["text"] == YOU_ARE_IN_IT


def test_the_bar_opens_it_with_the_same_start_as_kairu_workspace(config, monkeypatch):
    pytest.importorskip("tkinter")
    from tests_kairu.test_bar import StandInCore as BarCore, make_bar
    started = []
    monkeypatch.setattr(app, "open_or_start", lambda cfg, config_file=None: started.append(cfg) or (True, "The workspace is open."))
    bar = make_bar(config, core=BarCore())
    try:
        assert bar.handle("Kairu, open the workspace") == "The workspace is open." and started and bar.core.orders == []
        assert bar.handle("open Notepad") == "Done." and bar.core.orders == ["open Notepad"]
    finally:
        bar.close()


def test_the_window_keeps_its_timers_while_hidden_so_the_mic_rule_counts_real_closing(tmp_path):
    arguments = app.window_arguments(tmp_path, "http://127.0.0.1:1/#key=x")
    assert "--disable-background-timer-throttling" in arguments and "--disable-renderer-backgrounding" in arguments


# --- Ember Glow --------------------------------------------------------------------------------------------------------

def test_ember_glow_is_blue_listening_red_working_and_gone_otherwise():
    from kairu.bar import ember
    voice = StandInVoice()
    assert ember.mode_of(False, None) is None and ember.mode_of(False, voice) is None
    voice.state = "starting"
    assert ember.mode_of(False, voice) == "listen"
    voice.state, voice.session = "on", True
    assert ember.mode_of(False, voice) == "listen" and ember.mode_of(True, voice) == "work"
    voice.working = True
    assert ember.mode_of(False, voice) == "work"
    assert ember.blend("#4fc3ff", "#000000", 1) == "#4fc3ff" and ember.blend("#4fc3ff", "#000000", 0) == "#000000"


def test_the_pages_glass_bar_uses_the_owners_colours_and_no_inline_style():
    assert "--ember-blue: #4FC3FF; --ember-red: #FF4545;" in PAGE
    assert len(re.findall(r"\.embers span:nth-child\(\d+\)", PAGE)) == 13
    markup = PAGE[PAGE.index("<body>"):PAGE.index("<script")]
    assert ' style="' not in markup  # the CSP allows no style attribute: the embers are placed by the stylesheet
    assert 'id="glass"' in markup and "renderGlass()" in PAGE


def test_a_narrow_window_still_reaches_the_panel_with_its_own_button():
    """The owner's PC (11 Nov 2026): at Windows' display scaling the window is under 980 px wide, where the panel was hidden
    with no way to open it. Now a "Files & progress" button opens it over the mission."""
    narrow = PAGE[PAGE.index("@media (max-width: 980px) {"):]
    assert ".body.panel-open .panel { display: block; }" in narrow and ".panel-btn.can { display: inline-block; }" in narrow
    assert 'id="panel-btn"' in PAGE and '$("panel-btn").addEventListener("click"' in PAGE


def test_a_program_is_refused_by_its_kind_even_when_it_is_not_there(data, work, desk):
    """The owner's gate test (11 Nov 2026): `open file notepad.exe` said "there is no notepad.exe"; the kind decides first."""
    assert actions.open_file(str(data), JOB, "notepad.exe", str(work)) == actions.REFUSED
    assert "never opens programs, scripts or shortcuts" in said(data).text


def test_clicking_a_files_name_sends_the_same_order_as_open():
    panel = PAGE[PAGE.index("// Files (W2)"):PAGE.index('const needs = el("section");')]
    assert panel.count('sendText("open the " + (folder ? "folder" : "file")') == 2
