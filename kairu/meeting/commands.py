"""`kairu meeting ...` (HACKATHON.md stage 1, ADR-055 proposed). Every one that sends or changes anything asks Guardian.

  kairu meeting add FILE [--title T] [--date YYYY-MM-DD]   read a meeting: a recording (mp3, wav, m4a, ogg, mp4, webm ...) or
                                                          a transcript (txt, md, vtt, srt). A file outside your work folder
                                                          is copied into its meetings folder first (never overwriting).
                                                          Gemini hears and reads it: "yes" and your PIN
  kairu meeting record [--title T] [--minutes 60]         record a meeting from the mic, in memory only ("yes" and your PIN);
                                                          `kairu meeting end` (or saying "end the meeting") hands it to Gemini
  kairu meeting end                                       end the recording
  kairu meeting list                                      the meetings Kairu read, newest first
  kairu meeting show [N]                                  what came out of meeting N (the newest if left out)
  kairu meeting transcript N                              its transcript, as kept on this PC (secrets left out)
  kairu meeting forget N                                  delete it from this PC
  kairu meeting ledger                                    every decision and action across meetings, with its status
  kairu meeting conflicts                                 what clashes across meetings (Gemini's and Kairu's own checks)
  kairu meeting ask "the launch date"                     what the meetings decided about it, with the meeting and day
  kairu meeting resolve 2.1 new|old                       decide a conflict (Medium)
  kairu meeting split [N] [--hours H]                     Main Kairu splits the open actions for your Clones (team.split)
"""

import os
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path

READ_SECONDS = 420
WORK_SUBFOLDER = "meetings"


def add_parsers(commands) -> None:
    meeting = commands.add_parser("meeting", help="Meeting in: a meeting becomes decisions, owners, deadlines (HACKATHON.md)"
                                  ).add_subparsers(dest="meeting_command", required=True)
    add = meeting.add_parser("add", help='read a meeting recording or transcript with Gemini ("yes" and your PIN)')
    add.add_argument("file", help="the recording or transcript")
    add.add_argument("--title", default="", help="a name for the meeting (else Gemini names it)")
    add.add_argument("--date", default="", help="the day it was held, YYYY-MM-DD (else today)")
    record = meeting.add_parser("record", help='record a meeting from the mic, in memory only ("yes" and your PIN)')
    record.add_argument("--title", default="")
    record.add_argument("--minutes", type=float, default=60, help="end by itself after this long (at most 120)")
    meeting.add_parser("end", help="end the recording: Gemini writes it down")
    meeting.add_parser("list", help="the meetings Kairu read")
    meeting.add_parser("show", help="what came out of a meeting").add_argument("number", type=int, nargs="?")
    meeting.add_parser("transcript", help="a meeting's transcript").add_argument("number", type=int)
    meeting.add_parser("forget", help="delete a meeting from this PC").add_argument("number", type=int)
    meeting.add_parser("ledger", help="every decision and action across your meetings, with its status")
    meeting.add_parser("conflicts", help="what clashes across your meetings, to decide")
    meeting.add_parser("ask", help='what your meetings decided about something').add_argument("topic", nargs="+")
    resolve = meeting.add_parser("resolve", help="decide a conflict: keep the new decision or the old one")
    resolve.add_argument("conflict", help="MEETING.CONFLICT, as `kairu meeting conflicts` shows it, e.g. 2.1")
    resolve.add_argument("keep", choices=("new", "old"))
    split = meeting.add_parser("split", help="Main Kairu splits the open actions into tasks for your Clones")
    split.add_argument("number", type=int, nargs="?", help="only this meeting's actions (else every meeting's)")
    split.add_argument("--hours", type=float, default=0, help="due this many hours from now")


def into_work_folder(work_folder, file: str) -> str:
    """The name to give meeting.read: the file's name inside the work folder. One outside it is copied into
    work_folder/meetings first, under a free name (nothing is overwritten). An owner command: you named the file."""
    from kairu.meeting import read
    from kairu.tasks import fence
    source = Path(file).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"there's no file {file}")
    read.kind_of(source.name)
    folder = fence.work_folder(work_folder)
    real = Path(os.path.realpath(source))
    try:
        return real.relative_to(folder).as_posix()
    except ValueError:
        pass
    target_folder = folder / WORK_SUBFOLDER
    target_folder.mkdir(exist_ok=True)
    target, number = target_folder / source.name, 2
    while target.exists():
        target = target_folder / f"{source.stem} ({number}){source.suffix}"
        number += 1
    shutil.copyfile(real, target)
    return target.relative_to(folder).as_posix()


def _reply(cfg, job: str) -> str:
    from kairu.tasks.store import TaskStore
    reply = TaskStore(cfg.data_dir).take_reply(job)
    return reply.text if reply else ""


def meeting(args, cfg) -> int:
    from kairu.cli import _act
    from kairu.meeting import conduct, read
    from kairu.meeting.store import MeetingStore, exists
    which = args.meeting_command
    if which == "add":
        try:
            if args.date:
                datetime.strptime(args.date, "%Y-%m-%d")
            name = into_work_folder(cfg.work_folder, args.file)
            place, data = conduct.file_of(str(cfg.work_folder), name)
        except ValueError:
            print("A day looks like 2026-11-21.", file=sys.stderr)
            return 2
        except (FileNotFoundError, read.NotAMeeting, conduct.Stop) as problem:
            print(f"Not read: {problem}", file=sys.stderr)
            return 1
        kind = "recording" if read.kind_of(place.name) == "audio" else "transcript"
        print(f"Reading the {kind} {name} ({len(data) / 1024 / 1024:.1f} MB) with Gemini...")
        job = secrets.token_hex(8)
        problem = _act(cfg, "meeting.read", {"job": job, "file": name, "sha": conduct.sha_of(data), "title": args.title,
                                             "held": args.date}, high=True, seconds=READ_SECONDS)
        said = _reply(cfg, job)
        print(said or problem or "Nothing came back; Guardian's log says why.")
        return 0 if not problem else 1
    if which == "record":
        from kairu import approval, channel
        from kairu.client import GuardianClient
        from kairu.guardian import Action, Refused, Verdict
        guardian = GuardianClient(cfg)
        action = Action("meeting.record", {"job": secrets.token_hex(8), "title": args.title, "minutes": args.minutes,
                                           "held": ""})
        try:
            decision = guardian.check(action)
            if decision.verdict is Verdict.DENY:
                print(f"Guardian refused meeting.record: {decision.reason}")
                return 1
            granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
            if decision.verdict is Verdict.NEEDS_APPROVAL and granted is None:
                print("Not approved, so the mic stayed off.")
                return 1
            guardian.run(action, granted)
        except (Refused, channel.ChannelError) as why:
            print(f"Not recording: {why}")
            return 1
        print("Recording the meeting (in memory only). End it with `kairu meeting end` or say \"end the meeting\"; "
              "then see it with `kairu meeting show`.")
        return 0
    if which == "end":
        job = secrets.token_hex(8)
        problem = _act(cfg, "meeting.stop", {"job": job})
        print(_reply(cfg, job) or problem)
        return 1 if problem else 0
    if which == "list":
        found = MeetingStore(cfg.data_dir).meetings() if exists(cfg.data_dir) else []
        for item in found:
            print(f"{item['number']}. {item['held']}  {item['title']}  ({item['decisions']} decisions, {item['actions']} actions, "
                  f"{item['questions']} open)")
        if not found:
            print("No meetings yet: `kairu meeting add FILE` or `kairu meeting record`.")
        return 0
    if which == "show":
        job = secrets.token_hex(8)
        problem = _act(cfg, "meeting.show", {"job": job, "meeting": float(args.number or 0)})
        print(_reply(cfg, job) or problem)
        return 1 if problem else 0
    if which == "transcript":
        found = MeetingStore(cfg.data_dir).meeting(args.number, transcript=True) if exists(cfg.data_dir) else None
        if not found:
            print(f"There's no meeting {args.number}.")
            return 1
        print("\n".join(found["transcript"]))
        return 0
    if which == "forget":
        job = secrets.token_hex(8)
        problem = _act(cfg, "meeting.forget", {"job": job, "meeting": float(args.number)})
        print(_reply(cfg, job) or problem)
        return 1 if problem else 0
    from kairu.meeting import ledger
    if which == "ledger":
        print(ledger.told_ledger(MeetingStore(cfg.data_dir).ledger() if exists(cfg.data_dir) else []))
        return 0
    if which in ("conflicts", "ask"):
        job = secrets.token_hex(8)
        if which == "conflicts":
            problem = _act(cfg, "meeting.check", {"job": job})
        else:
            problem = _act(cfg, "meeting.ask", {"job": job, "topic": " ".join(args.topic)})
        print(_reply(cfg, job) or problem)
        return 1 if problem else 0
    if which == "resolve":
        meeting_number, _, conflict = args.conflict.partition(".")
        if not (meeting_number.isdigit() and conflict.isdigit()):
            print("A conflict looks like 2.1 (meeting 2, conflict 1), as `kairu meeting conflicts` shows it.", file=sys.stderr)
            return 2
        job = secrets.token_hex(8)
        problem = _act(cfg, "meeting.resolve", {"job": job, "meeting": float(meeting_number), "conflict": float(conflict),
                                                "keep": args.keep})
        print(_reply(cfg, job) or problem)
        return 1 if problem else 0
    if which == "split":
        found = ledger.check(cfg.data_dir)
        if found["between"]:
            print(ledger.told_check(found))
            print("Decide the conflicts between meetings first, then split.")
            return 1
        try:
            name, brief = ledger.brief(cfg.data_dir, args.number)
        except ValueError as problem:
            print(problem)
            return 1
        import time
        from kairu.brain.store import BrainStore
        print(f"Brief for Main Kairu: {brief}")
        ask = secrets.token_hex(8)
        deadline = time.time() + args.hours * 3600 if args.hours else 0
        problem = _act(cfg, "team.split", {"brief": brief, "name": name, "deadline": deadline, "ask": ask, "source": "pc"},
                       seconds=150)
        answer = BrainStore(cfg.data_dir).take_answer(ask)
        print(answer.text if answer else problem or "No split came back; Guardian's log says why.")
        if answer and answer.status == "answered":
            print("Start it with `kairu team start`, and watch it on the Clones page (kairu workspace).")
        return 0 if answer and answer.status == "answered" else 1
    return 2
