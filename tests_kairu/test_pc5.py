"""PC5 (BAR.md "Commands and installs"): commands with no shell, their tiers from what they are, and winget installs."""

import os
import secrets
import sys

import pytest

from kairu import executors, policy
from kairu.policy import Tier
from kairu.tasks import core, skills, terminal
from kairu.tasks.store import TaskStore
from tests_kairu.helpers import POLICY

RULES = policy.load(POLICY).rules


@pytest.mark.parametrize("command, action", [
    ("git status", "terminal.run"), ("git log --oneline -5", "terminal.run"), ("git diff --stat", "terminal.run"),
    ("python --version", "terminal.run"), ("winget list", "terminal.run"), ("pip list", "terminal.run"),
    ("git branch", "terminal.run"), ("git branch -D main", "terminal.run_any"), ("git remote add x y", "terminal.run_any"),
    ("git pull", "terminal.run_work"), ("git commit -m 'fix the bar'", "terminal.run_work"), ("pytest -q", "terminal.run_work"),
    ("py -3.12 -m pytest tests_kairu", "terminal.run_work"), ("npm test", "terminal.run_work"), ("npm run build", "terminal.run_work"),
    ("git checkout -b pc5", "terminal.run_work"), ("npm run evil", "terminal.run_any"),
    ("git push --force", "terminal.run_any"), ("curl https://example.com", "terminal.run_any"), ("python -c print(1)", "terminal.run_any"),
    ("sudo apt install x", "terminal.admin"), ("runas /user:Administrator cmd", "terminal.admin"), ("gsudo winget", "terminal.admin"),
    ("bcdedit /set testsigning on", "terminal.admin"), ("netsh advfirewall set allprofiles state off", "terminal.admin"),
    ("powershell -enc ZQBjAGgAbwA=", "terminal.admin"), ("powershell Set-MpPreference -DisableRealtimeMonitoring 1", "terminal.admin"),
    ("powershell Start-Process cmd -Verb RunAs", "terminal.admin"), ("reg add HKLM\\Software\\x", "terminal.admin"),
    ("net user bob pass /add", "terminal.admin"), ("C:\\Windows\\System32\\sc.exe stop WinDefend", "terminal.admin"),
])
def test_a_commands_tier_comes_from_what_it_is(command, action):
    assert terminal.classify(command) == action


@pytest.mark.parametrize("command", ["git status | findstr x", "git status && del x", "dir > out.txt", "echo `whoami`",
                                     "echo $(whoami)", "git status; rm x", "", "x" * 401, "git commit -m 'never closed"])
def test_pipes_chains_redirection_and_broken_quotes_are_refused(command):
    with pytest.raises(terminal.TerminalRefused):
        terminal.classify(command)


def test_the_tiers_are_in_the_policy_and_admin_and_hidden_installs_have_no_way_through():
    expected = {"terminal.run": Tier.LOW, "terminal.run_work": Tier.MEDIUM, "terminal.run_any": Tier.HIGH, "apps.install": Tier.HIGH,
                "apps.uninstall": Tier.HIGH, "terminal.admin": Tier.CRITICAL, "apps.install_hidden": Tier.CRITICAL}
    assert {name: RULES[name].tier for name in expected} == expected
    assert "terminal.admin" not in executors.EXECUTORS and "apps.install_hidden" not in executors.EXECUTORS


@pytest.mark.parametrize("order, action", [
    ("run the kairu tests", "terminal.run_work"), ("git status", "terminal.run"), ("git pull in kairu", "terminal.run_work"),
    ("run the command git push", "terminal.run_any"), ("run the command sudo shutdown now", "terminal.admin"),
    ("install vlc", "apps.install"), ("install vlc silently", "apps.install_hidden"), ("quietly install zoom", "apps.install_hidden"),
    ("uninstall vlc", "apps.uninstall"),
])
def test_the_bar_picks_the_action_from_the_command_not_from_the_words_around_it(order, action):
    step = core._terminal_checked(core._step(skills.match(skills.SKILLS, order)))
    assert step.action == action
    assert "hidden" not in step.details


def test_commands_run_only_in_the_work_folder_or_kairus_own(tmp_path):
    work = tmp_path / "work"
    (work / "site").mkdir(parents=True)
    assert terminal.folder_of("", str(work)) == work.resolve()
    assert terminal.folder_of("site", str(work)) == (work / "site").resolve()
    assert terminal.folder_of("kairu", str(work)) == terminal.KAIRU_FOLDER
    for outside in ("..", "C:\\Windows", "/etc", "../../x", "missing"):
        with pytest.raises(terminal.TerminalRefused):
            terminal.folder_of(outside, str(work))


def test_an_apps_name_is_its_winget_id_when_known_and_a_hidden_install_is_never_done():
    assert terminal.app_id("VLC") == ("--id", "VideoLAN.VLC")
    assert terminal.app_id("Some App") == ("--name", "Some App")
    for bad in ("vlc silently", "x; rm", "--force", ""):
        with pytest.raises(terminal.TerminalRefused):
            terminal.app_id(bad)


def reply(data_dir, job):
    return TaskStore(data_dir).take_reply(job)


def test_on_the_pretend_pc_nothing_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIRU_TEST_PC", str(tmp_path / "pc"))
    job = secrets.token_hex(8)
    assert terminal.run_work(str(tmp_path), str(tmp_path / "work"), job, "git pull", "") is None
    assert "(pretend PC) Would run `git pull`" in reply(tmp_path, job).text
    job = secrets.token_hex(8)
    terminal.install(str(tmp_path), job, "vlc")
    assert "Would install vlc" in reply(tmp_path, job).text


def test_an_action_refuses_a_command_of_another_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIRU_TEST_PC", str(tmp_path / "pc"))
    job = secrets.token_hex(8)
    assert terminal.run(str(tmp_path), str(tmp_path / "work"), job, "git push --force", "") is terminal.REFUSED
    got = reply(tmp_path, job)
    assert not got.ok and "terminal.run_any, not terminal.run" in got.text


def test_a_safe_command_really_runs_with_no_shell_and_its_output_is_only_shown(tmp_path, monkeypatch):
    monkeypatch.delenv("KAIRU_TEST_PC", raising=False)
    job = secrets.token_hex(8)
    assert terminal.run(str(tmp_path), str(tmp_path / "work"), job, "python --version", "") is None
    got = reply(tmp_path, job)
    assert got.ok and "Ran `python --version` in work" in got.text and "Python 3" in got.text


def test_what_a_command_prints_is_cut_and_cleaned():
    printed = ("\x1b[32mok\x1b[0m\n" + "  ██████▒▒▒▒  45%\n" + "line\n" * 2000).encode()
    text = terminal.shown(printed)
    assert len(text) <= terminal.SHOWN + 1 and "\x1b" not in text and "██" not in text


def test_wingets_own_codes_are_said_in_words():
    assert "admin prompt" in terminal.winget_says(1602) and "already installed" in terminal.winget_says(0x8A15002B)
    assert "no app by that exact name" in terminal.winget_says(-1978335212) and terminal.winget_says(5) == ""
