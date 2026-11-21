"""Shadows (Phase H, SHADOW.md), piece by piece: the skill pack check, what a Shadow may say, lessons, and a Shadow's
whole trip with the owner's side run in this process (the Gate is tests_kairu/fake_relay.py, the repository is a folder
on this PC, the friend's laptop is another folder). The trip through the real Guardian program: test_shadow_program.py.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from kairu import config as kairu_config
from kairu.link import keys, store as link_store
from kairu.link.message import seal
from kairu.shadow import agent, kinds, lessons, manager, pack as packs, wire
from kairu.shadow.store import ShadowStore
from tests_kairu.fake_relay import FakeRelay
from tests_kairu.helpers import wait_for

SKILL = '''"""Adds the numbers in your words."""
import re


def run(text: str) -> str:
    numbers = [int(word) for word in re.findall(r"-?\\d+", text)]
    return f"The total is {sum(numbers)}."
'''
TEST = '''import unittest

import skill


class Totals(unittest.TestCase):
    def test_it_adds(self):
        self.assertEqual(skill.run("lunch 120 and bus 30"), "The total is 150.")

    def test_no_numbers(self):
        self.assertEqual(skill.run("nothing"), "The total is 0.")
'''
READ_ME = """# Expense total

Adds up the amounts in what you say.

Say: `kairu pack run expense-total lunch 120 and bus 30`.
It answers: "The total is 150."
It needs nothing but Python.
"""


def git(*arguments, cwd=None):
    done = subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def relay():
    fake = FakeRelay(keepalive=0.5)
    yield fake
    fake.close()


@pytest.fixture
def repo(tmp_path):
    """The owner's repository: a bare one, with one commit on main."""
    bare, seed = tmp_path / "kairuu.git", tmp_path / "seed"
    git("init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    git("init", "--quiet", "--initial-branch=main", str(seed))
    (seed / "README.md").write_text("Kairu\n")
    git("add", "README.md", cwd=seed)
    git("-c", "user.name=Owner", "-c", "user.email=owner@example.invalid", "commit", "--quiet", "-m", "start", cwd=seed)
    git("push", "--quiet", str(bare), "main", cwd=seed)
    return bare


def write_pack(folder: Path, name="expense-total", skill=SKILL):
    (folder / "tests").mkdir(parents=True, exist_ok=True)
    (folder / "pack.json").write_text(json.dumps({"pack": 1, "name": name, "title": "Expense total",
                                                  "description": "Adds up the amounts you say", "version": "0.1",
                                                  "entry": "skill.py", "made_by": "Rahul"}))
    (folder / "skill.py").write_text(skill)
    (folder / "tests" / "test_skill.py").write_text(TEST)
    (folder / "README.md").write_text(READ_ME)
    return folder


def build(shadow: agent.Shadow, lesson_lines=()):
    """What the friend does: write the use case inside the Shadow's workspace."""
    write_pack(shadow.pack_folder, shadow.state["pack"])
    if lesson_lines:
        (shadow.base / agent.WORK / lessons.FILE_NAME).write_text("\n".join(f"- {line}" for line in lesson_lines))


class Owner:
    """The owner's PC with no Guardian program: the manager's functions called as Guardian would call them."""

    def __init__(self, tmp_path, relay, repo):
        self.data, self.relay, self.repo = tmp_path / "owner-data", relay, repo
        self.data.mkdir()
        self.store = ShadowStore(self.data)

    def send(self, friend_base: Path, pack="expense-total", hours=3.0, code=None) -> agent.Shadow:
        """shadow.create, and the friend's laptop joining with the invite and the code."""
        thread = threading.Thread(target=self._create, args=(pack, hours), daemon=True)
        thread.start()
        wait_for(lambda: manager.read_offer(self.data), timeout=20)
        offer = manager.read_offer(self.data)
        self.offer = offer
        shadow = agent.Shadow.join(offer["text"], code or offer["code"], friend_base, wait=20)
        thread.join(20)
        return shadow

    def _create(self, pack, hours):
        try:
            manager.create(str(self.data), self.relay.url, "Rahul", "Add up the expenses I say", pack, hours, str(self.repo))
        except SystemExit:
            pass

    def sync(self):
        manager.sync(str(self.data), self.relay.url)
        return self.store.get(1)


@pytest.fixture
def owner(tmp_path, relay, repo):
    return Owner(tmp_path, relay, repo)


@pytest.fixture
def friend(tmp_path):
    return tmp_path / "friend-laptop" / "Kairu-shadow"


# --- the skill pack -------------------------------------------------------------------------------------------------

def test_a_finished_pack_passes_the_check_its_tests_and_runs(tmp_path):
    folder = write_pack(tmp_path / "expense-total")
    assert packs.check(folder, "expense-total") == []
    assert packs.run_tests(folder)[:2] == (True, 2)
    assert packs.run(folder, "tea 20, snacks 55") == (True, "The total is 75.")
    assert packs.uses(folder) == []
    assert not (folder / "__pycache__").exists() and not (folder / "tests" / "__pycache__").exists()


@pytest.mark.parametrize("change,problem", [
    (lambda f: (f / "skill.py").write_text("import requests\n\ndef run(text):\n    return ''\n"), "imports requests"),
    (lambda f: (f / "skill.py").write_text("def other(text):\n    return ''\n"), "needs `def run"),
    (lambda f: (f / "skill.py").write_text("def run(:\n"), "not Python"),
    (lambda f: (f / "README.md").write_text("# Title\n"), "README.md is not written yet"),
    (lambda f: (f / "tests" / "test_skill.py").unlink(), "no tests"),
    (lambda f: (f / "tool.exe").write_bytes(b"MZ"), "text files only"),
    (lambda f: (f / ".env").write_text("KEY=1"), "no hidden files"),
    (lambda f: (f / "big.txt").write_text("x" * (packs.MOST_FILE_BYTES + 1)), "larger than"),
    (lambda f: (f / "notes.md").write_text(f"{packs.UNFINISHED}: later"), "marker"),
    (lambda f: (f / "pack.json").write_text("{}"), "must have exactly"),
])
def test_what_is_not_a_pack_is_named(tmp_path, change, problem):
    folder = write_pack(tmp_path / "expense-total")
    change(folder)
    assert any(problem in item for item in packs.check(folder, "expense-total")), packs.check(folder, "expense-total")


def test_a_pack_under_another_name_is_refused(tmp_path):
    folder = write_pack(tmp_path / "expense-total", name="other-name")
    assert any("other-name" in item for item in packs.check(folder, "expense-total"))


@pytest.mark.skipif(sys.platform == "win32", reason="making a link needs a special right on Windows")
def test_a_link_out_of_the_pack_is_refused(tmp_path):
    secret = tmp_path / "passwords.txt"
    secret.write_text("the friend's own file")
    folder = write_pack(tmp_path / "expense-total")
    os.symlink(secret, folder / "notes.txt")
    assert any("link" in item for item in packs.check(folder, "expense-total"))
    with pytest.raises(packs.PackProblem):
        packs.digest(folder)


def test_the_digest_is_the_same_on_windows_and_linux_and_changes_with_any_file(tmp_path):
    folder = write_pack(tmp_path / "expense-total")
    before = packs.digest(folder)
    (folder / "skill.py").write_bytes(SKILL.replace("\n", "\r\n").encode())
    assert packs.digest(folder) == before
    (folder / "skill.py").write_text(SKILL + "# one more line\n")
    assert packs.digest(folder) != before


def test_what_a_packs_code_reaches_for_is_named(tmp_path):
    folder = write_pack(tmp_path / "expense-total",
                        skill="import subprocess\nimport urllib.request\n\ndef run(text):\n    return ''\n")
    assert packs.uses(folder) == ["network", "other programs"]


def test_a_pack_that_fails_or_hangs_is_reported_not_raised(tmp_path):
    folder = write_pack(tmp_path / "expense-total", skill="def run(text):\n    raise ValueError('broken')\n")
    ok, why = packs.run(folder, "x")
    assert not ok and "broken" in why
    (folder / "skill.py").write_text("import time\n\ndef run(text):\n    time.sleep(30)\n")
    assert packs.run(folder, "x", seconds=1) == (False, "it was still running after 1 seconds, so it was ended")


# --- what a Shadow may say ------------------------------------------------------------------------------------------

def test_a_shadow_can_say_only_progress_or_a_return():
    for text in ('{"action": "security.disable"}', '{"shadow": {"kind": "command", "action": "files.delete"}}',
                 '{"shadow": {"kind": "progress"}, "action": "x"}', "not json", '{"shadow": "progress"}'):
        assert wire.from_shadow(text) is None
    said = wire.from_shadow(wire.body("progress", files=4, tests="2 pass", ready=True, note="x" * 500, approve="yes 482916"))
    assert said == {"kind": "progress", "files": 4, "tests": "2 pass", "ready": True, "note": "x" * kinds.MAX_NOTE}


def test_a_return_report_is_cut_down_to_its_own_fields():
    said = wire.from_shadow(wire.body("return", done="yes", pack="../../etc", digest="short", files=-5, tests="many",
                                      lessons=["a" * 500, 7, "fine\x1b[31m lesson"] + ["more"] * 10, uses="network",
                                      commit="c" * 90, pin="482916"))
    assert said["done"] is False and said["pack"] == "" and said["digest"] == "" and said["files"] == 0 and said["tests"] == 0
    assert len(said["lessons"]) == kinds.MOST_LESSONS and said["lessons"][0] == "a" * kinds.MAX_LESSON
    assert "\x1b" not in said["lessons"][1] and said["uses"] == [] and len(said["commit"]) == 40 and "pin" not in said


def test_only_general_lessons_are_kept():
    kept = lessons.keep_general([
        "Run the tests before every change, not only at the end",
        "Rahul keeps his notes in C:\\Users\\rahul\\notes",
        "The bug was in skill.py line 40",
        "Email me at rahul@example.com about it",
        "See https://example.com/how for the trick",
        "short",
        "The expense total pack needed a regex",
        "Run the tests before every change, not only at the end",
        "Small functions were easier to test than one long one",
    ], private=("Rahul", "expense-total"))
    assert kept == ["Run the tests before every change, not only at the end",
                    "Small functions were easier to test than one long one"]


def test_an_invite_that_was_changed_or_cut_is_refused(owner, friend):
    shadow = owner.send(friend)
    text = owner.offer["text"]
    assert wire.read_invite(text)["shadow"] == shadow.state["shadow"]
    for bad in (text[:-20], text.replace("kairu-shadow", "kairu-pair"), "kairu-shadow:1:e30"):
        with pytest.raises(wire.NotAnInvite):
            wire.read_invite(bad)


# --- the trip -------------------------------------------------------------------------------------------------------

def test_a_shadow_joins_with_the_code_and_starts_with_an_empty_workspace(owner, friend):
    shadow = owner.send(friend)
    record = owner.store.get(1)
    assert record["state"] == "working" and record["device"] == shadow.me.id and record["branch"] == shadow.state["branch"]
    assert owner.offer["code"] not in owner.offer["text"] and manager.read_offer(owner.data) is None
    assert link_store.paired(owner.data) == []  # never a paired device: nothing it sends is read as a request
    assert sorted(path.name for path in friend.iterdir()) == ["shadow.key", "shadow.log", "state.json", "workspace"]
    assert sorted(path.name for path in (friend / "workspace").iterdir()) == ["MISSION.md", "expense-total"]
    state = (friend / "state.json").read_text()
    assert "sign" in state and bytes(shadow.me.signing).hex() not in state  # the state has public keys only
    problems, ran = shadow.check()
    assert ran == 0 and any(packs.UNFINISHED in item for item in problems)  # the scaffold is not a finished pack


def test_a_wrong_code_does_not_join_and_five_cancel_the_invite(owner, friend, relay):
    thread = threading.Thread(target=owner._create, args=("expense-total", 3.0), daemon=True)
    thread.start()
    wait_for(lambda: manager.read_offer(owner.data), timeout=20)
    offer = manager.read_offer(owner.data)
    invite = wire.read_invite(offer["text"])
    wrong = f"{(int(offer['code']) + 1) % 10 ** 6:06d}"
    for _ in range(kinds.INVITE_TRIES):
        relay.publish(invite["topic"], wire.join_request(keys.new_identity("dev"), invite, wrong, "someone else"))
    thread.join(20)
    assert not thread.is_alive() and owner.store.get(1)["state"] == "expired" and manager.read_offer(owner.data) is None
    with pytest.raises(agent.ShadowProblem, match="did not answer"):
        agent.Shadow.join(offer["text"], offer["code"], friend, wait=2)  # the right code, too late
    assert not friend.exists()


def test_the_done_check_keeps_an_unfinished_shadow_from_coming_home(owner, friend, repo):
    shadow = owner.send(friend)
    with pytest.raises(agent.ShadowProblem, match="not done yet"):
        shadow.come_home("done")
    assert (friend / "shadow.key").exists() and git("branch", "--list", cwd=repo).split() == ["*", "main"]
    build(shadow)
    (shadow.pack_folder / "tests" / "test_skill.py").write_text(TEST.replace("150", "999"))
    with pytest.raises(agent.ShadowProblem, match="tests do not all pass"):
        shadow.come_home("done")
    assert owner.sync()["state"] == "working"


def test_progress_is_counts_only_and_the_owner_sees_it(owner, friend, relay):
    shadow = owner.send(friend)
    build(shadow)
    shadow.progress(force=True)
    record = owner.sync()
    assert record["progress"] == {"kind": "progress", "files": 4, "tests": "2 pass", "ready": True,
                                  "note": "the done check passes"}
    assert "The total is" not in json.dumps([message["message"] for message in relay.messages])  # and it is encrypted


def test_it_comes_home_with_the_use_case_and_removes_itself(owner, friend, repo, tmp_path):
    shadow = owner.send(friend)
    build(shadow, ["Small functions were easier to test than one long one", "Rahul's token is in C:/keys/token.txt"])
    branch, wanted = shadow.state["branch"], packs.digest(shadow.pack_folder)
    report = shadow.come_home("done")
    assert report["done"] and report["digest"] == wanted and report["tests"] == 2 and report["sent"]
    # on the repository: one new branch, with only packs/expense-total added
    assert git("ls-tree", "-r", "--name-only", branch, cwd=repo).splitlines() == [
        "README.md", "packs/expense-total/README.md", "packs/expense-total/pack.json", "packs/expense-total/skill.py",
        "packs/expense-total/tests/test_skill.py"]
    assert git("rev-parse", branch, cwd=repo) == report["commit"] and git("rev-parse", "main", cwd=repo) != report["commit"]
    # on the friend's laptop: nothing left but the receipt
    assert not friend.exists()
    receipt = Path(report["receipt"]).read_text()
    assert wanted in receipt and "Nothing else on this laptop was read or copied" in receipt and "token" not in receipt
    # on the owner's PC: the report, the lesson waiting for a yes, and the Shadow's key gone
    record = owner.sync()
    assert record["state"] == "returned" and record["report"]["digest"] == wanted
    assert record["sign"] is None and record["topic"] is None and owner.store.device(record) is None
    assert [item["text"] for item in owner.store.lessons("waiting")] == ["Small functions were easier to test than one long one"]
    with pytest.raises(agent.ShadowProblem, match="no Shadow is on this laptop"):
        agent.Shadow(friend)


def test_come_back_now_brings_it_home_at_once_and_unfinished_work_stays_with_the_friend(owner, friend, repo):
    shadow = owner.send(friend)
    (shadow.pack_folder / "skill.py").write_text("def run(text):\n    return 'half done'\n")
    assert shadow.tick() is None
    manager.recall(str(owner.data), owner.relay.url, 1.0)
    assert owner.store.get(1)["state"] == "recalled"
    assert agent.Shadow(friend).tick() == "recalled"
    assert not (friend / "shadow.key").exists() and not (friend / "state.json").exists()
    assert (friend / "workspace" / "expense-total" / "skill.py").read_text().endswith("'half done'\n")  # the friend's own
    assert git("branch", "--list", cwd=repo).split() == ["*", "main"]  # nothing was pushed
    record = owner.sync()
    assert record["state"] == "unfinished" and record["report"]["why"] == "the owner called it back" and record["sign"] is None


def test_the_friends_stop_ends_it_without_pushing_even_finished_work(owner, friend, repo):
    shadow = owner.send(friend)
    build(shadow)
    report = shadow.come_home("stopped")
    assert not report["done"] and git("branch", "--list", cwd=repo).split() == ["*", "main"]
    assert (friend / "workspace" / "expense-total" / "skill.py").exists() and not (friend / "shadow.key").exists()
    assert owner.sync()["state"] == "unfinished"


def test_the_time_limit_brings_it_home(owner, friend):
    shadow = owner.send(friend, hours=0.0001)
    time.sleep(0.5)
    assert shadow.tick() == "time"
    assert owner.sync()["report"]["why"] == "its time limit ended"


def test_a_shadows_message_is_never_a_request(owner, friend, relay):
    """Even a well-signed message from a real Shadow, of the phone's "command" type, changes nothing on the owner's PC."""
    shadow = owner.send(friend)
    for kind, body in (("command", json.dumps({"action": "files.delete", "details": {"name": "*"}})),
                       ("report", json.dumps({"action": "security.disable"})),
                       ("report", wire.body("install", shadow=1)), ("ask", "what is the owner's PIN")):
        relay.publish(shadow.topic, seal(shadow.me, shadow.pc.id, shadow.pc.box, kind, body))
    record = owner.sync()
    assert record["state"] == "working" and record["progress"] is None and record["report"] is None
    assert owner.store.packs() == [] and not (owner.data / "link.db").exists()


def test_nothing_is_read_from_a_shadow_after_it_came_home(owner, friend, relay):
    shadow = owner.send(friend)
    me, pc, topic = shadow.me, shadow.pc, shadow.topic
    build(shadow)
    shadow.come_home("done")
    owner.sync()
    relay.publish(topic, seal(me, pc.id, pc.box, "report", wire.body("return", done=True, pack="expense-total",
                                                                     digest="0" * 64)))
    owner.store.set_state(1, "working")  # even if its row were active again, its key is gone
    assert owner.sync()["report"]["digest"] != "0" * 64


def test_giving_up_revokes_the_key_when_the_gate_cannot_be_reached(owner, friend, relay):
    owner.send(friend)
    relay.close()
    manager.recall(str(owner.data), "http://127.0.0.1:9", 1.0, give_up=True)
    record = owner.store.get(1)
    assert record["state"] == "unfinished" and record["sign"] is None


# --- installing -----------------------------------------------------------------------------------------------------

@pytest.fixture
def home_again(owner, friend, repo, tmp_path, monkeypatch):
    """A Shadow that came home finished; the owner's project folder is a clone of the repository."""
    shadow = owner.send(friend)
    build(shadow)
    branch = shadow.state["branch"]
    shadow.come_home("done")
    owner.sync()
    project = tmp_path / "project"
    git("clone", "--quiet", str(repo), str(project))
    monkeypatch.setattr(kairu_config, "ROOT", project)
    return branch


def test_install_takes_the_branch_checks_it_again_and_keeps_the_pack(owner, home_again, tmp_path):
    manager.install(str(owner.data), 1.0)
    assert owner.store.get(1)["state"] == "installed"
    installed = owner.store.pack("expense-total")
    assert installed["made_by"] == "Rahul" and installed["digest"] == owner.store.get(1)["report"]["digest"]
    assert not (tmp_path / "project" / "packs").exists()  # the project folder's own files were not touched
    manager.run_pack(str(owner.data), "expense-total", "tea 20 and bus 30", "job-1")
    assert owner.store.run_result("job-1")["output"] == "The total is 50."


def test_a_branch_changed_after_the_shadow_came_home_is_not_installed(owner, home_again, repo, tmp_path, capsys):
    work = tmp_path / "attacker"
    git("clone", "--quiet", "--branch", home_again, str(repo), str(work))
    (work / "packs" / "expense-total" / "skill.py").write_text(SKILL + "\nimport os\n")
    git("-c", "user.name=X", "-c", "user.email=x@example.invalid", "commit", "--quiet", "-am", "later change", cwd=work)
    git("push", "--quiet", "origin", home_again, cwd=work)
    with pytest.raises(SystemExit):
        manager.install(str(owner.data), 1.0)
    assert "not the files the Shadow tested" in capsys.readouterr().err
    assert owner.store.packs() == [] and owner.store.get(1)["state"] == "returned"


def test_an_installed_pack_whose_files_changed_is_not_run(owner, home_again, capsys):
    manager.install(str(owner.data), 1.0)
    (owner.data / "packs" / "expense-total" / "skill.py").write_text("def run(text):\n    return 'changed'\n")
    with pytest.raises(SystemExit):
        manager.run_pack(str(owner.data), "expense-total", "1 2", "job-2")
    assert owner.store.run_result("job-2")["ok"] == 0 and "not the ones installed" in capsys.readouterr().err
    manager.remove_pack(str(owner.data), "expense-total")
    assert owner.store.packs() == [] and not (owner.data / "packs" / "expense-total").exists()


def test_an_unfinished_shadow_has_nothing_to_install(owner, friend, capsys):
    shadow = owner.send(friend)
    shadow.come_home("stopped")
    owner.sync()
    with pytest.raises(SystemExit):
        manager.install(str(owner.data), 1.0)
    assert "has not come home with a finished use case" in capsys.readouterr().err


def test_a_lesson_is_kept_only_by_the_owners_own_yes(owner, friend):
    shadow = owner.send(friend)
    build(shadow, ["Small functions were easier to test than one long one", "Write the README while the idea is fresh"])
    shadow.come_home("done")
    owner.sync()
    assert owner.store.lessons("kept") == []
    manager.lesson(str(owner.data), 1.0, True)
    manager.lesson(str(owner.data), 2.0, False)
    assert [item["text"] for item in owner.store.lessons("kept")] == ["Small functions were easier to test than one long one"]
    with pytest.raises(SystemExit):
        manager.lesson(str(owner.data), 1.0, False)  # decided once


# --- the friend's commands and the background part ------------------------------------------------------------------

def test_the_friends_commands_from_join_to_home(owner, friend, monkeypatch, capsys):
    monkeypatch.setenv("KAIRU_SHADOW_HOME", str(friend))
    thread = threading.Thread(target=owner._create, args=("expense-total", 3.0), daemon=True)
    thread.start()
    wait_for(lambda: manager.read_offer(owner.data), timeout=20)
    offer = manager.read_offer(owner.data)
    spaced = f"{offer['code'][:3]} {offer['code'][3:]}"  # as `kairu shadow create` shows it
    assert agent.main(["join", offer["text"], spaced, "--no-background"]) == 0
    thread.join(20)
    assert "Joined." in capsys.readouterr().out
    assert agent.main(["join", offer["text"], offer["code"], "--no-background"]) == 1  # one Shadow per laptop
    assert agent.main(["status"]) == 0 and agent.main(["check"]) == 1 and agent.main(["home"]) == 1
    assert "Still missing" in capsys.readouterr().out and (friend / "shadow.key").exists()
    build(agent.Shadow(friend))
    assert agent.main(["check"]) == 0 and agent.main(["home"]) == 0
    said = capsys.readouterr().out
    assert "Home. The pack is on the branch shadow/" in said and "Your receipt:" in said
    assert agent.main(["status"]) == 1 and owner.sync()["state"] == "returned"


def test_the_background_part_sends_progress_and_ends_when_called_back(owner, friend):
    shadow = owner.send(friend)
    build(shadow)
    ended = []
    thread = threading.Thread(target=lambda: ended.append(agent.run(friend, poll=0.2)), daemon=True)
    thread.start()
    wait_for(lambda: (owner.sync() or {}).get("progress"), timeout=20, every=0.3)
    assert agent.running(friend)
    manager.recall(str(owner.data), owner.relay.url, 1.0)
    thread.join(30)
    assert ended == [0] and not (friend / "shadow.key").exists()
    record = owner.sync()
    assert record["state"] == "returned" and record["report"]["why"] == "the owner called it back"  # it was finished


def test_the_background_part_starts_whatever_folder_the_friend_joined_from(owner, friend, tmp_path, monkeypatch):
    """It runs as a program of its own: it must find Kairu even when the terminal was in another folder."""
    shadow = owner.send(friend)
    elsewhere = tmp_path / "Downloads"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(agent, "POLL_SECONDS", 60)
    assert agent.start_background(friend, window=False)
    wait_for(lambda: agent.running(friend), timeout=30, every=0.3)
    manager.recall(str(owner.data), owner.relay.url, 1.0)
    shadow.state["recalled"] = True  # the background part reads the Gate once a minute; end it here instead of waiting
    shadow.come_home("recalled")
    assert not (friend / "shadow.key").exists() and owner.sync()["state"] == "unfinished"
