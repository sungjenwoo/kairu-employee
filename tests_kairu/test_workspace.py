"""The Kairu App workspace (W1, WORKSPACE.md): its store, its server's locks, the order that runs, and Guardian's card.

Guardian and the task core are stand-ins here, except for Stop, which writes the real stop;
tests_kairu/test_workspace_program.py runs orders through the real Guardian on a pretend PC.
"""

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from kairu import channel, safemode
from kairu.config import ROOT
from kairu.guardian import Action, Approval, Decision, Refused, Verdict
from kairu.policy import Tier
from kairu.store import Store
from kairu.workspace import app, server as workspace_server
from kairu.workspace.server import Server, Workspace
from kairu.workspace.store import BadName, NotFound, WorkspaceStore, title_for
from tests_kairu.helpers import wait_for

PAGE = (ROOT / "kairu" / "workspace" / "page.html").read_text(encoding="utf-8")
SERVER = (ROOT / "kairu" / "workspace" / "server.py").read_text(encoding="utf-8")
DECISION = Decision(Verdict.NEEDS_APPROVAL, Action("system.restart", {"job": "a" * 16, "note": "a detail"}), Tier.HIGH,
                    "High tier", "Restart this PC", "request-1")


class StandInGuardian:
    def __init__(self):
        self.mode, self.down, self.approved = "normal", False, []

    def status(self):
        if self.down:
            raise channel.NotRunning("not running")
        return {"mode": self.mode, "safe_reason": "a test"}

    def approve(self, request_id, confirmation, pin):
        self.approved.append((request_id, confirmation, pin))
        if confirmation.strip().lower() != "yes":
            raise Refused('not approved: you did not type "yes"')
        if pin != "482916":
            raise Refused("wrong PIN")
        return Approval("token", "system.restart", time.time() + 60)


class StandInCore:
    """Says what it was told; or, with `then`, does something first (opens the card, tells its progress)."""

    def __init__(self):
        self.orders, self.reply, self.then = [], "Done.", None

    def handle(self, order):
        self.orders.append(order)
        if self.then:
            return self.then(order)
        return self.reply


@pytest.fixture
def workspace(config):
    made = Workspace(config, client=StandInGuardian(), core=StandInCore())
    yield made
    made.wait(5)


@pytest.fixture
def served(workspace):
    running = Server(workspace)
    thread = threading.Thread(target=running.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield running
    running.shutdown()
    running.server_close()


def call(running, path, body=None, key=None, host=None, kind="application/json", raw=None):
    """An HTTP call to the test server: (status, JSON or text)."""
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(f"http://127.0.0.1:{running.port}{path}", data=data, method="POST" if data is not None else "GET")
    request.add_header("X-Kairu-Key", running.key if key is None else key)
    if data is not None:
        request.add_header("Content-Type", kind)
    if host:
        request.add_header("Host", host)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as reply:
            text, status = reply.read().decode(), reply.status
    except urllib.error.HTTPError as error:
        text, status = error.read().decode(), error.code
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


# --- the store ---------------------------------------------------------------------------------------------

def test_projects_and_their_missions_are_kept(tmp_path):
    store = WorkspaceStore(tmp_path)
    project = store.add_project("  Google   Buildathon ", "due 13 Nov")
    assert project["name"] == "Google Buildathon" and project["notes"] == "due 13 Nov" and project["missions"] == 0
    mission = store.add_mission("Fill the form", project["id"])
    store.say(mission["id"], "you", "open Chrome")
    store.say(mission["id"], "step", "open Chrome", "done")
    store.say(mission["id"], "kairu", "Opened Chrome.")
    assert [m["who"] for m in store.messages(mission["id"])] == ["you", "step", "kairu"]
    assert store.messages(mission["id"], after=store.messages(mission["id"])[1]["id"])[0]["text"] == "Opened Chrome."
    assert store.project(project["id"])["missions"] == 1 and store.missions(project=project["id"])[0]["id"] == mission["id"]
    assert WorkspaceStore(tmp_path).projects()[0]["name"] == "Google Buildathon"  # kept across starts


def test_renaming_archiving_and_deleting_a_project_keeps_its_missions(tmp_path):
    store = WorkspaceStore(tmp_path)
    project = store.add_project("Old name")
    mission = store.add_mission("Something", project["id"])
    assert store.change_project(project["id"], name="New name")["name"] == "New name"
    store.change_project(project["id"], archived=True)
    assert store.projects() == [] and store.projects(archived=True)[0]["id"] == project["id"]
    store.delete_project(project["id"])
    assert store.mission(mission["id"])["project"] is None
    with pytest.raises(NotFound):
        store.project(project["id"])


def test_a_mission_can_move_between_projects_and_deleting_it_deletes_what_was_said(tmp_path):
    store = WorkspaceStore(tmp_path)
    one, two = store.add_project("One"), store.add_project("Two")
    mission = store.add_mission("Moving", one["id"])
    store.say(mission["id"], "you", "hello")
    assert store.change_mission(mission["id"], project=two["id"])["project"] == two["id"]
    assert store.change_mission(mission["id"], no_project=True)["project"] is None
    store.delete_mission(mission["id"])
    with pytest.raises(NotFound):
        store.mission(mission["id"])
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_names_are_checked(tmp_path):
    store = WorkspaceStore(tmp_path)
    for bad in ("", "   ", "x" * 81):
        with pytest.raises(BadName):
            store.add_project(bad)
    with pytest.raises(NotFound):
        store.add_mission("x", project=999)
    assert title_for("open Notepad and set volume to 20 then close it") == "open Notepad and set volume to 20 then…"
    assert title_for("what's open?") == "what's open" and title_for("   ") == "New mission"


def test_search_finds_titles_and_messages_and_treats_wildcards_as_text(tmp_path):
    store = WorkspaceStore(tmp_path)
    first = store.add_mission("Hackathon slides")
    second = store.add_mission("Other")
    store.say(second["id"], "you", "find pdfs from today")
    assert [m["id"] for m in store.search("hackathon")] == [first["id"]]
    assert [m["id"] for m in store.search("pdfs")] == [second["id"]]
    assert store.search("%") == [] and store.search("_") == [] and store.search("") == []


@pytest.mark.skipif(sys.platform == "win32", reason="file modes are Linux's")
def test_the_file_is_readable_by_you_only(tmp_path):
    WorkspaceStore(tmp_path)
    assert oct((tmp_path / "workspace.db").stat().st_mode & 0o777) == "0o600"


# --- who may talk to the server ----------------------------------------------------------------------------

def test_the_server_listens_on_127_0_0_1_only(served):
    assert served.server_address[0] == "127.0.0.1" and served.url().startswith(f"http://127.0.0.1:{served.port}/#key=")


def test_without_the_key_the_api_answers_nothing(served):
    for key in ("", "wrong", served.key[:-1] + ("a" if served.key[-1] != "a" else "b")):
        status, reply = call(served, "/api/state", key=key)
        assert status == 401 and "projects" not in str(reply)
        status, _ = call(served, "/api/order", {"text": "restart"}, key=key)
        assert status == 401
    assert served.workspace.core.orders == []


def test_a_name_that_only_points_at_127_0_0_1_is_refused(served):
    for host in ("evil.example", f"evil.example:{served.port}", f"127.0.0.1:{served.port + 1}"):
        status, _ = call(served, "/api/state", host=host)
        assert status == 403
        status, _ = call(served, "/", host=host)
        assert status == 403
    assert call(served, "/api/state", host=f"localhost:{served.port}")[0] == 200


def test_the_page_has_a_strict_policy_and_no_key_in_it(served):
    request = urllib.request.Request(f"http://127.0.0.1:{served.port}/")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as reply:
        page, policy = reply.read().decode(), reply.headers["Content-Security-Policy"]
        assert reply.headers["X-Frame-Options"] == "DENY" and reply.headers["Cache-Control"] == "no-store"
    nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
    assert f'nonce="{nonce}"' in page and "{{NONCE}}" not in page and served.key not in page
    assert "default-src 'none'" in policy and "frame-ancestors 'none'" in policy and "unsafe" not in policy


def test_only_json_of_a_sensible_size_is_read(served):
    assert call(served, "/api/projects", raw=b"name=x", kind="application/x-www-form-urlencoded")[0] == 400
    assert call(served, "/api/projects", raw=b"not json")[0] == 400
    assert call(served, "/api/projects", raw=json.dumps({"name": "x" * 70000}).encode())[0] == 400
    assert call(served, "/api/projects", raw=b"[1, 2]")[0] == 400


def test_projects_and_missions_through_the_api(served):
    status, made = call(served, "/api/projects", {"name": "College fest", "notes": "site"})
    assert status == 200
    number = made["project"]["id"]
    assert call(served, f"/api/projects/{number}", {"name": "Fest 2026"})[1]["project"]["name"] == "Fest 2026"
    assert call(served, "/api/projects", {"name": ""})[0] == 400
    assert call(served, "/api/projects/999")[0] == 404
    status, state = call(served, "/api/state")
    assert state["projects"][0]["name"] == "Fest 2026" and state["guardian"]["state"] == "running" and state["card"] is None


# --- an order ----------------------------------------------------------------------------------------------

def test_an_order_starts_a_mission_in_its_project_and_kairus_answer_is_kept(served, workspace):
    project = call(served, "/api/projects", {"name": "Hackathon"})[1]["project"]["id"]
    workspace.core.reply = "Opened Notepad. Volume 20."
    status, reply = call(served, "/api/order", {"text": "open Notepad and set volume to 20", "project": project})
    assert status == 200
    mission = reply["mission"]
    wait_for(lambda: call(served, "/api/state")[1]["run"] is None)
    shown = call(served, f"/api/missions/{mission}")[1]
    assert shown["mission"]["project"] == project and shown["mission"]["title"] == "open Notepad and set volume to 20"
    assert [(m["who"], m["text"]) for m in shown["messages"]] == [("you", "open Notepad and set volume to 20"),
                                                                  ("kairu", "Opened Notepad. Volume 20.")]
    assert workspace.core.orders == ["open Notepad and set volume to 20"]


def test_one_order_at_a_time(served, workspace):
    go = threading.Event()
    workspace.core.then = lambda order: go.wait(5) and "Done."
    mission = call(served, "/api/order", {"text": "first"})[1]["mission"]
    status, reply = call(served, "/api/order", {"mission": mission, "text": "second"})
    assert status == 409 and "still on the last order" in reply["error"]
    go.set()
    wait_for(lambda: call(served, "/api/state")[1]["run"] is None)
    assert workspace.core.orders == ["first"]


def test_an_empty_or_long_order_is_refused(served, workspace):
    assert call(served, "/api/order", {"text": "   "})[0] == 400
    assert call(served, "/api/order", {"text": "x" * 2001})[0] == 400
    assert workspace.core.orders == []


def test_saying_stop_is_what_kairu_stop_does_even_while_an_order_runs(served, workspace, config):
    store = Store(config.data_dir)
    before = safemode.stop_count(store)
    go = threading.Event()
    workspace.core.then = lambda order: go.wait(5) and "Done."
    call(served, "/api/order", {"text": "something slow"})
    status, reply = call(served, "/api/order", {"text": "Kairu, stop"})
    assert status == 200 and reply["stopped"].startswith("Stopped everything")
    assert safemode.stop_count(store) == before + 1 and safemode.is_safe(store)
    go.set()


def test_the_stop_button_is_what_kairu_stop_does(served, config):
    store = Store(config.data_dir)
    before = safemode.stop_count(store)
    status, reply = call(served, "/api/stop", {})
    assert status == 200 and "Stopped" in reply["text"] and safemode.stop_count(store) == before + 1


def test_the_steps_show_while_they_run_and_are_kept_when_finished(served, workspace):
    seen = {}

    def work(order):
        tell = workspace._progress
        tell({"kind": "steps", "steps": [{"action": "apps.open", "label": "open Notepad"}, {"action": "system.volume", "label": "volume 20"}]})
        tell({"kind": "step", "number": 1, "state": "running", "text": ""})
        seen["running"] = call(served, "/api/state")[1]["run"]["steps"]
        tell({"kind": "step", "number": 1, "state": "done", "text": "Opened Notepad."})
        tell({"kind": "step", "number": 2, "state": "running", "text": ""})
        tell({"kind": "step", "number": 2, "state": "not done", "text": "Volume can't be 200."})
        tell({"kind": "step", "number": 9, "state": "done", "text": "no such step"})
        return "Opened Notepad. Volume can't be 200."

    workspace.core.then = work
    mission = call(served, "/api/order", {"text": "open Notepad and set volume to 200"})[1]["mission"]
    wait_for(lambda: call(served, "/api/state")[1]["run"] is None)
    assert seen["running"] == [{"label": "open Notepad", "state": "running", "text": ""}, {"label": "volume 20", "state": "waiting", "text": ""}]
    messages = call(served, f"/api/missions/{mission}")[1]["messages"]
    assert [(m["who"], m["text"], m["state"]) for m in messages] == [
        ("you", "open Notepad and set volume to 200", ""), ("step", "open Notepad", "done"), ("step", "volume 20", "not done"),
        ("kairu", "Opened Notepad. Volume can't be 200.", "")]


def test_progress_that_goes_wrong_never_stops_the_core():
    from kairu.tasks.core import TaskCore

    def broken(event):
        raise RuntimeError("a broken window")

    core = TaskCore.__new__(TaskCore)
    core.progress = broken
    core._tell({"kind": "thinking"})  # nothing raised


def test_a_crash_in_the_core_is_an_answer_not_a_dead_workspace(served, workspace):
    def crash(order):
        raise ValueError("boom")

    workspace.core.then = crash
    mission = call(served, "/api/order", {"text": "x"})[1]["mission"]
    wait_for(lambda: call(served, "/api/state")[1]["run"] is None)
    assert "Something went wrong" in call(served, f"/api/missions/{mission}")[1]["messages"][-1]["text"]
    assert call(served, "/api/order", {"mission": mission, "text": "again"})[0] == 200


def test_guardian_down_or_in_safe_mode_shows(served, workspace):
    workspace.client.mode = "safe"
    assert call(served, "/api/state")[1]["guardian"] == {"state": "safe", "text": "Safe Mode: a test"}
    workspace.client.down = True
    assert call(served, "/api/state")[1]["guardian"]["state"] == "down"


# --- the card: only your own typing fills it ---------------------------------------------------------------

def open_card(served, workspace, ask=None):
    """An order whose core asks for approval; returns (the card as the window sees it, the box the result goes in)."""
    box = {}

    def work(order):
        try:
            box["result"] = (ask or (lambda: workspace.ask_approval(DECISION)))()
        except Refused as refusal:
            box["refused"] = str(refusal)
        box["done"] = True
        return "Finished."

    workspace.core.then = work
    call(served, "/api/order", {"text": "restart"})
    wait_for(lambda: call(served, "/api/state")[1]["card"] is not None)
    return call(served, "/api/state")[1]["card"], box


def test_the_card_shows_the_action_and_never_what_was_typed(served, workspace):
    card, box = open_card(served, workspace)
    assert card["heading"] == "Guardian asks for your approval" and card["with_pin"] is True
    text = "\n".join(card["lines"])
    assert "system.restart: Restart this PC" in text and "note: a detail" in text and "High" in text and "job" not in text
    assert set(card) == {"id", "heading", "lines", "with_pin", "seconds_left"}
    call(served, "/api/answer", {"card": card["id"], "go_on": False})
    wait_for(lambda: box.get("done"))


def test_yes_and_the_pin_go_to_guardian_and_are_then_forgotten(served, workspace):
    card, box = open_card(served, workspace)
    status, reply = call(served, "/api/answer", {"card": card["id"], "go_on": True, "yes": "yes", "pin": "482916"})
    assert status == 200 and reply == {"ok": True}
    wait_for(lambda: box.get("done"))
    assert box["result"].token == "token" and workspace.client.approved == [("request-1", "yes", "482916")]
    assert call(served, "/api/state")[1]["card"] is None and workspace._card is None


def test_refusing_tells_guardian_and_approves_nothing(served, workspace):
    card, box = open_card(served, workspace)
    call(served, "/api/answer", {"card": card["id"], "go_on": False, "yes": "yes", "pin": "482916"})
    wait_for(lambda: box.get("done"))
    assert box["result"] is None and workspace.client.approved == [("request-1", "", "")]


def test_a_wrong_pin_is_refused_and_says_why(served, workspace):
    card, box = open_card(served, workspace)
    call(served, "/api/answer", {"card": card["id"], "go_on": True, "yes": "yes", "pin": "000000"})
    wait_for(lambda: box.get("done"))
    assert box["refused"] == "wrong PIN"


def test_an_answer_to_another_card_does_nothing(served, workspace):
    card, box = open_card(served, workspace)
    status, reply = call(served, "/api/answer", {"card": "0" * 16, "go_on": True, "yes": "yes", "pin": "482916"})
    assert status == 409 and reply == {"ok": False} and not box.get("done")
    call(served, "/api/answer", {"card": card["id"], "go_on": False})
    wait_for(lambda: box.get("done"))
    assert call(served, "/api/answer", {"card": card["id"], "go_on": True, "yes": "yes", "pin": "482916"})[0] == 409
    assert workspace.client.approved == [("request-1", "", "")]


def test_a_card_nobody_answers_ends_as_a_refusal(served, workspace, monkeypatch):
    monkeypatch.setattr(workspace_server, "CARD_SECONDS", 0.6)
    card, box = open_card(served, workspace)
    wait_for(lambda: box.get("done"))
    assert box["result"] is None and workspace.client.approved == [("request-1", "", "")]
    assert call(served, "/api/state")[1]["card"] is None


def test_the_warning_card_needs_yes_and_no_pin(served, workspace):
    card, box = open_card(served, workspace, lambda: workspace.ask_confirmation("Wi-Fi off drops your phone's link."))
    assert card["with_pin"] is False and "Wi-Fi" in card["lines"][0]
    call(served, "/api/answer", {"card": card["id"], "go_on": True, "yes": "yes"})
    wait_for(lambda: box.get("done"))
    assert box["result"] is True and workspace.client.approved == []


def test_a_plan_card_shows_the_whole_plan(served, workspace):
    plan = "Plan: 1) put a.txt in the Recycle Bin (High)."
    card, box = open_card(served, workspace, lambda: workspace.ask_plan_approval(DECISION, plan))
    assert card["heading"] == "Guardian asks for your approval of this plan" and card["lines"][0] == plan
    assert "Yes runs the whole plan." in card["lines"][-1]
    call(served, "/api/answer", {"card": card["id"], "go_on": False})
    wait_for(lambda: box.get("done"))


def test_nothing_in_the_page_can_fill_or_press_the_card():
    """Read from the code: the two boxes are only read and emptied, and no button is pressed by code."""
    script = PAGE[PAGE.index("<script"):]
    for box in ("yesBox", "pinBox"):
        written = re.findall(rf"\b{box}\.value\s*=(?!=)\s*([^;]+);", script)
        assert written and all(value.strip() == '""' for value in written), (box, written)
        assert not re.search(rf"\b{box}\.(defaultValue|setRangeText|dispatchEvent)\b", script)
        assert not re.search(rf"\b{box}\.setAttribute\(\s*[\"'](value|autocomplete)", script)  # aria-label only
    assert ".click(" not in script and "dispatchEvent" not in script and "execCommand" not in script
    assert "new Event(" not in script and "KeyboardEvent" not in script


def test_the_page_never_turns_data_into_markup():
    """Names, orders, answers, window titles and file names are data: shown with textContent, never as HTML."""
    script = PAGE[PAGE.index("<script"):]
    for writer in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert writer not in script, writer
    assert "setAttribute(\"style\"" not in script and "setAttribute('style'" not in script


def test_the_server_never_keeps_or_shows_what_was_typed():
    public = SERVER[SERVER.index("def _public_card"):SERVER.index("# --- HTTP")]
    assert '"yes"' not in public and '"pin"' not in public
    assert "def log_message" in SERVER and "body.clear()" in SERVER


# --- the program -------------------------------------------------------------------------------------------

def test_the_state_file_is_yours_and_is_read_back(tmp_path):
    path = app.write_state(tmp_path, 51234, "a-key")
    assert app.read_state(tmp_path) == {"port": 51234, "key": "a-key", "pid": os.getpid()}
    if sys.platform != "win32":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
    path.write_text("{not json")
    assert app.read_state(tmp_path) is None


def test_the_window_has_a_profile_of_its_own(tmp_path):
    arguments = app.window_arguments(tmp_path, "http://127.0.0.1:5000/#key=x")
    assert arguments[0] == "--app=http://127.0.0.1:5000/#key=x"
    assert f"--user-data-dir={(tmp_path / 'workspace-profile').resolve()}" in arguments
    assert "browser-profile" not in " ".join(arguments)


def test_tests_never_open_a_window(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIRU_TEST_PC", str(tmp_path))
    (tmp_path / "pc.json").write_text("{}")
    assert app.open_window(tmp_path, "http://127.0.0.1:1/") == "none (test)"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows holds a named mutex; this checks the Linux lock")
def test_only_one_workspace_runs(tmp_path):
    first = app.OneWorkspace(tmp_path)
    second = app.OneWorkspace(tmp_path)
    assert first.held is not None and second.held is None
    first.release()
    third = app.OneWorkspace(tmp_path)
    assert third.held is not None
    third.release()


def test_kairu_workspace_talks_to_a_running_one_with_its_key(served, config):
    app.write_state(config.data_dir, served.port, served.key)
    state = app.read_state(config.data_dir)
    assert app.call(state, "/api/ping") == {"ok": True}
    assert app.call({**state, "key": "wrong"}, "/api/ping") is None
    opened = []
    served.workspace.open_window = lambda: opened.append(True)
    assert app.call(state, "/api/open", {}) == {"ok": True} and opened == [True]
