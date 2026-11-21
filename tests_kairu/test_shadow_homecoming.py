"""A Cowork Shadow's homecoming (ADR-041): it explains what the friend built; after "yes" and the PIN, the owner's Kairu
upgrades itself with exactly those changes, only after Kairu's own check passes on the upgraded Kairu in a separate folder.

Uses the stand-in Kairu of test_shadow_cowork.py: its tools/check_guardian.py passes at once, or fails while a file named
BREAK is there.
"""

import sys

import pytest

from kairu import policy as policies
from kairu.executors import EXECUTORS, argument_problem
from kairu.policy import Tier
from kairu.shadow import homecoming, manager
from tests_kairu.helpers import POLICY
from tests_kairu.test_shadow import friend, git, relay  # noqa: F401 (fixtures)
from tests_kairu.test_shadow_cowork import installed, kairu_repo, owner, ran  # noqa: F401 (fixtures)

POLICY_BEFORE = """version: 1
actions:
  apps.open:
    tier: Medium
    description: Open an app
  money.spend:
    tier: Critical
    description: Spend money
  files.delete:
    tier: High
    description: Delete a file
"""
SKILL_RULES = """  screen.type:
    tier: Medium
    private: true
    description: Type words in a safe app's window
  screen.confirm:
    tier: High
    description: The same hands after your yes and PIN
"""
WHO = ["-c", "user.name=Omesh", "-c", "user.email=omesh@example.invalid"]


@pytest.fixture
def kairu_now(kairu_repo, tmp_path):  # noqa: F811
    """main of the owner's Kairu with a policy.yaml and a test file, then the owner's own Kairu folder: a clone of it."""
    seed = tmp_path / "seed-2"
    git("clone", "--quiet", str(kairu_repo), str(seed))
    (seed / "policy.yaml").write_text(POLICY_BEFORE)
    (seed / "tests_kairu").mkdir()
    (seed / "tests_kairu" / "test_a.py").write_text("def test_one():\n    pass\n\n\ndef test_two():\n    pass\n")
    git("add", "--all", cwd=seed)
    git(*WHO, "commit", "--quiet", "-m", "policy and tests", cwd=seed)
    git("push", "--quiet", "origin", "main", cwd=seed)
    root = tmp_path / "owners-kairu"
    git("clone", "--quiet", str(kairu_repo), str(root))
    return root


def build(shadow, policy_text=POLICY_BEFORE + SKILL_RULES, message="Kairu's hands: open Chrome, then type in the search bar",
          extra=None):
    """What the friend does in the copy: changes, one commit with their own words."""
    (shadow.copy / "policy.yaml").write_text(policy_text)
    (shadow.copy / "kairu_screen.py").write_text("SAFE_APPS = {'chrome', 'notepad'}\n")
    (shadow.copy / "tests_kairu" / "test_screen.py").write_text("def test_types():\n    pass\n")
    for name, text in (extra or {}).items():
        (shadow.copy / name).write_text(text)
    git("add", "--all", cwd=shadow.copy)
    git(*WHO, "commit", "--quiet", "-m", message, cwd=shadow.copy)


@pytest.fixture
def home(owner, friend, kairu_now, ran):  # noqa: F811
    """Omesh's Cowork Shadow, home with finished changes; the owner's PC has read its report."""
    shadow = owner.send(friend, pack="task-handling")
    installed(shadow)
    build(shadow, message="Kairu's hands: open Chrome, then type in the search bar\n\n\"Open Chrome, then in the search bar "
                          "type Instagram\" now works.\n\x1b[31mred\x1b[0m words stay plain text\n\n"
                          "Co-Authored-By: Claude <noreply@anthropic.com>")
    report = shadow.come_home("done")
    assert report["done"]
    owner.sync()
    return owner, kairu_now, report


def found(owner, number=1):
    return {**owner.store.get(number), "number": number}


def head(root):
    return git("rev-parse", "HEAD", cwd=root)


# --- the explanation -----------------------------------------------------------------------------------------------

def test_it_explains_what_the_friend_built_in_plain_words(home):
    owner, root, report = home
    commit = homecoming.fetch(root, found(owner))
    said = homecoming.explain(root, found(owner), commit)
    text = said.text()
    assert 'came home from Omesh: "Make the task core open sites in Chrome"' in text
    assert "* Kairu's hands: open Chrome, then type in the search bar" in text
    assert '"Open Chrome, then in the search bar type Instagram" now works.' in text
    assert "\x1b" not in text, [line for line in text.splitlines() if "\x1b" in line]
    assert "words stay plain text" in text  # a friend's words can't drive your terminal
    assert "Co-Authored-By" not in text
    assert "+ screen.type" in text and "Medium" in text and "+ screen.confirm" in text and "High" in text
    assert "new      kairu_screen.py" in text and "changed  policy.yaml" in text
    assert "Tests: 1 new tests; none removed" in text and "Watch: nothing unusual" in text
    assert not said.blocked


def test_the_explanation_is_made_by_rules_the_same_every_time(home):
    owner, root, _ = home
    commit = homecoming.fetch(root, found(owner))
    assert homecoming.explain(root, found(owner), commit).text() == homecoming.explain(root, found(owner), commit).text()


@pytest.mark.parametrize("new_rules,blocked", [
    ({"money.spend": {"tier": "High"}}, "makes the Critical rule money.spend High"),
    ({}, "removes the Critical rule money.spend"),
])
def test_loosening_a_critical_rule_can_never_be_installed(new_rules, blocked):
    old = {"money.spend": {"tier": "Critical"}, "apps.open": {"tier": "Medium"}}
    new = {"apps.open": {"tier": "Medium"}, **new_rules}
    assert any(blocked in line for line in homecoming.rule_changes(old, new)[3])


def test_a_lowered_tier_is_shown_plainly():
    added, removed, changed, blocked = homecoming.rule_changes({"files.delete": {"tier": "High"}}, {"files.delete": {"tier": "Medium"}})
    assert changed == ["  ~ files.delete         tier High -> Medium  <- LOWER: fewer checks"] and not blocked


# --- the upgrade ---------------------------------------------------------------------------------------------------

def test_the_upgrade_moves_your_kairu_to_exactly_the_shadows_commit(home):
    owner, root, report = home
    before = head(root)
    manager._upgrade(str(owner.data), 1, root, sys.executable, check_seconds=120)
    assert head(root) == report["commit"] and git("rev-parse", "HEAD^{tree}", cwd=root) == report["tree"]
    assert git("rev-parse", "HEAD~1", cwd=root) == before
    assert (root / "kairu_screen.py").exists() and "screen.type" in (root / "policy.yaml").read_text()
    assert owner.store.get(1)["state"] == "installed"
    assert not (owner.data / "shadow-upgrade-1").exists() and "shadow-upgrade" not in git("worktree", "list", cwd=root)


def test_a_branch_changed_after_it_came_home_is_not_installed(home, kairu_repo, tmp_path):  # noqa: F811
    owner, root, report = home
    sneaky = tmp_path / "sneaky"
    git("clone", "--quiet", "--branch", owner.store.get(1)["branch"], str(kairu_repo), str(sneaky))
    (sneaky / "policy.yaml").write_text(POLICY_BEFORE.replace("tier: Critical", "tier: Low"))
    git("add", "--all", cwd=sneaky)
    git(*WHO, "commit", "--quiet", "-m", "a small fix", cwd=sneaky)
    git("push", "--quiet", "origin", "HEAD", cwd=sneaky)
    before = head(root)
    with pytest.raises(SystemExit):
        manager._upgrade(str(owner.data), 1, root, sys.executable, check_seconds=120)
    assert head(root) == before and owner.store.get(1)["state"] == "returned"


def test_a_failing_check_on_the_upgraded_kairu_leaves_your_kairu_as_it_was(home):
    owner, root, _ = home
    (root / "BREAK").write_text("")  # the owner's own Kairu moved on since the Shadow left; together they fail
    git("add", "BREAK", cwd=root)
    git(*WHO, "commit", "--quiet", "-m", "something of the owner's", cwd=root)
    before = head(root)
    with pytest.raises(SystemExit):
        manager._upgrade(str(owner.data), 1, root, sys.executable, check_seconds=120)
    assert head(root) == before and not (root / "kairu_screen.py").exists()
    assert owner.store.get(1)["state"] == "returned" and "shadow-upgrade" not in git("worktree", "list", cwd=root)


def test_your_kairus_own_new_commits_are_kept_by_a_tested_merge(home):
    owner, root, report = home
    (root / "NOTES.md").write_text("the owner's own work\n")
    git("add", "NOTES.md", cwd=root)
    git(*WHO, "commit", "--quiet", "-m", "owner's notes", cwd=root)
    mine = head(root)
    manager._upgrade(str(owner.data), 1, root, sys.executable, check_seconds=120)
    assert (root / "NOTES.md").exists() and (root / "kairu_screen.py").exists()
    parents = git("rev-list", "--parents", "-n", "1", "HEAD", cwd=root).split()[1:]
    assert sorted(parents) == sorted([report["commit"], mine])


def test_uncommitted_changes_in_your_kairu_stop_the_upgrade(home):
    owner, root, _ = home
    (root / "README.md").write_text("half-done edit\n")
    with pytest.raises(SystemExit):
        manager._upgrade(str(owner.data), 1, root, sys.executable, check_seconds=120)
    assert (root / "README.md").read_text() == "half-done edit\n" and not (root / "kairu_screen.py").exists()


def test_a_clash_with_your_own_changes_is_left_to_you(home):
    owner, root, _ = home
    (root / "policy.yaml").write_text(POLICY_BEFORE + "  apps.close:\n    tier: Medium\n    description: Close an app\n")
    git("add", "policy.yaml", cwd=root)
    git(*WHO, "commit", "--quiet", "-m", "owner's own rule", cwd=root)
    before = head(root)
    with pytest.raises(SystemExit):
        manager._upgrade(str(owner.data), 1, root, sys.executable, check_seconds=120)
    assert head(root) == before


def test_a_shadow_that_loosens_a_critical_rule_is_never_installed(owner, friend, kairu_now, ran):  # noqa: F811
    shadow = owner.send(friend, pack="task-handling")
    installed(shadow)
    build(shadow, policy_text=POLICY_BEFORE.replace("    tier: Critical", "    tier: High"))
    shadow.come_home("done")
    owner.sync()
    before = head(kairu_now)
    commit = homecoming.fetch(kairu_now, found(owner))
    assert homecoming.explain(kairu_now, found(owner), commit).blocked
    with pytest.raises(SystemExit):
        manager._upgrade(str(owner.data), 1, kairu_now, sys.executable, check_seconds=120)
    assert head(kairu_now) == before


def test_only_a_cowork_shadow_that_came_home_finished_is_upgraded(owner, friend, kairu_now, ran):  # noqa: F811
    shadow = owner.send(friend, pack="task-handling")
    installed(shadow)
    shadow.come_home("recalled")  # called back before its check passed: nothing came home
    owner.sync()
    with pytest.raises(SystemExit):
        manager._upgrade(str(owner.data), 1, kairu_now, sys.executable, check_seconds=120)


# --- the rule ------------------------------------------------------------------------------------------------------

def test_the_upgrade_is_high_and_takes_only_the_shadows_number():
    rule = policies.load(POLICY).rules["shadow.upgrade"]
    assert rule.tier is Tier.HIGH and not rule.read_only
    executor = EXECUTORS["shadow.upgrade"]
    assert executor.target == "kairu.shadow.manager:upgrade" and executor.supplied == ("data_dir",)
    assert not argument_problem("shadow.upgrade", executor, {"shadow": 1.0})
    assert argument_problem("shadow.upgrade", executor, {"shadow": 1.0, "folder": "C:/elsewhere"})


def test_kairu_shadow_explain_prints_it_and_status_points_to_it(home, monkeypatch, capsys):
    from kairu import config
    from kairu.shadow import commands
    owner, root, _ = home
    monkeypatch.setattr(config, "ROOT", root)
    code, explained = commands._explain(owner.store, 1)
    out = capsys.readouterr().out
    assert code == 0 and "What Omesh built" in out and "+ screen.type" in out
    commands._status(owner.store, 1)
    assert "`kairu shadow explain 1`" in capsys.readouterr().out


def test_rules_you_added_since_it_left_are_not_shown_as_its_changes(home):
    owner, root, _ = home
    (root / "policy.yaml").write_text(POLICY_BEFORE + "  shadow.upgrade:\n    tier: High\n    description: yours\n")
    git("add", "policy.yaml", cwd=root)
    git(*WHO, "commit", "--quiet", "-m", "the owner's own new rule", cwd=root)
    commit = homecoming.fetch(root, found(owner))
    text = homecoming.explain(root, found(owner), commit).text()
    assert "shadow.upgrade" not in text and "+ screen.type" in text
