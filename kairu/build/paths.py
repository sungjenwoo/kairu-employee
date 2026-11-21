"""Five Paths (BUILDER.md "Five Paths"): one big task, five plans, a judge, and you pick. Only the one you pick runs.

    paths.draft (Low)  the free cloud AI (brain.build_providers, Gemini first) writes five plans for the task, one per style
                       (Fast, Careful, Simple, Creative, Thorough), each of Kairu's KNOWN skills and read as strictly as any
                       plan (kairu/tasks/plan.py); then a judge scores each plan that came back against "done when" (yours,
                       or one the judge writes). All of it is kept in data/builder.db; nothing runs.

Then the task core (kairu/build/conduct.py) runs the rule checks: Guardian decides every step of every plan, and a plan with
a step Guardian refuses (Critical, or not in policy.yaml) is dropped, as is one with more than one High step. You see the rest,
best first, each with the judge's reason, and say "run path 2" (or "run the best path"). That plan is then shown and run like
any plan: after your "yes", with your PIN if it has a High step, and Guardian decides each step again as it runs.
"""

import json
import re

from kairu.build.store import BuilderStore
from kairu.tasks import plan as planner

STYLES = (
    ("Fast", "the fewest steps that get it done"),
    ("Careful", "look before changing anything (find, list or read first), and prefer steps that can be undone"),
    ("Simple", "the plainest way, as a beginner would do it by hand"),
    ("Creative", "a fresh, clever way to do it, still with only these skills"),
    ("Thorough", "cover everything the task could need, within the step limit"),
)
LONGEST_WHY = 160
LONGEST_DONE = 200


class NoJudgement(Exception):
    pass


def style_instructions(style: str, how: str, earlier: list[str] | None = None) -> str:
    """earlier: the plans the paths before this one wrote (as Kairu describes their steps), so this one finds its own way."""
    told = (planner.instructions(planner.PLANNABLE) +
            f"\nYou are the {style} path, one of five Kairus each planning the same task their own way. Your way: {how}.")
    if earlier:
        told += ("\nThe other paths already planned:\n" + "\n".join(earlier) +
                 f"\nMake your plan clearly different from theirs, in the {style} way (other skills, another order, an extra "
                 "check or a better finish), unless the same steps truly are the only good way.")
    return told


def judge_instructions(done: str, listing: str) -> str:
    """listing: the plans as Kairu describes their steps (kairu/tasks/plan.py describe), never your own words."""
    target = (f'The task is done when: {done}.' if done else
              'First write in a few words when the task is done ("done").')
    return (
        "You are the judge of Five Paths: several plans for one task on a Windows PC, each a list of steps. "
        f"{target} Score each plan from 0 to 10 for how surely it gets the task done, safely and without extra steps. "
        "Reply with JSON only, no other words: "
        '{"done": "<when the task is done>", "scores": [{"path": <its number>, "score": <0-10>, "why": "<one short sentence>"}]}. '
        "Score every plan below, once, and give each its own reason: say what makes it better or worse than the others.\n"
        "The plans:\n" + listing)


def _json(text: str):
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", body, re.DOTALL)
    try:
        return json.loads(fenced.group(1) if fenced else body, strict=False)
    except ValueError:
        raise NoJudgement("the judge's answer wasn't scores") from None


def read_judgement(text: str, numbers: list[int]) -> tuple[str, dict[int, tuple[int, str]]]:
    """("done when", {path number: (score, why)}) for exactly these paths, or NoJudgement."""
    data = _json(text)
    if not isinstance(data, dict) or set(data) != {"done", "scores"} or not isinstance(data["scores"], list):
        raise NoJudgement("the judge's answer wasn't scores")
    done = data["done"] if isinstance(data["done"], str) else ""
    scores = {}
    for item in data["scores"]:
        if not isinstance(item, dict) or set(item) != {"path", "score", "why"}:
            raise NoJudgement("a score wasn't a path, a score and why")
        number, score, why = item["path"], item["score"], item["why"]
        if type(number) is not int or number not in numbers or number in scores:
            raise NoJudgement("a score was for a path that isn't there, or twice")
        if type(score) not in (int, float) or isinstance(score, bool) or not 0 <= score <= 10:
            raise NoJudgement("a score wasn't 0 to 10")
        if not isinstance(why, str) or not why.strip() or len(why) > LONGEST_WHY or re.search(r"[\x00-\x1f]", why):
            raise NoJudgement("a reason wasn't one short sentence")
        scores[number] = (round(score), " ".join(why.split()))
    if set(scores) != set(numbers):
        raise NoJudgement("the judge didn't score every path")
    return " ".join(done.split())[:LONGEST_DONE], scores


def by_rules(paths: list[dict]) -> dict[int, tuple[int, str]]:
    """When the judge can't answer: plans with fewer steps first, and said so."""
    return {number: (max(1, 8 - len(path["steps"]) // 2), "judged by rules: fewer steps first (the judge didn't answer)")
            for number, path in enumerate(paths, 1) if path["steps"]}


def draft(data_dir: str, task: str, done: str, ask: str, source: str, brain: dict | None = None) -> None:
    from kairu.brain.ask import _check, _keep
    from kairu.brain.gateway import ANSWERED, NOT_SENT, Gateway, Result
    _check(ask, source)
    gateway = Gateway(data_dir, brain)
    started = gateway.now()
    if done and len(done) > LONGEST_DONE:
        return _keep(data_dir, ask, source, Result(NOT_SENT, "L3", f'"Done when" is at most {LONGEST_DONE} characters.'))
    paths, said_by, earlier = [], set(), []
    for style, how in STYLES:
        result = gateway.build(task, source, style_instructions(style, how, earlier), longest=6000, tokens=1500)
        if result.status != ANSWERED:
            if not paths or result.reasons:  # the privacy filter or no AI: the same for all five, so say it once
                return _keep(data_dir, ask, source, result)
            paths.append({"style": style, "steps": None, "why_not": "no answer came back"})
            continue
        said_by.add(result.provider)
        try:
            steps = planner.parse(result.text, planner.PLANNABLE)
        except planner.NoPlan as why:
            paths.append({"style": style, "steps": None, "why_not": str(why)})
            continue
        paths.append({"style": style, "steps": [[action, details] for action, details in steps] or None,
                      "why_not": "" if steps else "it found no way with Kairu's skills"})
        if steps:
            earlier.append(f"{style}: " + "; ".join(planner.describe(action, details) for action, details in steps))
    planned = [path for path in paths if path["steps"]]
    numbers = [number for number, path in enumerate(paths, 1) if path["steps"]]
    judged_done, scores = done, by_rules(paths)
    if planned:
        listing = "\n".join(f"Plan {number} ({path['style']}): " + "; ".join(
            planner.describe(action, details) for action, details in path["steps"])
            for number, path in enumerate(paths, 1) if path["steps"])
        judged = gateway.build(task, source, judge_instructions(done, listing), longest=4000, tokens=1200, lead="Task")
        if judged.status == ANSWERED:
            try:
                written, scores = read_judgement(judged.text, numbers)
                judged_done = done or written
            except NoJudgement:
                pass
    for number, path in enumerate(paths, 1):
        path["score"], path["why"] = scores.get(number, (0, ""))
    BuilderStore(data_dir).add_paths(ask, task, judged_done, paths)
    who = ", ".join(sorted(name for name in said_by if name)) or "the free AI"
    _keep(data_dir, ask, source, Result(ANSWERED, "L3", f"{len(planned)} of {len(STYLES)} paths came back ({who}).",
                                        ",".join(sorted(said_by)), seconds=gateway.now() - started))
