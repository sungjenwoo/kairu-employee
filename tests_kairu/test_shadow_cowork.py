"""A Cowork Shadow (ADR-039): a copy of Kairu on a friend's laptop; its changes come home as a branch and a pull request.

The owner's repository is a small stand-in for Kairu on this PC, whose tools/check_guardian.py answers at once (PASSED,
or FAILED while a file named BREAK is there). Setting up a real Kairu (Guardian at sign-in, a PIN, the bar) is not done
in tests: the `kairu` commands the Shadow runs on the copy are recorded instead.
"""

import sqlite3
import threading

import pytest

from kairu.shadow import agent, cowork, manager
from kairu.shadow.store import ShadowStore
from tests_kairu.helpers import wait_for
from tests_kairu.test_shadow import Owner, friend, git, relay  # noqa: F401 (fixtures)

CHECK = '''import pathlib, sys
root = pathlib.Path(__file__).resolve().parents[1]
if (root / "BREAK").exists():
    print("  Result: FAILED   2 passed, 1 failed, 0 skipped")
    sys.exit(1)
print("  Result: PASSED   3 passed, 0 failed, 0 skipped")
'''


@pytest.fixture
def kairu_repo(tmp_path):
    """The owner's Kairu, as a bare repository with a main branch."""
    bare, seed = tmp_path / "kairuu.git", tmp_path / "seed"
    git("init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    git("init", "--quiet", "--initial-branch=main", str(seed))
    (seed / "tools").mkdir()
    (seed / "tools" / "check_guardian.py").write_text(CHECK)
    (seed / "README.md").write_text("Kairu\n")
    (seed / ".gitignore").write_text("data/\n.venv-guardian/\nguardian-check-report.txt\n")
    git("add", "--all", cwd=seed)
    git("-c", "user.name=Owner", "-c", "user.email=owner@example.invalid", "commit", "--quiet", "-m", "start", cwd=seed)
    git("push", "--quiet", str(bare), "main", cwd=seed)
    return bare


@pytest.fixture
def ran(monkeypatch):
    """The `kairu ...` commands the Shadow runs on its copy, recorded instead of run."""
    said = []
    monkeypatch.setattr(cowork, "kairu", lambda copy, *arguments, **options: said.append(arguments) or 0)
    return said


class CoworkOwner(Owner):
    def _create(self, pack, hours):
        try:
            manager.create(str(self.data), self.relay.url, "Omesh", "Make the task core open sites in Chrome", pack, hours,
                           str(self.repo), mode="cowork", base="main")
        except SystemExit:
            pass


@pytest.fixture
def owner(tmp_path, relay, kairu_repo):  # noqa: F811
    return CoworkOwner(tmp_path, relay, kairu_repo)


def installed(shadow: agent.Shadow) -> None:
    """As if `setup` had run: the copy's private environment is there."""
    python = cowork.venv_python(shadow.copy)
    python.parent.mkdir(parents=True)
    python.write_text("")


def test_it_joins_with_a_copy_of_kairu_on_its_own_branch_and_nothing_of_the_owners(owner, friend):
    shadow = owner.send(friend, pack="task-core")
    assert shadow.cowork and shadow.copy == friend / "workspace" / "kairu"
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=shadow.copy) == shadow.state["branch"]
    assert (shadow.copy / "tools" / "check_guardian.py").exists() and not (shadow.copy / "data").exists()
    assert "YOUR OWN PIN" in (friend / "workspace" / "MISSION.md").read_text()
    record = owner.store.get(1)
    assert record["state"] == "working" and record["mode"] == "cowork" and record["base"] == "main"


def test_a_copy_that_cannot_be_downloaded_joins_nothing(owner, friend, tmp_path):
    thread = threading.Thread(target=owner._create, args=("task-core", 24.0), daemon=True)
    thread.start()
    wait_for(lambda: manager.read_offer(owner.data), timeout=20)
    offer = manager.read_offer(owner.data)
    owner.repo.rename(tmp_path / "gone.git")  # the friend's sign-in cannot reach it
    with pytest.raises(agent.ShadowProblem, match="could not be downloaded"):
        agent.Shadow.join(offer["text"], offer["code"], friend, wait=5)
    assert not (friend / "workspace").exists() and not (friend / "shadow.key").exists()
    assert owner.store.get(1)["state"] == "invited"


def test_done_means_changes_and_kairus_own_check_passing_on_exactly_them(owner, friend, monkeypatch):
    shadow = owner.send(friend, pack="task-core")
    assert shadow.check(with_tests=True)[0] == ["no changes to Kairu yet: make them in the copy, then check again"]
    (shadow.copy / "README.md").write_text("Kairu, with a better task core\n")
    problems, _ = shadow.check(with_tests=False)
    assert "has not passed on these changes yet" in problems[0]  # status and the background never run the long check
    (shadow.copy / "BREAK").write_text("")
    assert "did not pass" in shadow.check(with_tests=True)[0][0]
    (shadow.copy / "BREAK").unlink()
    assert shadow.check(with_tests=True) == ([], 3)
    monkeypatch.setattr(cowork, "_live", lambda *a, **k: pytest.fail("the check ran again on the same files"))
    assert shadow.check(with_tests=True) == ([], 3) and shadow.check(with_tests=False) == ([], 3)
    (shadow.copy / "README.md").write_text("changed again\n")
    assert shadow.check(with_tests=False)[0]  # a change after the check needs the check again


def test_it_comes_home_with_its_changes_on_a_branch_and_removes_the_kairu_it_set_up(owner, friend, kairu_repo, ran):
    shadow = owner.send(friend, pack="task-core")
    installed(shadow)
    (shadow.copy / "README.md").write_text("Kairu, with a better task core\n")
    (shadow.copy / "kairu_tasks_chrome.py").write_text("SITES = {'instagram': 'https://www.instagram.com'}\n")
    (shadow.copy / "data").mkdir()
    (shadow.copy / "data" / "guardian.db").write_text("Omesh's PIN hash")  # his own Kairu's data: never pushed
    (friend / "workspace" / "LESSONS.md").write_text("- Keep each skill small and test it alone first\n")
    report = shadow.come_home("done")
    branch = shadow.state["branch"]
    assert report["done"] and report["files"] == 2 and report["tests"] == 3 and report["sent"]
    assert sorted(report["changed"]) == ["README.md", "kairu_tasks_chrome.py"]
    # on the repository: the Shadow's branch on top of main; main itself untouched; no data folder
    assert git("ls-tree", "-r", "--name-only", branch, cwd=kairu_repo).splitlines() == [
        ".gitignore", "README.md", "kairu_tasks_chrome.py", "tools/check_guardian.py"]
    assert git("rev-parse", f"{branch}~1", cwd=kairu_repo) == git("rev-parse", "main", cwd=kairu_repo)
    assert git("rev-parse", branch, cwd=kairu_repo) == report["commit"]
    # on the friend's laptop: the Kairu it set up ended and out of Task Scheduler, the copy deleted, a receipt left
    assert ("guardian", "uninstall") in ran and ("bar", "uninstall") in ran and ("guardian", "quit") in ran
    assert not friend.exists()
    receipt = (friend.parent / f"Kairu-shadow-receipt-{shadow.state['shadow']}.txt").read_text()
    assert "kairu_tasks_chrome.py" in receipt and "taken out of Task Scheduler" in receipt and "PIN hash" not in receipt
    # on the owner's PC: home, with exactly what changed, its key forgotten, and nothing to install by itself
    record = owner.sync()
    assert record["state"] == "returned" and record["report"]["tree"] == report["tree"] and record["sign"] is None
    assert record["report"]["changed"] == report["changed"]
    assert [item["text"] for item in owner.store.lessons("waiting")] == ["Keep each skill small and test it alone first"]
    with pytest.raises(SystemExit):
        manager.install(str(owner.data), 1.0)
    assert owner.store.packs() == []


def test_home_refuses_until_the_check_passes_and_a_failing_check_keeps_it_there(owner, friend, kairu_repo, ran):
    shadow = owner.send(friend, pack="task-core")
    (shadow.copy / "README.md").write_text("half done\n")
    (shadow.copy / "BREAK").write_text("")
    with pytest.raises(agent.ShadowProblem, match="did not pass"):
        shadow.come_home("done")
    assert (friend / "shadow.key").exists() and ran == []
    assert git("branch", "--list", cwd=kairu_repo).split() == ["*", "main"]


def test_called_back_unfinished_it_pushes_nothing_ends_its_kairu_and_leaves_the_changes_with_the_friend(owner, friend,
                                                                                                     kairu_repo, ran):
    shadow = owner.send(friend, pack="task-core")
    installed(shadow)
    (shadow.copy / "README.md").write_text("half done\n")  # changed, but Kairu's check has not run on it
    manager.recall(str(owner.data), owner.relay.url, 1.0)
    assert agent.Shadow(friend).tick() == "recalled"
    assert ("guardian", "uninstall") in ran and ("guardian", "quit") in ran
    assert (friend / "workspace" / "kairu" / "README.md").read_text() == "half done\n"
    assert not (friend / "shadow.key").exists()
    assert git("branch", "--list", cwd=kairu_repo).split() == ["*", "main"]
    record = owner.sync()
    assert record["state"] == "unfinished" and record["report"]["why"] == "the owner called it back"


def test_called_back_after_the_check_passed_it_brings_the_checked_work_home(owner, friend, kairu_repo, ran):
    shadow = owner.send(friend, pack="task-core")
    (shadow.copy / "README.md").write_text("finished\n")
    assert shadow.check(with_tests=True) == ([], 3)
    manager.recall(str(owner.data), owner.relay.url, 1.0)
    assert agent.Shadow(friend).tick() == "recalled"
    assert owner.sync()["state"] == "returned"
    assert git("show", f"{shadow.state['branch']}:README.md", cwd=kairu_repo) == "finished"


def test_the_friends_commands_for_a_cowork_shadow(owner, friend, monkeypatch, capsys, ran):
    monkeypatch.setenv("KAIRU_SHADOW_HOME", str(friend))
    owner.send(friend, pack="task-core")
    assert agent.main(["status"]) == 0
    said = capsys.readouterr().out
    assert "Kairu here: not installed yet (`setup`)" in said and "no changes to Kairu yet" in said
    monkeypatch.setattr(cowork, "setup", lambda copy, say=print: [])
    assert agent.main(["setup"]) == 0 and "under your own PIN" in capsys.readouterr().out
    (friend / "workspace" / "kairu" / "README.md").write_text("better\n")
    assert agent.main(["check"]) == 0 and "The done check passes (3 tests)" in capsys.readouterr().out
    assert agent.main(["home"]) == 0
    assert "Your 1 changed files are on the branch shadow/" in capsys.readouterr().out


def test_setup_is_refused_for_a_pack_shadow(tmp_path, relay, monkeypatch, capsys):  # noqa: F811
    from tests_kairu.test_shadow import Owner as PackOwner
    bare = tmp_path / "pack.git"
    git("init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    friend_home = tmp_path / "laptop" / "Kairu-shadow"
    PackOwner(tmp_path, relay, bare).send(friend_home)
    monkeypatch.setenv("KAIRU_SHADOW_HOME", str(friend_home))
    assert agent.main(["setup"]) == 1 and "for a Cowork Shadow" in capsys.readouterr().out


def test_a_shadows_db_from_shadow_v0_gets_the_new_columns(tmp_path):
    with sqlite3.connect(tmp_path / "shadows.db") as db:
        db.execute("CREATE TABLE shadows (number INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, friend TEXT "
                   "NOT NULL, mission TEXT NOT NULL, pack TEXT NOT NULL, branch TEXT NOT NULL, repo TEXT NOT NULL, hours REAL "
                   "NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, joined REAL, ended REAL, device TEXT, sign TEXT, "
                   "box TEXT, topic TEXT, since TEXT, last_seen REAL, progress TEXT, report TEXT)")
        db.execute("INSERT INTO shadows (id, friend, mission, pack, branch, repo, hours, state, created) VALUES "
                   "('sh-00000001', 'Omesh', 'old', 'expense-total', 'shadow/00000001-expense-total', 'r', 3, 'returned', 0)")
    old = ShadowStore(tmp_path).get(1)
    assert old["mode"] == "pack" and old["base"] == "" and old["state"] == "returned"
