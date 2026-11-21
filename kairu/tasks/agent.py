"""The screen agent (ADR-051 proposed, BAR.md "Kairu's eyes"): "take control and ..." - see, think, act, then see again.

    "take control and play lofi music on youtube"
      1. you see the goal, and that a picture of one window will go to Google Gemini; nothing runs until you type "yes"
      2. look   screen.look (Guardian, Medium): a picture of the app in front and its buttons' names go to Gemini, which
                proposes ONE next step (click, type, press, launch an app, visit a site, search, wait), or says done or
                stuck
      3. act    that step, read strictly here, goes to Guardian like a typed order: Low and Medium run, a step that may send,
                submit or delete asks for your "yes" and PIN (screen.confirm), money, security apps, Kairu's own windows and
                secrets are refused with no approval path
      4. look again, and so on: at most MOST_STEPS steps, MOST_SECONDS in all, until Gemini says done or stuck

ADR-054 (proposed, the owner's GO of 20 Nov 2026): inside a run, a careful step (Send, Submit, Sign in, Apply, I agree, an
app off the safe list, a point with nothing readable) is screen.agent_confirm: the card asks "Is this correct?" and your
"yes" (typed, clicked or said) is enough, with no PIN. Gemini may also scroll, choose from a list, tick a box, click a point,
fill one of your saved details by its NAME (screen.fill types the value on this PC; Gemini never sees it, and every later
picture paints those boxes black), pick the browser's saved login (screen.saved_password), or hand over to you ("Your
turn: solve the captcha"): then nothing is looked at until you say "go on", within the same 10 minutes. Once a detail is
filled, the run is locked to that site: if the page moves to another site, it stops. "Too many requests" from Gemini: one
short wait, then one more try. Each step shows how long its look took.

This code holds no authority, like the rest of the task core: it never runs anything itself and never fills the bar's "yes"
and PIN. A proposal can only be one of Kairu's own hand and app skills (never files, commands, installs or the safe list),
with exactly that skill's details, all short text; anything else ends the run. The run ends at once on a stop (Ctrl+Alt+K,
"Kairu, stop", Safe Mode), on any refusal by Guardian or the hands, when you refuse a card, after MOST_MISSES steps in a row
that didn't work, or when the same step comes back a third time. What a window or page says is data: only your goal is an
order, and Gemini is told so. Steps and Gemini's words are shown to you; Gemini's "done" is its word, said as its word.
"""

import json
import re
import time

from kairu.brain import privacy
from kairu.research import quarantine
from kairu.tasks import details as my_details, eyes, screen
from kairu.tasks.core import NOT_FOR_A_PLAN, Step, label, tidy

MOST_STEPS = 15
MOST_MISSES = 3  # steps in a row that didn't work (a button not found ...): then it stops
MOST_SECONDS = 600
SETTLE = 0.8  # seconds a window gets to show what the last step did, before the next look
LONGEST_GOAL = 300
LONGEST_SAY = 300
LONGEST_WHY = 120
SCREEN = r"(?:the |my |this )?(?:screen|pc|laptop|computer|desktop|system)"
TAKE_CONTROL = re.compile(
    rf"(?:take (?:control|over)(?: (?:of )?{SCREEN})?|(?:control|use|see|watch|look at) {SCREEN}|do it yourself|"
    rf"do it on (?:the |my )?screen)"
    r"(?:\s*,\s*(?:and then|and|then)\s+|\s*[,:;-]\s*|\s+(?:and then|and|to|then)\s+)(?P<goal>.{3,})", re.IGNORECASE)
TAKE_CONTROL_ALONE = re.compile(rf"take (?:control|over)(?: (?:of )?{SCREEN})?", re.IGNORECASE)
DESCRIBE = re.compile(
    r"(?:what do you see|what can you see|look at|describe|tell me what(?:'s| is) on)(?: on)? (?:the |my )?screen"
    r"(?: (?:in|of) (?P<app>[\w .+-]{2,30}))?|what do you see(?: in (?P<app2>[\w .+-]{2,30}))?"
    r"|(?P<wall>(?:what(?:'s|s| is)(?: there)? (?:on|in)|what do you see (?:on|in)|what can you see (?:on|in)|look at|describe|"
    r"tell me what(?:'s|s| is) (?:on|in)) (?:the |my )?(?:desktop )?(?:wallpaper|background(?: picture| image)?))"
    r"|(?P<whole>(?:what(?:'s|s| is)(?: there)? on|what do you see on|what can you see on|look at|describe|"
    r"tell me what(?:'s|s| is) on|see) (?:the |my )?(?:whole|full|entire|complete) (?:screen|display|desktop))",
    re.IGNORECASE)
# a step that did not work and ends the run at once: refused by Guardian, by the hands' own rules, or by you
ENDS_AT_ONCE = ("Refused", "Guardian refused", "Not done", "Not sent", "Stopped")
DOS = {"click", "type", "press", "launch", "visit", "search", "wait", "done", "stuck", "scroll", "choose", "tick", "point",
       "fill", "password", "handover"}
SAME = {"open_app": "launch", "open_site": "visit", "your_turn": "handover", "hand_over": "handover", "select": "choose"}
FIELDS = {"": "", "search": "search", "address": "address", "cursor": "", "none": ""}
LIMITS = {"target": 80, "text": screen.LONGEST_TEXT, "keys": 40, "name": 40, "url": 200, "query": 200, "list": 80,
          "item": 80, "box": 80, "detail": 30}
IN_A_WINDOW = ("click", "type", "press", "scroll", "choose", "tick", "point", "fill", "password")
GEMINI_BUSY = re.compile(r"free limit|too many requests|\b429\b|rate.?limit|quota", re.IGNORECASE)
BUSY_WAIT = 20  # seconds to wait once when Gemini says "too many requests", unless it says how long (at most MOST_BUSY_WAIT)
MOST_BUSY_WAIT = 60
OWNERS_TURN = re.compile(r"sign ?in|log ?in|captcha|verif|otp|code|password|upload|résumé|resume|robot|human", re.IGNORECASE)


class NoStep(Exception):
    """Gemini's answer isn't one step Kairu may take. Its text says why."""


def _text(next_: dict, key: str, most: int) -> str:
    value = next_.get(key)
    if not isinstance(value, str) or not value.strip() or "\n" in value.strip() or len(value) > most:
        raise NoStep(f"has no usable {key}")
    return " ".join(value.split())


def _said(value, most: int) -> str:
    """Gemini's own words, as data you may see: lines giving orders or holding a secret left out, short."""
    if not isinstance(value, str):
        return ""
    lines, _ = quarantine.safe_lines(value)
    said = " ".join(lines)
    return said if len(said) <= most else said[:most].rsplit(" ", 1)[0] + " …"


def proposal(text: str) -> tuple[str, str, dict]:
    """screen.look's reply: (the app the look saw, its name, Gemini's proposal). Read strictly: anything else is NoStep."""
    try:
        data = json.loads(text)
    except ValueError:
        raise NoStep("couldn't be read") from None
    if not isinstance(data, dict) or not isinstance(data.get("next"), dict) or not isinstance(data.get("app"), str) \
            or not isinstance(data.get("name"), str):
        raise NoStep("wasn't one step")
    return data["app"], data["name"], data["next"]


def allowed_site(now: str, first_site: str | None, goal: str) -> bool:
    """ADR-054 "right site only": your details are typed only on the site that was open when the run started, or one your
    goal names ("on Internshala", "github.com")."""
    if not now:
        return False
    if now == first_site:
        return True
    words = re.findall(r"[a-z0-9][a-z0-9.-]*", goal.lower())
    name = now.split(".")[0]
    return now in words or name in words or any(word.endswith("." + now) for word in words)


def site_seen(text: str) -> str:
    """The site a look's browser was on ("" when it wasn't a browser, or it couldn't tell): data, for the run's lock."""
    try:
        data = json.loads(text)
    except ValueError:
        return ""
    site = data.get("site") if isinstance(data, dict) else None
    return my_details.site_of(site) if isinstance(site, str) else ""


def next_step(next_: dict, app: str) -> tuple[str, Step | None, str]:
    """One proposal as ("step", the Step, why) or ("done" / "stuck", None, what Gemini says). app: the program the look saw
    ("" when it saw no window): every click, typing and key goes to that app, whatever the proposal says."""
    do = next_.get("do")
    do = SAME.get(do, do) if isinstance(do, str) else do
    if do not in DOS:
        raise NoStep("isn't a step Kairu takes")
    if do in ("done", "stuck"):
        return do, None, _said(next_.get("say"), LONGEST_SAY) or ("Done." if do == "done" else "I can't go on by myself.")
    if do == "handover":
        return do, None, _said(next_.get("say"), LONGEST_SAY) or "Please do the next part yourself."
    why = _said(next_.get("why"), LONGEST_WHY)
    if do in IN_A_WINDOW and not app:
        raise NoStep("wants to click or type before any window is seen")
    if do == "scroll":
        direction, times = next_.get("direction", "down"), next_.get("times", 3)
        if direction not in ("up", "down") or type(times) is not int or not 1 <= times <= screen.MOST_NOTCHES:
            raise NoStep("scrolls a way Kairu doesn't (up or down, 1 to 10 notches)")
        return "step", Step("screen.scroll", {"app": app, "direction": direction, "times": str(times)}), why
    if do == "choose":
        return "step", Step("screen.choose", {"app": app, "box": _text(next_, "list", LIMITS["list"]),
                                              "item": _text(next_, "item", LIMITS["item"])}), why
    if do == "tick":
        on = next_.get("on", True)
        if on not in (True, False):
            raise NoStep("ticks a way Kairu doesn't (on true or false)")
        return "step", Step("screen.tick", {"app": app, "target": _text(next_, "target", LIMITS["target"]),
                                            "on": "yes" if on else "no"}), why
    if do == "point":
        x, y = next_.get("x"), next_.get("y")
        if type(x) is not int or type(y) is not int or not (0 <= x <= 20000 and 0 <= y <= 20000):
            raise NoStep("names a point Kairu doesn't take (two whole numbers on the picture)")
        return "step", Step("screen.point", {"app": app, "point": f"{x},{y}"}), why
    if do == "fill":
        key = my_details.key_of(_text(next_, "detail", LIMITS["detail"]))
        if key is None:
            raise NoStep("asks for a detail Kairu doesn't keep")
        return "step", Step("screen.fill", {"app": app, "box": _text(next_, "box", LIMITS["box"]), "detail": key,
                                            "site": ""}), why
    if do == "password":
        return "step", Step("screen.saved_password", {"app": app, "site": ""}), why
    if do == "click":
        return "step", Step("screen.click", {"app": app, "target": _text(next_, "target", LIMITS["target"])}), why
    if do == "type":
        field = next_.get("field", "")
        field = FIELDS.get(field.strip().lower() if isinstance(field, str) else None)
        enter = next_.get("enter", False)
        if field is None or enter not in (True, False, "yes", "no"):
            raise NoStep("has a field or Enter Kairu doesn't know")
        return "step", Step("screen.type", {"app": app, "text": _text(next_, "text", LIMITS["text"]), "field": field,
                                            "enter": "yes" if enter in (True, "yes") else "no"}), why
    if do == "press":
        return "step", Step("screen.press", {"app": app, "keys": _text(next_, "keys", LIMITS["keys"])}), why
    if do == "launch":
        name = _text(next_, "name", LIMITS["name"])
        if NOT_FOR_A_PLAN.search(name):
            raise NoStep("names an app with a path or a command in it")
        return "step", Step("apps.open", {"name": name}), why
    if do == "visit":
        return "step", Step("web.open", {"url": _text(next_, "url", LIMITS["url"])}), why
    if do == "search":
        return "step", Step("web.search", {"query": _text(next_, "query", LIMITS["query"])}), why
    seconds = next_.get("seconds")
    if type(seconds) not in (int, float) or not 1 <= seconds <= 10:
        raise NoStep("waits a time Kairu doesn't take (1 to 10 seconds)")
    return "step", Step("task.wait", {"seconds": str(int(seconds))}), why


def app_after(step: Step, app: str) -> str:
    """The app the next look is at: the one a step just opened, else the same one."""
    if step.action == "apps.open":
        return screen.program_of(step.details["name"])
    if step.action in ("web.open", "web.search"):
        return screen.BROWSER
    return app


class ScreenAgent:
    """One per task core. handle(text) -> the answer, or None when the order isn't for the screen agent."""

    def __init__(self, core):
        self.core = core

    def handle(self, text: str) -> str | None:
        text = tidy(text)
        described = DESCRIBE.fullmatch(text)
        if described:
            if described.group("wall"):
                return self.describe(eyes.WALLPAPER)
            if described.group("whole"):
                return self.describe(eyes.SCREEN)
            return self.describe((described.group("app") or described.group("app2") or "").strip())
        if TAKE_CONTROL_ALONE.fullmatch(text):
            return 'Tell me what to do, such as: take control and play lofi music on YouTube.'
        taken = TAKE_CONTROL.fullmatch(text)
        return self.take_control(taken.group("goal")) if taken else None

    # --- "what do you see on my screen" --------------------------------------------------------------------------

    def describe(self, app: str) -> str:
        if self.core.source != "pc":
            return "I look at the screen only for orders given at this PC."
        self.core._tell({"kind": "thinking"})
        _, text = self.core._run_step(Step("screen.look", {"app": app, "goal": eyes.DESCRIBE_GOAL, "history": "",
                                                           "mode": "describe"}))
        return text

    # --- "take control and ..." ---------------------------------------------------------------------------------------

    def take_control(self, goal: str) -> str:
        core = self.core
        goal = " ".join(goal.split()).strip(" .")
        if core.source != "pc":
            return "I take control of the screen only for orders given at this PC."
        if not 3 <= len(goal) <= LONGEST_GOAL:
            return f"Say what to do in 3 to {LONGEST_GOAL} characters."
        verdict = privacy.classify(goal)
        if verdict.secret:
            return f"Refused: your goal has {verdict.why()}. Secrets never leave this PC, not even with your approval."
        if verdict.personal:
            return (f"I didn't start: your goal has personal words ({verdict.why()}), and Kairu's eyes think with Gemini. "
                    "Say it without them.")
        question = (f"Take control to: {goal}? I'll look at the app in front (a picture of that one window goes to Google "
                    f"Gemini), then click, type or press one step at a time, at most {MOST_STEPS} steps. Before a step that "
                    "may send, submit, sign in or agree I ask you \"Is this correct?\" (yes, no PIN). Your saved details "
                    "are typed only here, never sent to Gemini, and those boxes are painted black in its pictures. "
                    '"Kairu, stop" or Ctrl+Alt+K ends it. Type "yes" to start.')
        if not core.confirmer(question):
            return "Not done: you didn't say yes. Nothing ran."
        if core._stopped():
            return "Stopped: it didn't start."
        kept, why = core._run_step(Step("task.plan", {"plan": json.dumps({"agent": goal, "steps": []}, sort_keys=True),
                                                      "approved": "yes", "request": "", "source": core.source}))
        if not kept:
            return f"Not done: the goal could not be kept in Guardian's log ({why.rstrip('.')}), so nothing ran."
        recent = core.working_in if core.working_in and time.monotonic() - core.working_in[1] < 300 else None
        return self._loop(goal, recent[0] if recent else "")

    def _look(self, app: str, goal: str, record: list[str], hide: list[str] | None = None) -> tuple[bool, str, float]:
        self.core._tell({"kind": "thinking"})
        began = time.monotonic()
        looked, seen = self.core._run_step(Step("screen.look", {
            "app": app, "goal": goal, "history": "\n".join(record[-12:]), "mode": "next",
            "hide": json.dumps(hide, ensure_ascii=False) if hide else ""}))
        return looked, seen, time.monotonic() - began

    def _busy_wait(self) -> int:
        """How long to wait once for Gemini's per-minute limit: what it asked (brain.db), else BUSY_WAIT; at most MOST_BUSY_WAIT."""
        try:
            from kairu.brain.store import BrainStore
            limit = BrainStore(self.core.cfg.data_dir).limit("gemini")
            if limit and limit.until > time.time():
                return max(3, min(MOST_BUSY_WAIT, int(limit.until - time.time()) + 1))
        except Exception:
            pass
        return BUSY_WAIT

    def _sleep(self, seconds: float) -> bool:
        """Wait, a little at a time; False if a stop came meanwhile."""
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if self.core._stopped():
                return False
            time.sleep(min(1.0, max(0.0, until - time.monotonic())))
        return True

    def _hand_over(self, said: str, started: float) -> bool:
        """Your turn (ADR-054): Kairu says what you must do and waits, taking no picture and sending nothing, until you say
        "go on" (or press the bar's Go on), within the run's 10 minutes. False: the run ends here."""
        core = self.core
        left = MOST_SECONDS - (time.monotonic() - started)
        handover = getattr(core, "handover", None)
        if handover is None or left < 5:
            return False
        core._tell({"kind": "handover", "text": said})
        try:
            going_on = bool(handover(said, left))
        except Exception:
            going_on = False
        return going_on and not core._stopped()

    def _loop(self, goal: str, app: str) -> str:
        core = self.core
        core.in_control = True  # careful steps are screen.agent_confirm while the run lasts (ADR-054)
        core._tell({"kind": "control", "on": True})  # the bar steps aside, so you see the screen; the pill shows the step
        try:
            return self._run(goal, app)
        finally:
            core.in_control = False
            core.careful_extra = {}
            core._tell({"kind": "control", "on": False})

    def _run(self, goal: str, app: str) -> str:
        core, record, done_steps, labels, shown_steps = self.core, [], 0, [], []
        misses, last, again = 0, None, 0
        site, filled, times = "", [], []  # the site the run is locked to once a detail is filled; (box, detail); look seconds
        first_site = None  # the site open in front at the run's first look (ADR-054: your details go only there, or to one
        # you named in the goal)
        started = time.monotonic()
        self.times = times
        for turn in range(MOST_STEPS + 1):
            if turn and core._stopped():
                return self._end("Stopped.", done_steps, labels)
            if time.monotonic() - started > MOST_SECONDS:
                return self._end(f"I stopped: {MOST_SECONDS // 60} minutes went by and the goal isn't done yet.", done_steps, labels)
            hide = [box for box, _ in filled]
            looked, seen, took = self._look(app, goal, record, hide)
            if not looked and turn == 0 and seen.startswith(eyes.CANT_SEE):  # the app in front can't be looked at: start blind
                core._tell({"kind": "step", "number": 0, "state": "not done", "text": seen})
                app = eyes.NO_WINDOW
                looked, seen, took = self._look(app, goal, record)
            if not looked and GEMINI_BUSY.search(seen):  # Gemini's per-minute limit: one short wait, then one more try
                wait = self._busy_wait()
                core._tell({"kind": "step", "number": len(labels) + 1, "state": "waiting",
                            "text": f"Gemini is busy (too many requests); waiting {wait} seconds."})
                if not self._sleep(wait):
                    return self._end("Stopped.", done_steps, labels)
                looked, seen, took = self._look(app, goal, record, hide)
                if not looked and GEMINI_BUSY.search(seen):
                    return self._end(f"I stopped: Gemini is still busy after a {wait}-second wait (its free limit). "
                                     f"Try again in a minute. ({seen})", done_steps, labels)
            if not looked:
                return self._end(f"I stopped: {seen}", done_steps, labels)
            times.append(took)
            try:
                seen_app, _, wanted = proposal(seen)
                kind, step, said = next_step(wanted, seen_app)
            except NoStep as problem:
                return self._end(f"I stopped: Gemini's answer {problem}.", done_steps, labels)
            now = site_seen(seen)
            if first_site is None:
                first_site = now
            if site and now and now != site:
                return self._end(f"I stopped: the page moved to {now}, not {site}, where I was filling your details. "
                                 "Nothing more was typed.", done_steps, labels)
            if kind == "done":
                return self._end(f"Done (Gemini's word, from the screen): {said}", done_steps, labels)
            if kind == "stuck" and not OWNERS_TURN.search(said):
                return self._end(f"I need you: {said}", done_steps, labels)
            if kind in ("stuck", "handover"):
                if not self._hand_over(f"Your turn: {said}", started):
                    return self._end(f"I need you: {said}", done_steps, labels)
                record.append(f"{len(record) + 1}. the owner's turn ({said}): the owner said go on")
                app = seen_app or app
                continue
            if turn == MOST_STEPS:
                return self._end(f"I used all {MOST_STEPS} steps and the goal isn't done yet.", done_steps, labels)
            if step.action in ("screen.fill", "screen.saved_password"):
                if not site and not allowed_site(now, first_site, goal):
                    return self._end(f"I stopped: I type your details only on the site you named or the one open when you "
                                     f"started, and this page is on {now or 'a site I cannot tell'}. Name the site in your "
                                     "order, or open it first.", done_steps, labels)
                if step.action == "screen.fill" and not site:
                    site = now  # the first detail typed locks the run to this site
                step = Step(step.action, {**step.details, "site": site or now})
            core.careful_extra = {"site": site, "filled": "; ".join(f"{box}: {detail}" for box, detail in filled)[:400]}
            same = (step.action, json.dumps(step.details, sort_keys=True))
            again = again + 1 if same == last else 0
            last = same
            if again >= 2:
                return self._end("I stopped: I was taking the same step again and again.", done_steps, labels)
            shown = label(step)
            shown_steps.append({"action": step.action, "label": shown + (f" ({said})" if said else ""), "files": []})
            core._tell({"kind": "steps", "steps": list(shown_steps)})
            core._tell({"kind": "step", "number": len(labels) + 1, "state": "running", "text": f"look {took:.1f} s"})
            ok, text = core._run_step(step)
            core._tell({"kind": "step", "number": len(labels) + 1, "state": "done" if ok else "not done", "text": text})
            labels.append(shown)
            record.append(f"{len(record) + 1}. {shown}: {'done' if ok else 'not done'} - {' '.join(text.split())[:200]}")
            if ok:
                done_steps, misses = done_steps + 1, 0
                app = app_after(step, seen_app or app)
                if step.action == "screen.fill":
                    filled.append((step.details["box"], step.details["detail"]))
                elif filled and text.startswith("Clicked") and screen.click_tier(text) == "high":
                    filled = []  # the form was sent (Submit, Sign in ...): those boxes are gone
            elif text.startswith(screen.YOUR_TURN):  # a skill says only you can do this part (a password, a missing detail)
                if not self._hand_over(text, started):
                    return self._end(f"I need you: {text[len(screen.YOUR_TURN):]}", done_steps, labels)
                record[-1] = f"{len(record)}. {shown}: the owner did it ({text[len(screen.YOUR_TURN):][:150]})"
                app = seen_app or app
            else:
                if text.startswith(ENDS_AT_ONCE):
                    return self._end(text, done_steps, labels)
                misses += 1
                if misses >= MOST_MISSES:
                    return self._end(f"I stopped: {MOST_MISSES} steps in a row didn't work (the last: {text})", done_steps,
                                     labels)
                app = seen_app or app
            time.sleep(SETTLE)
        return self._end(f"I used all {MOST_STEPS} steps and the goal isn't done yet.", done_steps, labels)

    def _end(self, text: str, done_steps: int, labels: list[str]) -> str:
        if not labels:
            return text
        shown = "; ".join(labels[-6:])
        more = f"{len(labels) - 6} more, then " if len(labels) > 6 else ""
        times = getattr(self, "times", [])
        took = f" Looks took {sum(times) / len(times):.1f} s on average." if times else ""
        return f"{text} ({done_steps} of {len(labels)} step{'s' if len(labels) != 1 else ''} done: {more}{shown}.){took}"


def taken(text: str) -> bool:
    """For the tests and the bar: is this an order for the screen agent?"""
    text = tidy(text)
    return bool(TAKE_CONTROL.fullmatch(text) or TAKE_CONTROL_ALONE.fullmatch(text) or DESCRIBE.fullmatch(text))

