"""The team board (TEAM.md): what Main Kairu shows the manager about a project, from data/team.db only. Read only.

For each task: its Clone, its state, how far it has got, what its Clone last said, and whether it is slipping. A task is
slipping when it isn't done and either its planned end has passed or, at the pace so far, it would end after the deadline.
The plan is simple: from the project's start, each Clone does its tasks in order, and a task starts when the tasks it
waits for are done; a task takes its minutes.

Also (TEAM.md "The manager's view"): each Clone's workload (tasks done and left, minutes left), time used against work
done (the deadline bar), a task whose Clone has said nothing for a while (silent), and the team feed: Main Kairu's notes
to its Clones and what the Clones said with `kairu team say` (data, shown as text only). On a Clone's laptop, its team
inbox (Main Kairu's notes to it).
"""

import time

from kairu.team.store import DONE, SENT, TeamStore, exists

QUIET_SECONDS = 600


def _inbox(data_dir) -> list[dict]:
    from kairu.team.inbox import read
    return read(data_dir)[-12:]


def _growth(store) -> dict:
    """The growth record for the manager's page: each Clone on its own in name order, suggestions, offers."""
    from kairu.team.growth import record, suggestions
    people = [record(store, clone["name"]) for clone in sorted(store.clones(), key=lambda row: row["name"].lower())]
    return {"people": people, "suggestions": suggestions(store), "offers": store.offers()[-20:]}


def board(data_dir, project: int | None = None, now: float | None = None) -> dict:
    now = now or time.time()
    if not exists(data_dir):
        return {"clones": [], "projects": [], "project": None, "inbox": _inbox(data_dir)}
    store = TeamStore(data_dir)
    clones = [{"name": clone["name"], "share": clone["share"], "seen": clone["seen"], "skills": clone.get("skills", ""),
               "quiet": not clone["seen"] or now - clone["seen"] > QUIET_SECONDS} for clone in store.clones()]
    inbox = _inbox(data_dir)
    projects = [{"number": p["number"], "name": p["name"], "state": p["state"], "deadline": p["deadline"]}
                for p in store.projects()[:20]]
    number = project or store.latest()
    if not number or store.project(number) is None:
        return {"clones": clones, "projects": projects, "project": None, "inbox": inbox, "growth": _growth(store)}
    info = store.project(number)
    tasks = store.tasks(number)
    start = info["started"] or now
    planned, expected = {}, {}
    free_planned, free_expected = {}, {}
    for task in tasks:
        clone, length = task["clone"], task["minutes"] * 60
        begin = max([free_planned.get(clone, start)] + [planned[a] for a in task["after"] if a in planned])
        planned[task["number"]] = begin + length
        free_planned[clone] = planned[task["number"]]
        if task["state"] == DONE:
            end = task["finished"] or now
        else:
            share_left = 1 - task["step"] / max(len(task["orders"]), 1)
            begin = max([free_expected.get(clone, start)] + [expected[a] for a in task["after"] if a in expected])
            if task["state"] == SENT and task["started"]:
                begin = max(begin, task["started"])
            end = max(begin + length, now + length * share_left)
        expected[task["number"]] = end
        free_expected[clone] = max(free_expected.get(clone, start), end)
    deadline = info["deadline"]
    seen = {clone["name"]: clone["seen"] for clone in clones}
    shown = []
    for task in tasks:
        late = task["state"] != DONE and (now > planned[task["number"]] or bool(deadline and expected[task["number"]] > deadline))
        heard = max(seen.get(task["clone"]) or 0, task["sent"] or 0)
        silent = task["state"] == SENT and info["state"] == "running" and now - heard > QUIET_SECONDS
        shown.append({"number": task["number"], "title": task["title"], "clone": task["clone"], "state": task["state"],
                      "step": task["step"], "orders": task["orders"], "done_check": task["done"], "after": task["after"],
                      "minutes": task["minutes"], "last": task["last"], "slipping": late, "silent": silent,
                      "planned_end": planned[task["number"]], "expected_end": expected[task["number"]]})
    total = sum(len(task["orders"]) for task in tasks) or 1
    finished = sum(len(task["orders"]) if task["state"] == DONE else task["step"] for task in tasks)
    projected = max(expected.values()) if expected else now
    workload = []
    for clone in clones:
        mine = [task for task in tasks if task["clone"] == clone["name"]]
        if not mine:
            continue
        left = sum(task["minutes"] * (1 - task["step"] / max(len(task["orders"]), 1)) for task in mine if task["state"] != DONE)
        now_on = next((task["number"] for task in mine if task["state"] == SENT), None)
        workload.append({"clone": clone["name"], "tasks": len(mine), "done": sum(task["state"] == DONE for task in mine),
                         "minutes_left": round(left), "working_on": now_on, "quiet": clone["quiet"],
                         "slipping": sum(task["slipping"] for task in shown if task["clone"] == clone["name"])})
    time_used = None
    if deadline and info["started"] and deadline > info["started"]:
        time_used = max(0, min(100, round(100 * (min(now, info["ended"] or now) - info["started"]) / (deadline - info["started"]))))
    return {"clones": clones, "projects": projects, "now": now, "inbox": inbox, "growth": _growth(store), "project": {
        "number": number, "name": info["name"], "state": info["state"], "deadline": deadline, "started": info["started"],
        "progress": round(100 * finished / total), "done": sum(task["state"] == DONE for task in tasks), "tasks_total": len(tasks),
        "projected_end": projected, "at_risk": bool(deadline and projected > deadline and info["state"] != "done"),
        "slipping": sum(task["slipping"] for task in shown), "tasks": shown, "workload": workload, "time_used": time_used,
        "feed": store.feed(number)}}


def lines(view: dict) -> list[str]:
    """The board as plain lines, for `kairu team show`."""
    out = []
    clones = ", ".join(f"{c['name']}{' (not heard from)' if c['quiet'] else ''}" for c in view["clones"]) or "none yet"
    out.append(f"Clones: {clones}")
    project = view.get("project")
    for note in view.get("inbox", [])[-5:] if not view["clones"] else []:
        out.append(f"From Main Kairu, {time.strftime('%d %b %H:%M', time.localtime(note['time']))}: {note['words'][:200]}")
    if not project:
        out.append("No project yet: `kairu team split \"<the project brief>\" --deadline \"YYYY-MM-DD HH:MM\"`.")
        return out
    when = time.strftime("%d %b %H:%M", time.localtime(project["deadline"])) if project["deadline"] else "none"
    flag = "  AT RISK" if project["at_risk"] else ""
    out.append(f"Project {project['number']}: {project['name']} [{project['state']}]  {project['progress']}%  "
               f"{project['done']}/{project['tasks_total']} tasks done  deadline {when}{flag}")
    if project.get("time_used") is not None:
        out.append(f"Time used {project['time_used']}%, work done {project['progress']}%"
                   f"{' (behind)' if project['time_used'] > project['progress'] + 10 and project['state'] != 'done' else ''}")
    for row in project.get("workload", []):
        on = f", now on task {row['working_on']}" if row["working_on"] else ""
        flags = (" SLIPPING" if row["slipping"] else "") + (" (not heard from)" if row["quiet"] else "")
        out.append(f"  {row['clone']}: {row['done']}/{row['tasks']} tasks done, about {row['minutes_left']} min left{on}{flags}")
    marks = {"done": "✓", "working": "▶", "waiting": "·", "blocked": "!"}
    for task in project["tasks"]:
        late = ("  SLIPPING" if task["slipping"] else "") + ("  SILENT" if task.get("silent") else "")
        out.append(f"  {marks.get(task['state'], '?')} {task['number']}. {task['title']} → {task['clone']} "
                   f"[{task['state']} {task['step']}/{len(task['orders'])}]{late}")
        if task["last"]:
            out.append(f"       {task['last'][:150]}")
    if project.get("feed"):
        out.append("Team feed:")
        for item in project["feed"][-8:]:
            to = f" → {item['whom']}" if item["whom"] else ""
            out.append(f"  {time.strftime('%H:%M', time.localtime(item['time']))} {item['who']}{to}: {item['words'][:160]}")
    return out
