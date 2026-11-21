"""`kairu shadow ...` and `kairu pack ...` on the owner's PC (SHADOW.md). Every one that does anything asks Guardian.

  kairu shadow create --for NAME --mission "WHAT TO BUILD" [--pack NAME] [--hours 3] [--repo URL]
                                   make a Shadow for a friend ("yes" and your PIN): an invite and a 6-digit code, 15 minutes
  kairu shadow create --cowork --for NAME --mission "WHAT TO CHANGE IN KAIRU" [--base BRANCH] [--hours 24]
                                   a Cowork Shadow: a full Kairu on the friend's laptop under their own PIN; its changes
                                   to Kairu come home as a pull request (ADR-039)
  kairu shadow list                your Shadows, after reading what they said through the Gate
  kairu shadow status N            one Shadow in full: its mission, progress, report and what to do next
  kairu shadow recall N [--give-up]  "come back now"; --give-up also stops waiting for it and revokes its key here
  kairu shadow explain N           what your friend built, in plain words (a Cowork Shadow that came home)
  kairu shadow install N [--folder PATH]  install the use case it brought home, after you tested it ("yes" and your PIN);
                                   a Cowork Shadow: the explanation, "yes" and your PIN, then your Kairu upgrades
  kairu shadow lessons             what your Shadows learned, waiting for your yes
  kairu shadow keep K | drop K     keep or drop one lesson
  kairu pack list                  the installed packs
  kairu pack run NAME [WORDS]      run one ("yes" and your PIN)
  kairu pack remove NAME           remove one
"""

import re
import secrets
import subprocess
import sys
import time
from datetime import datetime

from kairu.shadow import kinds, manager
from kairu.shadow.pack import good_name
from kairu.shadow.store import ShadowStore


def add_parsers(commands) -> None:
    shadow = commands.add_parser("shadow", help="Shadows: a temporary helper on a friend's laptop that comes home with a "
                                                "use case (SHADOW.md)").add_subparsers(dest="shadow_command", required=True)
    create = shadow.add_parser("create", help='make a Shadow for a friend: an invite and a 6-digit code ("yes" and your PIN)')
    create.add_argument("--for", dest="friend", required=True, help="your friend's name")
    create.add_argument("--mission", required=True, help="what to build, in one sentence")
    create.add_argument("--pack", help="the use case's short name, like expense-tracker (default: from the mission)")
    create.add_argument("--hours", type=float, default=None,
                        help=f"its time limit (default {kinds.DEFAULT_HOURS}, Cowork {kinds.COWORK_HOURS}; at most {kinds.MOST_HOURS})")
    create.add_argument("--cowork", action="store_true",
                        help="a full Kairu on the friend's laptop, under their own PIN; brings home its changes to Kairu")
    create.add_argument("--base", default="", help="Cowork: the branch its copy of Kairu starts from (default: this folder's)")
    create.add_argument("--repo", default="", help="the repository it pushes to (default: this project's origin)")
    shadow.add_parser("list", help="your Shadows")
    shadow.add_parser("status", help="one Shadow in full").add_argument("number", type=int)
    recall = shadow.add_parser("recall", help="tell a Shadow to come back now")
    recall.add_argument("number", type=int)
    recall.add_argument("--give-up", action="store_true", help="also stop waiting for it and revoke its key here")
    install = shadow.add_parser("install", help='install the use case a Shadow brought home ("yes" and your PIN)')
    install.add_argument("number", type=int)
    install.add_argument("--folder", default="", help="take the pack from this folder instead of fetching its branch")
    shadow.add_parser("explain", help="what your friend built, in plain words (a Cowork Shadow that came home)").add_argument(
        "number", type=int)
    shadow.add_parser("lessons", help="what your Shadows learned, waiting for your yes")
    shadow.add_parser("keep", help="keep a lesson").add_argument("lesson", type=int)
    shadow.add_parser("drop", help="drop a lesson").add_argument("lesson", type=int)
    pack = commands.add_parser("pack", help="the use cases (skill packs) installed from Shadows").add_subparsers(
        dest="pack_command", required=True)
    pack.add_parser("list", help="the installed packs")
    run = pack.add_parser("run", help='run an installed pack ("yes" and your PIN)')
    run.add_argument("name")
    run.add_argument("words", nargs="*")
    pack.add_parser("remove", help="remove an installed pack").add_argument("name")


def slug(mission: str) -> str:
    words = re.findall(r"[a-z0-9]+", mission.lower())
    name = "-".join(words[:3])[:kinds.MAX_PACK_NAME].strip("-")
    return name if good_name(name) else "use-case"


def _clock(moment) -> str:
    return datetime.fromtimestamp(moment).strftime("%d %b %H:%M") if moment else "never"


def _sync(cfg) -> None:
    from kairu.cli import _act
    if any(item["state"] in kinds.ACTIVE for item in ShadowStore(cfg.data_dir).all()):
        problem = _act(cfg, "shadow.sync", seconds=90)
        if problem:
            print(f"(The Gate was not read just now: {problem}. This is what Kairu last heard.)")


def shadow(args, cfg) -> int:
    from kairu.cli import _act
    command, store = args.shadow_command, ShadowStore(cfg.data_dir)
    if command == "create":
        return _create(args, cfg)
    if command == "list":
        _sync(cfg)
        found = store.all()
        if not found:
            print('You have no Shadows. `kairu shadow create --for NAME --mission "what to build"` makes one.')
            return 0
        for item in found:
            print(manager.describe(item))
        waiting = store.lessons("waiting")
        if waiting:
            print(f"{len(waiting)} lesson(s) wait for your yes: `kairu shadow lessons`.")
        return 0
    if command == "status":
        _sync(cfg)
        return _status(store, args.number)
    if command == "recall":
        problem = _act(cfg, "shadow.recall", {"shadow": float(args.number), "give_up": args.give_up}, seconds=90)
        if problem:
            print(f"Not recalled: {problem}")
            return 1
        print(f"Shadow {args.number}: " + ("its key is revoked here; nothing more from it is read." if args.give_up else
              "told to come back now. It answers when the friend's laptop is next on; `kairu shadow status "
              f"{args.number}` shows when it is home."))
        return 0
    if command == "install":
        return _install(args, cfg, store)
    if command == "explain":
        _sync(cfg)
        return _explain(store, args.number)[0]
    if command == "lessons":
        waiting = store.lessons("waiting")
        if not waiting:
            print("No lesson is waiting." + (f" Kept so far: {len(store.lessons('kept'))}." if store.lessons("kept") else ""))
            return 0
        print("Your Shadows learned this (general know-how only). Kairu keeps a lesson only after your yes:")
        for item in waiting:
            print(f"  {item['number']}. {item['text']}   (Shadow {item['shadow']})")
        print("`kairu shadow keep K` keeps one, `kairu shadow drop K` drops it. A lesson never changes a Guardian rule.")
        return 0
    keep = command == "keep"
    problem = _act(cfg, "shadow.lesson", {"lesson": float(args.lesson), "keep": keep})
    print(f"Lesson {args.lesson}: {problem}" if problem else f"Lesson {args.lesson} {'kept' if keep else 'dropped'}.")
    return 1 if problem else 0


def _create(args, cfg) -> int:
    from kairu import approval, channel
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Refused, Verdict
    name = args.pack or slug(args.mission)
    hours = args.hours if args.hours is not None else (kinds.COWORK_HOURS if args.cowork else kinds.DEFAULT_HOURS)
    details = {"friend": args.friend, "mission": args.mission, "pack": name, "hours": float(hours),
               "mode": "cowork" if args.cowork else "pack"}
    if args.base:
        details["base"] = args.base
    if args.repo:
        details["repo"] = args.repo
    guardian, action = GuardianClient(cfg), Action("shadow.create", details)
    if args.cowork:
        print("A Cowork Shadow puts a full copy of Kairu (Guardian, the bar, the skills) on your friend's laptop, under "
              "THEIR OWN PIN, in a folder of its own. None of your data goes: no Gmail, phone, memory or AI keys. Their "
              "changes to Kairu come home as a pull request you test and merge. It can never ask your Kairu to do anything.")
    else:
        print("A Shadow is a temporary helper on your friend's laptop. It gets one empty folder there and a key of its own, "
              "and carries nothing of yours. It can only report to this PC; it can never ask Kairu to do anything.")
    decision = guardian.check(action)
    if decision.verdict is Verdict.DENY:
        print(f"Guardian refused shadow.create: {decision.reason}")
        return 1
    granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
    if decision.verdict is Verdict.NEEDS_APPROVAL and granted is None:
        return 1
    store, run = ShadowStore(cfg.data_dir), None
    before = {item["number"] for item in store.all()}
    try:
        run = guardian.run(action, granted)
        shown, deadline = False, time.monotonic() + kinds.INVITE_SECONDS + 30
        while (outcome := guardian.run_status(run["run"])["outcome"]) is None and time.monotonic() < deadline:
            offer = None if shown else manager.read_offer(cfg.data_dir)
            if offer:
                _show_offer(offer, args.friend)
                shown = True
            time.sleep(0.3)
    except KeyboardInterrupt:
        try:
            if run:
                guardian.end(run["run"])
        except Refused:
            pass
        print("The invite is cancelled.")
        return 1
    except (Refused, channel.ChannelError) as error:
        print(f"No Shadow was made: {error}")
        return 1
    new = [item for item in store.all() if item["number"] not in before]
    if outcome == "finished" and new and new[0]["state"] == "working":
        made = new[0]
        print(f"\nShadow {made['number']} is on {made['friend']}'s laptop, "
              + (f"working on Kairu (branch {made['branch']}). " if made["mode"] == "cowork" else f"building \"{made['pack']}\". ")
              + f"Time limit: {made['hours']:g} hours.")
        print(f"`kairu shadow status {made['number']}` shows its progress; `kairu shadow recall {made['number']}` calls it back.")
        return 0
    print(f"No Shadow joined ({outcome or 'no answer'}): the 15 minutes passed, the code was wrong 5 times, or the Gate "
          f"could not be reached. Guardian's log ({cfg.data_dir / 'guardian.log'}) says which.")
    return 1


def _show_offer(offer: dict, friend: str) -> None:
    print(f"\nSend {friend} these two things (the invite by chat or email; the code by another way, such as a call):\n")
    print(f"  Invite:  {offer['text']}\n")
    print(f"  Code:    {offer['code'][:3]} {offer['code'][3:]}   (not in the invite; valid until "
          f"{datetime.fromtimestamp(offer['expires']).strftime('%H:%M')}; 5 wrong codes cancel it)\n")
    print(f"On {friend}'s laptop, in the Kairu project folder (SHADOW.md, \"On your friend's laptop\"):\n")
    print('  py -3.12 -m kairu.shadow join "INVITE" CODE\n')
    print("Waiting for the laptop to join ... (Ctrl+C cancels)", flush=True)


def _status(store: ShadowStore, number: int) -> int:
    found = store.get(number)
    if found is None:
        print(f"There is no Shadow {number}. `kairu shadow list` shows them.")
        return 1
    print(manager.describe(found))
    print(f"  mission:  {found['mission']}")
    print(f"  made:     {_clock(found['created'])}   joined: {_clock(found['joined'])}   last heard: {_clock(found['last_seen'])}")
    print(f"  branch:   {found['branch']} of {found['repo']}")
    progress, report = found["progress"], found["report"]
    if found["state"] in kinds.ACTIVE:
        left = (found["joined"] or 0) + found["hours"] * 3600 - time.time()
        print(f"  time:     {max(0, left) / 3600:.1f} of {found['hours']:g} hours left")
        if progress:
            print(f"  progress: {progress['files']} files, tests {progress['tests'] or 'not run'}; {progress['note']}")
        print(f"  `kairu shadow recall {number}` calls it back now.")
    if report:
        print(f"  came home: {_clock(found['ended'])}, because {report['why']}")
        if report["done"] and found["mode"] == "cowork":
            print(f"  changes:  {report['files']} files changed in Kairu; Kairu's check passed on them there ({report['tests']} tests)")
            for name in report.get("changed", [])[:20]:
                print(f"            {name}")
            if report["pr"]:
                print(f"  {'pull request' if '/pull/' in report['pr'] else 'open the pull request'}: {report['pr']}")
        elif report["done"]:
            print(f"  use case: {report['files']} files, {report['tests']} tests passed on the friend's laptop; "
                  f"its code uses: {', '.join(report['uses']) or 'nothing beyond plain Python'}")
            print(f"  digest:   {report['digest']}")
            if report["pr"]:
                print(f"  {'pull request' if '/pull/' in report['pr'] else 'open the pull request'}: {report['pr']}")
            if report["lessons"]:
                print(f"  lessons:  {len(report['lessons'])} (`kairu shadow lessons`)")
    if found["state"] == "returned" and found["mode"] == "cowork":
        print(f"  Next: `kairu shadow explain {number}` says what {found['friend']} built; `kairu shadow install {number}` "
              "upgrades your Kairu with it (\"yes\" and your PIN).")
    elif found["state"] == "installed" and found["mode"] == "cowork":
        print("  Installed: your Kairu runs these changes. Merging the pull request on GitHub is yours.")
    elif found["state"] == "returned":
        print(f"  Next: read the pull request, then `kairu shadow install {number}` (\"yes\" and your PIN). "
              "A Shadow never installs anything by itself.")
    elif found["state"] == "installed":
        print(f"  Installed. `kairu pack run {found['pack']} WORDS` runs it.")
    return 0


def _install(args, cfg, store: ShadowStore) -> int:
    from kairu.cli import _act
    _sync(cfg)
    found = store.get(args.number)
    if found is None or found["state"] not in ("returned", "installed") or not found["report"]:
        print(f"Shadow {args.number} has not come home with a finished use case. `kairu shadow status {args.number}`.")
        return 1
    if found["mode"] == "cowork":
        return _upgrade(cfg, store, found, args.number)
    report = found["report"]
    print(f"Shadow {args.number} brought home the use case \"{found['pack']}\", built by {found['friend']}: {found['mission']}")
    print(f"  {report['files']} files, {report['tests']} tests passed there; its code uses: "
          f"{', '.join(report['uses']) or 'nothing beyond plain Python'}")
    print("  Installing takes exactly the files the Shadow signed for (digest " + report["digest"][:16] + "...), runs their "
          "tests again here, and keeps them in Kairu's data folder. It is your friend's code: read the pull request first.")
    details = {"shadow": float(args.number)}
    if args.folder:
        details["folder"] = args.folder
    problem = _act(cfg, "shadow.install", details, high=True, seconds=600)
    if problem:
        print(f"Not installed: {problem}")
        return 1
    print(f"Installed \"{found['pack']}\". `kairu pack run {found['pack']} WORDS` runs it (\"yes\" and your PIN each time, in v0).")
    return 0


def _explain(store: ShadowStore, number: int) -> tuple[int, object]:
    """Print what the friend built. (exit code, the Explanation or None)."""
    from kairu.config import ROOT
    from kairu.shadow import homecoming
    found = store.get(number)
    if found is None or found["mode"] != "cowork" or found["state"] not in ("returned", "installed") or \
            not (found["report"] or {}).get("done"):
        print(f"Shadow {number} has not come home with finished changes to Kairu. `kairu shadow status {number}`.")
        return 1, None
    try:
        commit = homecoming.fetch(ROOT, {**found, "number": number})
        explained = homecoming.explain(ROOT, {**found, "number": number}, commit)
    except homecoming.HomecomingProblem as problem:
        print(f"Shadow {number}: {problem}")
        return 1, None
    print(explained.text())
    return (1 if explained.blocked else 0), explained


def _upgrade(cfg, store: ShadowStore, found: dict, number: int) -> int:
    """A Cowork Shadow's homecoming: the explanation, "yes" and your PIN, the upgrade, then Guardian and the bar restart."""
    from kairu import channel, client
    from kairu.cli import _act
    from kairu.config import ROOT
    from kairu.shadow import homecoming
    if found["state"] == "installed":
        print(f"Shadow {number}'s changes are already in your Kairu.")
        return 0
    code, explained = _explain(store, number)
    if explained is None or explained.blocked:
        return 1
    old = homecoming.git(ROOT, "rev-parse", "HEAD").stdout.strip()
    print("\nInstalling upgrades your Kairu with exactly these changes. First Kairu's own check runs on the upgraded Kairu in a "
          "separate folder (about 20 minutes; don't type meanwhile: some tests press Ctrl+Alt+K). Only if it passes does "
          "your Kairu move forward; if anything fails, it stays as it is.")
    problem = _act(cfg, "shadow.upgrade", {"shadow": float(number)}, high=True, seconds=homecoming_seconds())
    if problem:
        print(f"Not installed, your Kairu is as it was: {problem}")
        return 1
    print(f"Your Kairu is upgraded with {found['friend']}'s work. Restarting Guardian and the bar so they run it ...")
    try:
        client.quit_guardian(cfg)
        time.sleep(1)
    except channel.ChannelError:
        pass
    restart = [sys.executable, "-m", "kairu"]
    subprocess.run([*restart, "guardian", "run"], cwd=ROOT, timeout=120, check=False)
    subprocess.run([*restart, "bar", "quit"], cwd=ROOT, timeout=60, check=False, capture_output=True)
    time.sleep(2.5)
    subprocess.run([*restart, "bar", "--hidden"], cwd=ROOT, timeout=60, check=False, capture_output=True)
    print(f"Done. To go back to your Kairu as it was: `git reset --hard {old[:12]}` in {ROOT}, then "
          "`kairu guardian quit` and `kairu guardian run`.")
    print("Merging its pull request on GitHub is still yours: GitHub's main branch doesn't change by itself.")
    return 0


def homecoming_seconds() -> float:
    return 3700  # Kairu's whole check (about 20 minutes on a laptop, at most an hour) and the git steps


def cowork_steps(found: dict) -> str:
    return "\n".join([
        f"    git fetch origin {found['branch']}",
        f"    git checkout {found['branch']}",
        "    py -3.12 tools\\check_guardian.py",
        "    kairu guardian quit; kairu guardian run      (Guardian then runs the changed Kairu)",
        f"  If you like it, merge its pull request on GitHub. `git checkout {found['base'] or 'main'}` goes back."])


def pack(args, cfg) -> int:
    from kairu.cli import _act
    command, store = args.pack_command, ShadowStore(cfg.data_dir)
    if command == "list":
        found = store.packs()
        if not found:
            print("No pack is installed. A Shadow brings one home: `kairu shadow create`.")
            return 0
        for item in found:
            print(f"  {item['name']:<24} {item['title']}  (v{item['version']}, by {item['made_by']}, Shadow {item['shadow']}, "
                  f"installed {_clock(item['installed'])}; uses: {item['uses'] or 'plain Python'})")
        return 0
    if store.pack(args.name) is None:
        print(f"No pack named {args.name!r} is installed. `kairu pack list` shows them.")
        return 1
    if command == "remove":
        problem = _act(cfg, "pack.remove", {"name": args.name})
        print(f"Not removed: {problem}" if problem else f"Removed the pack {args.name}.")
        return 1 if problem else 0
    job = secrets.token_hex(8)
    problem = _act(cfg, "pack.run", {"name": args.name, "text": " ".join(args.words), "job": job}, high=True, seconds=120)
    result = store.run_result(job)
    if result is not None:
        print(result["output"] if result["ok"] else f"The pack did not answer: {result['output']}")
        return 0 if result["ok"] else 1
    print(f"Not run: {problem or 'no answer'}")
    return 1
