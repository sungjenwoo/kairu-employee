"""Forge (BUILDER.md "Forge"): when no skill fits an order, Kairu writes one, tries it, and keeps it only with your PIN.

    forge.draft  (Low)   the free cloud AI writes a RECIPE: a name, the orders it answers ("make a study folder for {subject}"),
                         up to 3 slots, at most MOST_STEPS steps that are Kairu's KNOWN skills (the same ones a plan may use,
                         without commands), and five examples to try it with. Read strictly here, kept as a draft.
    forge.test   (Low)   five dry runs, one per example, on a stand-in laptop: a pretend PC in a folder of its own
                         (kairu/tasks/pc.py StandIn), with its own empty work folder and data folder. The real skills' code runs
                         against it, so nothing on this PC is opened, typed into, moved or deleted. The stand-in has every
                         app and button a recipe names: a dry run proves the recipe's steps are whole and keep the rules, not
                         that a real window has that button.
    forge.save   (High)  keep the recipe, with "yes" and your PIN, only after all five dry runs passed.
    forge.forget (Medium) delete a kept skill.

Before the dry runs, the task core asks Guardian about every step of the recipe (kairu/build/conduct.py): a step Guardian
refuses (Critical, or not in policy.yaml) means there is no skill, and so does a recipe with more than one High step.

A kept skill is a known order from then on, and still nothing more: when you say it, its steps are filled in with your words,
read strictly again (kairu/tasks/plan.py), shown to you, and run only after your "yes"; Guardian decides every step by
policy.yaml, so a recipe can never raise a tier. Built-in skills always come first: a recipe whose order a built-in skill
already answers is no recipe.
"""

import json
import os
import re
import secrets
import shutil
import tempfile
from importlib import import_module
from pathlib import Path

from kairu import executors
from kairu.build.store import MOST_SKILLS, BuilderStore, digest
from kairu.tasks import pc
from kairu.tasks import plan as planner
from kairu.tasks import skills as skill_list
from kairu.tasks.actions import Refusal, _guarded
from kairu.tasks.store import TaskStore

RUNS = 5
MOST_STEPS = planner.MOST_STEPS
MOST_SLOTS = 3
MOST_SAYS = 4
FORGEABLE = tuple(action for action in planner.PLANNABLE if action != "terminal.run")  # a command is never in a recipe
SKILL_NAME = re.compile(r"[a-z0-9][a-z0-9 '-]{2,39}")
SLOT = re.compile(r"[a-z]{1,12}")
PLACE = re.compile(r"\{([^{}]*)\}")
SAY_WORDS = re.compile(r"[A-Za-z0-9 ,'-]+")
LONGEST_VALUE = 60
STAND_IN_APPS = ("notepad", "chrome", "msedge", "firefox", "explorer", "calc", "mspaint", "winword", "excel", "powerpnt",
                 "spotify", "vlc", "outlook", "teams")


class NoRecipe(Exception):
    """The AI's answer (or a kept recipe) is not a recipe Kairu keeps. Its text says why, shortly."""


def instructions() -> str:
    return (
        "You are Forge, the part of Kairu that teaches Kairu a new skill for an order it does not know yet. Write a RECIPE "
        "that does the order with ONLY the skills below, so the same order with other words in it works next time.\n"
        "Reply with JSON only, no other words:\n"
        '{"name": "<2 to 6 words>", "says": ["<an order this skill answers, with {slot} where words change>", ...], '
        '"slots": {"<slot>": "<what goes there>"}, '
        '"steps": [{"action": "<skill>", "details": {"<name>": "<text, may hold {slot}>"}}], '
        '"examples": [{"<slot>": "<a sample value>"}, ... exactly 5]}\n'
        "- Use as few slots as the order needs (often one), every slot in at least one step, and write says as a person "
        "would say them (\"make a study folder for {subject}\", not \"make a {folder} folder for {subject}\"). Make the "
        "steps do the whole order well (a note file with useful words, not an empty one).\n"
        "- A folder: files.write cannot make one, but files.move of a file into a new folder's name makes it. So write the "
        "real file first, move it into the folder, and end with files.open of the folder's name, which opens the folder in "
        "File Explorer so the person sees it. Never make an empty placeholder file.\n"
        f"- At most {MOST_SLOTS} slots (lower-case letters only), at most {MOST_SAYS} says (each uses every slot once), at "
        f"most {MOST_STEPS} steps, exactly {RUNS} examples with a short value for every slot.\n"
        "- Use only these skills and exactly their detail names. File and folder names are inside the work folder.\n"
        "- Never a sign-in, payment, purchase, install or command.\n"
        "Skills:\n" + planner.catalogue(FORGEABLE))


def _json(text: str) -> dict:
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", body, re.DOTALL)
    if fenced:
        body = fenced.group(1)
    try:
        data = json.loads(body, strict=False)
    except ValueError:
        raise NoRecipe("the AI's answer wasn't a recipe") from None
    if not isinstance(data, dict):
        raise NoRecipe("the AI's answer wasn't a recipe")
    return data


def _value_problem(value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > LONGEST_VALUE:
        return f"a value is 1 to {LONGEST_VALUE} characters"
    if re.search(r"[\x00-\x1f{}]", value):
        return "a value has no braces or control characters"
    return ""


def fill(steps: list[dict], values: dict) -> list[tuple[str, dict]]:
    """The recipe's steps with these words in their slots, read as strictly as any plan (NoRecipe if not a plan)."""
    filled = []
    for step in steps:
        details = {name: PLACE.sub(lambda found: values.get(found.group(1), found.group(0)), text)
                   for name, text in step["details"].items()}
        filled.append({"action": step["action"], "details": details})
    try:
        plan = planner.parse(json.dumps({"steps": filled}), FORGEABLE)
    except planner.NoPlan as why:
        raise NoRecipe(str(why)) from None
    if len(plan) != len(steps):  # a note that became a file and its opening: never in a recipe
        raise NoRecipe("a step typed a list or a note; a recipe writes it as a file instead")
    return plan


def say_pattern(said: str, slots) -> re.Pattern:
    parts, at = [], 0
    for found in PLACE.finditer(said):
        parts.append(re.escape(said[at:found.start()]))
        parts.append(f"(?P<{found.group(1)}>[^\\n]{{1,{LONGEST_VALUE}}}?)")
        at = found.end()
    parts.append(re.escape(said[at:]))
    return re.compile("".join(parts).replace(" ", " +"), re.IGNORECASE)


def read(data: dict) -> dict:
    """A recipe, read strictly: from the AI's answer at forge.draft, and again every time it is tried, kept or used."""
    if set(data) != {"name", "says", "slots", "steps", "examples"}:
        raise NoRecipe("the recipe didn't have exactly a name, says, slots, steps and examples")
    name = data["name"].strip().lower() if isinstance(data["name"], str) else ""
    if not SKILL_NAME.fullmatch(name):
        raise NoRecipe("the skill's name isn't 3 to 40 plain letters")
    slots = data["slots"]
    if not isinstance(slots, dict) or len(slots) > MOST_SLOTS or not all(
            isinstance(slot, str) and SLOT.fullmatch(slot) and isinstance(what, str) and 0 < len(what) <= LONGEST_VALUE
            for slot, what in slots.items()):
        raise NoRecipe(f"a recipe has at most {MOST_SLOTS} slots, each a short lower-case name")
    says = data["says"]
    if not isinstance(says, list) or not 1 <= len(says) <= MOST_SAYS:
        raise NoRecipe(f"a recipe answers 1 to {MOST_SAYS} orders")
    for said in says:
        if not isinstance(said, str) or not 5 <= len(said) <= 120 or len(said.split()) < 2:
            raise NoRecipe("an order the recipe answers is 2 or more words, at most 120 characters")
        used = PLACE.findall(said)
        if sorted(used) != sorted(slots) or not SAY_WORDS.fullmatch(PLACE.sub("x", said)):
            raise NoRecipe("an order the recipe answers must use every slot once, and plain words")
    steps = data["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MOST_STEPS:
        raise NoRecipe(f"a recipe has 1 to {MOST_STEPS} steps")
    for step in steps:
        if (not isinstance(step, dict) or set(step) != {"action", "details"} or step["action"] not in FORGEABLE
                or not isinstance(step["details"], dict)):
            raise NoRecipe("a step isn't one of the skills a recipe may use, with its details")
        for text in step["details"].values():
            if not isinstance(text, str) or any(slot not in slots for slot in PLACE.findall(text)):
                raise NoRecipe("a step's detail names a slot the recipe doesn't have")
    examples = data["examples"]
    if not isinstance(examples, list) or len(examples) != RUNS:
        raise NoRecipe(f"a recipe has exactly {RUNS} examples to try it with")
    for example in examples:
        if not isinstance(example, dict) or set(example) != set(slots):
            raise NoRecipe("every example gives a value for every slot")
        for value in example.values():
            problem = _value_problem(value)
            if problem:
                raise NoRecipe(problem)
    recipe = {"name": name, "says": [" ".join(said.split()) for said in says], "slots": dict(slots),
              "steps": [{"action": step["action"], "details": dict(step["details"])} for step in steps],
              "examples": [dict(example) for example in examples]}
    for example in recipe["examples"]:
        fill(recipe["steps"], example)
        for said in recipe["says"]:
            order = PLACE.sub(lambda found: example[found.group(1)], said)
            if skill_list.match(skill_list.SKILLS, order) is not None:
                raise NoRecipe(f'Kairu already knows "{order}" as a built-in skill')
    used = {slot for step in recipe["steps"] for text in step["details"].values() for slot in PLACE.findall(text)}
    if set(recipe["slots"]) - used:
        raise NoRecipe(f"the slot {sorted(set(recipe['slots']) - used)[0]} isn't used by any step")
    return recipe


def parse(text: str) -> dict:
    return read(_json(text))


def matching(recipes: list[dict], order: str) -> tuple[dict, dict] | None:
    """(the kept recipe whose order this is, the words in its slots), or None."""
    for recipe in recipes:
        for said in recipe["says"]:
            found = say_pattern(said, recipe["slots"]).fullmatch(order.strip(" .!?"))
            if found:
                values = {slot: " ".join(value.split()) for slot, value in found.groupdict().items()}
                if all(not _value_problem(value) for value in values.values()):
                    return recipe, values
    return None


def describe(recipe: dict) -> str:
    steps = "; ".join(f"{number}) {planner.describe(step['action'], step['details'])}"
                      for number, step in enumerate(recipe["steps"], 1))
    return f'"{recipe["name"]}", for "{recipe["says"][0]}": {steps}'


# --- forge.draft ---------------------------------------------------------------------------------------------

def draft(data_dir: str, task: str, ask: str, source: str, brain: dict | None = None) -> None:
    from kairu.brain.ask import _check, _keep
    from kairu.brain.gateway import ANSWERED, NOT_SENT, Gateway, Result
    _check(ask, source)
    result = Gateway(data_dir, brain).build(task, source, instructions(), longest=8000, tokens=3000, lead="Order to learn")
    if result.status != ANSWERED:
        return _keep(data_dir, ask, source, result)
    try:
        recipe = parse(result.text)
    except NoRecipe as why:
        return _keep(data_dir, ask, source, Result(NOT_SENT, "L3", f"Forge couldn't make a skill for that ({why}).",
                                                   result.provider))
    BuilderStore(data_dir).add_recipe(ask, recipe)
    _keep(data_dir, ask, source, Result(ANSWERED, "L3", describe(recipe), result.provider, seconds=result.seconds))


# --- forge.test: five dry runs on a stand-in laptop ----------------------------------------------------------

SAMPLE_FILES = ("notes.txt", "report.pdf", "photo.png", "song.mp3", "plan.md", "data.csv")


def _desk(folder: Path) -> None:
    apps = {name: f"C:/stand-in/{name}.exe" for name in STAND_IN_APPS}
    (folder / "pc.json").write_text(json.dumps({
        "windows": [{"app": name, "title": f"{name} (stand-in)"} for name in ("notepad", "chrome", "explorer")],
        "apps": apps, "browsers": {"chrome": apps["chrome"], "msedge": apps["msedge"]}, "volume": 50, "brightness": 70,
        "controls": {}}), encoding="utf-8")


def _program(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower()) or "app"


def _show(desk: pc.StandIn, action: str, details: dict) -> None:
    """The stand-in has every app and button a recipe names: put it there before the step, in front."""
    state = desk.state()
    windows, apps, controls = state.get("windows", []), state.get("apps", {}), state.get("controls", {})
    app = (details.get("app") or details.get("name") or "") if action.startswith(("screen.", "apps.")) else ""
    if app and app.lower() not in ("browser", "the browser"):
        program = _program(app)
        apps.setdefault(app.lower(), f"C:/stand-in/{program}.exe")
        windows = [item for item in windows if item["app"] != program]
        windows.insert(0, {"app": program, "title": f"{app} (stand-in)"})
        if action == "screen.click":
            controls[program] = [*controls.get(program, []), ["button", details.get("target", "")]]
        if action == "screen.type" and details.get("field"):
            controls[program] = [*controls.get(program, []), ["box", "Search"]]
    desk.path.write_text(json.dumps({**state, "windows": windows, "apps": apps, "controls": controls}), encoding="utf-8")


def dry_run(recipe: dict, values: dict, room: Path) -> tuple[bool, str]:
    """One run of the recipe on a fresh stand-in laptop in `room`: (all steps done, what happened)."""
    if os.environ.get(pc.TEST_PC) != str(room / "pc") or not isinstance(pc.backend(), pc.StandIn):
        return False, "the stand-in laptop wasn't ready, so nothing was tried"
    for folder in ("work", "data"):
        shutil.rmtree(room / folder, ignore_errors=True)
        (room / folder).mkdir()
    shutil.rmtree(room / "pc", ignore_errors=True)
    (room / "pc").mkdir()
    _desk(room / "pc")
    for name in SAMPLE_FILES:
        (room / "work" / name).write_text(f"stand-in {name}\n", encoding="utf-8")
    try:
        steps = fill(recipe["steps"], values)
    except NoRecipe as why:
        return False, f"its steps weren't a plan with these words ({why})"
    supplied = {"data_dir": str(room / "data"), "work_folder": str(room / "work")}
    for number, (action, details) in enumerate(steps, 1):
        if action == "task.wait":
            continue  # a wait is only time: the stand-in doesn't wait
        executor = executors.EXECUTORS.get(action)
        if executor is None or set(executor.supplied) - set(supplied):
            return False, f"step {number} ({action}) can't be tried on the stand-in"
        _show(pc.StandIn(room / "pc"), action, details)
        module, function = executor.target.split(":")
        job = secrets.token_hex(8)
        try:
            getattr(import_module(module), function)(**details, job=job, **{name: supplied[name] for name in executor.supplied})
        except SystemExit:
            pass
        except Exception as error:  # the skill's own code broke: a failed run, said shortly
            return False, f"step {number} ({action}) broke ({type(error).__name__})"
        reply = TaskStore(supplied["data_dir"]).take_reply(job)
        if reply is None or not reply.ok:
            said = (reply.text if reply else "no answer").replace("\n", " ")[:120]
            return False, f"step {number} ({action}): {said}"
    return True, "every step done"


def test(data_dir: str, job: str, recipe: float, sha: str) -> None:
    def work(_) -> str:
        store = BuilderStore(data_dir)
        found = store.recipe(int(recipe))
        if found is None or found["sha256"] != sha or digest(found["recipe"]) != sha:
            raise Refusal("Not tried: that recipe is gone or isn't the one you were shown.")
        try:
            checked = read(found["recipe"])
        except NoRecipe as why:
            raise Refusal(f"Not tried: {why}.") from None
        passed, notes = 0, []
        was = os.environ.get(pc.TEST_PC)
        with tempfile.TemporaryDirectory(prefix="kairu-stand-in-") as room:
            room = Path(room)
            os.environ[pc.TEST_PC] = str(room / "pc")  # this program only: every skill below sees the stand-in laptop
            try:
                (room / "pc").mkdir()
                for number, values in enumerate(checked["examples"], 1):
                    ok, said = dry_run(checked, values, room)
                    passed += ok
                    if not ok:
                        notes.append(f"run {number}: {said}")
            finally:
                if was is None:
                    os.environ.pop(pc.TEST_PC, None)
                else:
                    os.environ[pc.TEST_PC] = was
        store.tried(found["id"], passed, "; ".join(notes))
        text = f"Dry runs on a stand-in laptop: {passed} of {RUNS} passed."
        if passed != RUNS:
            raise Refusal(f"{text} {'; '.join(notes[:2])}.")
        return text
    return _guarded(data_dir, job, work)


# --- forge.save and forge.forget -----------------------------------------------------------------------------

def save(data_dir: str, job: str, recipe: float, sha: str) -> None:
    def work(_) -> str:
        store = BuilderStore(data_dir)
        found = store.recipe(int(recipe))
        if found is None or found["sha256"] != sha or digest(found["recipe"]) != sha:
            raise Refusal("Not kept: that recipe is gone or isn't the one you were shown.")
        if found["passed"] != RUNS:
            raise Refusal(f"Not kept: a skill is kept only after all {RUNS} dry runs pass.")
        try:
            checked = read(found["recipe"])
        except NoRecipe as why:
            raise Refusal(f"Not kept: {why}.") from None
        names = {kept["name"] for kept in store.skills()}
        if checked["name"] not in names and store.skill_count() >= MOST_SKILLS:
            raise Refusal(f"Not kept: Kairu keeps at most {MOST_SKILLS} forged skills. Forget one first.")
        store.keep_skill(checked)
        example = PLACE.sub(lambda found: checked["examples"][0][found.group(1)], checked["says"][0])
        return f'Learned "{checked["name"]}". Say, for example: {example}.'
    return _guarded(data_dir, job, work)


def forget(data_dir: str, job: str, name: str) -> None:
    def work(_) -> str:
        if not BuilderStore(data_dir).forget_skill(" ".join(name.lower().split())):
            raise Refusal(f'There is no forged skill called "{name[:40]}".')
        return f'Forgot the skill "{name[:40]}".'
    return _guarded(data_dir, job, work)
