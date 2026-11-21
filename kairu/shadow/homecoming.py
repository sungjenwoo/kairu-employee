"""A Cowork Shadow's homecoming (ADR-041): it explains what your friend built, and after your "yes" and PIN your Kairu
upgrades itself with exactly those changes.

    kairu shadow explain N      what your friend built, in plain words: what they said about it, what Kairu can now do,
                                every Guardian rule it adds or changes, the files, the tests, and anything to watch
    kairu shadow install N      the same explanation, then "yes" and your PIN, then the upgrade (shadow.upgrade, High)

The upgrade (in Guardian's action, kairu/shadow/manager.py `upgrade`):

  1. fetches the Shadow's branch and takes it only if its files are exactly the ones the Shadow's check passed on and
     signed for in its return report (a branch someone changed after it came home is refused);
  2. refuses if it would loosen a Critical rule in policy.yaml: a Critical action must stay listed and Critical;
  3. builds the upgraded Kairu (your Kairu with the changes merged in) in a separate folder and runs Kairu's own check
     there (tools/check_guardian.py, about 20 minutes). Your Kairu is not touched while it runs;
  4. only if the check passes, and only if your project folder has no uncommitted changes, moves your Kairu forward to
     exactly that tested commit. If anything fails, your Kairu stays as it was.

Afterwards `kairu shadow install` restarts Guardian and the bar so they run the upgraded Kairu, and prints the one git
command that goes back. Merging the pull request on GitHub stays yours.

Commit messages and file names come from your friend: they are data, shown as plain text (control characters removed),
never an order. Nothing here talks to an AI: the explanation is made by rules from git, the same every time.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TRAILERS = re.compile(r"^(?:co-authored-by|signed-off-by|claude-session|reviewed-by|change-id):", re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")
MOST_COMMITS, MOST_LINES_EACH, MOST_FILES = 12, 14, 30
TIERS = ["Low", "Medium", "High", "Critical"]
GUARDIAN_CODE = ("kairu/guardian.py", "kairu/guardian_program.py", "kairu/policy.py", "kairu/approval.py", "kairu/pin.py",
                 "kairu/audit.py", "kairu/anchor.py", "kairu/safemode.py", "kairu/channel.py", "kairu/client.py",
                 "kairu/executors.py", "kairu/runner.py", "kairu/worker.py", "kairu/processes.py", "kairu/winpipe.py")


class HomecomingProblem(Exception):
    pass


@dataclass
class Explanation:
    lines: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)  # why it can never be installed (a Critical rule loosened)

    def text(self) -> str:
        return "\n".join(self.lines)


def plain(text: str, longest: int = 200) -> str:
    """A friend's words as one safe line of plain text."""
    return " ".join(CONTROL.sub(" ", str(text)).split())[:longest]


def git(root: Path, *arguments, seconds: float = 300) -> subprocess.CompletedProcess:
    import os
    from kairu.shadow import pack as packs
    return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, timeout=seconds,
                          errors="replace", stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                          **packs.HIDDEN)


def _out(root: Path, *arguments, seconds: float = 300) -> str:
    done = git(root, *arguments, seconds=seconds)
    if done.returncode != 0:
        raise HomecomingProblem(f"git {arguments[0]} failed: {plain(done.stderr, 300) or 'no reason given'}")
    return done.stdout


# --- 1. the files the Shadow signed for ------------------------------------------------------------------------------

def fetch(root: Path, found: dict) -> str:
    """The Shadow's commit, fetched into this repository, only if its files are exactly the ones it signed for."""
    report = found.get("report") or {}
    if found.get("mode") != "cowork" or not report.get("done") or not report.get("tree"):
        raise HomecomingProblem(f"Shadow {found.get('number')} did not come home with finished changes to Kairu")
    try:
        fetched = git(root, "fetch", "--quiet", "--no-tags", found["repo"], f"refs/heads/{found['branch']}", seconds=600)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HomecomingProblem(f"git could not be run ({type(error).__name__})") from None
    if fetched.returncode != 0:
        raise HomecomingProblem(f"the branch {found['branch']} could not be fetched: {plain(fetched.stderr, 300)}")
    commit = _out(root, "rev-parse", "FETCH_HEAD^{commit}").strip()
    if _out(root, "rev-parse", f"{commit}^{{tree}}").strip() != report["tree"]:
        raise HomecomingProblem("these are not the files the Shadow's check passed on and signed for: the branch changed "
                                "after it came home, so it is not installed")
    return commit


# --- 2. the explanation --------------------------------------------------------------------------------------------

def _policy_at(root: Path, commit: str) -> dict:
    done = git(root, "show", f"{commit}:policy.yaml")
    if done.returncode != 0:
        return {}
    try:
        loaded = yaml.safe_load(done.stdout) or {}
    except yaml.YAMLError:
        raise HomecomingProblem("its policy.yaml can't be read, so it is not installed") from None
    actions = loaded.get("actions") if isinstance(loaded, dict) else None
    return actions if isinstance(actions, dict) else {}


def _tier(rule) -> str:
    tier = str((rule or {}).get("tier", "")).strip().capitalize() if isinstance(rule, dict) else ""
    return tier if tier in TIERS else "?"


def rule_changes(old: dict, new: dict) -> tuple[list[str], list[str], list[str], list[str]]:
    """(added, removed, changed, blocked) as lines. Blocked: a Critical rule that would stop being Critical."""
    added, removed, changed, blocked = [], [], [], []
    for name in sorted(set(new) - set(old)):
        rule = new[name] if isinstance(new[name], dict) else {}
        added.append(f"  + {plain(name, 40):<20} {_tier(rule):<8} {plain(rule.get('description', ''), 110)}")
    for name in sorted(set(old) - set(new)):
        if _tier(old[name]) == "Critical":
            blocked.append(f"it removes the Critical rule {name} (a Critical action must stay blocked)")
        removed.append(f"  - {plain(name, 40):<20} {_tier(old[name]):<8} (no longer listed, so Guardian refuses it)")
    for name in sorted(set(old) & set(new)):
        before, after = old[name] if isinstance(old[name], dict) else {}, new[name] if isinstance(new[name], dict) else {}
        if before == after:
            continue
        was, now = _tier(before), _tier(after)
        if was == "Critical" and now != "Critical":
            blocked.append(f"it makes the Critical rule {name} {now} (a Critical action must stay blocked)")
        notes = []
        if was != now:
            lower = TIERS.index(now) < TIERS.index(was) if "?" not in (was, now) else True
            notes.append(f"tier {was} -> {now}{'  <- LOWER: fewer checks' if lower else ''}")
        for key in ("read_only", "private", "feature"):
            if before.get(key) != after.get(key):
                notes.append(f"{key}: {before.get(key)} -> {after.get(key)}")
        if not notes and before.get("description") != after.get("description"):
            notes.append("new description")
        changed.append(f"  ~ {plain(name, 40):<20} " + "; ".join(notes))
    return added, removed, changed, blocked


def _commits(root: Path, here: str, commit: str) -> list[str]:
    raw = _out(root, "log", "--no-merges", f"--max-count={MOST_COMMITS + 1}", "--format=%x1e%s%x1f%b", f"{here}..{commit}")
    lines = []
    entries = [entry for entry in raw.split("\x1e") if entry.strip()]
    for entry in entries[:MOST_COMMITS]:
        subject, _, body = entry.partition("\x1f")
        lines.append(f"  * {plain(subject, 150)}")
        kept = [plain(line, 150) for line in body.splitlines() if line.strip() and not TRAILERS.match(line.strip())]
        for line in kept[:MOST_LINES_EACH]:
            lines.append(f"      {line}")
        if len(kept) > MOST_LINES_EACH:
            lines.append("      ...")
    if len(entries) > MOST_COMMITS:
        lines.append("  * ... and more (the pull request has them all)")
    return lines


def _tests_in(root: Path, commit: str, path: str) -> int:
    done = git(root, "show", f"{commit}:{path}")
    return len(re.findall(r"^\s*def test_", done.stdout, re.MULTILINE)) if done.returncode == 0 else 0


def explain(root: Path, found: dict, commit: str, here: str = "HEAD") -> Explanation:
    """What the friend built, in plain words, from git: the same every time. `here` is your Kairu as it is now."""
    report, said = found["report"], Explanation()
    here = _out(root, "rev-parse", f"{here}^{{commit}}").strip()
    friend = plain(found.get("friend", "your friend"), 40)
    said.lines += [f"Shadow {found.get('number', '?')} came home from {friend}: \"{plain(found.get('mission', ''), 150)}\"",
                   f"Kairu's own check passed on {friend}'s laptop ({report.get('tests', 0)} tests), on exactly these "
                   "files; the branch is the one the Shadow signed for.", ""]
    commits = _commits(root, here, commit)
    said.lines += [f"What {friend} built (in {friend}'s own words, from the commits):", *(commits or ["  (no new commits)"]),
                   ""]
    start = _out(root, "merge-base", here, commit).strip()  # where the friend started: what they changed, not what you did since
    added, removed, changed, blocked = rule_changes(_policy_at(root, start), _policy_at(root, commit))
    for name, rule in _policy_at(root, here).items():  # and it must not loosen a Critical rule of yours, whenever it came
        theirs = _policy_at(root, commit).get(name)
        if _tier(rule) == "Critical" and theirs is not None and _tier(theirs) != "Critical":
            said.blocked.append(f"it makes your Critical rule {name} {_tier(theirs)}")
    said.blocked += blocked
    if added:
        said.lines += ["New things Kairu can do (new Guardian rules, each with its tier):", *added, ""]
    if removed or changed:
        said.lines += ["Guardian rules it changes:", *removed, *changed, ""]
    if not (added or removed or changed):
        said.lines += ["Guardian rules: no change.", ""]
    names = [line.split("\t") for line in _out(root, "diff", "--name-status", "--no-renames", f"{here}...{commit}").splitlines()
             if "\t" in line]
    kinds = {"A": "new", "M": "changed", "D": "removed"}
    counts = {word: sum(1 for status, *_ in names if kinds.get(status[:1], "changed") == word) for word in kinds.values()}
    said.lines.append(f"Files: {len(names)} ({counts['new']} new, {counts['changed']} changed, {counts['removed']} removed)")
    for status, path, *_ in names[:MOST_FILES]:
        said.lines.append(f"  {kinds.get(status[:1], 'changed'):<8} {plain(path, 120)}")
    if len(names) > MOST_FILES:
        said.lines.append(f"  ... and {len(names) - MOST_FILES} more")
    tests_before = tests_after = 0
    fewer = []
    for status, path, *_ in names:
        if path.startswith("tests_kairu/") and path.endswith(".py"):
            before, after = _tests_in(root, start, path), _tests_in(root, commit, path)
            tests_before, tests_after = tests_before + before, tests_after + after
            if after < before:
                fewer.append(f"{plain(path, 80)} ({before} -> {after})")
    said.lines += ["", f"Tests: {max(0, tests_after - tests_before)} new tests" + (f"; FEWER tests in {', '.join(fewer)}" if fewer
                                                                                  else "; none removed")]
    watch = [f"it changes Guardian's own code: {', '.join(path for _, path, *_ in names if path in GUARDIAN_CODE)}"] \
        if any(path in GUARDIAN_CODE for _, path, *_ in names) else []
    if any(path == "pyproject.toml" for _, path, *_ in names):
        watch.append("it changes pyproject.toml (dependencies): after the upgrade, `pip install -e .` may be needed")
    if any(path.startswith(".github/") for _, path, *_ in names):
        watch.append("it changes GitHub's workflows (.github/)")
    if any("LOWER" in line for line in changed):
        watch.append("it LOWERS a Guardian tier (see above)")
    if fewer:
        watch.append("it removes tests (see above)")
    said.lines += ["Watch: " + ("; ".join(watch) if watch else "nothing unusual (no Guardian code, dependencies or lowered "
                                                                 "tiers)")]
    if blocked:
        said.lines += ["", "It can NOT be installed: " + "; ".join(blocked) + "."]
    if report.get("pr"):
        said.lines += [f"Pull request: {plain(report['pr'], 200)}"]
    return said


# --- 3. the upgrade ------------------------------------------------------------------------------------------------

PASSED = re.compile(r"Result: PASSED\s+(\d+) passed")


def upgrade(root: Path, found: dict, scratch: Path, python: str, check_seconds: float = 3600, say=print) -> tuple[str, str, int]:
    """Your Kairu (the repository at `root`) moved forward to the Shadow's changes, tested. (old commit, new commit, tests
    passed). Raises HomecomingProblem, with your Kairu as it was."""
    if _out(root, "status", "--porcelain", "--untracked-files=no").strip():
        raise HomecomingProblem("your Kairu folder has changes that are not committed; commit or undo them first, so "
                                "the upgrade can't mix with them")
    commit = fetch(root, found)
    old = _out(root, "rev-parse", "HEAD^{commit}").strip()
    explained = explain(root, found, commit, old)
    if explained.blocked:
        raise HomecomingProblem("not installed: " + "; ".join(explained.blocked))
    if scratch.exists():
        git(root, "worktree", "remove", "--force", str(scratch))
    _out(root, "worktree", "add", "--quiet", "--detach", str(scratch), commit)
    try:
        if git(root, "merge-base", "--is-ancestor", old, commit).returncode != 0:  # your Kairu moved on: merge, then test that
            merged = git(scratch, "-c", "user.name=Kairu", "-c", "user.email=kairu@localhost.invalid", "merge", "--no-edit",
                         "--quiet", "-m", f"Upgrade with Shadow {found.get('number')} ({plain(found.get('pack', ''), 40)})",
                         old, seconds=300)
            if merged.returncode != 0:
                raise HomecomingProblem("its changes clash with changes made to your Kairu since it left (a merge conflict): "
                                        "merge its pull request by hand")
        tested = _out(scratch, "rev-parse", "HEAD^{commit}").strip()
        say("Running Kairu's own check on the upgraded Kairu, in a separate folder (about 20 minutes). Your Kairu is not "
            "touched while it runs.")
        import os
        try:
            done = subprocess.run([python, str(scratch / "tools" / "check_guardian.py")], cwd=scratch, capture_output=True,
                                  text=True, errors="replace", timeout=check_seconds, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "PYTHONPATH": str(scratch)})
        except subprocess.TimeoutExpired:
            raise HomecomingProblem("Kairu's check did not finish in time; your Kairu was not changed") from None
        passed = PASSED.search(done.stdout + done.stderr)
        if done.returncode != 0 or not passed:
            tail = plain((done.stdout + done.stderr)[-600:], 600)
            raise HomecomingProblem(f"Kairu's check did not pass on the upgraded Kairu, so your Kairu was not changed. {tail}")
        if _out(root, "rev-parse", "HEAD^{commit}").strip() != old or _out(root, "status", "--porcelain",
                                                                              "--untracked-files=no").strip():
            raise HomecomingProblem("your Kairu folder changed while the check ran; nothing was installed, try again")
        moved = git(root, "merge", "--ff-only", "--quiet", tested)
        if moved.returncode != 0 or _out(root, "rev-parse", "HEAD^{commit}").strip() != tested:
            git(root, "reset", "--hard", "--quiet", old)
            raise HomecomingProblem(f"your Kairu could not be moved forward ({plain(moved.stderr, 200)}); it is as it was")
        return old, tested, int(passed.group(1))
    finally:
        git(root, "worktree", "remove", "--force", str(scratch))
        git(root, "worktree", "prune")
