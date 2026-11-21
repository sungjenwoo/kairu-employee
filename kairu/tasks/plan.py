"""Free-form orders (Sprint Day 4): the brain may map an order the rules don't know to steps of Kairu's KNOWN skills.

    catalogue()      what the brain is told it may use: only the skills in PLANNABLE, with their details
    parse(text, ..)  the brain's answer, read strictly: JSON only, at most MOST_STEPS steps, each a plannable skill that exists
                     (in policy.yaml, not Critical), with exactly that skill's details, all short text. Anything else: no plan.
    describe(step)   one short line for the plan you see in the bar before anything runs

What a plan cannot do, whatever the AI writes:
  - invent a skill: an action outside PLANNABLE, or one the registry refused at load, makes the whole plan void;
  - raise or lower a tier: a step has no tier; Guardian decides each step by policy.yaml, as for a typed order;
  - leave the work folder: the file skills' own fence refuses any name outside it, as for a typed order;
  - run without you: the plan is shown first; you type "yes", and "yes" plus your PIN if a step is High.
The AI only ever sees your order (after the privacy filter), never a file name, a window title or a page.
"""

import json
import re
import time

MOST_STEPS = 8
LONGEST_DETAIL = 200
LONGEST_NOTE = 1500  # PC6: a list or note the brain wrote, kept as a file (files.write's own limit is far higher)
PLANNABLE = ("files.find", "files.move", "files.rename", "files.delete", "files.write", "files.open", "files.show", "web.open",
             "web.search", "apps.open", "apps.close", "apps.arrange", "apps.list_open", "system.volume", "system.brightness", "system.status", "system.lock", "task.wait",
             "screen.type", "screen.press", "screen.click", "screen.read", "terminal.run")
DETAILS = {  # each skill's details, as its executor in kairu/executors.py takes them (a test checks they agree)
    "files.find": ("what", "when"), "files.move": ("name", "to"), "files.rename": ("old", "new"), "files.delete": ("name",),
    "files.write": ("name", "text"), "files.open": ("name",), "files.show": ("name",),
    "web.open": ("url",), "web.search": ("query",), "apps.open": ("name",), "apps.close": ("name",), "apps.arrange": ("name", "how"),
    "apps.list_open": (), "system.volume": ("setting",), "system.brightness": ("setting",), "system.status": (), "system.lock": (),
    "task.wait": ("seconds",),
    "screen.type": ("app", "text", "field", "enter"), "screen.press": ("app", "keys"), "screen.click": ("app", "target"),
    "screen.read": ("app",),
    "terminal.run": ("command", "folder"),
}
OPTIONAL = {"files.find": {"when": "", "what": ""}, "files.write": {"text": ""},
            "screen.type": {"app": "", "field": "", "enter": "no"}, "screen.press": {"app": ""}, "screen.click": {"app": ""},
            "screen.read": {"app": ""}, "terminal.run": {"folder": ""}}
WHAT = {
    "files.find": ("list files in the work folder by name (never opening them)",
                   'what: words in the name, a kind such as "pdfs" or "images", or a pattern such as "*.pdf"; '
                   'when: "", "today", "yesterday", "this week" or "last week"'),
    "files.move": ("move files into a folder inside the work folder (made if missing); overwrites nothing",
                   'name: a file name, or a pattern such as "*.pdf"; to: the folder\'s name'),
    "files.rename": ("rename one file in the work folder", "old: its name now; new: its new name"),
    "files.delete": ("move ONE file or folder to the Recycle Bin (the owner must approve it)", "name: its name; no patterns"),
    "files.write": ("make a NEW text file in the work folder; overwrites nothing",
                    'name: its name with .txt, .md, .csv, .json or .html; text: its words on one line (may be ""); for a list '
                    'or note of several lines put \\n between the lines, then files.open it to show it'),
    "files.open": ("open one file in the work folder with its own app (documents, pictures, sound, video, text)", "name: its name"),
    "files.show": ("show one file or folder of the work folder in Explorer", "name: its name"),
    "web.open": ("open a web page in the browser", 'url: an http or https address, or a site such as "youtube"'),
    "web.search": ("search Google in the browser", "query: the words"),
    "apps.open": ("open an installed app by its name", 'name: such as "Notepad"'),
    "apps.close": ("close an app politely", "name"),
    "apps.arrange": ("place an app's window", 'name; how: "left", "right", "maximize", "minimize" or "front"'),
    "apps.list_open": ("say which apps are open", "no details"),
    "system.volume": ("set the volume", 'setting: 0 to 100, "up", "down", "mute" or "unmute"'),
    "system.brightness": ("set the screen brightness", 'setting: 0 to 100, "up" or "down"'),
    "system.status": ("say free memory, battery and CPU", "no details"),
    "system.lock": ("lock the PC", "no details"),
    "task.wait": ("wait between steps", "seconds: 1 to 60"),
    "screen.type": ("type words in an app's window, where the cursor is or into its search or address bar",
                    'app: the app\'s name, or "" for the app just opened or in front; text: the words, one short line (a list or '
                    'a note of several lines is files.write then files.open instead); field: "", "search" or '
                    '"address"; enter: "yes" to press Enter after typing into a search or address bar, else "no"'),
    "screen.press": ("press keys in an app", 'app; keys: such as "tab", "ctrl+t", "alt+left", "pagedown" or "enter"'),
    "screen.click": ("click a button, link or tab by the name shown on it", "app; target: the name on it"),
    "screen.read": ("say which buttons, links and boxes an app's window shows", "app"),
    "terminal.run": ("run one command with no shell in the work folder or Kairu's folder (PC5); read-only ones such as git status "
                     "run at once, others ask the owner first",
                     'command: such as "git status" or "python -m pytest -q"; folder: "", a folder in the work folder, or "kairu"'),
}
EXAMPLE = ('Order: put all the pdfs in Kairu-files into a folder called pdfs\n'
           '{"steps": [{"action": "files.find", "details": {"what": "*.pdf", "when": ""}}, '
           '{"action": "files.move", "details": {"name": "*.pdf", "to": "pdfs"}}]}\n'
           'Order: open github and search for python tutorials\n'
           '{"steps": [{"action": "web.open", "details": {"url": "github.com"}}, '
           '{"action": "web.search", "details": {"query": "python tutorials"}}]}\n'
           'Order: open notepad and write a shopping list with milk and eggs\n'
           '{"steps": [{"action": "apps.open", "details": {"name": "Notepad"}}, '
           '{"action": "screen.type", "details": {"app": "Notepad", "text": "Shopping list: milk, eggs", "field": "", "enter": "no"}}]}\n'
           'Order: make me a sandwich\n{"steps": []}')


class NoPlan(Exception):
    """The brain's answer is not a plan Kairu can use. Its text says why, shortly."""


def details_of(action: str) -> tuple[str, ...]:
    """The details a skill takes from you: its executor's arguments, without the job id Kairu adds."""
    return DETAILS[action]


def catalogue(usable_actions) -> str:
    """The skills the brain may use, one line each: only plannable ones that exist."""
    lines = []
    for action in PLANNABLE:
        if action in usable_actions:
            what, details = WHAT[action]
            names = ", ".join(details_of(action)) or "none"
            lines.append(f"- {action} (details: {names}): {what}. {details}")
    return "\n".join(lines)


def instructions(usable_actions) -> str:
    return ("You turn one order for a Windows PC into steps, using ONLY the skills below. Reply with JSON only, nothing else:\n"
            '{"steps": [{"action": "<skill>", "details": {"<name>": "<text>"}}]}\n'
            f"- At most {MOST_STEPS} steps, in the order they should run. Every detail is text.\n"
            "- Use only these skills and exactly their detail names. Never add a step the order did not ask for.\n"
            "- File and folder names are relative to the work folder (Kairu-files): never a whole path or a drive.\n"
            '- If the order can\'t be done with these skills, reply {"steps": []}.\n'
            "Skills:\n" + catalogue(usable_actions) + "\nExamples:\n" + EXAMPLE)


NUMBERS = {("system.volume", "setting"), ("system.brightness", "setting"), ("task.wait", "seconds")}


def _plain(action: str, details: dict) -> dict:
    """An AI often writes a number as a number (30, not "30") and yes/no as true/false. Only these few details take that
    form; a name or anything else that isn't text is still no plan."""
    out = dict(details)
    for name, value in details.items():
        if (action, name) in NUMBERS and type(value) in (int, float) and not isinstance(value, bool):
            out[name] = str(int(value)) if float(value).is_integer() else str(value)
        elif action == "screen.type" and name == "enter" and isinstance(value, bool):
            out[name] = "yes" if value else "no"
    return out


def _notes_as_files(steps: list, usable_actions) -> list:
    """PC6: a step that would type a list or a note (several lines, or longer than a line) becomes "make a new text file
    with those words, then open it" (files.write never overwrites; files.open shows it in its own app, Notepad for .txt).
    Typing stays one short line (screen.text_problem). The plan, changed, is still shown first and runs only after yes."""
    if not {"files.write", "files.open"} <= set(usable_actions):
        return steps
    out, number = [], 0
    for step in steps:
        details = step.get("details") if isinstance(step, dict) else None
        text = details.get("text") if isinstance(details, dict) else None
        if (isinstance(step, dict) and step.get("action") == "screen.type" and isinstance(text, str)
                and ("\n" in text or len(text) > LONGEST_DETAIL) and len(text) <= LONGEST_NOTE):
            number += 1
            name = f"kairu-note-{time.strftime('%H%M%S')}{'-' + str(number) if number > 1 else ''}.txt"
            words = "\\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().split("\n"))
            out += [{"action": "files.write", "details": {"name": name, "text": words}},
                    {"action": "files.open", "details": {"name": name}}]
            continue
        out.append(step)
    return out


def parse(text: str, usable_actions) -> list[tuple[str, dict]]:
    """[(action, details), ...] from the brain's answer, or NoPlan. An empty list means the brain found no way."""
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", body, re.DOTALL)
    if fenced:
        body = fenced.group(1)
    try:
        data = json.loads(body)
    except ValueError:
        raise NoPlan("the AI's answer wasn't a plan") from None
    if not isinstance(data, dict) or set(data) != {"steps"} or not isinstance(data["steps"], list):
        raise NoPlan("the AI's answer wasn't a plan")
    steps = data["steps"]
    if len(steps) > MOST_STEPS:
        raise NoPlan(f"the plan had more than {MOST_STEPS} steps")
    steps = _notes_as_files(steps, usable_actions)
    if len(steps) > MOST_STEPS:
        raise NoPlan(f"the plan had more than {MOST_STEPS} steps")
    plan = []
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"action", "details"} or not isinstance(step.get("action"), str):
            raise NoPlan("a step of the plan wasn't a skill and its details")
        action, details = step["action"], step.get("details") or {}
        if action not in PLANNABLE or action not in usable_actions:
            raise NoPlan(f"the plan named a skill Kairu doesn't have ({action[:40]})")
        if not isinstance(details, dict):
            raise NoPlan("a step's details weren't names and text")
        wanted = details_of(action)
        filled = {**OPTIONAL.get(action, {}), **_plain(action, details)}
        if set(filled) != set(wanted):
            raise NoPlan(f"the plan gave {action} the wrong details")
        for name, value in filled.items():
            longest = LONGEST_NOTE if (action, name) == ("files.write", "text") else LONGEST_DETAIL
            if not isinstance(value, str) or len(value) > longest or re.search(r"[\x00-\x1f]", value):
                raise NoPlan(f"the plan gave {action} a detail that isn't short text")
        plan.append((action, {name: value.strip() for name, value in filled.items()}))
    return plan


def _app(details: dict) -> str:
    app = details.get("app", "")
    return "the browser" if app == "browser" else app or "the app in front"


def _where(details: dict) -> str:
    field = {"search": "the search bar of ", "address": "the address bar of "}.get(details.get("field", ""), "")
    return field + _app(details)


def _careful(d: dict) -> str:
    """screen.confirm's and screen.agent_confirm's step in a few words."""
    verb = d.get("verb", "")
    if verb == "type":
        return f'type "{d["what"]}" in {_where(d)}{" and press Enter" if d.get("enter") == "yes" else ""}'
    if verb == "press":
        return f"press {d['what']} in {_app(d)}"
    if verb == "choose":
        return f'choose "{d["what"]}" in "{d.get("field", "")}" in {_app(d)}'
    if verb == "tick":
        return f'{"tick" if d.get("enter", "yes") == "yes" else "untick"} "{d["what"]}" in {_app(d)}'
    if verb == "point":
        return f"click the point {d['what']} in {_app(d)}"
    return f'click "{d["what"]}" in {_app(d)}'


def describe(action: str, details: dict) -> str:
    """One short line for a step: what you will see before it runs. Details are shown as they are: they are data."""
    d = details
    lines = {
        "files.find": lambda: f"find {d.get('what') or 'files'}{' from ' + d['when'] if d.get('when') else ''} in your work folder",
        "files.move": lambda: f"move {d['name']} into {d['to']}",
        "files.rename": lambda: f"rename {d['old']} to {d['new']}",
        "files.delete": lambda: f"put {d['name']} in the Recycle Bin",
        "files.write": lambda: f"make {d['name']}",
        "files.open": lambda: f"open {d['name']}",
        "files.show": lambda: f"show {d['name']} in its folder",
        "web.open": lambda: f"open {d['url']} in Kairu's browser",
        "web.search": lambda: f"search Google for {d['query']}",
        "apps.open": lambda: f"open {d['name']}",
        "apps.close": lambda: f"close {d['name']}",
        "apps.arrange": lambda: f"{d['how']} {d['name']}",
        "apps.list_open": lambda: "say what's open",
        "system.volume": lambda: f"volume {d['setting']}",
        "system.brightness": lambda: f"brightness {d['setting']}",
        "system.status": lambda: "say the free RAM, battery and CPU",
        "system.lock": lambda: "lock the PC",
        "task.wait": lambda: f"wait {d['seconds']} seconds",
        "screen.type": lambda: (f'type "{d["text"]}" in {_where(d)}{" and press Enter" if d.get("enter") == "yes" else ""}'),
        "screen.press": lambda: f"press {d['keys']} in {_app(d)}",
        "screen.click": lambda: f'click "{d["target"]}" in {_app(d)}',
        "screen.read": lambda: f"read {_app(d)}'s window",
        "screen.read_text": lambda: f"read the words in {_app(d)}",
        "screen.numbers": lambda: f"number what you can click in {_app(d)}",
        "hands.mark_safe": lambda: f"put {d['app']} on the safe list",
        "hands.unmark_safe": lambda: f"take {d['app']} off the safe list",
        "hands.safe_list": lambda: "say which apps are safe",
        "screen.confirm": lambda: _careful(d) + " (needs your PIN)",
        "screen.agent_confirm": lambda: _careful(d) + (f" on {d['site']}" if d.get("site") else "") + " (asks you: is this correct?)",
        "screen.scroll": lambda: f"scroll {d['direction']} in {_app(d)}",
        "screen.choose": lambda: f'choose "{d["item"]}" in "{d["box"]}" in {_app(d)}',
        "screen.tick": lambda: f'{"tick" if d.get("on", "yes") == "yes" else "untick"} "{d["target"]}" in {_app(d)}',
        "screen.point": lambda: f"click the point {d['point']} in {_app(d)}",
        "screen.fill": lambda: f'fill your {d["detail"]} in "{d["box"]}"',
        "screen.saved_password": lambda: "pick the browser's saved login",
        "details.keep": lambda: f"keep your {d['key']} on this PC",
        "details.forget": lambda: f"forget your saved {d['key']}",
        "details.show": lambda: "show your saved details",
    }
    try:
        return lines[action]()
    except KeyError:
        return f"{action} " + ", ".join(f"{name}: {value}" for name, value in d.items())
