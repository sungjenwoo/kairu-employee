"""A Cowork Shadow (ADR-039): a full Kairu on a friend's laptop, and its changes to Kairu come home as a pull request.

The owner's choices (14 Nov 2026): what the owner's laptop can do, the Shadow can do; the friend's own PIN approves
High steps there; nothing of the owner's goes with it (no Gmail, phone, memory or AI keys); and every change the friend
makes to Kairu comes home as a pull request the owner tests and merges.

    workspace/kairu/   the Shadow's copy of Kairu: the owner's repository at the base branch, on the Shadow's branch.
                       `python -m kairu.shadow setup` installs it there: its own .venv-guardian, Guardian started at
                       sign-in with the friend's own PIN, and the Kairu bar. Its data folder starts empty.

Done means: the copy has changes, and Kairu's own check (tools/check_guardian.py, every test) passes on exactly those
changes. Coming home commits them, pushes the branch with the friend's own git sign-in, and opens the pull request
against the base branch. Whenever the Shadow leaves (home, stop, recall, time), the Kairu it set up is ended and its
Task Scheduler tasks are removed, so it never stays running on the friend's laptop; when the work went home, the
whole copy is deleted, its data folder (with the friend's PIN) included.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from kairu.shadow import pack as packs

KAIRU = "kairu"
VENV = ".venv-guardian"
CHECK_SECONDS = 3600  # Kairu's whole check takes about 20 minutes on a laptop
PASSED = re.compile(r"Result: PASSED\s+(\d+) passed")


class CoworkProblem(Exception):
    pass


def folder(base: Path) -> Path:
    return base / "workspace" / KAIRU


def _env() -> dict:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    environment.pop("KAIRU_CONFIG", None)  # never another Kairu's settings: the copy uses its own config.yaml
    environment.pop("KAIRU_SHADOW_HOME", None)
    return environment


def git(*arguments, cwd=None, seconds: float = 300, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True, timeout=seconds, errors="replace",
                          stdin=subprocess.DEVNULL, env=env or _env(), **packs.HIDDEN)


def copy_kairu(repo: str, base: str, branch: str, target: Path) -> None:
    """The owner's Kairu at the base branch, on the Shadow's own branch. Raises CoworkProblem."""
    try:
        cloned = git("clone", "--quiet", "--single-branch", "--branch", base, repo, str(target), seconds=600)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CoworkProblem(f"git could not be run ({type(error).__name__}); is git installed?") from None
    if cloned.returncode != 0:
        raise CoworkProblem("Kairu could not be downloaded (does your GitHub sign-in have access to the owner's "
                            f"repository?): {cloned.stderr.strip()[-300:]}")
    made = git("checkout", "--quiet", "-b", branch, cwd=target)
    if made.returncode != 0:
        raise CoworkProblem(f"the Shadow's branch could not be made: {made.stderr.strip()[-300:]}")


def venv_python(copy: Path) -> Path:
    return copy / VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def set_up(copy: Path) -> bool:
    """True once `setup` has installed this copy (its private environment exists)."""
    return venv_python(copy).exists()


def kairu(copy: Path, *arguments, interactive: bool = False, seconds: float = 120) -> int:
    """`kairu ...` of the Shadow's copy, in its own environment. Interactive: the friend types (the PIN)."""
    argv = [str(venv_python(copy)), "-m", "kairu", *arguments]
    try:
        if interactive:
            return subprocess.run(argv, cwd=copy, env=_env(), timeout=seconds).returncode
        return subprocess.run(argv, cwd=copy, env=_env(), timeout=seconds, capture_output=True, text=True,
                              errors="replace", stdin=subprocess.DEVNULL, **packs.HIDDEN).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


def _live(argv, copy: Path, say, seconds: float) -> tuple[int, str]:
    """Run a program in the copy, showing what it prints as it goes. (exit code, everything it printed)."""
    said = []
    try:
        process = subprocess.Popen(argv, cwd=copy, env=_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace")
    except OSError as error:
        return 1, f"it could not be started ({error})"
    try:
        for line in process.stdout:
            said.append(line)
            if say:
                say(line.rstrip())
        return process.wait(timeout=seconds), "".join(said)
    except subprocess.TimeoutExpired:
        process.kill()
        return 1, "".join(said) + f"\nstill running after {seconds:g} seconds, so it was ended"


def setup(copy: Path, say=print) -> list[str]:
    """Install the copy: its private environment, Guardian at sign-in, the friend's own PIN, the Kairu bar.
    What did not work, in plain words ([] when all of it did)."""
    if not set_up(copy):
        say("Making Kairu's private environment and installing it (a few minutes) ...")
        code, said = _live([sys.executable, "-m", "venv", VENV], copy, None, 600)
        if code != 0:
            return [f"the private environment could not be made: {said.strip()[-300:]}"]
        code, said = _live([str(venv_python(copy)), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-e", "."],
                           copy, say, 1800)
        if code != 0:
            return [f"Kairu could not be installed: {said.strip()[-300:]}"]
    problems = []
    say("\nStarting Guardian, and at every sign-in (Task Scheduler) ...")
    if kairu(copy, "guardian", "install", interactive=True, seconds=120) != 0:
        problems.append("Guardian did not start. If another Kairu runs on this laptop, end it in its own folder first: "
                        "`kairu guardian uninstall`, `kairu guardian quit`, `kairu bar uninstall`, `kairu bar quit`")
        return problems
    say("\nNow set YOUR OWN PIN for this laptop (at least 6 characters). It approves High steps here; the owner's PIN "
        "never comes here.")
    if kairu(copy, "pin", "set", interactive=True, seconds=600) != 0:
        problems.append("the PIN was not set: run `python -m kairu.shadow setup` again")
    if kairu(copy, "bar", "install", interactive=True) != 0 or kairu(copy, "bar", interactive=True) != 0:
        problems.append("the Kairu bar did not start (Guardian works without it)")
    return problems


def tree(copy: Path) -> str:
    """git's id for exactly what the copy holds now, its files as git sees them (.gitignore'd ones left out)."""
    with tempfile.TemporaryDirectory(prefix="kairu-cowork-") as scratch:
        env = {**_env(), "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        for step in (("read-tree", "HEAD"), ("add", "--all")):
            done = git(*step, cwd=copy, env=env)
            if done.returncode != 0:
                raise CoworkProblem(f"git could not read the copy: {done.stderr.strip()[-300:]}")
        written = git("write-tree", cwd=copy, env=env)
    if written.returncode != 0:
        raise CoworkProblem(f"git could not read the copy: {written.stderr.strip()[-300:]}")
    return written.stdout.strip()


def changed(copy: Path, base: str, now: str) -> list[str]:
    """The files that differ from where the copy started (the base branch)."""
    done = git("diff", "--name-only", f"origin/{base}", now, cwd=copy)
    return [line for line in done.stdout.splitlines() if line.strip()] if done.returncode == 0 else []


def check(copy: Path, base: str, state: dict, run_check: bool, say=None) -> tuple[list[str], int]:
    """The done check. (what is still missing, how many Kairu tests passed). The check result is kept in `state` for
    exactly the files it ran on, so it runs again only when something changed."""
    if not copy.is_dir():
        return ["the Shadow's copy of Kairu is missing"], 0
    try:
        now = tree(copy)
    except CoworkProblem as problem:
        return [str(problem)], 0
    if not changed(copy, base, now):
        return ["no changes to Kairu yet: make them in the copy, then check again"], 0
    if state.get("checked") == now:
        return [], state.get("passed", 0)
    if not run_check:
        return ["Kairu's own check has not passed on these changes yet (`python -m kairu.shadow check` runs it, about "
                "20 minutes)"], 0
    if say:
        say("Running Kairu's own check on your changes (tools/check_guardian.py, about 20 minutes). Do not type while "
            "it runs: some tests press Ctrl+Alt+K.")
    code, said = _live([sys.executable, str(copy / "tools" / "check_guardian.py")], copy, say, CHECK_SECONDS)
    found = PASSED.search(said)
    if code != 0 or not found:
        return ["Kairu's own check did not pass on these changes. Its report: "
                f"{copy / 'guardian-check-report.txt'}"], 0
    if tree(copy) != now:
        return ["the files changed while the check ran: check again"], 0
    state.update(checked=now, passed=int(found.group(1)))
    return [], state["passed"]


def push(copy: Path, state: dict) -> str:
    """Commit the checked changes on the Shadow's branch and push it. The commit. Raises CoworkProblem."""
    if git("add", "--all", cwd=copy).returncode != 0:
        raise CoworkProblem("git could not add the changes")
    if git("diff", "--cached", "--quiet", cwd=copy).returncode != 0:
        identity = [] if git("config", "user.email", cwd=copy).stdout.strip() else \
            ["-c", "user.name=Kairu Shadow", "-c", "user.email=shadow@kairu.invalid"]
        made = git(*identity, "commit", "--quiet", "-m",
                   f"Cowork Shadow {state['pack']}: {state['mission']}\n\nBuilt by {state['friend']} in Shadow "
                   f"{state['shadow']}, from {state['base']}.", cwd=copy)
        if made.returncode != 0:
            raise CoworkProblem(f"the changes could not be committed: {made.stderr.strip()[-300:]}")
    if git("rev-parse", "HEAD^{tree}", cwd=copy).stdout.strip() != state.get("checked"):
        raise CoworkProblem("these are not the files Kairu's check passed on: check again")
    pushed = git("push", "--quiet", "origin", f"HEAD:refs/heads/{state['branch']}", cwd=copy, seconds=600)
    if pushed.returncode != 0:
        raise CoworkProblem("the branch could not be pushed (does your GitHub sign-in have access to the owner's "
                            f"repository?): {pushed.stderr.strip()[-300:]}")
    commit = git("rev-parse", "HEAD", cwd=copy).stdout.strip()
    there = git("ls-remote", "--heads", "origin", state["branch"], cwd=copy).stdout.split()
    if not there or there[0] != commit:
        raise CoworkProblem("the branch on the repository is not the commit that was pushed")
    return commit


def take_down(copy: Path) -> None:
    """End the Kairu the Shadow set up and remove its Task Scheduler tasks, so nothing of it keeps running here."""
    if not set_up(copy):
        return
    for step in (("bar", "uninstall"), ("bar", "quit"), ("workspace", "quit"), ("guardian", "uninstall"),
                 ("guardian", "quit")):
        kairu(copy, *step, seconds=60)
