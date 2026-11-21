"""Sprint Day 4 through the real Guardian program: files, Kairu's own browser, free-form plans and a stop in the middle.

KAIRU_TEST_PC is always set here, so the browser and the Recycle Bin are a pretend PC's (kairu/tasks/pc.py, recycle.py) and
the free AI is a stand-in on 127.0.0.1 (tests_kairu/fake_provider.py). Every step is decided and run by Guardian.
"""

import json
import threading
import time

import pytest
import yaml

from kairu import audit, safemode
from kairu.brain import keys
from kairu.guardian import Action, Refused, Verdict
from kairu.store import Store
from kairu.tasks import pc
from kairu.tasks.core import CANT, TaskCore
from tests_kairu.fake_provider import FakeProviders
from tests_kairu.helpers import PIN, POLICY, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)

GROQ_KEY = "gsk_" + "k" * 40
BROWSER = "C:/apps/chrome.exe"


@pytest.fixture
def providers(monkeypatch):
    fake = FakeProviders()
    monkeypatch.setenv("KAIRU_TEST_PROVIDERS", fake.url)
    yield fake
    fake.close()


@pytest.fixture
def desk(tmp_path, monkeypatch):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "pc.json").write_text(json.dumps({
        "windows": [{"app": "notepad", "title": "Untitled"}], "apps": {"notepad": "C:/Windows/notepad.exe"},
        "browsers": {"chrome": BROWSER}, "volume": 50}))
    monkeypatch.setenv(pc.TEST_PC, str(folder))
    return folder


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / "Kairu-files"
    folder.mkdir()
    return folder


@pytest.fixture
def config_path(tmp_path, monkeypatch, desk, work, providers):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "brain": {"public_to_cloud": True, "providers": ["groq"]},
                                    "tasks": {"work_folder": str(work)},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


class Owner:
    """What you would do at the bar's card: the tests choose. Records every card it was shown."""

    def __init__(self, program, yes=True, pin=PIN):
        self.program, self.yes, self.pin = program, yes, pin
        self.cards, self.plans, self.confirmed = [], [], []

    def approver(self, decision):
        self.cards.append(decision)
        return self.program.client.approve(decision.request_id, "yes", self.pin) if self.yes else None

    def plan_approver(self, decision, text):
        self.plans.append(text)
        return self.approver(decision)

    def confirmer(self, text):
        self.confirmed.append(text)
        return self.yes


@pytest.fixture
def owner(program_with_pin):
    keys.save(program_with_pin.data_dir, "groq", GROQ_KEY)
    return Owner(program_with_pin)


def core_for(program, owner) -> TaskCore:
    return TaskCore(program.config, program.client, approver=owner.approver, confirmer=owner.confirmer,
                    plan_approver=owner.plan_approver)


def calls(desk):
    log = desk / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def runs(data_dir, decision="started"):
    return [row for row in audit.tail(Store(data_dir), 3000, kind="run") if row["decision"] == decision]


def logged(data_dir) -> str:
    with Store(data_dir).connect() as db:
        return " ".join(str(row) for row in db.execute("SELECT * FROM audit"))


def make(folder, *names):
    for name in names:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(name)


# --- files -------------------------------------------------------------------------------------------------

def test_find_move_and_undo_through_guardian_and_the_log_keeps_no_file_names(program_with_pin, owner, work):
    make(work, "tax-report.pdf", "secret-plan.txt")
    core = core_for(program_with_pin, owner)
    assert core.handle("find report") == "Found 1: tax-report.pdf."
    assert core.handle("move secret-plan.txt to notes") == "Moved secret-plan.txt into notes (a new folder)."
    assert (work / "notes" / "secret-plan.txt").exists()
    assert core.handle("undo") == "Undone: 1 file back where it was."
    assert (work / "secret-plan.txt").exists() and not (work / "notes").exists()
    everything = logged(program_with_pin.data_dir)
    assert "tax-report" not in everything and "secret-plan" not in everything and audit.verify(Store(program_with_pin.data_dir)).ok
    assert [row["action"] for row in runs(program_with_pin.data_dir)][-3:] == ["files.find", "files.move", "task.undo"]


def test_delete_asks_for_yes_and_the_pin_and_refusing_deletes_nothing(program_with_pin, owner, work, desk):
    make(work, "a.txt")
    owner.yes = False
    assert core_for(program_with_pin, owner).handle("delete a.txt") == "Not done: you refused it."
    [card] = owner.cards
    assert card.verdict is Verdict.NEEDS_APPROVAL and card.tier == "High" and card.action.name == "files.delete"
    assert (work / "a.txt").exists() and "files.delete" not in [row["action"] for row in runs(program_with_pin.data_dir)]


def test_delete_with_the_pin_goes_to_the_bin_and_undo_brings_it_back(program_with_pin, owner, work, desk):
    make(work, "a.txt")
    core = core_for(program_with_pin, owner)
    assert core.handle("delete a.txt") == 'The file a.txt is in the Recycle Bin. "undo" brings it back.'
    assert not (work / "a.txt").exists() and len(owner.cards) == 1
    assert core.handle("undo") == "Undone: a.txt is back from the Recycle Bin." and (work / "a.txt").read_text() == "a.txt"


def test_deleting_a_folder_is_high_too(program_with_pin, owner, work, desk):
    make(work, "notes/one.txt")
    owner.yes = False
    assert "Not done" in core_for(program_with_pin, owner).handle("delete the folder notes")
    assert owner.cards[0].tier == "High" and (work / "notes" / "one.txt").exists()


def test_a_wrong_pin_deletes_nothing(program_with_pin, owner, work):
    make(work, "a.txt")
    owner.pin = "000000"
    reply = core_for(program_with_pin, owner).handle("delete a.txt")
    assert reply.startswith("Not done") and "PIN" in reply and (work / "a.txt").exists()


def asked_guardian(program, action):
    return [row for row in audit.tail(Store(program.data_dir), 3000) if row["action"] == action]


def test_a_move_outside_the_work_folder_is_refused_at_once_before_guardian_is_asked(program_with_pin, owner, work, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    core = core_for(program_with_pin, owner)
    for order in (f"move {outside} to notes", "move ../outside.txt to notes", "move ../*.txt to notes", "move a.txt to ../notes",
                  "move a.txt to C:/notes"):
        assert core.handle(order).startswith("Refused:"), order
    assert outside.read_text() == "not yours" and not (work / "notes").exists() and not (tmp_path / "notes").exists()
    assert asked_guardian(program_with_pin, "files.move") == []


@pytest.mark.parametrize("name", ["../outside.txt", "OUTSIDE", "C:/Windows/win.ini", "..\\outside.txt", "notes/../../outside.txt"])
def test_a_delete_outside_the_work_folder_is_refused_at_once_with_no_pin_card(program_with_pin, owner, work, tmp_path, name):
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    order = f"delete {outside}" if name == "OUTSIDE" else f"delete {name}"
    started = time.monotonic()
    reply = core_for(program_with_pin, owner).handle(order)
    assert reply.startswith("Refused:") and "outside your work folder" in reply and time.monotonic() - started < 2
    assert owner.cards == [] and asked_guardian(program_with_pin, "files.delete") == []  # no card, no PIN, Guardian never asked
    assert outside.read_text() == "not yours"


def test_a_delete_inside_the_work_folder_still_asks_for_the_pin(program_with_pin, owner, work):
    make(work, "notes/a.txt")
    owner.yes = False
    assert core_for(program_with_pin, owner).handle("delete notes/a.txt") == "Not done: you refused it."
    assert [card.action.name for card in owner.cards] == ["files.delete"] and (work / "notes" / "a.txt").exists()


def test_the_skills_own_fence_still_refuses_a_request_that_skips_the_core(program_with_pin, work, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    run = program_with_pin.client.run(Action("files.move", {"job": "e" * 16, "name": "../outside.txt", "to": "notes"}))
    wait_for(lambda: program_with_pin.client.run_status(run["run"])["outcome"] is not None, timeout=20)
    assert program_with_pin.client.run_status(run["run"])["outcome"] == "refused" and outside.read_text() == "not yours"
    action = Action("files.delete", {"job": "f" * 16, "name": "../outside.txt"})
    granted = program_with_pin.client.approve(program_with_pin.client.check(action).request_id, "yes", PIN)
    run = program_with_pin.client.run(action, granted)
    wait_for(lambda: program_with_pin.client.run_status(run["run"])["outcome"] is not None, timeout=20)
    assert program_with_pin.client.run_status(run["run"])["outcome"] == "refused" and outside.read_text() == "not yours"


def test_an_outside_rename_keeps_sprint_day_1s_way(program_with_pin, owner, work, tmp_path):
    """files.rename is Medium (no PIN): it still reaches Guardian, and the skill's fence refuses it, recorded as refused."""
    (tmp_path / "outside.txt").write_text("not yours")
    assert core_for(program_with_pin, owner).handle("rename ../outside.txt to stolen.txt").startswith("Refused:")
    ends = [row["decision"] for row in runs(program_with_pin.data_dir, "refused") if row["action"] == "files.rename"]
    assert ends == ["refused"] and owner.cards == []


def test_a_request_can_never_point_a_file_skill_at_another_folder(program_with_pin, tmp_path):
    for name, details in (("files.find", {"what": "", "when": ""}), ("files.move", {"name": "a", "to": "b"}),
                          ("files.delete", {"name": "a"})):
        with pytest.raises(Refused, match="takes only"):
            program_with_pin.client.run(Action(name, {"job": "a" * 16, **details, "work_folder": str(tmp_path)}))


def test_delete_cannot_run_without_an_approval_even_if_asked_directly(program_with_pin, work):
    make(work, "a.txt")
    with pytest.raises(Refused, match="not approved"):
        program_with_pin.client.run(Action("files.delete", {"job": "a" * 16, "name": "a.txt"}))
    assert (work / "a.txt").exists()


# --- Kairu's own browser ------------------------------------------------------------------------------------

def test_open_github_opens_kairus_browser_profile(program_with_pin, owner, desk):
    assert core_for(program_with_pin, owner).handle("open github.com") == "Opened github.com in Kairu's browser."
    [call] = calls(desk)
    profile = program_with_pin.data_dir.resolve() / "browser-profile"
    assert call == f"browse {BROWSER} --user-data-dir={profile} --no-first-run --no-default-browser-check --force-renderer-accessibility https://github.com"


def test_open_javascript_is_refused_and_starts_nothing(program_with_pin, owner, desk):
    for order in ("open javascript:alert(1)", "open file:///C:/Windows/win.ini", "open data:text/html,hi"):
        assert core_for(program_with_pin, owner).handle(order).startswith("Refused: Kairu opens only http and https")
    assert calls(desk) == []
    ends = [row["decision"] for row in runs(program_with_pin.data_dir, "refused") if row["action"] == "web.open"]
    assert len(ends) == 3


def test_a_public_search_goes_straight_to_google(program_with_pin, owner, desk):
    reply = core_for(program_with_pin, owner).handle("google the weather in Hyderabad")
    assert reply == "Searched Google for the weather in Hyderabad in Kairu's browser." and owner.cards == []
    assert calls(desk)[0].endswith("https://www.google.com/search?q=the+weather+in+Hyderabad")
    assert "Hyderabad" not in logged(program_with_pin.data_dir)


def test_a_personal_search_asks_first_and_no_means_nothing_is_searched(program_with_pin, owner, desk):
    owner.yes = False
    reply = core_for(program_with_pin, owner).handle("google Ravi 9876543210 home address")
    assert reply == "Not done: you refused it." and calls(desk) == []
    [card] = owner.cards
    assert card.action.name == "web.search_private" and card.tier == "High" and "Ravi" in card.action.details["query"]
    owner.yes = True
    assert core_for(program_with_pin, owner).handle("google Ravi 9876543210 home address").startswith("Searched Google")
    assert len(calls(desk)) == 1 and "9876543210" not in logged(program_with_pin.data_dir)


def test_a_personal_search_asked_for_directly_as_medium_is_still_refused(program_with_pin, desk):
    """Even a request that skips the core: web.search's own code reads the words and refuses."""
    run = program_with_pin.client.run(Action("web.search", {"job": "c" * 16, "query": "Ravi 9876543210 home address"}))
    wait_for(lambda: program_with_pin.client.run_status(run["run"])["outcome"] is not None, timeout=20)
    assert program_with_pin.client.run_status(run["run"])["outcome"] == "refused" and calls(desk) == []


# --- free-form plans ----------------------------------------------------------------------------------------

PDF_PLAN = {"steps": [{"action": "files.find", "details": {"what": "*.pdf", "when": ""}},
                      {"action": "files.move", "details": {"name": "*.pdf", "to": "pdfs"}}]}
ORDER = "put all the pdfs in Kairu-files into a folder called pdfs"


def test_a_free_form_order_is_planned_shown_and_run_after_yes(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps(PDF_PLAN)
    make(work, "a.pdf", "b.pdf", "keep.txt")
    reply = core_for(program_with_pin, owner).handle(ORDER)
    assert len(owner.confirmed) == 1, reply
    [shown] = owner.confirmed
    assert shown.startswith("Plan: 1) find *.pdf in your work folder (Low); 2) move *.pdf into pdfs (Medium).")
    assert reply in ("Found 2: a.pdf, b.pdf. Moved 2 files into pdfs (a new folder).",
                     "Found 2: b.pdf, a.pdf. Moved 2 files into pdfs (a new folder).")
    assert sorted(p.name for p in (work / "pdfs").iterdir()) == ["a.pdf", "b.pdf"] and (work / "keep.txt").exists()
    [asked] = providers.heard("groq")
    assert ORDER in json.dumps(asked["body"]) and "keep.txt" not in json.dumps(asked["body"])  # the AI sees your order, no file
    assert [row["action"] for row in runs(program_with_pin.data_dir)][-4:] == ["brain.plan", "task.plan", "files.find", "files.move"]
    assert "pdfs" not in logged(program_with_pin.data_dir)


def kept_plans(program):
    from kairu.tasks.store import TaskStore
    return TaskStore(program.data_dir).plans()


def plan_rows(program):
    return [row for row in audit.tail(Store(program.data_dir), 3000, kind="run") if row["action"] == "task.plan"]


def test_a_plan_is_kept_in_the_audit_log_as_a_hash_with_how_you_approved_it(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps(PDF_PLAN)
    make(work, "a.pdf")
    core_for(program_with_pin, owner).handle(ORDER)
    assert [row["decision"] for row in plan_rows(program_with_pin)] == ["started", "finished"]
    decided = [row for row in audit.tail(Store(program_with_pin.data_dir), 3000) if row["action"] == "task.plan" and row["kind"] == "check"]
    [kept] = kept_plans(program_with_pin)
    assert kept["approved"] == "yes" and kept["request"] == "" and kept["source"] == "pc"
    assert kept["steps"] == ["files.find", "files.move"]
    assert decided and all(row["details"].get("details_sha256") == kept["sha256"] and "plan" not in row["details"] for row in decided)
    plan_at = plan_rows(program_with_pin)[0]["id"]
    assert all(row["id"] > plan_at for row in runs(program_with_pin.data_dir) if row["action"] in ("files.find", "files.move"))


def test_a_plan_with_a_pin_is_kept_with_guardians_own_approval(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps({"steps": [{"action": "files.delete", "details": {"name": "old.txt"}}]})
    make(work, "old.txt")
    core_for(program_with_pin, owner).handle("clean up the old file in my work folder")
    [kept] = kept_plans(program_with_pin)
    assert kept["approved"] == "yes+PIN" and kept["steps"] == ["files.delete"]
    granted = [row for row in audit.tail(Store(program_with_pin.data_dir), 3000, kind="approval") if row["decision"] == "granted"]
    assert granted[-1]["action"] == "files.delete" and granted[-1]["details"]["request"] == kept["request"]


def test_a_plan_refused_on_its_card_is_never_kept_and_never_runs(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps(PDF_PLAN)
    make(work, "a.pdf")
    owner.yes = False
    core_for(program_with_pin, owner).handle(ORDER)
    assert kept_plans(program_with_pin) == [] and plan_rows(program_with_pin) == []


def test_a_made_up_plan_record_is_refused(program_with_pin):
    from kairu.tasks.store import TaskStore
    for details in ({"plan": "not a plan", "approved": "yes", "request": "", "source": "pc"},
                    {"plan": '{"steps": []}', "approved": "yes+PIN", "request": "", "source": "pc"},
                    {"plan": '{"steps": []}', "approved": "the bar", "request": "", "source": "pc"}):
        run = program_with_pin.client.run(Action("task.plan", {"job": "d" * 16, **details}))
        wait_for(lambda: program_with_pin.client.run_status(run["run"])["outcome"] is not None, timeout=20)
        assert program_with_pin.client.run_status(run["run"])["outcome"] == "refused"
    assert TaskStore(program_with_pin.data_dir).plans() == []


def test_saying_no_to_the_plan_runs_none_of_it(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps(PDF_PLAN)
    make(work, "a.pdf")
    owner.yes = False
    assert core_for(program_with_pin, owner).handle(ORDER) == "Not done: you didn't say yes to the plan. Nothing ran."
    assert (work / "a.pdf").exists() and [row["action"] for row in runs(program_with_pin.data_dir)][-1] == "brain.plan"


@pytest.mark.parametrize("answer", [
    {"steps": [{"action": "files.wipe", "details": {"name": "a.pdf"}}]},
    {"steps": [{"action": "system.shutdown", "details": {}}]},
    {"steps": [{"action": "files.move", "details": {"name": "*.pdf", "to": "pdfs"}, "tier": "Low"}]},
    {"steps": [{"action": "files.move", "details": {"name": "*.pdf", "to": "pdfs", "work_folder": "C:/"}}]},
])
def test_a_plan_that_invents_a_skill_raises_a_tier_or_names_another_folder_runs_nothing(program_with_pin, owner, providers, work,
                                                                                       desk, answer):
    providers.answers["groq"] = json.dumps(answer)
    make(work, "a.pdf")
    reply = core_for(program_with_pin, owner).handle(ORDER)
    assert reply.startswith(CANT) and owner.confirmed == [] and owner.cards == [] and calls(desk) == []
    assert [row["action"] for row in runs(program_with_pin.data_dir)][-1] == "brain.plan" and (work / "a.pdf").exists()


def test_a_plan_cannot_leave_the_work_folder(program_with_pin, owner, providers, work, tmp_path):
    outside = tmp_path / "outside.pdf"
    outside.write_text("not yours")
    providers.answers["groq"] = json.dumps({"steps": [{"action": "files.move", "details": {"name": "../outside.pdf", "to": "pdfs"}}]})
    reply = core_for(program_with_pin, owner).handle(ORDER)
    assert reply.startswith("Step 1 (files.move): Refused:") and reply.endswith("Nothing ran.")
    assert owner.confirmed == [] and owner.plans == [] and asked_guardian(program_with_pin, "files.move") == []
    assert outside.read_text() == "not yours" and not (work / "pdfs").exists()


def test_a_plan_with_a_delete_outside_never_shows_a_pin_card(program_with_pin, owner, providers, work, tmp_path):
    (tmp_path / "outside.txt").write_text("not yours")
    providers.answers["groq"] = json.dumps({"steps": [{"action": "files.find", "details": {"what": "*.txt", "when": ""}},
                                                      {"action": "files.delete", "details": {"name": "../outside.txt"}}]})
    reply = core_for(program_with_pin, owner).handle("clean up the old file in my work folder")
    assert reply.startswith("Step 2 (files.delete): Refused:") and owner.plans == [] and owner.cards == []
    assert asked_guardian(program_with_pin, "files.delete") == [] and (tmp_path / "outside.txt").exists()


def test_a_plan_with_a_high_step_asks_once_for_yes_and_the_pin_before_anything_runs(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps({"steps": [
        {"action": "files.move", "details": {"name": "*.pdf", "to": "pdfs"}},
        {"action": "files.delete", "details": {"name": "old.txt"}}]})
    make(work, "a.pdf", "old.txt")
    owner.yes = False
    assert core_for(program_with_pin, owner).handle("put the pdfs in a folder and delete the old file") == \
        "Not done: you refused the plan. Nothing ran."
    assert (work / "a.pdf").exists() and (work / "old.txt").exists() and owner.confirmed == []
    owner.yes, owner.plans, owner.cards = True, [], []
    reply = core_for(program_with_pin, owner).handle("put the pdfs in a folder and delete the old file")
    assert len(owner.plans) == 1 and len(owner.cards) == 1 and owner.confirmed == []  # once, for the whole plan
    assert "2) put old.txt in the Recycle Bin (High)" in owner.plans[0]
    assert reply.endswith('The file old.txt is in the Recycle Bin. "undo" brings it back.') and (work / "pdfs" / "a.pdf").exists()


def test_a_plan_with_two_high_steps_is_refused_whole(program_with_pin, owner, providers, work):
    providers.answers["groq"] = json.dumps({"steps": [{"action": "files.delete", "details": {"name": "a.txt"}},
                                                      {"action": "files.delete", "details": {"name": "b.txt"}}]})
    make(work, "a.txt", "b.txt")
    reply = core_for(program_with_pin, owner).handle("clean up a.txt and b.txt in my work folder")
    assert "only one" in reply and "Nothing ran" in reply and owner.cards == [] and (work / "a.txt").exists()


def test_a_personal_order_is_never_sent_to_be_planned(program_with_pin, owner, providers, work):
    reply = core_for(program_with_pin, owner).handle("move the files Ravi sent from 9876543210 into a folder")
    assert reply.startswith(CANT) and "personal" in reply and providers.heard() == []


def test_without_a_provider_a_free_form_order_still_cant_be_done(program_with_pin, providers, work):
    core = TaskCore(program_with_pin.config, program_with_pin.client)
    reply = core.handle(ORDER)
    assert reply.startswith(CANT) and providers.heard() == []


# --- a stop during a task ------------------------------------------------------------------------------------

def stop_during(program, core, order, wait_for_action):
    """Start the order, wait until `wait_for_action` is running, press the stop, and time how long the task takes to end."""
    box = {}
    thread = threading.Thread(target=lambda: box.update(reply=core.handle(order)), daemon=True)
    thread.start()
    wait_for(lambda: any(row["action"] == wait_for_action for row in runs(program.data_dir)), timeout=60)
    time.sleep(0.3)
    pressed = time.monotonic()
    safemode.emergency_stop(Store(program.data_dir), "test")
    thread.join(10)
    return box.get("reply"), time.monotonic() - pressed


def test_a_stop_during_a_line_of_steps_ends_it_in_under_1_second_and_the_rest_never_runs(program_with_pin, owner, desk):
    reply, took = stop_during(program_with_pin, core_for(program_with_pin, owner), "wait 20 seconds then volume 20", "task.wait")
    print(f"\n  a stop during 'wait 20 seconds then volume 20': the task ended {took:.3f} s later")
    assert took < 1.0 and "stopped" in reply.lower() and calls(desk) == []
    assert "system.volume" not in [row["action"] for row in runs(program_with_pin.data_dir)]
    wait_for(lambda: [row for row in runs(program_with_pin.data_dir, "halted") if row["action"] == "task.wait"], timeout=5)
    halted = [row for row in runs(program_with_pin.data_dir, "halted") if row["action"] == "task.wait"]
    assert halted[0]["details"]["seconds_since_stop"] < 1.0


def test_a_stop_during_a_free_form_plan_ends_it_and_the_rest_never_runs(program_with_pin, owner, providers, desk, work):
    (desk / "pc.json").write_text(json.dumps({"apps": {"notepad": "C:/Windows/notepad.exe"}, "browsers": {"chrome": BROWSER},
                                              "slow": 20}))  # the pretend PC takes 20 s to open an app
    providers.answers["groq"] = json.dumps({"steps": [{"action": "apps.open", "details": {"name": "notepad"}},
                                                      {"action": "web.open", "details": {"url": "github.com"}}]})
    reply, took = stop_during(program_with_pin, core_for(program_with_pin, owner), "show me github and notepad on the web",
                              "apps.open")
    print(f"\n  a stop during a free-form plan: the plan ended {took:.3f} s later")
    assert took < 1.0 and "stopped" in reply.lower() and calls(desk) == []
    assert "web.open" not in [row["action"] for row in runs(program_with_pin.data_dir)]


def test_a_stop_between_steps_ends_the_rest(program_with_pin, owner, desk):
    core = core_for(program_with_pin, owner)
    real = core._run_step

    def then_stop(step, job=None, granted=None):
        done = real(step, job, granted)
        safemode.emergency_stop(Store(program_with_pin.data_dir), "test")
        wait_for(lambda: program_with_pin.client.status()["mode"] == "safe", timeout=5)
        return done

    core._run_step = then_stop
    reply = core.handle("volume 30 then volume 40")
    assert reply.startswith("Volume 30.") and "Stopped" in reply and calls(desk) == ["volume 30 None"]


def test_whats_open_still_works(program_with_pin, owner):
    assert core_for(program_with_pin, owner).handle("what's open?") == "Open: notepad (Untitled)."
