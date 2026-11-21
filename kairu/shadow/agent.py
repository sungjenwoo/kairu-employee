"""The Shadow itself: the small program that runs on a friend's laptop (SHADOW.md). `python -m kairu.shadow ...`

    join "kairu-shadow:1:..." 123456   join with the invite and the 6-digit code the owner gave you (15 minutes)
    setup                              Cowork only: install the Shadow's copy of Kairu here, with your own PIN
    status                             the mission, the time left, and what is still missing
    check                              the done check: the pack check and the pack's own tests
    home                               come home: only when the done check passes
    stop                               your Stop: the Shadow ends now and removes itself; your files stay
    run [--window]                     the background part (join starts it): progress, "come back now", the time limit

What it is allowed, all of it:

  - one folder of its own, ~/Kairu-shadow (KAIRU_SHADOW_HOME changes it): its sealed temporary key, its state, and
    workspace/PACK, which starts as an empty scaffold. It reads and writes nothing else on this laptop; a pack may
    hold plain files only, so a link out of the folder is refused before anything is sent;
  - the Gate, for messages to the owner's PC only: progress (counts and a test result, never file contents) and one
    return report. It can ask the owner's Kairu for nothing: its messages are never requests;
  - git, when it comes home: packs/PACK goes to the owner's repository as a new branch, with your own git sign-in.
    Nothing else of this laptop is copied anywhere.

It carries nothing of the owner's: no memory, no files, no keys but its own temporary one. In v0 it has no AI of its
own either: you build with your own tools (your own Claude, your editor) inside the workspace.

When it leaves (home, stop, "come back now" or the time limit) it deletes its key and its state, tells the owner's PC,
which forgets the key too, and writes you a receipt next to the folder. A finished pack is on the branch, so the
folder is removed; unfinished work is yours and stays where it is.

Needs Python 3.12 and PyNaCl (the same message crypto as the phone); nothing else of Kairu runs here.

A Cowork Shadow (kairu/shadow/cowork.py, ADR-039) is different on three points: its workspace holds a copy of the owner's
Kairu that `setup` installs here under the friend's own PIN (nothing of the owner's comes with it), its done check is
Kairu's own check, and it brings home every change to Kairu as a branch and a pull request. The Kairu it set up is ended
and taken out of Task Scheduler whenever it leaves.
"""

import argparse
import base64
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from nacl.public import PrivateKey
from nacl.signing import SigningKey

from kairu.link import keys
from kairu.link.message import Rejected, open_envelope, seal, sender_of
from kairu.link.relay import Relay, RelayError
from kairu.link.store import Device
from kairu.protect import sealed
from kairu.shadow import cowork, kinds, lessons, pack as packs, wire

POLL_SECONDS, PROGRESS_SECONDS = 60, 600
KEY, STATE, WORK, LOG, BEAT = "shadow.key", "state.json", "workspace", "shadow.log", "run.beat"

SKILL = f'''"""{{title}}

{packs.UNFINISHED}: write the use case here, then take this line out.
Kairu calls run(text) with the owner's words and shows what it returns.
"""


def run(text: str) -> str:
    return "not built yet"
'''
TEST = f'''"""{packs.UNFINISHED}: test the use case here, then take this line out. `python -m kairu.shadow check` runs it."""

import unittest

import skill


class SkillTest(unittest.TestCase):
    def test_it_answers_with_text(self):
        self.assertIsInstance(skill.run("hello"), str)
'''
READ_ME = f"""# {{title}}

{packs.UNFINISHED}: say what this use case does, how to use it (what to say to Kairu, what comes back) and what it
needs, in at least five lines. Then take this line out.
"""
MISSION = """# Shadow mission for {friend}

**Build:** {mission}

**Where:** only in the folder `{pack}` next to this file. That folder is the skill pack that goes home to Kairu.

**Done means** (`python -m kairu.shadow check` shows what is still missing):

- `{pack}/skill.py` has `def run(text) -> str`: the owner's words in, the answer out as text
- `{pack}/tests/test_*.py` are unittest tests, and they all pass
- `{pack}/README.md` says what it does and how to use it
- the pack uses Python's standard library and its own files only: text files, no links, small
- no `{todo}` marker is left

**Then:** `python -m kairu.shadow home`. The pack goes to the branch `{branch}` of {repo},
the owner's Kairu is told, and the Shadow removes itself. The owner tests it and installs it with their PIN.

**Optional:** up to five general lessons (not about your files) in `LESSONS.md` here, one per line starting with "- ".

**Your Stop:** `python -m kairu.shadow stop` ends the Shadow at once. Time limit: {hours:g} hours from joining.
"""


COWORK_MISSION = """# Cowork Shadow mission for {friend}

**Work on Kairu:** {mission}

**Where:** the folder `kairu` next to this file: a full copy of Kairu, on the branch `{branch}` (it started from
`{base}`). Change anything in it: the task core, the bar, skills, docs, tests.

**First, once:** `python -m kairu.shadow setup` installs this copy here: Guardian (started at sign-in), YOUR OWN PIN for
this laptop, and the Kairu bar (Ctrl+Alt+Space). It works on this laptop only. Nothing of the owner's is in it: no Gmail,
phone, memory or AI keys (add your own free AI key in it if you need the brain). After you change Kairu's code, restart
it to use the change: in the `kairu` folder, `.venv-guardian\\Scripts\\kairu guardian quit`, then `... guardian run`.

**Done means** (`python -m kairu.shadow check` shows what is still missing):

- the copy has your changes
- Kairu's own check passes on exactly those changes (`check` runs it: about 20 minutes, do not type meanwhile). Leave
  `config.yaml` as it came: two of the check's tests need voice and research switched off in it

**Then:** `python -m kairu.shadow home`. Your changes go to the branch `{branch}` of {repo} with a pull request; the
owner tests and merges it. The Kairu set up here is ended and removed, and the copy with it.

**Optional:** up to five general lessons (not about your files) in `LESSONS.md` here, one per line starting with "- ".

**Your Stop:** `python -m kairu.shadow stop` ends the Shadow at once (your changes stay here, nothing is pushed).
Time limit: {hours:g} hours from joining.
"""


class ShadowProblem(Exception):
    pass


def home_folder() -> Path:
    return Path(os.environ.get("KAIRU_SHADOW_HOME") or Path.home() / "Kairu-shadow")


def _git(*arguments, cwd=None, seconds: float = 180) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True, timeout=seconds, errors="replace",
                          stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, **packs.HIDDEN)


class Shadow:
    def __init__(self, base: Path | None = None):
        self.base = Path(base or home_folder())
        try:
            self.state = json.loads((self.base / STATE).read_text(encoding="utf-8"))
            secret = sealed.read(self.base / KEY, kinds.SEAL_PURPOSE)
        except (OSError, ValueError, sealed.SealBroken):
            self.state = secret = None
        if not self.state or not secret:
            raise ShadowProblem("no Shadow is on this laptop (`python -m kairu.shadow join INVITE CODE` starts one)")
        signing = SigningKey(base64.b64decode(secret["sign"]))
        self.me = keys.Identity(keys.device_id(bytes(signing.verify_key)), signing, PrivateKey(base64.b64decode(secret["box"])))
        self.topic = secret["topic"]
        pc = self.state["pc"]
        self.pc = Device(pc["id"], "the owner's PC", base64.b64decode(pc["sign"]), base64.b64decode(pc["box"]), self.topic, 0.0)

    # joining

    @classmethod
    def join(cls, invite_text: str, code: str, base: Path | None = None, wait: float = 90) -> "Shadow":
        base = Path(base or home_folder())
        if (base / KEY).exists():
            raise ShadowProblem(f"a Shadow is already on this laptop ({base}); `python -m kairu.shadow stop` ends it")
        if (base / WORK).exists():
            raise ShadowProblem(f"{base / WORK} is still there from an earlier Shadow: move your files out of it first")
        try:
            invite = wire.read_invite(invite_text)
        except wire.NotAnInvite as problem:
            raise ShadowProblem(str(problem)) from None
        if invite["expires"] < time.time():
            raise ShadowProblem("that invite has ended (it is valid 15 minutes); ask for a new one")
        code = "".join(ch for ch in code if ch.isdigit())
        copied = None
        if invite["mode"] == "cowork":  # the copy of Kairu first: if it cannot be made, nothing is joined
            print(f"Downloading Kairu ({invite['base']}) for this Cowork Shadow ...", flush=True)
            copied = cowork.folder(base)
            try:
                cowork.copy_kairu(invite["repo"], invite["base"], invite["branch"], copied)
            except cowork.CoworkProblem as problem:
                _remove_tree(base / WORK)
                raise ShadowProblem(str(problem)) from None
        try:
            return cls._join(invite, code, base, wait, copied)
        except BaseException:
            if copied is not None:
                _remove_tree(base / WORK)
            raise

    @classmethod
    def _join(cls, invite: dict, code: str, base: Path, wait: float, copied: Path | None) -> "Shadow":
        me, gate, since = keys.new_identity("dev"), Relay(invite["relay"]), int(time.time()) - 5
        pc = Device(invite["pc"], "the owner's PC", base64.b64decode(invite["sign"]), base64.b64decode(invite["box"]),
                    invite["topic"], 0.0)
        try:
            gate.publish(invite["topic"], wire.join_request(me, invite, code, f"Shadow for {invite['friend']}"))
            deadline, joined, seen = time.monotonic() + wait, None, set()
            while joined is None and time.monotonic() < deadline:
                for event in gate.poll([invite["topic"]], since):
                    text = event.get("message")
                    if not isinstance(text, str) or sender_of(text) != pc.id:
                        continue
                    try:
                        message = open_envelope(text, me, lambda sender: pc if sender == pc.id else None,
                                                lambda device, nonce, ts, now: nonce not in seen and not seen.add(nonce),
                                                relay_time=event.get("time"))
                    except Rejected:
                        continue
                    said = wire.to_shadow(message.body)
                    if said and said["kind"] == "joined" and said["pc"] == pc.id:
                        joined = said
                        break
                if joined is None:
                    time.sleep(1)
        except RelayError as error:
            raise ShadowProblem(f"the Gate could not be reached ({error})") from None
        if joined is None:
            raise ShadowProblem("the owner's PC did not answer: a wrong code, or the invite ended. Nothing was set up")
        base.mkdir(parents=True, exist_ok=True)
        now = time.time()
        sealed.write(base / KEY, {"sign": base64.b64encode(bytes(me.signing)).decode(),
                                  "box": base64.b64encode(bytes(me.private)).decode(), "topic": joined["topic"]},
                     kinds.SEAL_PURPOSE)
        state = {key: invite[key] for key in ("shadow", "friend", "mission", "pack", "branch", "repo", "hours", "relay",
                                              "mode", "base")}
        state.update(pc={"id": invite["pc"], "sign": invite["sign"], "box": invite["box"]}, joined=now,
                     ends=now + invite["hours"] * 3600, since=str(int(now) - 5), nonces=[], recalled=False, said=0, last="")
        (base / STATE).write_text(json.dumps(state, indent=1), encoding="utf-8")
        shadow = cls(base)
        if copied is None:
            shadow.scaffold()
        else:
            (base / WORK / "MISSION.md").write_text(COWORK_MISSION.format(**state), encoding="utf-8")
        shadow.log("joined")
        return shadow

    def scaffold(self) -> None:
        """The empty workspace: the mission, and a pack that is not written yet."""
        state, folder = self.state, self.pack_folder
        (folder / packs.TESTS).mkdir(parents=True)
        title = state["mission"][:60]
        about = {"pack": 1, "name": state["pack"], "title": title, "description": state["mission"], "version": "0.1",
                 "entry": packs.ENTRY, "made_by": state["friend"]}
        (folder / packs.MANIFEST).write_text(json.dumps(about, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / packs.ENTRY).write_text(SKILL.format(title=title.replace('"', "'")), encoding="utf-8")
        (folder / packs.TESTS / "test_skill.py").write_text(TEST, encoding="utf-8")
        (folder / packs.README).write_text(READ_ME.format(title=title), encoding="utf-8")
        (self.base / WORK / "MISSION.md").write_text(MISSION.format(todo=packs.UNFINISHED, **state), encoding="utf-8")

    # where it is

    @property
    def pack_folder(self) -> Path:
        return self.base / WORK / self.state["pack"]

    @property
    def cowork(self) -> bool:
        return self.state.get("mode") == "cowork"

    @property
    def copy(self) -> Path:
        return cowork.folder(self.base)

    def save(self) -> None:
        if not (self.base / KEY).exists():  # it has left (home or stop in another terminal): write nothing back
            return
        temp = self.base / (STATE + ".tmp")
        try:
            temp.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
            os.replace(temp, self.base / STATE)
        except OSError as error:
            self.log(f"the state was not saved ({error})")

    def log(self, text: str) -> None:
        try:
            with open(self.base / LOG, "a", encoding="utf-8") as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
        except OSError:
            pass

    def seconds_left(self) -> float:
        return self.state["ends"] - time.time()

    # the done check

    def check(self, with_tests: bool = True, say=None) -> tuple[list[str], int]:
        """(what is still missing, how many tests passed). Done means: nothing missing.
        A Cowork Shadow runs Kairu's own check only when with_tests (and only on changes it has not passed on yet)."""
        if self.cowork:
            problems, passed = cowork.check(self.copy, self.state["base"], self.state, with_tests, say)
            self.save()
            return problems, passed
        problems = packs.check(self.pack_folder, self.state["pack"])
        if problems or not with_tests:
            return problems, 0
        passed, ran, tail = packs.run_tests(self.pack_folder)
        if not passed:
            return [f"the tests do not all pass ({ran} ran):\n{tail}"], 0
        return packs.check(self.pack_folder, self.state["pack"]), ran  # again: the tests must not have changed the pack

    # talking to the owner's PC

    def say(self, kind: str, **fields) -> None:
        Relay(self.state["relay"]).publish(self.topic, seal(self.me, self.pc.id, self.pc.box, "report",
                                                            wire.body(kind, **fields)))

    def _remember(self, device: str, nonce: str, ts: float, now: float) -> bool:
        if nonce in self.state["nonces"]:
            return False
        self.state["nonces"] = (self.state["nonces"] + [nonce])[-200:]
        return True

    def hear(self) -> bool:
        """Read the Gate. True once the owner has said "come back now"."""
        for event in Relay(self.state["relay"]).poll([self.topic], self.state["since"]):
            text = event.get("message")
            self.state["since"] = str(event.get("id") or self.state["since"])
            if not isinstance(text, str) or sender_of(text) != self.pc.id:
                continue
            try:
                message = open_envelope(text, self.me, lambda sender: self.pc if sender == self.pc.id else None,
                                        self._remember, relay_time=event.get("time"))
            except Rejected:
                continue
            said = wire.to_shadow(message.body)
            if said and said["kind"] == "recall":
                self.state["recalled"] = True
        self.save()
        return self.state["recalled"]

    def progress(self, force: bool = False) -> None:
        """Tell the owner's PC how far the work is: counts and a test result only, and only when something changed."""
        if self.cowork:
            try:
                found = cowork.tree(self.copy)
            except cowork.CoworkProblem:
                found = "problem"
        else:
            try:
                found = packs.digest(self.pack_folder)
            except packs.PackProblem:
                found = "problem"
        if not force and (found == self.state["last"] or time.time() - self.state["said"] < PROGRESS_SECONDS):
            return
        problems, ran = self.check(with_tests=not self.cowork)  # Kairu's own check is 20 minutes: never in the background
        tests = f"{ran} pass" if not problems else ("failing" if any("tests do not" in item for item in problems) else "not ready")
        if self.cowork:
            count = len(cowork.changed(self.copy, self.state["base"], found)) if found != "problem" else 0
        else:
            try:
                count = len(packs.files(self.pack_folder))
            except packs.PackProblem:
                count = 0
        self.say("progress", files=count, tests=tests, ready=not problems,
                 note=f"{len(problems)} thing(s) still missing" if problems else "the done check passes")
        self.state.update(last=found, said=time.time())
        self.save()

    def tick(self) -> str | None:
        """One round of the background part. Why the Shadow went home ("recalled", "time"), or None while it stays."""
        (self.base / BEAT).write_text(str(os.getpid()))
        try:
            recalled = self.hear()
        except RelayError as error:
            self.log(f"the Gate could not be read ({error})")
            recalled = self.state["recalled"]
        why = "recalled" if recalled else ("time" if self.seconds_left() <= 0 else None)
        if why:
            self.come_home(why)
            return why
        try:
            self.progress()
        except RelayError as error:
            self.log(f"progress was not sent ({error})")
        return None

    # coming home

    def come_home(self, why: str = "done", say=None) -> dict:
        """Come home. why: done (only when the done check passes), recalled, time or stopped. The report that was sent."""
        if self.cowork:
            return self._come_home_cowork(why, say)
        problems, ran = self.check()
        finished = not problems and why != "stopped"  # the friend's Stop only ends it: nothing is pushed
        if why == "done" and not finished:
            raise ShadowProblem("not done yet, so the Shadow stays:\n  - " + "\n  - ".join(problems))
        commit = link = ""
        if finished:
            try:
                commit, link = self.push()
            except ShadowProblem as problem:
                if why == "done":
                    raise
                self.log(f"the pack was not pushed ({problem})")
                finished = False
        state = self.state
        words = {"done": "the use case is finished", "recalled": "the owner called it back",
                 "time": "its time limit ended", "stopped": f"{state['friend']} stopped it"}[why]
        report = {"done": finished, "why": words,
                  "pack": state["pack"], "digest": packs.digest(self.pack_folder) if finished else "",
                  "files": len(packs.files(self.pack_folder)) if finished else 0, "tests": ran if finished else 0,
                  "commit": commit, "pr": link, "uses": packs.uses(self.pack_folder) if finished else [],
                  "lessons": self.lessons() if finished else []}
        sent = self._send_report(report, must=why == "done")
        receipt = self._receipt(report, sent)
        self.log(f"came home: {words}")
        self.leave(remove_work=finished)
        return {**report, "receipt": str(receipt), "sent": sent}

    def _come_home_cowork(self, why: str, say) -> dict:
        state = self.state
        problems, passed = self.check(with_tests=why == "done", say=say)  # called back: only an already passed check
        finished = not problems and why != "stopped"
        if why == "done" and not finished:
            raise ShadowProblem("not done yet, so the Shadow stays:\n  - " + "\n  - ".join(problems))
        commit = link = ""
        if finished:
            try:
                commit = cowork.push(self.copy, state)
                link = self._pull_request(self.copy)
            except cowork.CoworkProblem as problem:
                if why == "done":
                    raise ShadowProblem(str(problem)) from None
                self.log(f"the changes were not pushed ({problem})")
                finished = False
        words = {"done": "the work on Kairu is finished", "recalled": "the owner called it back",
                 "time": "its time limit ended", "stopped": f"{state['friend']} stopped it"}[why]
        names = cowork.changed(self.copy, state["base"], state.get("checked", "")) if finished else []
        report = {"done": finished, "why": words, "pack": state["pack"], "digest": "", "tree": state["checked"] if finished else "",
                  "changed": names, "files": len(names), "tests": passed if finished else 0, "commit": commit, "pr": link,
                  "uses": [], "lessons": self.lessons() if finished else []}
        sent = self._send_report(report, must=why == "done")
        cowork.take_down(self.copy)
        receipt = self._receipt(report, sent)
        self.log(f"came home: {words}")
        self.leave(remove_work=finished)
        return {**report, "receipt": str(receipt), "sent": sent}

    def lessons(self) -> list[str]:
        try:
            text = (self.base / WORK / lessons.FILE_NAME).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        names = [] if self.cowork else [path.stem for path in packs.files(self.pack_folder)]
        try:
            user = getpass.getuser()
        except (OSError, KeyError):
            user = ""
        return lessons.keep_general(lessons.read(text), private=(self.state["friend"], self.state["pack"], user, *names))

    def _send_report(self, report: dict, must: bool) -> bool:
        for attempt in range(3):
            try:
                self.say("return", **report)
                return True
            except RelayError as error:
                self.log(f"the report was not sent ({error})")
                time.sleep(2 * (attempt + 1))
        if must:
            raise ShadowProblem("the pack is on its branch, but the owner's PC could not be told through the Gate. "
                                "Try `python -m kairu.shadow home` again when you are online")
        return False

    def push(self) -> tuple[str, str]:
        """packs/PACK to the owner's repository as the Shadow's branch. (the commit, the pull request or where to open it)."""
        state, name = self.state, self.state["pack"]
        scratch = Path(tempfile.mkdtemp(prefix="kairu-shadow-push-"))
        try:
            clone = scratch / "repo"
            try:
                cloned = _git("clone", "--quiet", "--depth", "1", state["repo"], str(clone))
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ShadowProblem(f"git could not be run ({type(error).__name__}); is git installed?") from None
            if cloned.returncode != 0:
                raise ShadowProblem(f"the repository could not be read: {cloned.stderr.strip()[-300:]}")
            existing = _git("ls-remote", "--heads", "origin", state["branch"], cwd=clone)
            sha = packs.digest(self.pack_folder)
            if existing.stdout.strip():  # an earlier try got this far: the branch is this Shadow's own
                _git("fetch", "--quiet", "--depth", "1", "origin", f"refs/heads/{state['branch']}", cwd=clone)
                _git("checkout", "--quiet", "-B", state["branch"], "FETCH_HEAD", cwd=clone)
            else:
                if (clone / "packs" / name).exists():
                    raise ShadowProblem(f"Kairu already has a pack named {name}; ask the owner for a Shadow with another name")
                _git("checkout", "--quiet", "-b", state["branch"], cwd=clone)
            target = clone / "packs" / name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(self.pack_folder, target, ignore=shutil.ignore_patterns(*packs.SKIPPED))
            _git("add", "--all", "--", f"packs/{name}", cwd=clone)
            if _git("diff", "--cached", "--quiet", cwd=clone).returncode != 0:
                identity = [] if _git("config", "user.email", cwd=clone).stdout.strip() else \
                    ["-c", "user.name=Kairu Shadow", "-c", "user.email=shadow@kairu.invalid"]
                about = packs.manifest(self.pack_folder)
                made = _git(*identity, "commit", "--quiet", "-m",
                            f"Shadow pack {name}: {about['title']}\n\nBuilt by {state['friend']} in Shadow {state['shadow']}.\n"
                            f"Pack digest: {sha}", cwd=clone)
                if made.returncode != 0:
                    raise ShadowProblem(f"the pack could not be committed: {made.stderr.strip()[-300:]}")
            pushed = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{state['branch']}", cwd=clone)
            if pushed.returncode != 0:
                raise ShadowProblem("the branch could not be pushed (does your GitHub sign-in have access to the owner's "
                                    f"repository?): {pushed.stderr.strip()[-300:]}")
            commit = _git("rev-parse", "HEAD", cwd=clone).stdout.strip()
            there = _git("ls-remote", "--heads", "origin", state["branch"], cwd=clone).stdout.split()
            if not there or there[0] != commit:
                raise ShadowProblem("the branch on the repository is not the commit that was pushed")
            return commit, self._pull_request(clone)
        finally:
            _remove_tree(scratch)

    def _pull_request(self, clone: Path) -> str:
        state = self.state
        slug = _github_slug(state["repo"])
        if not slug:
            return ""
        if shutil.which("gh"):
            try:
                made = subprocess.run(
                    ["gh", "pr", "create", "--repo", slug, "--head", state["branch"], *self._pull_request_words()],
                    cwd=clone, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, errors="replace",
                    **packs.HIDDEN)
                if made.returncode == 0 and made.stdout.strip().startswith("https://"):
                    return made.stdout.strip().splitlines()[-1]
            except (OSError, subprocess.TimeoutExpired):
                pass
        if self.cowork:
            return f"https://github.com/{slug}/compare/{state['base']}...{state['branch']}?expand=1"
        return f"https://github.com/{slug}/compare/{state['branch']}?expand=1"

    def _pull_request_words(self) -> list[str]:
        state = self.state
        if self.cowork:
            return ["--base", state["base"], "--title", f"Cowork Shadow: {state['mission'][:80]} (from {state['friend']})",
                    "--body", f"Changes to Kairu made in Cowork Shadow {state['shadow']}, started from `{state['base']}`: "
                              f"{state['mission']}\n\nKairu's own check passed on exactly these changes on "
                              f"{state['friend']}'s laptop. The owner tests them (`py -3.12 tools\\check_guardian.py`) and "
                              "merges; nothing installs by itself."]
        return ["--title", f"Shadow pack {state['pack']} (from {state['friend']})", "--body",
                f"A use case built in Shadow {state['shadow']}: {state['mission']}\n\nIt adds only packs/{state['pack']}. "
                "The owner installs it with `kairu shadow install` after testing (\"yes\" and the PIN)."]

    def _receipt(self, report: dict, sent: bool) -> Path:
        """The friend's receipt (glass box): what left this laptop, and that nothing else did."""
        state = self.state
        lines = [f"Kairu Shadow {state['shadow']}: receipt for {state['friend']}", "",
                 f"Mission: {state['mission']}", f"Ended:   {time.strftime('%Y-%m-%d %H:%M')}, because {report['why']}", ""]
        if report["done"] and self.cowork:
            lines += [f"What left this laptop: your changes to Kairu ({report['files']} files), pushed to the branch",
                      f"  {state['branch']} of {state['repo']}", f"  commit {report['commit']}",
                      f"  Kairu's own check passed here on exactly these files ({report['tests']} tests)", ""]
            lines += [f"    {name}" for name in report["changed"]]
            lines += ["", "Lessons it took home (general know-how only):"] + \
                     ([f"  - {line}" for line in report["lessons"]] or ["  (none)"])
        elif report["done"]:
            lines += [f"What left this laptop: the folder packs/{state['pack']} ({report['files']} files), pushed to the branch",
                      f"  {state['branch']} of {state['repo']}", f"  commit {report['commit']}",
                      f"  pack digest (SHA-256) {report['digest']}", f"  {report['tests']} tests passed here before it left", ""]
            for relative in packs.files(self.pack_folder):
                lines.append(f"    {relative.as_posix()}")
            lines += ["", "Lessons it took home (general know-how only):"] + \
                     ([f"  - {line}" for line in report["lessons"]] or ["  (none)"])
        else:
            lines += ["Nothing was pushed: the use case was not finished.",
                      f"Your files are still in {self.base / WORK}; they are yours."]
        if self.cowork:
            lines += ["", "The Kairu the Shadow set up here was ended and taken out of Task Scheduler"
                      + (", and its copy deleted, its data folder (with your PIN) included." if report["done"] else
                         ". Its copy, with your changes and its data folder, is still yours in the folder above.")]
        lines += ["", "To the owner's PC, through the Gate: progress counts, and one report with the lines above."
                      + ("" if sent else " (The report could not be sent.)"),
                  "Nothing else on this laptop was read or copied. The Shadow's key is deleted; it can send nothing more.", ""]
        path = self.base.parent / f"Kairu-shadow-receipt-{state['shadow']}.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def leave(self, remove_work: bool) -> None:
        """Self-removal: the key first, then the state; the workspace too when its pack is safely on the branch."""
        sealed.delete(self.base / KEY)
        for name in (STATE, STATE + ".tmp", BEAT, LOG):
            try:
                (self.base / name).unlink()
            except OSError:
                pass
        if remove_work:
            _remove_tree(self.base)


def _remove_tree(folder: Path) -> None:
    """Delete a folder with everything in it, also git's read-only files on Windows, so nothing is left behind."""
    def writable_then_again(function, path, error):
        try:
            os.chmod(path, 0o700)
            function(path)
        except OSError:
            pass

    shutil.rmtree(folder, onexc=writable_then_again)


def _github_slug(repo: str) -> str:
    for start in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
        if repo.startswith(start):
            return repo[len(start):].removesuffix("/").removesuffix(".git")
    return ""


def running(base: Path) -> bool:
    try:
        return time.time() - (base / BEAT).stat().st_mtime < 3 * POLL_SECONDS
    except OSError:
        return False


def start_background(base: Path, window: bool = True) -> bool:
    """Start `run --window` as a program of its own that outlives this terminal. (Tests pass window=False.)"""
    python = sys.executable
    if sys.platform == "win32" and Path(python).with_name("pythonw.exe").exists():
        python = str(Path(python).with_name("pythonw.exe"))
    argv = [python, "-m", "kairu.shadow", "run"] + (["--window"] if window else [])
    project = Path(__file__).resolve().parents[2]  # the folder that holds kairu/, so `-m kairu.shadow` is found from anywhere
    common = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(project),
                  env={**os.environ, "KAIRU_SHADOW_HOME": str(base.resolve()),
                       "PYTHONPATH": os.pathsep.join(filter(None, (str(project), os.environ.get("PYTHONPATH"))))})
    try:
        if sys.platform == "win32":
            subprocess.Popen(argv, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, **common)
        else:
            subprocess.Popen(argv, start_new_session=True, **common)
    except OSError:
        return False
    return True


def run(base: Path, window: bool = False, poll: float = POLL_SECONDS) -> int:
    if running(base):
        print("The Shadow's background part is already running.")
        return 0
    try:
        shadow = Shadow(base)
    except ShadowProblem as problem:
        print(problem)
        return 1

    def step() -> bool:
        """False once the Shadow is gone."""
        nonlocal shadow
        try:
            shadow = Shadow(base)  # `stop` or `home` in a terminal may have ended it
            return shadow.tick() is None
        except (ShadowProblem, OSError):
            return False

    if window and _window(shadow, step, poll):
        return 0
    while step():
        time.sleep(poll)
    return 0


def _window(shadow: Shadow, step, poll: float) -> bool:
    """A small window that is always there while the Shadow runs, with the friend's Stop. False if it cannot be shown."""
    try:
        import tkinter
        root = tkinter.Tk()
    except Exception:  # no tkinter or no screen: the loop runs without it
        return False
    state = shadow.state
    root.title("Kairu Shadow")
    root.resizable(False, False)
    tkinter.Label(root, text=f"Kairu Shadow is running on this laptop.\nMission: {state['mission'][:80]}\nFolder: {shadow.base / WORK}",
                  justify="left", padx=12, pady=8).pack()
    left = tkinter.Label(root, text="", padx=12)
    left.pack()

    def stop() -> None:
        try:
            Shadow(shadow.base).come_home("stopped")
        except ShadowProblem:
            pass
        root.destroy()

    tkinter.Button(root, text="STOP the Shadow", command=stop, bg="#b00020", fg="white", padx=12, pady=6).pack(pady=8)
    root.protocol("WM_DELETE_WINDOW", root.iconify)  # closing only hides it: it stays visible in the taskbar

    def again() -> None:
        if not step():
            root.destroy()
            return
        left.config(text=f"Time left: {max(0, shadow.seconds_left()) / 3600:.1f} hours")
        root.after(int(poll * 1000), again)

    root.after(100, again)
    root.mainloop()
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kairu.shadow", description="The Kairu Shadow on a friend's laptop.")
    commands = parser.add_subparsers(dest="command", required=True)
    join = commands.add_parser("join", help="join with the invite and the 6-digit code")
    join.add_argument("invite")
    join.add_argument("code")
    join.add_argument("--no-background", action="store_true", help="do not start the background part")
    for name, text in (("setup", "Cowork: install the Shadow's copy of Kairu here, with your own PIN"),
                       ("status", "the mission, the time left, what is missing"), ("check", "the done check"),
                       ("home", "come home (only when the done check passes)"), ("stop", "end the Shadow now")):
        commands.add_parser(name, help=text)
    background = commands.add_parser("run", help="the background part")
    background.add_argument("--window", action="store_true")
    args, base = parser.parse_args(argv), home_folder()
    try:
        if args.command == "join":
            shadow = Shadow.join(args.invite, args.code, base)
            state = shadow.state
            print(f"Joined. This Shadow builds: {state['mission']}")
            if shadow.cowork:
                print(f"Its copy of Kairu: {shadow.copy}  (read MISSION.md next to it; change Kairu there)")
                print("Next: `python -m kairu.shadow setup` installs that Kairu here, with YOUR OWN PIN.")
            else:
                print(f"Its workspace: {base / WORK}  (read MISSION.md there; build only inside {state['pack']})")
            print(f"Time limit: {state['hours']:g} hours. Your Stop: `python -m kairu.shadow stop`.")
            if not args.no_background:
                print("Its background part is running, with a small Kairu Shadow window." if start_background(base)
                      else "Its background part could not be started; run `python -m kairu.shadow run` in another terminal.")
            return 0
        if args.command == "run":
            return run(base, args.window)
        shadow = Shadow(base)
        if args.command == "setup":
            if not shadow.cowork:
                print("`setup` is for a Cowork Shadow. This one builds a skill pack: read MISSION.md in its workspace.")
                return 1
            problems = cowork.setup(shadow.copy)
            if problems:
                print("\nNot everything worked:\n  - " + "\n  - ".join(problems))
                return 1
            print("\nKairu is running on this laptop, under your own PIN. Ctrl+Alt+Space opens the bar. Change Kairu in "
                  f"{shadow.copy}; `python -m kairu.shadow check` when you are done.")
            return 0
        if args.command in ("status", "check"):
            problems, ran = shadow.check(with_tests=args.command == "check" or not shadow.cowork,
                                         say=print if args.command == "check" else None)
            state = shadow.state
            print(f"Shadow {state['shadow']} for {state['friend']}: {state['mission']}")
            if shadow.cowork:
                print(f"Kairu here: {'installed (setup done)' if cowork.set_up(shadow.copy) else 'not installed yet (`setup`)'}")
            print(f"Workspace: {shadow.copy if shadow.cowork else shadow.pack_folder}   time left: {max(0, shadow.seconds_left()) / 3600:.1f} hours   "
                  f"background part: {'running' if running(base) else 'not running'}")
            if problems:
                print("Still missing:\n  - " + "\n  - ".join(problems))
                return 1 if args.command == "check" else 0
            print(f"The done check passes ({ran} tests). `python -m kairu.shadow home` takes it home.")
            return 0
        report = shadow.come_home("done" if args.command == "home" else "stopped", say=print)
        if report["done"] and shadow.cowork:
            print(f"Home. Your {report['files']} changed files are on the branch {shadow.state['branch']} "
                  f"(commit {report['commit'][:10]}); the Kairu set up here is removed.")
            if "/pull/" in report["pr"]:
                print(f"Pull request: {report['pr']}")
            else:
                print("Open the pull request" + (f" here: {report['pr']}" if report["pr"] else ", or ask the owner to."))
        elif report["done"]:
            print(f"Home. The pack is on the branch {shadow.state['branch']} (commit {report['commit'][:10]}).")
            if "/pull/" in report["pr"]:
                print(f"Pull request: {report['pr']}")
            else:
                print("Open the pull request" + (f" here: {report['pr']}" if report["pr"] else ", or ask the owner to."))
        else:
            print("The Shadow ended and removed itself" + (" and the Kairu it set up" if shadow.cowork else "")
                  + f". Your files are still in {base / WORK}.")
        print(f"Your receipt: {report['receipt']}")
        return 0
    except ShadowProblem as problem:
        print(problem)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
