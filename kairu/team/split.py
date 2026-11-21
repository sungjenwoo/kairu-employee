"""Main Kairu splits a project (TEAM.md): what the brain is told, and how its answer is read.

    instructions(clones, minutes)  the brain's instructions: the Clones and their shares, the time left, and the only kind of
                                   orders a task may hold (plain orders the bar already knows, one per line)
    parse(text, clones)            the brain's answer, read strictly: JSON only, 1 to MOST_TASKS tasks, each for a Clone that
                                   exists, with 1 to MOST_ORDERS short orders, a "done" check, the tasks it waits for (earlier
                                   ones only, so there is no loop) and its minutes. Anything else: no split.

What a split cannot do, whatever the AI writes: name a Clone you have not added; send an approval, a PIN or a "yes" (an
order is only words, and each Clone's own Guardian decides every step, with "yes" and that laptop's PIN for High); run
anything on Main Kairu's PC (a split is only kept in data/team.db until you start it).
"""

import json
import re

MOST_TASKS = 8
MOST_ORDERS = 4
LONGEST_ORDER = 240
LONGEST_TITLE = 80
LONGEST_DONE = 160
FORBIDDEN = re.compile(r"\b(?:pin|password|passcode|otp)\b|^\s*(?:yes|y|approve)\s*$", re.I)

EXAMPLES = (
    "open notepad",
    "type Welcome to our shop in notepad",
    "save it in notepad",
    "make a file called homepage.txt saying Hero line: Fresh bread every morning",
    "open file homepage.txt",
    "google best colours for a bakery website",
    "open youtube",
    "research the top 3 bakery websites in Hyderabad",
    "what is a good tagline for a bakery",
    "close notepad",
)


class NoSplit(Exception):
    pass


def _who(clone: dict, busy: dict) -> str:
    said = f'"{clone["name"]}" (share {clone["share"]:g}'
    if clone.get("skills"):
        said += f', good at: {clone["skills"]}'
    if busy.get(clone["name"]):
        said += f', already busy for about {int(busy[clone["name"]])} minutes on other projects'
    return said + ")"


def instructions(clones: list[dict], minutes: float | None, busy: dict | None = None) -> str:
    """`busy`: minutes of unfinished work each Clone already has in other projects, so the split weighs workload."""
    team = "; ".join(_who(clone, busy or {}) for clone in clones)
    time_left = f"about {int(minutes)} minutes until the deadline" if minutes else "no deadline given"
    return (
        "You are Main Kairu, the lead of a team of AI teammates called Clones, each a Kairu on an employee's laptop. "
        "Split the project you are given into tasks, one Clone per task, so the team finishes before the deadline. "
        f"The Clones are: {team}. A share of 2 means that Clone takes about twice the work of a share of 1. Time: {time_left}.\n"
        "Each task has orders: short plain commands that the Clone's laptop already understands, one per order, such as: "
        + " | ".join(EXAMPLES) + ". "
        "Only use orders like these: open or close an app, type words in an app, save in an app, make a text file with words, "
        "open a file, google something, open a website, research a question or ask a question. Every type, press, save or click "
        "order ends with in and its app, such as 'type Hello in notepad', after an order that opens that app. Never an order with a PIN, a "
        "password, money, a purchase, installing, deleting or a terminal.\n"
        "Answer with JSON only, no other words: "
        '{"tasks": [{"title": "...", "clone": "<a Clone\'s name>", "orders": ["...", "..."], '
        '"done": "how we know it is done", "after": [<numbers of earlier tasks it waits for, 1 is the first>], "minutes": 10}]}. '
        f"At most {MOST_TASKS} tasks, at most {MOST_ORDERS} orders each, every order under {LONGEST_ORDER} characters. "
        "The clone field must be exactly one of the Clones' names above, as written. "
        "Give each task to the Clone whose skills fit it best, and balance the work by share and by how busy each Clone "
        "already is. Give every Clone at least one task when there is enough work. Keep titles short. The done field says "
        "how the manager can check the task is finished, such as 'homepage.txt exists with a hero line'."
    )


def _text(value, longest: int, what: str) -> str:
    if not isinstance(value, str):
        raise NoSplit(f"a task's {what} is not text")
    value = " ".join(value.split())
    if not value or len(value) > longest:
        raise NoSplit(f"a task's {what} is empty or longer than {longest} characters")
    return value


HANDS = re.compile(r"^(?:type|press|save|click)\b", re.I)
OPENS = re.compile(r"^open (?!file\b|the file\b)([a-z0-9][a-z0-9 .+&-]{0,39})$", re.I)
ENDS_IN = re.compile(r"\bin [a-z0-9][a-z0-9 .+&-]{0,39}$", re.I)


def name_apps(orders: list[str], number: int) -> list[str]:
    """Every type, press, save or click order names its app (found in the laptop test, 17 Nov 2026: "type ..." with no app went
    to the window in front, PowerShell, and the hands refused). One without "in APP" gets the app this task opened last; if
    the task opened none, the split is refused. Kairu only fills in the task's own app: it never picks a riskier one."""
    out, opened = [], None
    for order in orders:
        found = OPENS.match(order.strip())
        if found:
            opened = found.group(1).strip()
        elif HANDS.match(order.strip()):
            if opened and not order.lower().rstrip(" .").endswith(f" in {opened.lower()}"):
                order = f"{order.rstrip(' .')} in {opened}"
            elif not opened and not ENDS_IN.search(order.rstrip(" .")):
                raise NoSplit(f"task {number}: say which app this order is for: {order[:60]}")
        out.append(order)
    return out


def parse(text: str, clones: list[dict]) -> list[dict]:
    found = re.search(r"\{.*\}", text or "", re.S)  # an AI may still wrap its JSON in a few words or a code fence
    if not found:
        raise NoSplit("the answer was not JSON")
    try:
        data = json.loads(found.group(0))
    except ValueError:
        raise NoSplit("the answer was not JSON") from None
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MOST_TASKS:
        raise NoSplit(f"a split has 1 to {MOST_TASKS} tasks")
    names = {clone["name"].lower(): clone["name"] for clone in clones}

    def which(said) -> str | None:
        """The Clone a task names. An AI may write another name for it ("Clone 1", "Main Kairu"): with one Clone that is it,
        and "Clone N" is the Nth. Only ever one of your own Clones; anything else is no split."""
        said = str(said or "").strip()
        if said.lower() in names:
            return names[said.lower()]
        if len(clones) == 1:
            return clones[0]["name"]
        found = re.fullmatch(r"(?:clone|teammate|member)\s*#?\s*(\d)", said, re.I)
        if found and 1 <= int(found.group(1)) <= len(clones):
            return clones[int(found.group(1)) - 1]["name"]
        return None
    out = []
    for number, task in enumerate(tasks, 1):
        if not isinstance(task, dict) or set(task) - {"title", "clone", "orders", "done", "after", "minutes"}:
            raise NoSplit(f"task {number} has parts a task doesn't have")
        clone = which(task.get("clone"))
        if clone is None:
            raise NoSplit(f"task {number} is for a Clone you haven't added")
        orders = task.get("orders")
        if not isinstance(orders, list) or not 1 <= len(orders) <= MOST_ORDERS:
            raise NoSplit(f"task {number} needs 1 to {MOST_ORDERS} orders")
        orders = name_apps([_text(order, LONGEST_ORDER, "order") for order in orders], number)
        if any(FORBIDDEN.search(order) for order in orders):
            raise NoSplit(f"task {number} has an order with a PIN, a password or an approval in it")
        after = task.get("after", [])
        if not isinstance(after, list) or any(type(n) is not int or not 1 <= n < number for n in after):
            raise NoSplit(f"task {number} may wait only for earlier tasks")
        minutes = task.get("minutes", 10)
        if type(minutes) not in (int, float) or not 1 <= minutes <= 600:
            raise NoSplit(f"task {number}'s minutes must be 1 to 600")
        out.append({"title": _text(task.get("title"), LONGEST_TITLE, "title"), "clone": clone, "orders": orders,
                    "done": _text(task.get("done") or "its orders all finished", LONGEST_DONE, "done check"),
                    "after": sorted(set(after)), "minutes": float(minutes)})
    return out


def load(tasks: list[dict], clones: list[dict]) -> list[dict]:
    """How the work of a split falls on each Clone: its tasks, its minutes, and how that compares with its share.

    fair is the minutes it would have if the work followed the shares exactly; over is True when it has more than a
    third above that (the manager may move a task with `kairu team move`)."""
    total = sum(task["minutes"] for task in tasks) or 1
    shares = sum(clone["share"] for clone in clones) or 1
    out = []
    for clone in clones:
        mine = [task for task in tasks if task["clone"] == clone["name"]]
        minutes = sum(task["minutes"] for task in mine)
        fair = total * clone["share"] / shares
        out.append({"clone": clone["name"], "tasks": len(mine), "minutes": minutes, "fair": round(fair, 1),
                    "over": bool(mine) and minutes > fair * 4 / 3 + 5})
    return out
