"""The team actions (TEAM.md), each a Guardian action run in its own program, like every other.

    team.add     (High)    pair Main Kairu with a Clone: the offer and 6-digit code `kairu device pair` showed on the Clone
    team.remove  (Medium)  forget a Clone: its row and Main Kairu's keys for it
    team.split   (Low)     the brain splits a project brief into tasks for the Clones (a public brief only, as brain.plan)
    team.run     (Medium)  run a project: send each Clone its next order, read what each Clone says, hand work on when the
                           tasks it waited for are done; ends when every task is done or nothing more can go on
    team.set     (Medium)  change a Clone's share or skills (words for the next split)
    team.move    (Medium)  give a task that hasn't started to another Clone
    team.status  (Low)     "how's the project going?": the board in two short sentences and one question, by rules
    team.check   (Medium)  the manager confirms a done task met its "done when" check (growth record)
    team.offer   (Medium)  the manager offers a Clone's person a bigger task; they accept or decline on their laptop

The growth record (kairu/team/growth.py, TEAM.md "Growth"): each done task, the manager's check and each offer become an
entry in that Clone's queue (clones.pending) and ride on its next order, in any project, so the employee sees everything
recorded about them. A Clone's answer to an offer ("[Kanswer] N yes") changes only that offer, made to that Clone.

Main Kairu's own notes to a Clone (a welcome, a hand-off, a heads-up that its task is slipping) ride on that Clone's next
order, after a "NOTE " line (kairu/tasks/remote.py keeps them in the Clone's team inbox with team.note). They are built only
from Main Kairu's own data: the project's name, the task titles of the split you saw, the Clones' names and times; never a
Clone's words. What a Clone says with `kairu team say` goes on the manager's board only.

None of them approves anything on a Clone: an order is a request there, decided by that Clone's own Guardian. A Clone's
words are data, kept in data/team.db for the team board, never handed to Guardian, a brain or another Clone.
"""

import sys
from pathlib import Path
import re
import time

from kairu.team import peer as peers
from kairu.team.split import NoSplit, instructions, load, parse
from kairu.team.store import BLOCKED, DONE, SENT, WAITING, TeamError, TeamStore, clean_name

MAIN = "Main Kairu"
SAY = "[Ksay]"  # what a Clone's person said with `kairu team say`: data for the board, never moves a task
ANSWER = re.compile(r"\[Kanswer\] (\d{1,6}) (yes|no)")  # a Clone's person's answer to an offer made to that Clone
NOTE_ROOM = 600

POLL_SECONDS = 3.0
MOST_HOURS = 12  # a run ends by itself after this; start it again to go on
QUIET_SECONDS = 600  # a Clone not heard from this long shows as "not heard from" on the board


LOG = "team.log"  # in the data folder: why a team action said no (Guardian's own output is not kept on Windows)


def _say(text: str, data_dir: str | None = None) -> None:
    print(f"team: {text}", file=sys.stderr, flush=True)
    if data_dir:
        try:
            with open(Path(data_dir) / LOG, "a", encoding="utf-8") as out:
                out.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
        except OSError:
            pass


def last_reason(data_dir) -> str:
    """The newest line of data/team.log, for the command that just saw a team action fail."""
    try:
        lines = (Path(data_dir) / LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return lines[-1].split(" ", 2)[-1] if lines else ""


# --- team.add / team.remove ---------------------------------------------------------------------------

def add(data_dir: str, relay: str, name: str, offer: str, code: str, share: float = 1.0, skills: str = "") -> None:
    store = TeamStore(data_dir)
    try:
        name = clean_name(name)
        if store.clone(name):
            raise TeamError(f"there is already a Clone called {name}")
        from kairu.team.store import check_share, clean_skills
        check_share(float(share or 1))
        clean_skills(skills)
        peer = peers.Peer(data_dir, name)
        peer.pair(offer.strip(), code.strip())
        store.add_clone(name, peer.device, float(share or 1), skills)
    except (TeamError, RuntimeError, ValueError, OSError) as why:
        _say(f"{name!r} was not added: {why}", data_dir)
        raise SystemExit(1)
    except Exception as why:  # anything else: still say why, then fail as before
        _say(f"{name!r} was not added: {type(why).__name__}: {why}", data_dir)
        raise
    _say(f"{name} is now a Clone of Main Kairu", data_dir)


def remove(data_dir: str, name: str) -> None:
    store = TeamStore(data_dir)
    clone = store.clone(name)
    if not clone or not store.remove_clone(clone["name"]):
        _say(f"there is no Clone called {name!r}")
        raise SystemExit(1)
    peers.key_file(data_dir, clone["name"]).unlink(missing_ok=True)
    _say(f"{clone['name']} was removed; unpair Main Kairu on that laptop too (`kairu device remove` there)")


def set_clone(data_dir: str, name: str, share: float = 0, skills: str | None = None) -> None:
    """team.set: a Clone's share (0 leaves it) or skills (None leaves them; "" clears them)."""
    try:
        TeamStore(data_dir).set_clone(name, share if share else None, skills)
    except TeamError as why:
        _say(str(why))
        raise SystemExit(1)
    _say(f"{name} changed")


def move(data_dir: str, project: float, task: float, clone: str) -> None:
    """team.move: a task that hasn't started yet goes to another of your Clones. A task already sent stays where it is."""
    store = TeamStore(data_dir)
    number, which = int(project), int(task)
    try:
        info = store.project(number)
        if info is None:
            raise TeamError(f"there is no project {number}")
        if info["state"] == "done":
            raise TeamError(f"project {number} is already done")
        found = next((t for t in store.tasks(number) if t["number"] == which), None)
        if found is None:
            raise TeamError(f"project {number} has no task {which}")
        target = store.clone(clone)
        if target is None:
            raise TeamError(f"there is no Clone called {clone}")
        if found["state"] not in (WAITING, BLOCKED) or (found["state"] == WAITING and found["step"]):
            raise TeamError(f"task {which} has already started on {found['clone']}; it stays there")
        store.set_task(number, which, clone=target["name"], last=f"Moved from {found['clone']} to {target['name']}.")
        store.add_feed(number, MAIN, "", f"Task {which} '{found['title']}' moved from {found['clone']} to {target['name']}.")
    except TeamError as why:
        _say(str(why))
        raise SystemExit(1)
    _say(f"task {which} of project {number} is now {target['name']}'s")


def busy_minutes(store: TeamStore, but: int | None = None) -> dict:
    """Minutes of work each Clone still has in projects that aren't done (for the split's workload)."""
    busy: dict = {}
    for project in store.projects():
        if project["number"] == but or project["state"] in ("done", "stopped"):
            continue
        for task in store.tasks(project["number"]):
            if task["state"] != DONE:
                left = task["minutes"] * (1 - task["step"] / max(len(task["orders"]), 1))
                busy[task["clone"]] = busy.get(task["clone"], 0) + left
    return busy


def load_lines(tasks: list[dict], clones: list[dict]) -> list[str]:
    out = []
    for row in load(tasks, clones):
        if not row["tasks"]:
            out.append(f"  {row['clone']}: no task this time")
            continue
        heavy = "  (more than its share: `kairu team move` can give a task to someone else)" if row["over"] else ""
        out.append(f"  {row['clone']}: {row['tasks']} task{'s' if row['tasks'] != 1 else ''}, "
                   f"{row['minutes']:g} min{heavy}")
    return out


def check(data_dir: str, project: float, task: float) -> None:
    """team.check: the manager confirms a done task met its "done when" check. The entry goes to that Clone's laptop too."""
    store = TeamStore(data_dir)
    number, which = int(project), int(task)
    found = next((t for t in store.tasks(number) if t["number"] == which), None) if store.project(number) else None
    if found is None or found["state"] != DONE:
        _say(f"project {number} has no done task {which} to check")
        raise SystemExit(1)
    store.set_task(number, which, checked=time.time())
    store.add_pending(found["clone"], f"Record: your manager checked task {which} '{found['title']}' in project {number}: "
                                      "it meets its done check.")
    _say(f"task {which} checked")


def offer(data_dir: str, clone: str, words: str) -> None:
    """team.offer: the manager's offer of a bigger task. It reaches the Clone with its next order; only its person answers."""
    try:
        number = TeamStore(data_dir).add_offer(clone, words)
    except TeamError as why:
        _say(str(why))
        raise SystemExit(1)
    _say(f"offer #{number} made: it reaches {clone} with its next order")


# --- team.split ------------------------------------------------------------------------------------

def split(data_dir: str, brief: str, name: str, deadline: float, ask: str, source: str, brain: dict | None = None) -> None:
    """Ask the brain for a split (the same privacy filter as brain.plan), read it strictly, keep it as a planned project."""
    from kairu.brain.ask import _check, _keep
    from kairu.brain.gateway import ANSWERED, NOT_SENT, Gateway, Result
    _check(ask, source)
    store = TeamStore(data_dir)
    clones = store.clones()
    started = time.time()
    if not clones:
        return _keep(data_dir, ask, source, Result(NOT_SENT, "L3", "No Clones yet: add one with `kairu team add` first."))
    minutes = (deadline - time.time()) / 60 if deadline and deadline > time.time() else None
    result = Gateway(data_dir, brain).plan(brief, source, instructions(clones, minutes, busy_minutes(store)), longest=4000)
    if result.status != ANSWERED:
        return _keep(data_dir, ask, source, result)
    try:
        tasks = parse(result.text, clones)
    except NoSplit as why:
        return _keep(data_dir, ask, source, Result(NOT_SENT, "L3", f"The split didn't come out right ({why}). Try again, "
                                                                     "or say the project more simply.", result.provider))
    number = store.add_project(name or brief[:40], brief, deadline or None, tasks)
    lines = [f"Project {number} planned: {len(tasks)} tasks for {len({task['clone'] for task in tasks})} Clones."]
    for index, task in enumerate(tasks, 1):
        waits = f", after {', '.join(map(str, task['after']))}" if task["after"] else ""
        lines.append(f"{index}. {task['title']} → {task['clone']} ({task['minutes']:g} min{waits}). Done when: {task['done']}")
    lines.append("Work per Clone:")
    lines += load_lines(tasks, clones)
    lines.append(f"Check it with `kairu team show {number}`; start it with `kairu team start {number}` (or say \"start the project\").")
    _keep(data_dir, ask, source, Result(ANSWERED, "L3", "\n".join(lines), result.provider, seconds=time.time() - started))


# --- team.run ----------------------------------------------------------------------------------------

def ready(tasks: list[dict]) -> list[dict]:
    done = {task["number"] for task in tasks if task["state"] == DONE}
    return [task for task in tasks if task["state"] == WAITING and set(task["after"]) <= done]


def stalled(tasks: list[dict]) -> bool:
    return not any(task["state"] == SENT for task in tasks) and not ready(tasks)


class Runner:
    def __init__(self, data_dir: str, project: int, clock=time.time, sleep=time.sleep, make_peer=None):
        self.data_dir, self.project, self.clock, self.sleep = data_dir, int(project), clock, sleep
        self.store = TeamStore(data_dir)
        self.make_peer = make_peer or (lambda name: peers.Peer(data_dir, name))
        self.peers = {}

    def peer(self, name: str):
        if name not in self.peers:
            self.peers[name] = self.make_peer(name)
        return self.peers[name]

    def begin(self) -> None:
        project = self.store.project(self.project)
        if project is None:
            raise TeamError(f"there is no project {self.project}")
        if project["state"] == "done":
            raise TeamError(f"project {self.project} is already done")
        clones = {clone["name"] for clone in self.store.clones()}
        for task in self.store.tasks(self.project):
            if task["clone"] not in clones:
                raise TeamError(f"task {task['number']} is for {task['clone']}, who is not a Clone any more")
            if task["state"] == BLOCKED:  # starting again tries a stuck task once more, from the order that stopped
                self.store.set_task(self.project, task["number"], state=WAITING, last="Trying again.")
        self.store.set_project(self.project, state="running", started=project["started"] or self.clock(), ended=None)

    def hand_out(self) -> None:
        """Each Clone with nothing running gets the next order of its first task that is ready, with Main Kairu's note."""
        tasks = self.store.tasks(self.project)
        busy = {task["clone"] for task in tasks if task["state"] == SENT}
        for task in ready(tasks):
            if task["clone"] in busy:
                continue
            order = task["orders"][task["step"]]
            note = self.note_for(task, tasks)
            more = self.extras(task["clone"], NOTE_ROOM - len(note) - 1)
            note = f"{note} {more}".strip()
            self.peer(task["clone"]).send_order(self.project, task["number"], task["step"] + 1, order, note)
            if note:
                self.store.add_feed(self.project, MAIN, task["clone"], note, self.clock())
            self.store.set_task(self.project, task["number"], state=SENT, sent=self.clock(), note="",
                                started=task["started"] or self.clock(), last=f"Sent: {order}")
            busy.add(task["clone"])

    def note_for(self, task: dict, tasks: list[dict]) -> str:
        """Main Kairu's note for this order, from its own data only: a welcome on a Clone's first order of the project, a
        hand-off when the tasks this one waited for are done, and a heads-up kept from the slip watch."""
        parts = []
        project = self.store.project(self.project)
        mine = [t for t in tasks if t["clone"] == task["clone"]]
        if task["step"] == 0 and not any(t["started"] for t in mine):
            due = f", due {_clock(project['deadline'])}" if project["deadline"] else ""
            listed = "; ".join(f"{t['number']}. {t['title']}" for t in mine)
            parts.append(f"Welcome to project {self.project} '{project['name']}'{due}. Your tasks: {listed}.")
        if task["step"] == 0 and task["after"]:
            by = {t["number"]: t for t in tasks}
            done = ", ".join(f"task {n} '{by[n]['title']}' ({by[n]['clone']})" for n in task["after"] if n in by)
            parts.append(f"Hand-off: {done} {'is' if len(task['after']) == 1 else 'are'} done, so your task "
                         f"{task['number']} '{task['title']}' starts now.")
        if task["note"]:
            parts.append(task["note"])
        return " ".join(parts)

    def record_done(self, number: int) -> None:
        """The growth record's entry for a task just done, queued for its Clone's next order."""
        from kairu.team.growth import entry
        tasks = self.store.tasks(self.project)
        task = next(t for t in tasks if t["number"] == number)
        waited = sum(number in t["after"] for t in tasks)
        self.store.add_pending(task["clone"], entry({**task, "project": self.project}, self.store.project(self.project), waited))

    def answer(self, clone: str, number: int, yes: bool) -> None:
        offer = next((o for o in self.store.offers(clone) if o["number"] == number), None)
        if offer is None or offer["state"] not in ("waiting", "sent"):
            return  # not an open offer made to this Clone: words only
        self.store.set_offer(number, "accepted" if yes else "declined", self.clock())
        self.store.add_feed(self.project, offer["clone"], "", f"{'Accepted' if yes else 'Said no thanks to'} offer #{number}: "
                                                              f"{offer['words']}.", self.clock())

    def extras(self, clone: str, room: int) -> str:
        """Open offers and growth record entries for this Clone, as much as fits; the rest waits for its next order."""
        parts, used = [], 0
        for offer in self.store.offers(clone):
            if offer["state"] != "waiting":
                continue
            said = (f"Offer #{offer['number']} from your manager: {offer['words']}. Yours to decide: kairu team accept "
                    f"{offer['number']} or kairu team decline {offer['number']}.")
            if used + len(said) + 1 > room:
                break
            parts.append(said)
            used += len(said) + 1
            self.store.set_offer(offer["number"], "sent")
        pending = self.store.pending(clone)
        kept = 0
        for item in pending:
            if used + len(item) + 1 > room:
                break
            parts.append(item)
            used += len(item) + 1
            kept += 1
        if kept:
            self.store.set_pending(clone, pending[kept:])
        return " ".join(parts)

    def watch(self) -> None:
        """The slip watch: the first time a task slips, the manager's feed says so and its Clone gets a heads-up with its
        next order. Read from the board, so the manager and the Clone see the same thing."""
        from kairu.team.board import board
        view = board(self.data_dir, self.project, now=self.clock())["project"]
        if not view:
            return
        tasks = {t["number"]: t for t in self.store.tasks(self.project)}
        for shown in view["tasks"]:
            task = tasks.get(shown["number"])
            if not shown["slipping"] or task is None or task["warned"]:
                continue
            due = f" The deadline is {_clock(view['deadline'])}." if view["deadline"] else ""
            self.store.set_task(self.project, task["number"], warned=1,
                                note=f"Heads-up: task {task['number']} '{task['title']}' is behind its plan.{due}")
            self.store.add_feed(self.project, MAIN, "", f"Task {task['number']} '{task['title']}' ({task['clone']}) is "
                                                        f"slipping: planned to end {_clock(shown['planned_end'])}.", self.clock())

    def listen(self) -> None:
        for clone in self.store.clones():
            try:
                news, newest = self.peer(clone["name"]).news(clone["since"])
            except OSError as error:
                _say(f"{clone['name']}: the Gate can't be reached ({type(error).__name__}); trying again")
                continue
            if news:
                self.store.heard(clone["name"], newest, self.clock())
            elif newest > clone["since"]:
                self.store.heard(clone["name"], newest, clone["seen"] or 0)
            for message in news:
                if message.get("type") == "report":
                    self.take(clone["name"], message.get("body", ""))

    def take(self, clone: str, body: str) -> None:
        if (body or "").startswith(SAY):  # the Clone's person, to the team: shown on the board, nothing more
            self.store.add_feed(self.project, clone, "", body[len(SAY):].strip(), self.clock())
            return
        answer = ANSWER.fullmatch((body or "").strip())
        if answer:
            self.answer(clone, int(answer.group(1)), answer.group(2) == "yes")
            return
        tasks = {task["number"]: task for task in self.store.tasks(self.project)}
        ref, finished, words = peers.read_report(body)
        if ref is None or ref[0] != self.project:
            running = [task for task in tasks.values() if task["clone"] == clone and task["state"] == SENT]
            if running and words and ref is None:  # "Your mission reached the PC", or a step waiting for a PIN there
                self.store.set_task(self.project, running[0]["number"], last=words)
            return
        task = tasks.get(ref[1])
        if task is None or task["clone"] != clone or task["state"] != SENT or ref[2] != task["step"] + 1:
            return  # an old step, or not this Clone's: never trusted to move a task
        if not finished:
            self.store.set_task(self.project, task["number"], last=words)
            return
        self.store.log_result(self.project, task["number"], words)
        if peers.failed(words):
            self.store.set_task(self.project, task["number"], state=BLOCKED, blocked_once=1, last=words or "It stopped.")
            return
        step = task["step"] + 1
        if step >= len(task["orders"]):
            self.store.set_task(self.project, task["number"], state=DONE, step=step, finished=self.clock(), last=words or "Done.")
            self.record_done(task["number"])
        else:
            self.store.set_task(self.project, task["number"], state=WAITING, step=step, last=words or "Done.")

    def run(self) -> str:
        self.begin()
        until = self.clock() + MOST_HOURS * 3600
        while self.clock() < until:
            self.hand_out()
            self.listen()
            self.watch()
            tasks = self.store.tasks(self.project)
            if all(task["state"] == DONE for task in tasks):
                self.store.set_project(self.project, state="done", ended=self.clock())
                return "done"
            if stalled(tasks):
                self.store.set_project(self.project, state="stuck")
                return "stuck"
            self.sleep(POLL_SECONDS)
        self.store.set_project(self.project, state="paused")
        return "paused"


def run(data_dir: str, relay: str, project: float) -> None:
    try:
        ended = Runner(data_dir, int(project)).run()
    except TeamError as why:
        _say(str(why))
        raise SystemExit(1)
    _say(f"project {int(project)}: {ended}")


def _clock(moment) -> str:
    return time.strftime("%H:%M", time.localtime(moment)) if moment else "?"


# --- team.status: "how's the project going?" --------------------------------------------------------------

def summary(view: dict) -> str:
    """The board in Tenmin's way, by rules: the answer first and short, then exactly one question."""
    project = view.get("project")
    if not view.get("clones"):
        return "You have no Clones yet. Want to add one with kairu team add?"
    if not project:
        return "There's no project yet. Want me to split one? Say: split the project, then the brief."
    head = (f"Project {project['number']}, {project['name']}, is {project['progress']}% done: "
            f"{project['done']} of {project['tasks_total']} tasks.")
    if project["state"] == "done":
        return f"{head} It's finished. Want to see the board?"
    blocked = [t for t in project["tasks"] if t["state"] == BLOCKED]
    late = [t for t in project["tasks"] if t["slipping"]]
    quiet = [t for t in project["tasks"] if t.get("silent")]
    if blocked:
        t = blocked[0]
        return f"{head} Task {t['number']} with {t['clone']} is blocked. Want me to try it again with kairu team start?"
    if quiet:
        t = quiet[0]
        return f"{head} No word from {t['clone']} for a while on task {t['number']}. Want to check that laptop?"
    if late:
        t = late[0]
        risk = " The deadline is at risk." if project["at_risk"] else ""
        return f"{head} Task {t['number']} with {t['clone']} is slipping.{risk} Want to move a task to someone else?"
    if project["state"] == "planned":
        return f"{head} It hasn't started. Shall I start it?"
    end = f" Expected to end {_clock(project['projected_end'])}, before the deadline." if project["deadline"] else ""
    return f"{head} On track.{end} Want to see the board?"


def status(data_dir: str, job: str) -> None:
    from kairu.tasks.actions import _say as reply
    from kairu.team.board import board
    reply(data_dir, job, True, summary(board(data_dir)))
