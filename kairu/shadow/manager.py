"""The Shadow Manager: the actions Guardian runs on the owner's PC for Shadows and their skill packs (SHADOW.md).

    shadow.create   High   make a Shadow for a friend: an invite and a 6-digit code, valid 15 minutes; it ends when the
                           friend's laptop joined (exit code 0) or the invite ended (exit code 1)
    shadow.sync     Low    read what the Shadows said through the Gate: progress, or the report of one that came home
    shadow.recall   Low    tell one to come back now; with give_up, stop waiting for it and revoke its key here
    shadow.lesson   Low    keep or drop one lesson a Shadow brought home
    shadow.install  High   install the use case a Shadow brought home: only the exact files it tested (its signed
                           digest), only after they pass the pack check and their own tests again here
    pack.run        High   run an installed pack's run(text), in a program of its own, if its files are still exactly
                           the ones installed
    pack.remove     Low    remove an installed pack

A Shadow is never a paired device and holds no authority: nothing it says is a request, and these actions read its
words as data. Nothing here changes policy.yaml or adds an action: a pack is run only through pack.run. The relay
and the data folder come from Guardian's own config.yaml, never from a request.

Each ends with exit code 1, and the reason on Guardian's log, when it could not do its work.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from kairu.shadow import kinds, lessons, pack as packs, wire
from kairu.shadow.store import OFFER_NAME, ShadowStore, TooManyShadows, packs_folder


def _fail(why: str):
    print(f"kairu shadow: {why}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def _log(text: str) -> None:
    print(f"kairu shadow: {text}", file=sys.stderr, flush=True)


def _number(value: float, what: str = "a Shadow's number") -> int:
    if value != int(value) or value < 1:
        _fail(f"{what} is a whole number, not {value}")
    return int(value)


def _git(*arguments, cwd=None, seconds: float = 120) -> subprocess.CompletedProcess:
    """git, with a list of arguments (no shell), never waiting for a typed password."""
    return subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True, timeout=seconds, errors="replace",
                          stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, **packs.HIDDEN)


def repo_address(given: str = "") -> str:
    """Where a Shadow pushes its use case: the address given, or this project's own `origin`. Never with a password in it."""
    address = given.strip()
    if not address:
        from kairu.config import ROOT
        try:
            found = _git("-C", str(ROOT), "remote", "get-url", "origin", seconds=20)
        except (OSError, subprocess.TimeoutExpired):
            found = None
        address = found.stdout.strip() if found and found.returncode == 0 else ""
    if not address:
        _fail("this project folder has no git `origin`; give the repository with --repo")
    parts = urlsplit(address)
    if parts.scheme in ("http", "https") and "@" in parts.netloc:  # a token saved in the address stays on this PC
        address = urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))
    if not address.isprintable() or len(address) > 200 or address.startswith("-"):
        _fail("that is not a repository address")
    return address


# --- shadow.create ---------------------------------------------------------------------------------------------------

def base_branch(given: str = "") -> str:
    """Where a Cowork Shadow's copy of Kairu starts: the branch given, or the branch this project folder is on."""
    base = given.strip()
    if not base:
        from kairu.config import ROOT
        try:
            found = _git("-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD", seconds=20)
        except (OSError, subprocess.TimeoutExpired):
            found = None
        base = found.stdout.strip() if found and found.returncode == 0 else ""
    if not kinds.BASE_BRANCH.fullmatch(base) or ".." in base or base == "HEAD":
        _fail("give the branch a Cowork Shadow starts from with --base (like main)")
    return base


def create(data_dir: str, relay: str, friend: str, mission: str, pack: str, hours: float = kinds.DEFAULT_HOURS,
           repo: str = "", mode: str = "pack", base: str = "") -> None:
    from kairu.link import keys
    from kairu.link.relay import Relay
    from kairu.protect import sealed
    friend, mission = wire.clean(friend, kinds.MAX_FRIEND), wire.clean(mission, kinds.MAX_MISSION)
    if not friend or not mission:
        _fail("a Shadow needs the friend's name and the mission: what to build")
    if not packs.good_name(pack):
        _fail(f"the pack's name is small letters, digits and dashes, at most {kinds.MAX_PACK_NAME} long (like expense-tracker)")
    if mode not in kinds.MODES:
        _fail(f"a Shadow's mode is one of: {', '.join(kinds.MODES)}")
    if not 0 < hours <= kinds.MOST_HOURS:
        _fail(f"a Shadow's time limit is more than 0 and at most {kinds.MOST_HOURS} hours")
    address = repo_address(repo)
    base = base_branch(base) if mode == "cowork" else ""
    store, sid = ShadowStore(data_dir), f"sh-{secrets.token_hex(4)}"
    card = {"shadow": sid, "friend": friend, "mission": mission, "pack": pack, "branch": wire.branch_of(sid, pack),
            "repo": address, "hours": hours, "mode": mode, "base": base}
    try:
        number = store.create(sid, friend, mission, pack, card["branch"], address, hours, mode, base)
    except TooManyShadows as error:
        _fail(str(error))
    me = keys.load_or_create(data_dir)
    code, topic = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(16)
    expires = time.time() + kinds.INVITE_SECONDS
    offer = Path(data_dir) / OFFER_NAME
    sealed.write(offer, {"text": wire.invite_text(me, topic, relay, expires, card), "code": code, "expires": expires,
                         "number": number}, kinds.SEAL_PURPOSE)
    try:
        device = _wait_for_join(Relay(relay), me, topic, code, expires)
        if device is not None:
            store.joined(number, device)
    finally:
        sealed.delete(offer)
    if device is None:
        store.set_state(number, "expired", ("invited",))
        raise SystemExit(1)
    _log(f"Shadow {number} ({sid}) joined from {friend}'s laptop")


def _wait_for_join(relay, me, topic: str, code: str, expires: float):
    """The Shadow that joined with the right code, with a topic of its own; None when the invite ended first."""
    from kairu.link.message import seal
    from kairu.link.pairing import NotAPairing, open_request
    from kairu.link.relay import Backoff, RateLimited, RelayError
    from kairu.link.send import deliver
    wrong, backoff, since = 0, Backoff(), int(time.time()) - 5
    while time.time() < expires:
        try:
            subscription = relay.subscribe([topic], since)
        except RelayError as error:
            wait = backoff.next(getattr(error, "retry_after", None), rate_limited=isinstance(error, RateLimited))
            _log(f"{error}; trying again in {wait:.0f} s")
            time.sleep(min(wait, max(0.0, expires - time.time())))
            continue
        timer = threading.Timer(max(0.0, expires - time.time()), subscription.close)
        timer.daemon = True
        timer.start()
        try:
            for event in subscription:
                if event.get("event") != "message" or not isinstance(event.get("message"), str):
                    continue
                since = max(since, int(event.get("time") or 0))
                try:
                    device = open_request(event["message"], me, code)
                except NotAPairing as refusal:
                    if refusal.wrong_code:
                        wrong += 1
                        _log(f"a wrong code ({wrong} of {kinds.INVITE_TRIES})")
                        if wrong >= kinds.INVITE_TRIES:
                            _log("the invite is cancelled: too many wrong codes")
                            return None
                    continue
                deliver(relay, topic, seal(me, device.id, device.box, "report",
                                           wire.body("joined", topic=device.topic, pc=me.id)))
                return device
        except RelayError as error:
            _log(f"{error}; reading again")
            time.sleep(min(backoff.next(), max(0.0, expires - time.time())))
        finally:
            timer.cancel()
            subscription.close()
    _log("the invite ended before a laptop joined")
    return None


# --- shadow.sync and shadow.recall -----------------------------------------------------------------------------------

def sync(data_dir: str, relay: str) -> None:
    from kairu.link import keys
    from kairu.link.message import Rejected, open_envelope, sender_of
    from kairu.link.relay import Relay, RelayError
    store, me, gate = ShadowStore(data_dir), keys.load(data_dir), Relay(relay)
    if me is None:
        return
    failed = None
    for shadow in store.all():
        device = store.device(shadow)
        if shadow["state"] not in kinds.ACTIVE or device is None:
            continue
        try:
            events = gate.poll([device.topic], shadow["since"] or int(shadow["joined"]) - 5)
        except RelayError as error:
            failed = error
            continue
        for event in events:
            text = event.get("message")
            if not isinstance(text, str):
                continue
            store.heard(shadow["number"], since=str(event.get("id") or ""))
            if sender_of(text) == me.id:
                continue
            try:
                message = open_envelope(text, me, lambda sender: device if sender == device.id else None, store.remember,
                                        relay_time=event.get("time"))
            except Rejected as refused:
                _log(f"Shadow {shadow['number']}: a message was refused ({refused.problem})")
                continue
            said = wire.from_shadow(message.body) if message.type == "report" else None
            if said is None:
                _log(f"Shadow {shadow['number']}: a message that is not progress or a return was dropped")
            elif said["kind"] == "progress":
                store.heard(shadow["number"], progress=said)
            else:
                _came_home(store, shadow, said)
                break
    if failed is not None:
        _fail(f"the Gate could not be read ({failed})")


def _came_home(store: ShadowStore, shadow: dict, report: dict) -> None:
    """A Shadow's return report: kept, its lessons checked again, and its temporary key revoked here."""
    report["lessons"] = lessons.keep_general(report["lessons"], private=(shadow["friend"], shadow["pack"]))
    brought = report["tree"] if shadow["mode"] == "cowork" else report["digest"]  # its changes to Kairu, or its pack
    finished = report["done"] and report["pack"] == shadow["pack"] and bool(brought)
    report["done"] = finished
    store.heard(shadow["number"], report=report)
    store.add_lessons(shadow["number"], report["lessons"])
    store.set_state(shadow["number"], "returned" if finished else "unfinished")
    store.forget_keys(shadow["number"])
    _log(f"Shadow {shadow['number']} came home " + ("with its use case" if finished else "without a finished use case"))


def recall(data_dir: str, relay: str, shadow: float, give_up: bool = False) -> None:
    from kairu.link import keys
    from kairu.link.message import seal
    from kairu.link.relay import Relay
    from kairu.link.send import deliver
    store, number = ShadowStore(data_dir), _number(shadow)
    found = store.get(number)
    if found is None or found["state"] not in ("invited", *kinds.ACTIVE):
        _fail(f"Shadow {number} is not out")
    device, me = store.device(found), keys.load(data_dir)
    if device is not None and me is not None:
        try:
            deliver(Relay(relay), device.topic, seal(me, device.id, device.box, "report", wire.body("recall")),
                    give_up=5 if give_up else 60)
        except (Exception, SystemExit) as error:  # the Gate could not be reached: giving up must still work
            if not give_up:
                _fail(f"the Shadow could not be told ({error})")
    if give_up:
        store.set_state(number, "unfinished")
        store.forget_keys(number)
    else:
        store.set_state(number, "recalled", ("working", "recalled"))


def lesson(data_dir: str, lesson: float, keep: bool = True) -> None:
    number = _number(lesson, "a lesson's number")
    if not ShadowStore(data_dir).decide_lesson(number, keep):
        _fail(f"no lesson {number} is waiting")


# --- shadow.install, pack.run, pack.remove ---------------------------------------------------------------------------

def install(data_dir: str, shadow: float, folder: str = "") -> None:
    store, number = ShadowStore(data_dir), _number(shadow)
    found = store.get(number)
    if found is None or found["state"] not in ("returned", "installed") or not found["report"]:
        _fail(f"Shadow {number} has not come home with a finished use case")
    if found["mode"] == "cowork":  # its changes to Kairu are a pull request: the owner tests and merges it, never Kairu
        _fail(f"Shadow {number} worked on Kairu itself: test its branch {found['branch']} and merge its pull request "
              "yourself (SHADOW.md, Cowork)")
    name, wanted = found["pack"], found["report"]["digest"]
    with tempfile.TemporaryDirectory(prefix="kairu-pack-") as scratch:
        source = Path(folder) if folder else _fetch(found["repo"], found["branch"], name, Path(scratch))
        if not source.is_dir():
            _fail(f"there is no folder {source}")
        problems = packs.check(source, name)
        if problems:
            _fail("not installed, the pack check failed: " + "; ".join(problems[:5]))
        if packs.digest(source) != wanted:
            _fail("not installed: these are not the files the Shadow tested and signed for (the branch changed after "
                  "it came home, or this is another folder)")
        staged = Path(scratch) / "staged" / name
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns(*packs.SKIPPED))
        passed, ran, tail = packs.run_tests(staged)
        if not passed:
            _fail(f"not installed: its tests do not pass on this PC ({ran} ran)\n{tail}")
        if packs.digest(staged) != wanted:
            _fail("not installed: the tests changed the pack's own files")
        about, home = packs.manifest(staged), packs_folder(data_dir)
        home.mkdir(parents=True, exist_ok=True)
        target = home / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(staged, target)
        store.install(about, wanted, packs.uses(target), number)
    store.set_state(number, "installed")
    _log(f"installed pack {name} from Shadow {number} ({ran} tests passed here)")


def upgrade(data_dir: str, shadow: float) -> None:
    """shadow.upgrade (High): your Kairu upgraded with the changes a Cowork Shadow brought home, after Kairu's own check
    passes on the upgraded Kairu in a separate folder (kairu/shadow/homecoming.py, ADR-041). Only the Shadow's number comes
    in: the project folder is this Kairu's own, never one a request names."""
    from kairu.config import ROOT
    _upgrade(data_dir, _number(shadow), ROOT, sys.executable)


def _upgrade(data_dir: str, number: int, root: Path, python: str, check_seconds: float = 3600) -> None:
    from kairu.shadow import homecoming
    store = ShadowStore(data_dir)
    found = store.get(number)
    if found is None or found["mode"] != "cowork" or found["state"] != "returned" or not (found["report"] or {}).get("done"):
        _fail(f"Shadow {number} has not come home with finished changes to Kairu (`kairu shadow status {number}`)")
    try:
        old, new, passed = homecoming.upgrade(Path(root), {**found, "number": number}, Path(data_dir) / f"shadow-upgrade-{number}",
                                              python, check_seconds, say=_log)
    except homecoming.HomecomingProblem as problem:
        _fail(str(problem))
    except (OSError, subprocess.TimeoutExpired) as error:
        _fail(f"git could not be run ({type(error).__name__}); your Kairu was not changed")
    store.set_state(number, "installed")
    _log(f"upgraded Kairu with Shadow {number}: {old[:12]} -> {new[:12]}; Kairu's check passed here ({passed} tests)")


def _fetch(repo: str, branch: str, name: str, scratch: Path) -> Path:
    """packs/NAME as it is on the Shadow's branch, in a scratch folder. The project folder's own files are not touched."""
    from kairu.config import ROOT
    try:
        fetched = _git("-C", str(ROOT), "fetch", "--quiet", "--no-tags", repo, f"refs/heads/{branch}")
        if fetched.returncode != 0:
            _fail(f"the branch {branch} could not be fetched: {fetched.stderr.strip()[-300:] or 'git failed'}")
        archive = scratch / "pack.tar"
        packed = _git("-C", str(ROOT), "archive", "--format=tar", f"--output={archive}", "FETCH_HEAD", f"packs/{name}")
        if packed.returncode != 0:
            _fail(f"the branch {branch} has no packs/{name}")
    except (OSError, subprocess.TimeoutExpired) as error:
        _fail(f"git could not be run ({type(error).__name__})")
    with tarfile.open(archive) as tar:
        tar.extractall(scratch / "tree", filter="data")
    return scratch / "tree" / "packs" / name


def run_pack(data_dir: str, name: str, text: str = "", job: str = "") -> None:
    store = ShadowStore(data_dir)
    record, folder = store.pack(name), packs_folder(data_dir) / name
    if record is None or not packs.good_name(name):
        _fail(f"no pack named {name!r} is installed")
    try:
        same = folder.is_dir() and packs.digest(folder) == record["digest"]
    except packs.PackProblem:
        same = False
    if not same:
        store.ran(job, name, False, "its files are not the ones you installed, so it was not run")
        _fail(f"pack {name}: its files are not the ones installed; install it again")
    ok, output = packs.run(folder, text)
    store.ran(job, name, ok, output)
    if not ok:
        _fail(f"pack {name}: {output}")


def remove_pack(data_dir: str, name: str) -> None:
    store = ShadowStore(data_dir)
    if not packs.good_name(name) or not store.remove_pack(name):
        _fail(f"no pack named {name!r} is installed")
    shutil.rmtree(packs_folder(data_dir) / name, ignore_errors=True)


def read_offer(data_dir) -> dict | None:
    """The invite waiting for `kairu shadow create` to show, or None."""
    from kairu.protect import sealed
    try:
        offer = sealed.read(Path(data_dir) / OFFER_NAME, kinds.SEAL_PURPOSE)
    except sealed.SealBroken:
        return None
    return offer if offer and offer.get("expires", 0) > time.time() else None


def describe(shadow: dict) -> str:
    """One line about a Shadow, for the owner."""
    line = f"#{shadow['number']}  {shadow['state']:<10}  {shadow['friend']}: " + \
        (f"Cowork on Kairu ({shadow['pack']})" if shadow.get("mode") == "cowork" else shadow["pack"])
    progress, report = shadow.get("progress"), shadow.get("report")
    if shadow["state"] in kinds.ACTIVE and progress:
        line += f"  ({progress['files']} files, tests {progress['tests'] or 'not run'}" + \
                (", ready to come home" if progress["ready"] else "") + ")"
    if report:
        line += f"  ({report['why']})" if report["why"] else ""
    return line


def to_json(shadow: dict) -> str:
    return json.dumps({key: shadow[key] for key in ("number", "id", "friend", "pack", "state", "branch")})
