"""`kairu team ...` on Main Kairu's PC (TEAM.md). Every one that changes or sends anything asks Guardian.

  kairu team add NAME "kairu-pair:1:..." CODE [--share 1]   make a Clone: on its laptop run `kairu device pair` first, then
                                                             give its offer and 6-digit code here ("yes" and your PIN)
  kairu team list                                            your Clones
  kairu team remove NAME                                     forget a Clone
  kairu team split "BRIEF" [--name NAME] [--deadline "YYYY-MM-DD HH:MM" | --hours H]
                                                             Main Kairu splits a project into tasks for the Clones
  kairu team show [PROJECT]                                  the team board: every task, its Clone, progress, slipping
  kairu team start [PROJECT]                                 run it: the Clones get their orders, each decided by its own
                                                             Guardian; `kairu stop` ends it with everything else
  kairu team set NAME [--share 2] [--skills "research, writing"]   change a Clone's share or skills
  kairu team move PROJECT TASK NAME                          give a task that hasn't started to another Clone
  kairu team growth [NAME]                                   the growth record: what each Clone's tasks delivered, and
                                                             suggestions for you to decide (no score, no ranking)
  kairu team check PROJECT TASK                              confirm a done task met its "done when" check
  kairu team offer NAME "Lead the next research task"        offer a bigger task; its person accepts or declines

On a Clone's laptop:
  kairu team join NAME                                       pair this laptop with Main Kairu (`kairu device pair` with the
                                                             exact line to type on Main Kairu)
  kairu team inbox                                           Main Kairu's notes to this laptop
  kairu team say "WORDS"                                     tell Main Kairu's board something ("logo is ready")
  kairu team record                                          everything Main Kairu recorded about this laptop's work
  kairu team accept N / kairu team decline N                 answer the manager's offer #N
"""

import secrets
import sys
import time
from datetime import datetime


def add_parsers(commands) -> None:
    team = commands.add_parser("team", help="Clones: Main Kairu splits a project across Kairus on other laptops (TEAM.md)"
                               ).add_subparsers(dest="team_command", required=True)
    add = team.add_parser("add", help='make a Clone from the offer and code `kairu device pair` shows on its laptop ("yes" and your PIN)')
    add.add_argument("name", help="the Clone's name, such as Ravi-laptop")
    add.add_argument("offer", help="the kairu-pair:1:... text its laptop shows")
    add.add_argument("code", help="the 6-digit code its laptop shows")
    add.add_argument("--share", type=float, default=1.0, help="how much of a project it takes (1 even, 2 twice as much)")
    add.add_argument("--skills", default="", help='what its person is good at, such as "research, writing"')
    team.add_parser("list", help="your Clones")
    team.add_parser("remove", help="forget a Clone").add_argument("name")
    split = team.add_parser("split", help="Main Kairu splits a project into tasks for your Clones")
    split.add_argument("brief", help="the project, in a few sentences")
    split.add_argument("--name", default="", help="a short name for the project")
    split.add_argument("--deadline", default="", help='when it is due: "YYYY-MM-DD HH:MM" (your PC\'s time)')
    split.add_argument("--hours", type=float, default=0, help="or: due this many hours from now")
    team.add_parser("show", help="the team board").add_argument("project", type=int, nargs="?")
    team.add_parser("start", help="run a project: each Clone gets its orders").add_argument("project", type=int, nargs="?")
    change = team.add_parser("set", help="change a Clone's share or skills")
    change.add_argument("name")
    change.add_argument("--share", type=float, default=0, help="1 is an even share, 2 twice as much")
    change.add_argument("--skills", default=None, help='such as "research, writing" ("" clears them)')
    move = team.add_parser("move", help="give a task that hasn't started to another Clone")
    move.add_argument("project", type=int)
    move.add_argument("task", type=int)
    move.add_argument("name", help="the Clone it goes to")
    join = team.add_parser("join", help="on a Clone's laptop: pair it with Main Kairu")
    join.add_argument("name", help="this laptop's name on the team, such as Ravi-laptop")
    team.add_parser("inbox", help="on a Clone's laptop: Main Kairu's notes")
    team.add_parser("say", help="on a Clone's laptop: tell Main Kairu's board something").add_argument("words")
    team.add_parser("growth", help="the growth record and suggestions for you to decide").add_argument("name", nargs="?")
    check = team.add_parser("check", help='confirm a done task met its "done when" check')
    check.add_argument("project", type=int)
    check.add_argument("task", type=int)
    offer = team.add_parser("offer", help="offer a Clone's person a bigger task")
    offer.add_argument("name")
    offer.add_argument("words")
    team.add_parser("record", help="on a Clone's laptop: what Main Kairu recorded about this laptop's work")
    team.add_parser("accept", help="on a Clone's laptop: accept the manager's offer").add_argument("offer", type=int)
    team.add_parser("decline", help="on a Clone's laptop: decline the manager's offer").add_argument("offer", type=int)


def _deadline(args) -> float:
    if args.hours:
        return time.time() + args.hours * 3600
    if args.deadline:
        return datetime.strptime(args.deadline.strip(), "%Y-%m-%d %H:%M").timestamp()
    return 0.0


def team(args, cfg) -> int:
    from kairu.cli import _act
    from kairu.team.board import board, lines
    from kairu.team.store import TeamStore
    which = args.team_command
    if which == "add":
        details = {"name": args.name, "offer": args.offer, "code": args.code, "share": args.share}
        if args.skills:
            details["skills"] = args.skills
        problem = _act(cfg, "team.add", details, high=True, seconds=120)
        if problem and "failed" in problem:
            from kairu.team.conduct import last_reason
            problem = f"{problem}\n  Why: {last_reason(cfg.data_dir) or 'not written (see data/team.log)'}"
        print(problem or f"{args.name} is now a Clone. Split a project with `kairu team split \"...\"`.")
        return 1 if problem else 0
    if which == "list":
        clones = TeamStore(cfg.data_dir).clones()
        for clone in clones:
            seen = datetime.fromtimestamp(clone["seen"]).strftime("%d %b %H:%M") if clone["seen"] else "not yet"
            skills = f"  skills: {clone['skills']}" if clone.get("skills") else ""
            print(f"{clone['name']}  share {clone['share']:g}  heard from: {seen}{skills}")
        if not clones:
            print("No Clones yet. On the other laptop: `kairu team join NAME`; here: the `kairu team add` line it shows.")
        return 0
    if which == "remove":
        problem = _act(cfg, "team.remove", {"name": args.name})
        print(problem or f"{args.name} removed.")
        return 1 if problem else 0
    if which == "split":
        try:
            deadline = _deadline(args)
        except ValueError:
            print('A deadline looks like "2026-11-18 10:00".', file=sys.stderr)
            return 2
        from kairu.brain.store import BrainStore
        ask = secrets.token_hex(8)
        problem = _act(cfg, "team.split", {"brief": args.brief, "name": args.name, "deadline": deadline, "ask": ask,
                                           "source": "pc"}, seconds=150)
        answer = BrainStore(cfg.data_dir).take_answer(ask)
        print(answer.text if answer else problem or "No split came back; Guardian's log says why.")
        return 0 if answer and answer.status == "answered" else 1
    if which == "show":
        print("\n".join(lines(board(cfg.data_dir, args.project))))
        return 0
    if which == "start":
        from kairu import channel
        from kairu.client import GuardianClient
        from kairu.guardian import Action, Refused
        number = args.project or TeamStore(cfg.data_dir).latest()
        if not number:
            print("No project yet: `kairu team split \"...\"` first.")
            return 1
        try:
            GuardianClient(cfg).run(Action("team.run", {"project": number}))
        except (Refused, channel.ChannelError) as why:
            print(f"Not started: {why}")
            return 1
        print(f"Project {number} started. Watch it with `kairu team show` or on the workspace's Clones page.")
        return 0
    if which == "set":
        details = {"name": args.name}
        if args.share:
            details["share"] = args.share
        if args.skills is not None:
            details["skills"] = args.skills
        if len(details) == 1:
            print("Say what to change: --share or --skills.")
            return 2
        problem = _act(cfg, "team.set", details)
        print(problem or f"{args.name} changed.")
        return 1 if problem else 0
    if which == "move":
        problem = _act(cfg, "team.move", {"project": args.project, "task": args.task, "clone": args.name})
        print(problem or f"Task {args.task} of project {args.project} is now {args.name}'s.")
        return 1 if problem else 0
    if which == "join":
        return join(cfg, args.name)
    if which == "inbox":
        from kairu.team.inbox import read
        notes = read(cfg.data_dir)
        for note in notes:
            print(f"{datetime.fromtimestamp(note['time']).strftime('%d %b %H:%M')}  Main Kairu: {note['words']}")
        if not notes:
            print("No notes from Main Kairu yet. They come with its orders when a project runs.")
        return 0
    if which == "say":
        return say(cfg, args.words)
    if which == "growth":
        from kairu.team.growth import lines as growth_lines
        print("\n".join(growth_lines(TeamStore(cfg.data_dir), args.name)))
        return 0
    if which == "check":
        problem = _act(cfg, "team.check", {"project": args.project, "task": args.task})
        print(problem or f"Task {args.task} of project {args.project} checked; its person sees it with their next order.")
        return 1 if problem else 0
    if which == "offer":
        problem = _act(cfg, "team.offer", {"clone": args.name, "words": args.words})
        print(problem or f"Offer made. It reaches {args.name} with their next order; only they can accept it.")
        return 1 if problem else 0
    if which == "record":
        from kairu.team.inbox import read
        notes = [n for n in read(cfg.data_dir) if "Record:" in n["words"] or "Offer #" in n["words"]]
        for note in notes:
            print(f"{datetime.fromtimestamp(note['time']).strftime('%d %b %H:%M')}  {note['words']}")
        if not notes:
            print("Nothing recorded yet. Each entry Main Kairu keeps about your work comes here with its next order.")
        return 0
    if which in ("accept", "decline"):
        return _send(cfg, f"[Kanswer] {args.offer} {'yes' if which == 'accept' else 'no'}",
                     f"Your answer to offer #{args.offer} is on its way to Main Kairu.")
    return 2


MAIN_NAME = "Main Kairu"


def join(cfg, name: str) -> int:
    """On a Clone's laptop: `kairu device pair`, with the exact line for the manager to type on Main Kairu."""
    from kairu.cli import _device_pair
    from kairu.team.store import TeamError, clean_name
    try:
        name = clean_name(name)
    except TeamError as why:
        print(why)
        return 2
    if not cfg.link_enabled:
        print("First set link.enabled: true in this laptop's config.yaml and restart Guardian: a Clone gets its orders "
              "through Kairu Link.")
        return 1
    print(f"This laptop becomes a Clone called {name}. Main Kairu will be a paired device here, like a phone: every "
          "order it sends is a request this laptop's own Guardian decides, and High steps still need \"yes\" and YOUR PIN "
          "typed here.")
    return _device_pair(cfg, team_name=name)


def say(cfg, words: str) -> int:
    """On a Clone's laptop: words for Main Kairu's team board, sent with Guardian's own link.send to the paired Main Kairu.
    On Main Kairu they are shown on the board only, never an order and never passed to another Clone."""
    from kairu.team.conduct import SAY
    words = " ".join(str(words).split())[:400]
    if not words:
        print("Say something: kairu team say \"the logo is ready\".")
        return 2
    return _send(cfg, f"{SAY} {words}", "Sent to Main Kairu's board.")


def _send(cfg, text: str, done: str) -> int:
    """Guardian's link.send to this laptop's paired Main Kairu (a report: data there, never an order)."""
    from kairu import channel
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Refused
    from kairu.link import store as link_store
    main = [device for device in link_store.paired(cfg.data_dir) if device.name == MAIN_NAME]
    if not main:
        print("This laptop isn't a Clone yet: `kairu team join NAME` first.")
        return 1
    try:
        GuardianClient(cfg).run(Action("link.send", {"device": main[-1].id, "type": "report", "text": text}))
    except (Refused, channel.ChannelError) as why:
        print(f"Not sent: {why}")
        return 1
    print(done)
    return 0
