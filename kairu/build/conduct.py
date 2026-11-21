"""The task core's side of the Builder (BUILDER.md): the orders, and the order in which Guardian is asked.

    "build a website for Fresh Bakes, a bakery in Hyderabad"     build.draft, you see the files, "yes", build.write, files.open
    "make a web app: a tip calculator" / "make slides about ..."  the same; an app and slides open in the browser too
    "build a python app that converts temperatures"               the same, then build.test asks for "yes" and your PIN
    "test the build" / "test temperature-converter"              build.test again (High), for a Python program it made
    "learn to <order>", "forge a skill for <order>", "forge it"   forge.draft, Guardian decides each step's tier (a refused or
                                                                  Critical step: no skill), forge.test (five dry runs on a
                                                                  stand-in laptop), then forge.save with "yes" and your PIN
    "what skills have you learned", "forget the skill <name>"     the kept skills (read here), forge.forget (Medium)
    "try five ways to <task>[, done when <...>]"                  paths.draft, the rule checks, the five paths best first
    "run path 2", "run the best path"                             that one plan, shown and run like any plan

A kept skill is used from TaskCore.handle, after the built-in skills: kept_skill() fills its steps with your words and hands
them to the core's own _run_plan, which shows them and runs them only after your "yes" (and PIN for a High step).

This holds no authority, like the core: every step goes to Guardian; the confirmer and the cards are the core's own. The
Builder's orders work at Main Kairu's own PC only (source "pc"): a phone's or Main Kairu's order to a Clone never builds,
forges or picks a path there.
"""

import json
import re
import secrets
import time

from kairu.brain.store import BrainStore
from kairu.build import forge, make
from kairu.build.store import BuilderStore, exists
from kairu.guardian import Action, Refused, Verdict
from kairu.tasks import plan as planner
from kairu.tasks import skills as skill_list

DRAFT_SECONDS = 300  # the AI writing a whole build, or five plans and a judge
UNKNOWN_SECONDS = 600  # "forge it" means the last order Kairu couldn't do, if it was this recent
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

KAIRU = r"(?:kairu,? )?(?:please |can you |could you )?"
BUILD = re.compile(
    KAIRU + r"(?:build|make|create|design|code|generate|write)(?: me| us)? (?:a |an |the |some |my )?"
    r"(?:(?:simple|small|quick|nice|beautiful|cool|fun|modern|one[- ]page|single[- ]page|little|basic|working|new|short|tiny)\s+)*"
    r"(?P<what>web ?sites?|sites?|landing pages?|home ?pages?|web ?pages?|web ?apps?|apps?|games?|calculators?|"
    r"slide ?decks?|slides|presentations?|decks?|python (?:apps?|programs?|scripts?|tools?)|programs? with tests)"
    r"(?: (?:for|about|on|that|which|to|with|called|named|showing|where|of))?\s*[:,-]?\s*(?P<brief>\S.{2,1500})", re.I)
BUILD_NO_BRIEF = re.compile(KAIRU + r"(?:build|make|create|design) (?:me |us )?(?:a |an )?(?:new )?(?:web ?site|site|web app|app|"
                            r"slides|slide deck|presentation|python app|python program)", re.I)
TEST_BUILD = re.compile(KAIRU + r"(?:test|run the tests (?:of|for|in)|run tests (?:of|for|in)) (?:the |my |that |this )?"
                        r"(?P<folder>build|app|program|[a-z0-9][a-z0-9-]{1,40})(?: again)?", re.I)
FORGE = re.compile(KAIRU + r"(?:forge|learn|make|build|create|write)(?: me| yourself)? (?:a |the )?(?:new )?skill "
                   r"(?:for|to|that|so you can|which|so that you can)\s*[:,-]?\s*(?P<task>\S.{2,300})", re.I)
LEARN_TO = re.compile(KAIRU + r"(?:learn|teach yourself)(?: how)? to (?P<task>\S.{2,300})", re.I)
FORGE_IT = re.compile(KAIRU + r"(?:forge (?:it|that|one|a skill(?: for (?:it|that))?)|(?:learn|teach yourself)(?: how)?(?: to do)? "
                      r"(?:it|that))", re.I)
LIST_SKILLS = re.compile(KAIRU + r"(?:(?:what|which) (?:new )?skills (?:have you|did you) (?:forged?|learn(?:ed|t))|(?:list|show)(?: me)? "
                         r"(?:the |your )?(?:forged|learned|learnt|new) skills|what have you (?:forged|learn(?:ed|t)))", re.I)
FORGET_SKILL = re.compile(KAIRU + r"(?:forget|remove|delete|unlearn) (?:the |your )?(?:forged |learned )?skill (?:called |named )?"
                          r"[\"'“]?(?P<name>[^\"”]{3,40}?)[\"'”]?", re.I)
PATHS = re.compile(KAIRU + r"(?:try (?:it |this )?(?:five|5) (?:ways|paths)|five paths|5 paths|(?:use|run) five paths)"
                   r"(?: (?:to|for|on|at))?\s*[:,-]?\s*(?P<task>\S.{2,900}?)(?:[,.;]? done when (?P<done>\S.{2,200}))?", re.I)
PICK = re.compile(KAIRU + r"(?:run|pick|choose|take|go with|use|do) (?:the )?(?:path (?:number )?(?P<number>[1-5]|one|two|three|four|five)"
                  r"|(?P<best>best) path)", re.I)


def kind_of(what: str) -> str:
    what = what.lower()
    if "python" in what or "test" in what:
        return "tests"
    if re.search(r"slide|presentation|deck", what):
        return "slides"
    if re.search(r"site|page", what):
        return "site"
    return "app"


class Builder:
    def __init__(self, core):
        self.core = core
        self.unknown: tuple[str, float] | None = None  # the last order Kairu couldn't do, for "forge it"

    @property
    def store(self) -> BuilderStore:
        return BuilderStore(self.core.cfg.data_dir)

    def handle(self, text: str) -> str | None:
        """The Builder's answer to this order, or None when it isn't a Builder order."""
        orders = ((PICK, self._pick), (PATHS, self._paths), (LIST_SKILLS, self._list), (FORGET_SKILL, self._forget),
                  (FORGE_IT, self._forge_it), (FORGE, self._forge), (LEARN_TO, self._forge), (TEST_BUILD, self._test),
                  (BUILD, self._build), (BUILD_NO_BRIEF, self._no_brief))
        for pattern, answer in orders:
            found = pattern.fullmatch(text)
            if found is None:
                continue
            if pattern is TEST_BUILD and self._tests_build(found["folder"]) is None:
                return None  # not a Python program the Builder made: "run the tests in X" is PC5's, as before
            if self.core.source != "pc":
                return "The Builder works at Main Kairu's own PC."
            return answer(found)
        return None

    # --- talking to Guardian, through the core -------------------------------------------------------------

    def _draft(self, action: str, details: dict) -> tuple[object | None, str]:
        """Run a Low drafting action (the brain thinks); (its answer, "") or (None, what to tell you)."""
        self.core._tell({"kind": "thinking"})
        ask = secrets.token_hex(8)
        outcome = self.core._run(Action(action, {**details, "ask": ask, "source": self.core.source}), None, DRAFT_SECONDS)
        if outcome != "finished":
            from kairu.tasks.core import _ended
            return None, _ended("The Builder", outcome)
        answer = BrainStore(self.core.cfg.data_dir).take_answer(ask)
        if answer is None:
            return None, "Nothing came back; Guardian's log says why."
        if answer.status != "answered":
            return None, answer.text
        return answer, ask

    def _checked(self, steps, ask: bool = True) -> tuple[list, list[str], str]:
        """The rule checks: (the steps as they would run, each one's tier, why not, or ""). ask=False: only the steps as
        they would run, for the core's _run_plan, which asks Guardian about every step itself before anything runs."""
        from kairu.tasks.core import Step, _screen_checked, _searched_privately, _terminal_checked, handled
        usable = {skill.action for skill in self.core.skills}
        steps = handled(tuple(Step(action, details) for action, details in steps))
        steps = [_terminal_checked(_screen_checked(_searched_privately(step))) for step in steps]
        tiers, high = [], 0
        if not ask:
            return steps, tiers, ""
        for number, step in enumerate(steps, 1):
            if step.action not in usable:
                return steps, tiers, f"step {number} ({step.action}) isn't a skill Kairu may use now"
            refused = self.core.outside(step)
            if refused:
                return steps, tiers, f"step {number} ({step.action}): {refused}"
            decision = self.core.client.check(Action(step.action, {**step.details, "job": secrets.token_hex(8)}))
            if decision.verdict is Verdict.DENY:
                return steps, tiers, f"Guardian refused step {number} ({step.action}): {decision.reason.rstrip('.')}"
            tiers.append(decision.tier)
            high += decision.verdict is Verdict.NEEDS_APPROVAL
        if high > 1:
            return steps, tiers, f"it has {high} steps that need your PIN, and a plan may have only one"
        return steps, tiers, ""

    # --- Builder powers ----------------------------------------------------------------------------------------

    def _no_brief(self, found) -> str:
        return 'What is it for? Say it in one go, such as: build a website for Fresh Bakes, a bakery in Hyderabad.'

    def _build(self, found) -> str:
        from kairu.tasks.core import Step
        kind = kind_of(found["what"])
        answer, ask = self._draft("build.draft", {"brief": found.group(0), "kind": kind})
        if answer is None:
            return ask
        draft = self.store.draft(ask=ask)
        if draft is None:
            return "No build came back; Guardian's log says why."
        by = f" (written by {answer.provider})" if answer.provider else ""
        if not self.core.confirmer(f'{answer.text}{by}. Type "yes" to make it in your work folder.'):
            return "Not made: you didn't say yes. Nothing was written."
        done, said = self.core._run_step(Step("build.write", {"draft": float(draft["id"]), "sha": draft["sha256"]}))
        if not done:
            return said
        if kind == "tests":
            tested, result = self.core._run_step(Step("build.test", {"folder": draft["folder"]}))
            if not tested and result.startswith("Not done: you refused"):
                result = f'Not tested yet: it is code an AI wrote, so its tests run only with your PIN. Say "test {draft["folder"]}".'
            return f"{said} {result}"
        opened, shown = self.core._run_step(Step("files.open", {"name": f"{draft['folder']}/index.html"}))
        return f"{said} {shown}"

    def _tests_build(self, folder: str) -> dict | None:
        if folder.lower() in ("build", "app", "program"):
            return self.store.newest_build("tests")
        found = self.store.build(folder)
        return found if found and found["kind"] == "tests" else None

    def _test(self, found) -> str:
        from kairu.tasks.core import Step
        build = self._tests_build(found["folder"])
        return self.core._run_step(Step("build.test", {"folder": build["folder"]}))[1]

    # --- Forge ---------------------------------------------------------------------------------------------------

    def remember_unknown(self, order: str) -> None:
        self.unknown = (order, time.monotonic())

    def _forge_it(self, found) -> str:
        if self.unknown is None or time.monotonic() - self.unknown[1] > UNKNOWN_SECONDS:
            return "Which order should I learn? Say: learn to, then the order."
        return self._forge_task(self.unknown[0])

    def _forge(self, found) -> str:
        return self._forge_task(found["task"])

    def _forge_task(self, task: str) -> str:
        from kairu.tasks.core import Step
        answer, ask = self._draft("forge.draft", {"task": task.strip(" .")})
        if answer is None:
            return ask
        row = self.store.recipe(ask=ask)
        if row is None:
            return "No recipe came back; Guardian's log says why."
        try:
            recipe = forge.read(row["recipe"])
            steps, tiers, why_not = self._checked(forge.fill(recipe["steps"], recipe["examples"][0]))
        except forge.NoRecipe as why:
            return f"Forge couldn't make a skill for that ({why}). Nothing was kept."
        if why_not:
            return f"Forge dropped it: {why_not}. Nothing was kept."
        told = (f'Forge wrote "{recipe["name"]}" for "{recipe["says"][0]}": ' + "; ".join(
            f"{number}) {planner.describe(step['action'], step['details'])} ({tier})"
            for number, (step, tier) in enumerate(zip(recipe["steps"], tiers), 1)) + ".")
        tried, said = self.core._run_step(Step("forge.test", {"recipe": float(row["id"]), "sha": row["sha256"]}))
        if not tried:
            return f"{told} {said} So it wasn't kept."
        job = secrets.token_hex(8)
        details = {"recipe": float(row["id"]), "sha": row["sha256"]}
        decision = self.core.client.check(Action("forge.save", {**details, "job": job}))
        if decision.verdict is Verdict.DENY:
            return f"{told} {said} Guardian refused to keep it: {decision.reason.rstrip('.')}."
        granted = None
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            try:
                granted = self.core.plan_approver(decision, f"{told} {said} Keep this skill?")
            except Refused as refusal:
                return f"{told} {said} Not kept: {str(refusal).rstrip('.')}."
            if granted is None:
                return f"{told} {said} Not kept: you refused it."
        kept, saved = self.core._run_step(Step("forge.save", details), job, granted)
        return f"{told} {said} {saved}"

    def _list(self, found) -> str:
        kept = self.store.skills()
        if not kept:
            return "I haven't learned any new skills yet. Say: learn to, then an order I couldn't do."
        return f"Skills I learned ({len(kept)}): " + "; ".join(f'{recipe["name"]} ("{recipe["says"][0]}")' for recipe in kept) + "."

    def _forget(self, found) -> str:
        from kairu.tasks.core import Step
        return self.core._run_step(Step("forge.forget", {"name": found["name"].strip()}))[1]

    def kept_skill(self, text: str) -> str | None:
        """A kept skill's order: its steps with your words, shown and run like any plan. None if no kept skill answers it."""
        if skill_list.match(self.core.skills, text) is not None or not exists(self.core.cfg.data_dir):
            return None  # a built-in skill always comes first; no builder.db: nothing learned yet
        found = forge.matching(self.store.skills(), text)
        if found is None:
            return None
        recipe, values = found
        try:
            steps, _, _ = self._checked(forge.fill(recipe["steps"], values), ask=False)
        except forge.NoRecipe as why:
            return f'The skill "{recipe["name"]}" can\'t take those words ({why}). Nothing ran.'
        usable = {skill.action for skill in self.core.skills}
        if any(step.action not in usable for step in steps):
            return f'The skill "{recipe["name"]}" has a step Kairu may not use now. Nothing ran.'
        return f'Using the skill "{recipe["name"]}". ' + self.core._run_plan(tuple(steps))

    # --- Five Paths ----------------------------------------------------------------------------------------------

    def _paths(self, found) -> str:
        task, done = found["task"].strip(" .,;"), (found["done"] or "").strip(" .")
        answer, ask = self._draft("paths.draft", {"task": task, "done": done})
        if answer is None:
            return ask
        row = self.store.paths(ask=ask)
        if row is None:
            return "No paths came back; Guardian's log says why."
        ranked, lines, dropped, seen = [], [], [], {}
        for number, path in enumerate(row["paths"], 1):
            if not path["steps"]:
                dropped.append(f"{path['style']} ({path['why_not']})")
                continue
            same = json.dumps(path["steps"], sort_keys=True)
            if same in seen:  # the same plan again: shown once
                dropped.append(f"{path['style']} (the same steps as path {seen[same]})")
                continue
            seen[same] = number
            steps, tiers, why_not = self._checked(path["steps"])
            if why_not:
                dropped.append(f"{path['style']} ({why_not})")
                continue
            ranked.append(number)
            path["shown"] = "; ".join(f"{planner.describe(step.action, step.details)} ({tier})" for step, tier in zip(steps, tiers))
        ranked.sort(key=lambda number: (-row["paths"][number - 1]["score"], len(row["paths"][number - 1]["steps"])))
        self.store.rank(row["id"], ranked)
        if not ranked:
            return f"Five Paths: no path passed the rule checks. Dropped: {'; '.join(dropped)}. Nothing ran."
        lines.append(f"Five Paths for: {task}." + (f" Done when: {row['done']}." if row["done"] else ""))
        for place, number in enumerate(ranked, 1):
            path = row["paths"][number - 1]
            best = " BEST" if place == 1 else ""
            lines.append(f"Path {number}{best} ({path['style']}, {path['score']}/10): {path['why']} Steps: {path['shown']}.")
        if dropped:
            lines.append(f"Not shown: {'; '.join(dropped)}.")
        lines.append(f'Say "run path {ranked[0]}" for the best one, or another number. Only the one you pick runs.')
        return "\n".join(lines)

    def _pick(self, found) -> str:
        row = self.store.paths()
        if row is None:
            return "There are no Five Paths waiting (they last 30 minutes). Say: try five ways to, then the task."
        if found["best"]:
            if not row["ranked"]:
                return "No path passed the rule checks, so there is nothing to run."
            number = row["ranked"][0]
        else:
            number = WORDS.get(found["number"].lower()) or int(found["number"])
        if number not in row["ranked"]:
            return f"Path {number} didn't pass the rule checks, so it can't run. Pick one of {', '.join(map(str, row['ranked'])) or 'none'}."
        path = row["paths"][number - 1]
        try:
            steps = planner.parse(json.dumps({"steps": [{"action": action, "details": details}
                                                        for action, details in path["steps"]]}), planner.PLANNABLE)
        except planner.NoPlan as why:
            return f"Path {number} isn't a plan any more ({why}). Nothing ran."
        steps, _, _ = self._checked(steps, ask=False)
        return f"Path {number} ({path['style']}): " + self.core._run_plan(tuple(steps))
