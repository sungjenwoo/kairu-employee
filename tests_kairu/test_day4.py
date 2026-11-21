"""Sprint Day 4's parts: file skills in the work folder, Kairu's own browser, the Recycle Bin, free-form plans.

Every skill here works on a pretend PC (kairu/tasks/pc.py, StandIn) and a pretend Recycle Bin (kairu/tasks/recycle.py,
FakeBin): no test opens a browser or empties a Bin. A few Windows-only tests use the real Bin and the real Shell, on files
they make themselves. tests_kairu/test_day4_program.py runs the same skills through the real Guardian program.
"""

import json
import os
import re
import struct
import sys
import time
from pathlib import Path

import pytest

from kairu import executors, policy
from kairu.config import ROOT
from kairu.policy import Tier
from kairu.tasks import actions, core, fence, pc, plan, recycle, skills, web
from kairu.tasks.store import TaskStore
from tests_kairu.helpers import POLICY

RULES = policy.load(POLICY).rules
USABLE, REFUSED = skills.check(skills.SKILLS, RULES)
USABLE_ACTIONS = {skill.action for skill in USABLE}
JOB = "b" * 16
BROWSER = "C:/Program Files/Google/Chrome/Application/chrome.exe"


def steps_of(order):
    return [(step.action, step.details) for step in core.understand(order, USABLE).steps]


@pytest.fixture
def desk(tmp_path, monkeypatch):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "pc.json").write_text(json.dumps({"windows": [], "apps": {}, "browsers": {"chrome": BROWSER}}))
    monkeypatch.setenv(pc.TEST_PC, str(folder))
    return folder


@pytest.fixture
def data(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def work(tmp_path):
    return fence.work_folder(tmp_path / "Kairu-files")


def calls(desk):
    log = desk / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def said(data):
    return TaskStore(data).take_reply(JOB)


# --- the policy: tiers, private, read-only -------------------------------------------------------------

@pytest.mark.parametrize("name,tier,read_only", [
    ("files.find", Tier.LOW, True), ("files.move", Tier.MEDIUM, False), ("files.delete", Tier.HIGH, False),
    ("web.open", Tier.MEDIUM, False), ("web.search", Tier.MEDIUM, False), ("web.search_private", Tier.HIGH, False),
    ("task.wait", Tier.LOW, True), ("brain.plan", Tier.LOW, False), ("task.plan", Tier.LOW, False),
])
def test_each_new_action_has_its_tier_and_keeps_only_a_hash_of_your_words(name, tier, read_only):
    rule = RULES[name]
    assert rule.tier is tier and rule.read_only is read_only and rule.private


def test_files_delete_is_still_high_and_no_new_skill_is_critical():
    assert RULES["files.delete"].tier is Tier.HIGH and REFUSED == ()
    assert not [skill.action for skill in skills.SKILLS if RULES[skill.action].tier is Tier.CRITICAL]


def test_the_work_folder_and_the_browser_profile_are_supplied_by_guardian_never_by_a_request():
    for name in ("files.find", "files.move", "files.delete"):
        assert "work_folder" in executors.EXECUTORS[name].supplied and "work_folder" not in executors.EXECUTORS[name].arguments
    for name in ("web.open", "web.search", "web.search_private"):
        assert executors.EXECUTORS[name].supplied == ("data_dir",) and set(executors.EXECUTORS[name].arguments) <= {"job", "url", "query"}


def test_the_plans_details_agree_with_what_guardian_runs():
    for action in plan.PLANNABLE:
        assert action in USABLE_ACTIONS and RULES[action].tier is not Tier.CRITICAL
        assert set(plan.DETAILS[action]) == set(executors.EXECUTORS[action].arguments) - {"job"}, action


def test_a_plan_can_never_hold_power_wifi_undo_or_a_private_search():
    for action in ("system.shutdown", "system.restart", "system.sleep", "system.wifi", "task.undo", "web.search_private",
                   "brain.ask", "brain.send_private", "money.spend"):
        assert action not in plan.PLANNABLE


# --- understanding the orders -----------------------------------------------------------------------------

@pytest.mark.parametrize("order,expected", [
    ("find report", [("files.find", {"what": "report", "when": ""})]),
    ("find pdfs from today", [("files.find", {"what": "pdfs", "when": "today"})]),
    ("list my files", [("files.find", {"what": "", "when": ""})]),
    ("move a.txt to notes", [("files.move", {"name": "a.txt", "to": "notes"})]),
    ("move *.pdf into pdfs", [("files.move", {"name": "*.pdf", "to": "pdfs"})]),
    ("delete a.txt", [("files.delete", {"name": "a.txt"})]),
    ("delete the folder notes", [("files.delete", {"name": "notes"})]),
    ("open youtube", [("web.open", {"url": "youtube"})]),
    ("open github.com", [("web.open", {"url": "github.com"})]),
    ("open javascript:alert(1)", [("web.open", {"url": "javascript:alert(1)"})]),  # a skill, so that it is refused plainly
    ("google the weather in Hyderabad", [("web.search", {"query": "the weather in Hyderabad"})]),
    ("search the weather in Hyderabad on Google", [("web.search", {"query": "the weather in Hyderabad"})]),
    ("open Chrome and search the weather", [("apps.open", {"name": "Chrome"}), ("web.search", {"query": "the weather"})]),
    ("open github and search for python tutorials", [("web.open", {"url": "github"}), ("web.search", {"query": "python tutorials"})]),
    ("wait 10 seconds then volume 20", [("task.wait", {"seconds": "10"}), ("system.volume", {"setting": "20"})]),
    ("open Notepad", [("apps.open", {"name": "Notepad"})]),
    ("open google chrome", [("apps.open", {"name": "google chrome"})]),
    ("open Outlook", [("apps.open", {"name": "Outlook"})]),
])
def test_the_new_skills_answer_their_orders(order, expected):
    assert steps_of(order) == expected


@pytest.mark.parametrize("order", ["search the latest cricket news", "delete my files", "find the capital of France",
                                   "find out who won", "how do I open Notepad?", "delete all files"])
def test_questions_and_requests_still_go_to_the_brain(order):
    task = core.understand(order, USABLE)
    assert task.question == order and not task.steps


def test_a_search_after_something_that_is_not_a_browser_is_not_a_web_search():
    assert "web.search" not in [action for action, _ in steps_of("open Notepad and search the weather")]


@pytest.mark.parametrize("order", ["put all the pdfs in Kairu-files into a folder called pdfs", "organise my files into folders",
                                   "put all my screenshots into a new folder"])
def test_a_free_form_order_about_files_or_the_web_may_be_planned(order):
    task = core.understand(order, USABLE)
    assert task.plan and task.says == core.CANT and not task.steps


@pytest.mark.parametrize("order", ["tidy my desktop", "make my screen pretty", r"move all files from C:\Windows into pdfs",
                                   "put %TEMP% files in a folder", "open a & del files"])
def test_other_free_form_orders_and_any_with_a_path_are_never_sent_to_be_planned(order):
    task = core.understand(order, USABLE)
    assert task.says == core.CANT and not task.plan


def test_a_personal_search_becomes_the_high_search():
    personal = core._searched_privately(core.Step("web.search", {"query": "Ravi 9876543210 address"}))
    public = core._searched_privately(core.Step("web.search", {"query": "weather in Hyderabad"}))
    assert personal.action == "web.search_private" and public.action == "web.search"
    assert core.PERSONAL_SEARCH == actions.PERSONAL_SEARCH


# --- the plan the brain writes ----------------------------------------------------------------------------

GOOD = {"steps": [{"action": "files.find", "details": {"what": "*.pdf", "when": ""}},
                  {"action": "files.move", "details": {"name": "*.pdf", "to": "pdfs"}}]}


def test_a_good_plan_is_read_as_steps():
    assert plan.parse(json.dumps(GOOD), USABLE_ACTIONS) == [("files.find", {"what": "*.pdf", "when": ""}),
                                                           ("files.move", {"name": "*.pdf", "to": "pdfs"})]
    assert plan.parse("```json\n" + json.dumps(GOOD) + "\n```", USABLE_ACTIONS)[1][0] == "files.move"
    assert plan.parse('{"steps": [{"action": "files.find", "details": {"what": "report"}}]}', USABLE_ACTIONS) == [
        ("files.find", {"what": "report", "when": ""})]
    assert plan.parse('{"steps": []}', USABLE_ACTIONS) == []


@pytest.mark.parametrize("answer,why", [
    ('{"steps": [{"action": "files.wipe", "details": {"name": "a"}}]}', "doesn't have"),
    ('{"steps": [{"action": "money.spend", "details": {}}]}', "doesn't have"),
    ('{"steps": [{"action": "system.shutdown", "details": {}}]}', "doesn't have"),
    ('{"steps": [{"action": "files.move", "details": {"name": "a.txt", "to": "b"}, "tier": "Low"}]}', "wasn't a skill"),
    ('{"steps": [{"action": "files.move", "details": {"name": "a.txt", "to": "b", "work_folder": "C:/"}}]}', "wrong details"),
    ('{"steps": [{"action": "files.move", "details": {"name": "a.txt"}}]}', "wrong details"),
    ('{"steps": [{"action": "files.move", "details": {"name": 5, "to": "b"}}]}', "isn't short text"),
    ('{"steps": [{"action": "web.open", "details": {"url": "x"}}], "tier": "Low"}', "wasn't a plan"),
    ("Sure! First I will find the files.", "wasn't a plan"),
    (json.dumps({"steps": [{"action": "task.wait", "details": {"seconds": "1"}}] * 9}), "more than 8"),
])
def test_a_plan_that_invents_a_skill_or_a_tier_or_a_detail_is_no_plan(answer, why):
    with pytest.raises(plan.NoPlan, match=why):
        plan.parse(answer, USABLE_ACTIONS)


def test_a_skill_refused_at_load_is_never_in_a_plan():
    with pytest.raises(plan.NoPlan):
        plan.parse(json.dumps(GOOD), USABLE_ACTIONS - {"files.move"})


def test_the_brain_is_told_only_the_plannable_skills():
    told = plan.instructions(plan.PLANNABLE)
    assert "files.move" in told and "web.search" in told and "system.shutdown" not in told and "web.search_private" not in told


def test_each_step_is_described_in_a_short_line():
    assert plan.describe("files.move", {"name": "*.pdf", "to": "pdfs"}) == "move *.pdf into pdfs"
    assert plan.describe("files.delete", {"name": "a.txt"}) == "put a.txt in the Recycle Bin"


# --- the fence: find, move ------------------------------------------------------------------------------

def make(folder: Path, *names: str) -> None:
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)


def test_find_looks_at_names_only_and_never_opens_a_file(work, monkeypatch):
    make(work, "tax report.pdf", "notes/report-2.txt", "photo.png")
    opened = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda *a, **k: opened.append(a) or real_open(*a, **k))
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: opened.append(self) or real_open(self, *a, **k))
    assert sorted(fence.find(work, (), ("report",), None)) == ["notes/report-2.txt", "tax report.pdf"]
    assert fence.find(work, ("*.pdf",), (), None) == ["tax report.pdf"]
    assert opened == []


def test_find_by_day(work):
    make(work, "old.pdf", "new.pdf")
    old = time.time() - 3 * 86400
    os.utime(work / "old.pdf", (old, old))
    assert fence.find(work, ("*.pdf",), (), time.time() - 86400) == ["new.pdf"]


def test_find_never_walks_into_a_link_that_leads_out(work, tmp_path):
    outside = tmp_path / "outside"
    make(outside, "secret-report.txt")
    try:
        os.symlink(outside, work / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account can't make symlinks")
    assert fence.find(work, (), ("report",), None) == []


def test_move_overwrites_nothing_and_moves_nothing_if_one_would_clash(work):
    make(work, "a.pdf", "b.pdf", "pdfs/b.pdf")
    with pytest.raises(FileExistsError, match="overwrites nothing"):
        fence.move(work, "*.pdf", "pdfs")
    assert (work / "a.pdf").exists() and (work / "pdfs" / "b.pdf").read_text() == "pdfs/b.pdf"


def test_move_makes_the_folder_inside_the_work_folder_only(work, tmp_path):
    make(work, "a.txt")
    for outside in ("../out", str(tmp_path / "out"), "..\\out", "C:/out", "/", "/tmp/out", "\\out", "notes\\..\\..\\out"):
        with pytest.raises(fence.OutsideFolder):
            fence.move(work, "a.txt", outside)
    assert not (tmp_path / "out").exists() and (work / "a.txt").exists()


def test_move_refuses_a_name_outside_the_work_folder(work, tmp_path):
    make(tmp_path, "outside.txt")
    for name in ("../outside.txt", str(tmp_path / "outside.txt"), "../*.txt"):
        with pytest.raises((fence.OutsideFolder, FileNotFoundError)):
            fence.move(work, name, "notes")
    assert (tmp_path / "outside.txt").exists()


def test_a_pattern_may_be_only_in_the_last_part_and_never_double_star(work):
    for pattern in ("*/a.txt", "**.txt", "a/**"):
        with pytest.raises(fence.OutsideFolder):
            fence.matching(work, pattern)


# --- the skills on the pretend PC and the pretend Bin -----------------------------------------------------

def test_find_says_what_it_found(data, work, desk):
    make(work, "a.pdf", "b.pdf", "c.txt")
    actions.find_files(str(data), JOB, "pdfs", "", str(work))
    reply = said(data)
    assert reply.ok and reply.text.startswith("Found 2:") and "a.pdf" in reply.text and "c.txt" not in reply.text
    actions.find_files(str(data), JOB, "report", "", str(work))
    assert said(data).text == "No report in your work folder."
    assert actions.find_files(str(data), JOB, "report", "next year", str(work)) is not None and not said(data).ok


def test_move_then_undo_puts_everything_back_and_removes_the_folder_it_made(data, work, desk):
    make(work, "a.pdf", "b.pdf", "keep.txt")
    actions.move_files(str(data), JOB, "*.pdf", "pdfs", str(work))
    assert said(data).text == "Moved 2 files into pdfs (a new folder)."
    assert sorted(os.listdir(work / "pdfs")) == ["a.pdf", "b.pdf"]
    actions.undo(str(data), JOB, str(work))
    assert said(data).text == "Undone: 2 files back where they were."
    assert (work / "a.pdf").exists() and (work / "b.pdf").exists() and not (work / "pdfs").exists()


def test_a_refused_move_is_a_refusal_and_records_no_undo(data, work, desk):
    make(work, "a.txt")
    assert actions.move_files(str(data), JOB, "../x.txt", "notes", str(work)) is actions.REFUSED
    assert said(data).text.startswith("Not moved") or said(data) is None
    assert actions.move_files(str(data), JOB, "a.txt", "../notes", str(work)) is actions.REFUSED
    assert said(data).text.startswith("Refused:") and TaskStore(data).undo_count() == 0


def test_delete_goes_to_the_bin_and_undo_brings_it_back(data, work, desk):
    make(work, "a.txt")
    actions.delete(str(data), JOB, "a.txt", str(work))
    assert said(data).text == 'The file a.txt is in the Recycle Bin. "undo" brings it back.'
    assert not (work / "a.txt").exists() and list((desk / "bin").rglob("a.txt"))
    actions.undo(str(data), JOB, str(work))
    assert said(data).text == "Undone: a.txt is back from the Recycle Bin." and (work / "a.txt").read_text() == "a.txt"


def test_a_folder_goes_to_the_bin_whole(data, work, desk):
    make(work, "notes/one.txt", "notes/two.txt")
    actions.delete(str(data), JOB, "notes", str(work))
    assert said(data).text.startswith("The folder notes is in the Recycle Bin") and not (work / "notes").exists()
    actions.undo(str(data), JOB, str(work))
    assert sorted(os.listdir(work / "notes")) == ["one.txt", "two.txt"]


def test_undo_says_plainly_when_the_bin_was_emptied(data, work, desk):
    make(work, "a.txt")
    actions.delete(str(data), JOB, "a.txt", str(work))
    said(data)
    for place in (desk / "bin").iterdir():  # as if you emptied the Recycle Bin
        for item in sorted(place.rglob("*"), reverse=True):
            item.unlink() if item.is_file() else item.rmdir()
        place.rmdir()
    assert actions.undo(str(data), JOB, str(work)) is actions.REFUSED
    assert said(data).text.startswith("Windows can't restore a.txt: it is no longer in the Recycle Bin")


def test_undo_never_overwrites_a_new_file_with_the_same_name(data, work, desk):
    make(work, "a.txt")
    actions.delete(str(data), JOB, "a.txt", str(work))
    said(data)
    (work / "a.txt").write_text("new")
    actions.undo(str(data), JOB, str(work))
    assert "overwrites nothing" in said(data).text and (work / "a.txt").read_text() == "new"


def test_where_there_is_no_bin_nothing_is_deleted(data, work, desk):
    make(work, "a.txt")
    (desk / "no-bin").write_text("")
    assert actions.delete(str(data), JOB, "a.txt", str(work)) is actions.REFUSED
    assert "Kairu never deletes for good" in said(data).text and (work / "a.txt").exists()


@pytest.mark.parametrize("name", ["../outside.txt", "*.txt", "", "C:/Windows/win.ini", "."])
def test_delete_refuses_outside_the_folder_patterns_and_the_folder_itself(data, work, desk, tmp_path, name):
    make(tmp_path, "outside.txt")
    make(work, "a.txt")
    assert actions.delete(str(data), JOB, name, str(work)) is actions.REFUSED
    assert (tmp_path / "outside.txt").exists() and (work / "a.txt").exists() and work.exists()
    assert not (desk / "bin").exists()


def test_there_is_no_permanent_delete_anywhere_in_the_task_code():
    for path in (ROOT / "kairu" / "tasks").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(?:os\.remove|os\.unlink|shutil\.rmtree|\.unlink\(|\.rmdir\(|os\.rmdir)", text) or path.name in (
            "recycle.py", "actions.py", "pc.py"), path.name
    action_code = (ROOT / "kairu" / "tasks" / "actions.py").read_text(encoding="utf-8")
    assert "os.remove" not in action_code and "shutil.rmtree" not in action_code and ".unlink(" not in action_code
    assert action_code.count(".rmdir()") == 1  # only the empty folder a move made, on its undo


# --- Kairu's own browser ------------------------------------------------------------------------------------

@pytest.mark.parametrize("given,url", [
    ("github.com", "https://github.com"), ("youtube", "https://www.youtube.com/"), ("https://example.org/a b", None),
    ("http://example.org/x?q=1", "http://example.org/x?q=1"), ("GitHub.com/sungjenwoo", "https://github.com/sungjenwoo"),
])
def test_an_address_is_http_or_https_and_one_argument(given, url):
    if url is None:
        with pytest.raises(web.NotAnAddress):
            web.address(given)
    else:
        assert web.address(given) == url


@pytest.mark.parametrize("given", ["javascript:alert(1)", "file:///C:/Windows/win.ini", "data:text/html,<b>x</b>",
                                   "ftp://example.org", "ms-settings:privacy", "vbscript:x", "chrome://settings",
                                   "https://user:pw@example.org", 'https://example.org/" --kiosk', "notepad.exe",
                                   "https://-evil.com", "about:blank"])
def test_any_other_address_is_refused(given):
    with pytest.raises(web.NotAnAddress):
        web.address(given)


def test_the_browser_gets_kairus_own_profile_and_the_address_last(data):
    argv = web.arguments(web.profile(data), "https://github.com")
    assert argv[0] == f"--user-data-dir={Path(data).resolve() / 'browser-profile'}" and argv[-1] == "https://github.com"
    with pytest.raises(web.NotAnAddress):
        web.arguments(web.profile(data), "--disable-web-security")


def test_web_open_starts_the_found_browser_with_kairus_profile(data, desk):
    actions.web_open(str(data), JOB, "github.com")
    assert said(data).text == "Opened github.com in Kairu's browser."
    [call] = calls(desk)
    assert call.startswith(f"browse {BROWSER} --user-data-dir=") and "browser-profile" in call and call.endswith(" https://github.com")
    assert "User Data" not in call  # never your own profile (Chrome's and Edge's are called "User Data")


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/x", "data:text/html,x"])
def test_web_open_refuses_other_addresses_and_starts_nothing(data, desk, url):
    assert actions.web_open(str(data), JOB, url) is actions.REFUSED
    assert said(data).text.startswith("Refused: Kairu opens only http and https") and calls(desk) == []


def test_without_chrome_or_edge_it_says_so(data, desk):
    (desk / "pc.json").write_text(json.dumps({"browsers": {}}))
    assert actions.web_open(str(data), JOB, "github.com") is actions.REFUSED and "Chrome or Edge" in said(data).text


def test_a_public_search_goes_to_google_in_kairus_browser(data, desk):
    actions.web_search(str(data), JOB, "weather in Hyderabad")
    assert said(data).ok and calls(desk)[0].endswith(" https://www.google.com/search?q=weather+in+Hyderabad")


def test_a_personal_search_is_not_searched_without_your_approval(data, desk):
    assert actions.web_search(str(data), JOB, "Ravi 9876543210 home address") is actions.REFUSED
    assert said(data).text.startswith(actions.PERSONAL_SEARCH) and calls(desk) == []
    actions.web_search_private(str(data), JOB, "Ravi 9876543210 home address")
    assert said(data).ok and len(calls(desk)) == 1


def test_a_secret_is_never_searched_even_with_your_approval(data, desk):
    for skill in (actions.web_search, actions.web_search_private):
        assert skill(str(data), JOB, "my password is Xk9#vLq2!mZ") is actions.REFUSED
        assert "Secrets never leave this PC" in said(data).text
    assert calls(desk) == []


def test_wait_waits_1_to_60_seconds(data, desk):
    for wrong in ("0", "61", "x", "-1"):
        assert actions.wait(str(data), JOB, wrong) is actions.REFUSED
    started = time.monotonic()
    actions.wait(str(data), JOB, "1")
    assert 0.9 < time.monotonic() - started < 3 and said(data).text == "Waited 1 seconds."


# --- the bar: typing "stop" --------------------------------------------------------------------------------

@pytest.mark.parametrize("typed,stops", [("stop", True), ("Stop!", True), ("Kairu, stop", True), ("kairu stop everything", True),
                                         ("cancel", True), ("stop chrome", False), ("bus stop near me", False)])
def test_typing_stop_in_the_bar_is_the_stop(typed, stops):
    from kairu.bar.app import STOP_WORDS
    assert bool(STOP_WORDS.fullmatch(typed)) is stops


# --- Windows: the real Recycle Bin and the real Shell, on files these tests make --------------------------

def test_a_recycle_bin_record_is_read_as_windows_writes_it(tmp_path):
    path = "C:\\Users\\me\\Kairu-files\\a.txt"
    filetime = int((1_700_000_000 + 11644473600) * 1e7)
    record = tmp_path / "$IABC123.txt"
    record.write_bytes(struct.pack("<qqqi", 2, 10, filetime, len(path) + 1) + (path + "\x00").encode("utf-16-le"))
    found = recycle.read_record(record)
    assert found[0] == path and abs(found[1] - 1_700_000_000) < 1
    record.write_bytes(b"not a record")
    assert recycle.read_record(record) is None


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the real Recycle Bin and Shell are Windows'")


@windows_only
def test_the_real_bin_takes_a_file_and_gives_it_back(tmp_path, monkeypatch):
    monkeypatch.delenv(pc.TEST_PC, raising=False)
    folder = fence.work_folder(tmp_path / "Kairu-files")
    item = folder / f"kairu-test-{os.getpid()}.txt"
    item.write_text("from a Kairu test; it puts itself back")
    bin_ = recycle.backend()
    assert isinstance(bin_, recycle.WindowsBin)
    try:
        token = bin_.recycle(item)
    except recycle.CannotRecycle as why:
        pytest.skip(f"this drive's Bin won't take it: {why}")
    try:
        assert not item.exists() and token
    finally:
        if not item.exists():  # whatever happened, the test's file never stays in your Recycle Bin
            token = token or bin_.find(item, time.time() - 60)
            if token:
                bin_.restore(token, item)
    assert item.read_text() == "from a Kairu test; it puts itself back"
    with pytest.raises(recycle.CannotRestore):
        bin_.restore(token, item)  # once only


@windows_only
def test_a_bin_token_for_another_place_is_refused(tmp_path):
    with pytest.raises(recycle.CannotRestore):
        recycle.WindowsBin().restore("C:|$IZZZZZZ.txt", tmp_path / "a.txt")
    with pytest.raises(recycle.CannotRestore):
        recycle.WindowsBin().restore("..\\..\\x", tmp_path / "a.txt")


@windows_only
def test_the_browser_shortcut_holds_the_path_and_the_arguments_as_given(tmp_path):
    link = tmp_path / "open.lnk"
    argv = ["--user-data-dir=C:\\Users\\me\\Kairu\\data\\browser-profile", "--no-first-run", "https://github.com/a?b=1&c=2"]
    pc.make_shortcut(link, BROWSER.replace("/", "\\"), pc.subprocess.list2cmdline(argv))
    target, arguments = pc.read_shortcut(link)
    assert target.lower() == BROWSER.replace("/", "\\").lower()
    assert arguments == pc.subprocess.list2cmdline(argv)


@windows_only
def test_the_browsers_are_found_only_where_they_are_installed():
    for name, path in pc.Windows().browsers().items():
        assert name in ("chrome", "edge") and Path(path).is_file() and path.lower().endswith(("chrome.exe", "msedge.exe"))


def test_the_planning_instructions_pass_the_backstop_scanner():
    """The scanner reads the whole text that leaves, instructions too: nothing in them may look like a secret."""
    from kairu.brain import privacy
    assert privacy.secrets_in(plan.instructions(plan.PLANNABLE)) == []
