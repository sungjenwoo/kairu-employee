"""The growth record (TEAM.md "Growth", ADR-049 proposed): good work gets seen, and a person always decides.

Main Kairu keeps, for each Clone, a record of the work its tasks delivered, worked out by rules from team.db (no AI):

    delivered      tasks done
    early / on time / late
                   a task's real time (first order sent to last order done) against its planned minutes; on time is
                   within 10% or 5 minutes of the plan
    unblocked      done tasks that other tasks were waiting for
    stepped in     tasks that were blocked (a refused step, a PIN not given) and were still finished: what the person
                   at that laptop added
    checked        tasks whose "done when" check the manager confirmed (team.check): the manager's word on quality
    kinds of work  research, writing, design, testing, building, data, docs, from the task titles by fixed words

The safe version, by design:
- It measures tasks, never people: every entry says what a task did ("Task 3 'Research' was delivered 12 min early"), never
  how fast or hard a person works. A task's time includes the Clone's own work and any wait, and says so.
- Nothing is a score and nothing ranks: no totals across people, no "best", no order but the Clones' names.
- The employee sees everything recorded about them: each entry waits in that Clone's queue and rides on its next order
  (kairu/team/conduct.py), so it reaches that laptop's team inbox (`kairu team record` there). The manager's view says
  which entries are still waiting.
- Suggestions are for the manager to decide ("Suggestion for you to decide: ..."), with the evidence; Kairu never assigns,
  promotes or marks anyone down. A bigger task is an offer (team.offer) that the employee accepts or declines on their
  own laptop (`kairu team accept N` / `decline N`).
"""

import re

from kairu.team.store import BLOCKED, DONE, TeamStore

KINDS = (
    ("research", r"research|investigat|compar|competitor|survey|find out|look up|analy[sz]"),
    ("writing", r"writ|draft|copy|blog|article|email|text|content|summar"),
    ("design", r"design|logo|mockup|layout|banner|poster|slide|ui\b|style"),
    ("testing", r"test|qa\b|check|verif|bug|review"),
    ("building", r"build|code|implement|develop|page|site|app|fix|deploy|script"),
    ("data", r"data|sheet|spreadsheet|report|chart|numbers|excel|csv"),
    ("docs", r"doc|readme|guide|manual|notes|note\b"),
)
ON_TIME_SHARE = 0.10
ON_TIME_MINUTES = 5
SUGGEST_DELIVERED = 3  # a kind of work with this many tasks delivered early or on time, none late, may be suggested


def kinds(title: str) -> list[str]:
    text = title.lower()
    return [name for name, words in KINDS if re.search(words, text)] or ["other"]


def timing(task: dict) -> tuple[str, float] | None:
    """("early" | "on time" | "late", minutes off the plan) for a done task with both times; None otherwise."""
    if task["state"] != DONE or not task["started"] or not task["finished"]:
        return None
    took = (task["finished"] - task["started"]) / 60
    off = took - task["minutes"]
    slack = max(task["minutes"] * ON_TIME_SHARE, ON_TIME_MINUTES)
    if off > slack:
        return "late", off
    if off < -slack:
        return "early", -off
    return "on time", abs(off)


def entry(task: dict, project: dict | None, waited_on: int) -> str:
    """The record's words for one done task: about the task, never the person."""
    where = f"project {task['project']} '{project['name']}'" if project else f"project {task['project']}"
    said = f"Record: task {task['number']} '{task['title']}' in {where} was delivered"
    when = timing(task)
    if when:
        said += {"early": f" {round(when[1])} min early", "late": f" {round(when[1])} min after its plan",
                 "on time": " on time"}[when[0]]
    if task["blocked_once"]:
        said += "; it was blocked once and you got it finished"
    if waited_on:
        said += f"; it let {waited_on} other task{'s' if waited_on != 1 else ''} start"
    return said + "."


def _all_tasks(store: TeamStore) -> list[dict]:
    tasks = []
    for project in store.projects():
        for task in store.tasks(project["number"]):
            tasks.append({**task, "project": project["number"], "project_name": project["name"]})
    return tasks


def record(store: TeamStore, clone: str) -> dict:
    """One Clone's record. Counts only; no score."""
    tasks = _all_tasks(store)
    mine = [task for task in tasks if task["clone"].lower() == clone.lower()]
    done = [task for task in mine if task["state"] == DONE]
    waited = {}
    for task in tasks:
        for number in task["after"]:
            waited[(task["project"], number)] = waited.get((task["project"], number), 0) + 1
    out = {"clone": clone, "delivered": len(done), "early": 0, "on time": 0, "late": 0, "unblocked": 0, "stepped_in": 0,
           "checked": 0, "open": len(mine) - len(done), "blocked_now": sum(task["state"] == BLOCKED for task in mine), "kinds": {}}
    for task in done:
        when = timing(task)
        if when:
            out[when[0]] += 1
        out["unblocked"] += bool(waited.get((task["project"], task["number"])))
        out["stepped_in"] += bool(task["blocked_once"])
        out["checked"] += bool(task["checked"])
        for kind in kinds(task["title"]):
            row = out["kinds"].setdefault(kind, {"delivered": 0, "early": 0, "on time": 0, "late": 0})
            row["delivered"] += 1
            if when:
                row[when[0]] += 1
    out["pending"] = len(store.pending(clone))
    return out


def suggestions(store: TeamStore) -> list[dict]:
    """For the manager to decide, with the evidence: a kind of work where a Clone's tasks were delivered SUGGEST_DELIVERED
    times or more and never late. Never a ranking: each Clone is looked at on its own, in name order."""
    out = []
    taken = {(offer["clone"].lower(), offer["words"].lower()) for offer in store.offers() if offer["state"] != "declined"}
    for clone in sorted(store.clones(), key=lambda row: row["name"].lower()):
        for kind, row in sorted(record(store, clone["name"])["kinds"].items()):
            if kind == "other" or row["early"] + row["on time"] < SUGGEST_DELIVERED or row["late"]:
                continue
            offer = f"Lead the next {kind} task"
            if (clone["name"].lower(), offer.lower()) in taken:
                continue
            out.append({"clone": clone["name"], "kind": kind, "offer": offer,
                        "evidence": f"{row['delivered']} {kind} tasks delivered, {row['early']} early, "
                                    f"{row['on time']} on time, none late"})
    return out


def lines(store: TeamStore, clone: str | None = None) -> list[str]:
    """`kairu team growth [NAME]`: each Clone on its own, in name order, then the suggestions and the offers."""
    clones = sorted(store.clones(), key=lambda row: row["name"].lower())
    if clone:
        clones = [row for row in clones if row["name"].lower() == clone.lower()]
        if not clones:
            return [f"There is no Clone called {clone}."]
    if not clones:
        return ["No Clones yet."]
    out = ["Growth record: what each Clone's tasks delivered (tasks, not people; no score, no ranking).",
           "Every entry also goes to that person's laptop with their next order."]
    for row in clones:
        rec = record(store, row["name"])
        out.append(f"{row['name']}: {rec['delivered']} delivered ({rec['early']} early, {rec['on time']} on time, "
                   f"{rec['late']} after plan), {rec['open']} open")
        extra = []
        if rec["unblocked"]:
            extra.append(f"{rec['unblocked']} let other tasks start")
        if rec["stepped_in"]:
            extra.append(f"{rec['stepped_in']} finished after being blocked")
        if rec["checked"]:
            extra.append(f"{rec['checked']} checked by you")
        if extra:
            out.append("  " + "; ".join(extra))
        if rec["kinds"]:
            out.append("  kinds of work: " + ", ".join(f"{kind} {k['delivered']}" for kind, k in sorted(rec["kinds"].items())))
        if rec["pending"]:
            out.append(f"  {rec['pending']} entr{'ies' if rec['pending'] != 1 else 'y'} waiting to reach {row['name']}'s "
                       "laptop (with its next order)")
    names = {row["name"].lower() for row in clones}
    ideas = [idea for idea in suggestions(store) if idea["clone"].lower() in names]
    if ideas:
        out.append("Suggestions for you to decide (Kairu never assigns or promotes):")
        out += [f"  Offer {idea['clone']}: \"{idea['offer']}\" ({idea['evidence']}). "
                f"`kairu team offer {idea['clone']} \"{idea['offer']}\"`" for idea in ideas]
    offers = [offer for offer in store.offers() if offer["clone"].lower() in names]
    if offers:
        out.append("Offers:")
        out += [f"  #{offer['number']} {offer['clone']}: {offer['words']} ({offer['state']})" for offer in offers]
    return out
