"""Stage 5 of the meeting agent (HACKATHON.md): proof and tracking.

    link_project(data_dir, project, tasks, brief)   inside team.split, when the brief came from a meeting (its lines carry
                                                    ids like [A2.3]): each Clone task is linked to the meeting item it does.
                                                    The split may name the id ("from": "A2.3"); otherwise Kairu matches the
                                                    words; a brief with one action links every task to it
    progress(data_dir)                              read only: for each linked item, its Clone tasks, how many are done, and
                                                    its proof (who did it, the "done when" check, what was made)
    sync(data_dir)                                  writes it back: an item whose Clone work is all done (in one project)
                                                    becomes done in the ledger, with its proof. Called by team.run when a
                                                    task finishes and by team.check
    ledger(data_dir)                                the decision ledger with that work laid over it (read only), so every
                                                    reader sees "done" at once, even before the next write-back
    before(data_dir) / told_before(found)           the brief before the next meeting: what got done (with proof), what is
                                                    still open (overdue, no owner), slipping Clone tasks, conflicts to decide
                                                    and open questions; answered by rules (Tenmin: answer first, one question)

Nothing here runs, sends or approves anything. A Clone's words (its last report) are data shown to you, kept on this PC; they
never move an item by themselves: only the team board's own state "done" for every linked task does.
"""

import re
import time
from datetime import date, datetime

from kairu.meeting.store import MeetingError, MeetingStore, exists

ID = re.compile(r"\[(?P<kind>[AD])(?P<meeting>\d{1,6})\.(?P<item>\d{1,3})\]")
NAMED = re.compile(r"[AD]\d{1,6}\.\d{1,3}")
MATCH = 0.34          # word overlap at or above which a task does a meeting item
OWNER_BONUS = 0.25    # the task's Clone has the item's owner's name
MADE = re.compile(r"\b(?:file|document|doc|note|page)\s+(?:called|named)\s+[\"']?(?P<name>[\w.-]{1,60}\.\w{1,6})", re.I)
SHOWN = 6
LONGEST_LAST = 160


def ids_in(brief: str) -> dict[str, tuple[str, int, int]]:
    """The ids a meeting brief carries: {"A2.3": ("A", 2, 3), ...}."""
    return {found.group(0)[1:-1]: (found.group("kind"), int(found.group("meeting")), int(found.group("item")))
            for found in ID.finditer(brief or "")}


def _text(task: dict) -> str:
    return " ".join([task.get("title", ""), task.get("done", ""), *task.get("orders", [])])


def _best(text: str, items: list[dict], clone: str = "") -> dict | None:
    from kairu.meeting.ledger import overlap
    best, score = None, 0.0
    for item in items:
        value = overlap(text, item["what"])
        if clone and item.get("owner") and item["owner"].lower() == clone.lower():
            value += OWNER_BONUS
        if value > score:
            best, score = item, value
    return best if score >= MATCH else None


def link_project(data_dir, project: int, tasks: list[dict], brief: str) -> list[tuple[int, str]]:
    """Link each task of a just-split project to the meeting item it does. Returns [(task number, "A2.3"), ...]. A brief
    with no ids (an ordinary "split the project") links nothing. Never raises for a bad link: that task stays unlinked."""
    ids = ids_in(brief)
    if not ids or not exists(data_dir):
        return []
    store = MeetingStore(data_dir)
    known = {(item["meeting"], item["number"]): item for item in store.ledger()}
    actions = [dict(known[(m, n)], id=key) for key, (kind, m, n) in ids.items() if kind == "A" and (m, n) in known]
    decisions = [dict(known[(m, n)], id=key) for key, (kind, m, n) in ids.items() if kind == "D" and (m, n) in known]
    by_id = {item["id"]: item for item in actions + decisions}
    out = []
    for number, task in enumerate(tasks, 1):
        named = str(task.get("from") or "")
        action, how = None, "matched"
        if named in by_id and by_id[named] in actions:
            action, how = by_id[named], "named"
        elif len(actions) == 1:
            action, how = actions[0], "only"
        else:
            action = _best(_text(task), actions, task.get("clone", ""))
        if action is None:
            continue
        chosen = [(action, how)]
        decision = by_id.get(named) if named in by_id and by_id[named] in decisions else \
            _best(_text(task) + " " + action["what"], decisions)
        if decision:
            chosen.append((decision, "named" if decision["id"] == named else "matched"))
        for item, way in chosen:
            try:
                store.link(int(project), number, item["meeting"], item["number"], way)
            except MeetingError:
                continue
        out.append((number, action["id"]))
    return out


# --- what the Clones did for each item ---------------------------------------------------------------------------

def _clock(moment) -> str:
    return time.strftime("%d %b %H:%M", time.localtime(moment)) if moment else ""


def _made(task: dict) -> list[str]:
    names = []
    for order in task["orders"]:
        for found in MADE.finditer(order):
            if found.group("name") not in names:
                names.append(found.group("name"))
    return names


def _proof_of(task: dict) -> str:
    said = f"{task['clone']}'s Clone did task {task['number']} '{task['title']}' (project {task['project']}"
    said += f", {_clock(task['finished'])})" if task.get("finished") else ")"
    said += f". Done when: {task['done']}"
    if task.get("checked"):
        said += " (checked by you)"
    made = _made(task)
    if made:
        said += f". Made: {', '.join(made)}"
    last = " ".join(str(task.get("last") or "").split())
    if last:
        said += f". It said: {last[:LONGEST_LAST].rstrip(' .')}"
    return said + "."


def progress(data_dir) -> dict:
    """{(meeting, item): {"total", "done", "complete", "tasks": [...], "proof", "finished"}} for every linked item. Read only.
    An item is complete when every task linked to it in one project is done (a later re-split doesn't undo work done)."""
    if not exists(data_dir):
        return {}
    links = MeetingStore(data_dir).links()
    if not links:
        return {}
    from kairu.team.store import DONE, TeamStore, exists as team_exists
    if not team_exists(data_dir):
        return {}
    team = TeamStore(data_dir)
    projects, tasks = {}, {}
    for number in {link["project"] for link in links}:
        projects[number] = team.project(number)
        tasks[number] = {task["number"]: dict(task, project=number) for task in team.tasks(number)} if projects[number] else {}
    out: dict = {}
    for link in links:
        task = tasks.get(link["project"], {}).get(link["task"])
        if task is None:
            continue  # its project is gone from the board: nothing to show
        found = out.setdefault((link["meeting"], link["item"]), {"by_project": {}, "tasks": []})
        found["by_project"].setdefault(link["project"], []).append(task)
        found["tasks"].append({"project": link["project"], "number": task["number"], "title": task["title"],
                               "clone": task["clone"], "state": task["state"], "how": link["how"]})
    for found in out.values():
        complete = [held for held in found["by_project"].values() if all(task["state"] == DONE for task in held)]
        newest = max(complete, key=lambda held: max(task["finished"] or 0 for task in held)) if complete else None
        found["total"] = len(found["tasks"])
        found["done"] = sum(task["state"] == DONE for task in found["tasks"])
        found["complete"] = newest is not None
        found["proof"] = " ".join(_proof_of(task) for task in newest) if newest else ""
        found["finished"] = max(task["finished"] or 0 for task in newest) if newest else None
        del found["by_project"]
    return out


def split_already(data_dir) -> set[tuple[int, int]]:
    """The meeting items already linked to a Clone project that wasn't stopped (so the next split leaves them out)."""
    if not exists(data_dir):
        return set()
    links = MeetingStore(data_dir).links()
    from kairu.team.store import TeamStore, exists as team_exists
    if not links or not team_exists(data_dir):
        return set()
    team = TeamStore(data_dir)
    live = {number for number in {link["project"] for link in links}
            if (team.project(number) or {}).get("state", "stopped") != "stopped"}
    return {(link["meeting"], link["item"]) for link in links if link["project"] in live}


def overlay(items: list[dict], work: dict) -> list[dict]:
    """The items with their Clone work laid over them: "work" on every linked item, and an open item whose work is complete
    shown as done with its proof. Read only: sync() is what writes it back."""
    out = []
    for item in items:
        found = work.get((item["meeting"], item["number"]))
        if found:
            item = dict(item, work={key: found[key] for key in ("total", "done", "complete", "tasks")})
            if found["complete"] and item["status"] == "open":
                item.update(status="done", proof=found["proof"], done_at=found["finished"])
        out.append(item)
    return out


def ledger(data_dir, **filters) -> list[dict]:
    """MeetingStore.ledger with the Clone work laid over it."""
    if not exists(data_dir):
        return []
    return overlay(MeetingStore(data_dir).ledger(**filters), progress(data_dir))


def sync(data_dir) -> list[tuple[int, int]]:
    """Write the finished Clone work back to the ledger: each item whose work is complete becomes done, with its proof.
    Returns the items that changed. Only status, proof and when change; nothing runs."""
    work = progress(data_dir)
    if not work:
        return []
    store = MeetingStore(data_dir)
    changed = []
    for (meeting, number), found in sorted(work.items()):
        if found["complete"] and store.set_done(meeting, number, found["proof"], found["finished"]):
            changed.append((meeting, number))
    return changed


def told_sync(changed: list[tuple[int, int]], data_dir) -> str:
    if not changed:
        return ""
    known = {(item["meeting"], item["number"]): item for item in MeetingStore(data_dir).ledger()}
    names = [f"\"{known[key]['what']}\" (meeting {key[0]})" for key in changed if key in known]
    return f"Written back to the ledger as done: {'; '.join(names)}." if names else ""


# --- the brief before the next meeting -------------------------------------------------------------------------------

def _day(held: str) -> str:
    try:
        day = datetime.strptime(held, "%Y-%m-%d")
        return f"{day.day} {day.strftime('%b')}"
    except (TypeError, ValueError):
        return held or ""


def _slipping(data_dir, links: list[dict], known: dict) -> list[dict]:
    """Clone tasks that are blocked, slipping or silent, in every project that isn't done, with the meeting item each does."""
    from kairu.team.store import exists as team_exists
    if not team_exists(data_dir):
        return []
    from kairu.team.board import board
    from kairu.team.store import TeamStore
    which = {(link["project"], link["task"]): (link["meeting"], link["item"]) for link in links
             if known.get((link["meeting"], link["item"]), {}).get("kind") == "action"}
    out = []
    for project in TeamStore(data_dir).projects():
        if project["state"] in ("done", "stopped"):
            continue
        view = board(data_dir, project["number"]).get("project") or {}
        for task in view.get("tasks", []):
            why = "blocked" if task["state"] == "blocked" else "silent" if task.get("silent") else \
                "slipping" if task["slipping"] else ""
            if not why:
                continue
            item = known.get(which.get((project["number"], task["number"])))
            out.append({"project": project["number"], "number": task["number"], "title": task["title"], "clone": task["clone"],
                        "why": why, "planned_end": task["planned_end"], "last": task["last"][:LONGEST_LAST],
                        "item": {"meeting": item["meeting"], "number": item["number"], "what": item["what"]} if item else None})
    return out


def before(data_dir, today: date | None = None) -> dict:
    """Everything the brief before the next meeting says, read only."""
    today = today or date.today()
    empty = {"done": [], "open": [], "overdue": 0, "nobody": 0, "slipping": [], "conflicts": {"between": [], "rules": []},
             "questions": [], "meetings": 0, "unsplit": 0}
    if not exists(data_dir):
        return empty
    from kairu.meeting.ledger import busy, rule_conflicts
    store = MeetingStore(data_dir)
    meetings = store.meetings()
    if not meetings:
        return empty
    work = progress(data_dir)
    items = overlay(store.ledger(), work)
    known = {(item["meeting"], item["number"]): item for item in items}
    done = sorted((item for item in items if item["status"] == "done"), key=lambda item: item.get("done_at") or 0,
                  reverse=True)
    still = [item for item in items if item["kind"] == "action" and item["status"] == "open"]
    still.sort(key=lambda item: (item["due"] or "9999-99-99", item["meeting"], item["number"]))
    for item in still:
        item["overdue"] = bool(item["due"]) and item["due"] < today.isoformat()
    questions = [item for item in store.items_of("question", "open")]
    return {"done": done, "open": still, "overdue": sum(item["overdue"] for item in still),
            "nobody": sum(not item["owner"] for item in still), "slipping": _slipping(data_dir, store.links(), known),
            "conflicts": {"between": store.conflicts("open"), "rules": rule_conflicts(items, busy(data_dir), today)},
            "questions": questions[-SHOWN:], "meetings": len(meetings),
            "unsplit": sum(1 for item in still if not item.get("work"))}


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def told_before(found: dict) -> str:
    """The brief in Tenmin's way: the counts first, then each part in a few lines, then exactly one question."""
    if not found["meetings"]:
        return "No meetings yet, so there's nothing to brief. Want to read one? Say: read the meeting NAME."
    conflicts = len(found["conflicts"]["between"]) + len(found["conflicts"]["rules"])
    overdue = f" ({found['overdue']} overdue)" if found["overdue"] else ""
    head = (f"Before your next meeting: {len(found['done'])} done, {len(found['open'])} open{overdue}, "
            f"{len(found['slipping'])} slipping, {_plural(conflicts, 'conflict')} to decide.")
    out = [head]
    if found["done"]:
        out.append("Done, with proof:")
        for item in found["done"][:SHOWN]:
            proof = item.get("proof") or "marked done in the ledger."
            out.append(f"  ✓ {item['what'].rstrip('.')} ({item['meeting_title']}, {_day(item['held'])}): {proof}")
    if found["open"]:
        out.append("Still open:")
        for item in found["open"][:SHOWN]:
            bits = [item["owner"] or "nobody yet"]
            if item["due"]:
                bits.append(("OVERDUE, was due " if item.get("overdue") else "due ") + _day(item["due"]))
            work = item.get("work")
            bits.append(f"Clones {work['done']} of {work['total']} tasks done" if work else "not split to the Clones yet")
            out.append(f"  · {item['what'].rstrip('.')} ({', '.join(bits)}; meeting {item['meeting']})")
        if len(found["open"]) > SHOWN:
            out.append(f"  and {len(found['open']) - SHOWN} more.")
    if found["slipping"]:
        out.append("Slipping:")
        for task in found["slipping"][:SHOWN]:
            about = f", for \"{task['item']['what'].rstrip('.')}\" (meeting {task['item']['meeting']})" if task["item"] else ""
            out.append(f"  ! task {task['number']} '{task['title']}' ({task['clone']}, project {task['project']}) is "
                       f"{task['why']}{about}")
    if conflicts:
        out.append("Conflicts to decide:")
        for clash in found["conflicts"]["between"][:SHOWN]:
            out.append(f"  [{clash['meeting']}.{clash['number']}] {clash['kind']}: {clash['what']}")
        for clash in found["conflicts"]["rules"][:SHOWN]:
            out.append(f"  - {clash['kind']}: {clash['what']}")
    if found["questions"]:
        out.append("Open questions: " + "; ".join(item["what"].rstrip(".?") + "?" for item in found["questions"]))
    if found["conflicts"]["between"]:
        out.append("Want to decide the conflicts first? Say: show the conflicts.")
    elif found["slipping"]:
        out.append("Want to move a slipping task to someone else? See the Clones page.")
    elif found["unsplit"]:
        out.append("Want me to split the open actions to the Clones? Say: split the meeting.")
    elif found["open"]:
        out.append("Want to see how the project is going? Say: how's the project going?")
    else:
        out.append("Everything agreed is done. Want to see the ledger with its proof? Run: kairu meeting ledger.")
    return "\n".join(out)
