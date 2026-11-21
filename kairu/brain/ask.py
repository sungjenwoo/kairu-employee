"""brain.ask and brain.send_private: the Model Gateway as Guardian actions, one question each.

Guardian runs each in its own process inside its Job Object, like any action, so Ctrl+Alt+K, the tray's
STOP and `kairu stop` end a question within a second, network call and all. Its details are the
question, a random answer id (`ask`) and where it came from (`source`: pc, a paired device's id, or
mission:N); the brain's settings come from Guardian's own config.yaml (`brain`), never from a request.
Guardian's audit log keeps only a hash of the details (policy.yaml: private), never the question.

A question that needs fresh facts: the brain says so, and kairu/research/conduct.py, in this same process, asks
Guardian for the search and the page reads (RESEARCH.md); the brain then writes the answer from what they found.
The brain itself fetches nothing. "research deeply ..." does this for up to three searches, whose words the brain writes
before any page is read, and the answer is a short report (RESEARCH.md "Deep research"). An approved question with `search` set does the same, with your approval's mark.

The answer goes into data/brain.db under its id, for whoever asked to read once (`kairu ask`, Guardian for
your phone, a mission); then it is deleted. Exit code 0 whenever there is an answer to read, even "not
sent"; 1 (with the reason on Guardian's log) only when something went wrong.
"""

import re
import sys
import time

from kairu.brain.gateway import ANSWERED, LOCATION, MEMORY, SEARCH, WEATHER, Gateway, Result
from kairu.brain.store import Answer, BrainStore

ASK_ID = re.compile(r"[0-9a-f]{16}")
WHERE_NOTE = "from this PC's location"  # kairu/live/relay.py lets this answer through to Kairu Live (the owner, 19 Nov 2026)
SOURCE = re.compile(r"pc|dev-[0-9a-f]{16}|mission:[1-9]\d{0,8}")


def main(data_dir: str, question: str, ask: str, source: str, brain: dict | None = None) -> None:
    _check(ask, source)
    gateway = Gateway(data_dir, brain)
    started = gateway.now()
    result = gateway.ask(question, source)
    if result.status == MEMORY:  # "remember that ..." or "forget ...": Guardian runs it as its own action (MEMORY.md)
        from kairu.memory.conduct import Keeper
        keeper, route = Keeper(data_dir), result.route
        text = keeper.remember(route.query, source) if route.name == "remember" else keeper.forget(route.query)
        result = Result(ANSWERED, "L0", text, seconds=gateway.now() - started, route=route)
    if result.status == LOCATION:  # "where am I?": Windows' location and the area's name (kairu/research/where.py)
        from kairu.research.conduct import Research
        said = Research(data_dir).location() or "I couldn't find where you are right now.\nWant to try again in a minute?"
        result = Result(ANSWERED, "L0", said, note=WHERE_NOTE, seconds=gateway.now() - started, route=result.route)
    if result.status == WEATHER:  # Open-Meteo, in about a second; if it can't answer, the web as before
        from kairu.research.conduct import Research
        said = Research(data_dir).weather(result.search)
        if said:
            result = Result(ANSWERED, "L0", said, note="from Open-Meteo", seconds=gateway.now() - started, route=result.route)
        else:
            result = Result(SEARCH, "L3", route=result.route, search=gateway.search_words(question))
    if result.status == SEARCH:
        from kairu.research.conduct import Research
        if result.route.deep:  # "research deeply ...": the brain names the searches, Guardian runs each, the brain reports
            founds = Research(data_dir).look_into(gateway.deep_queries(result.search))
            result = gateway.deep_report(question, founds, source, result.route, started)
        else:
            result = gateway.from_the_web(question, Research(data_dir).look_up(result.search), source, result.route, started)
    _keep(data_dir, ask, source, result)
    _remember_talk(data_dir, question, source, result, brain)


def private(data_dir: str, question: str, provider: str, ask: str, source: str, brain: dict | None = None,
            search: str = "") -> None:
    _check(ask, source)
    gateway = Gateway(data_dir, brain)
    started, found = gateway.now(), None
    if search and not gateway.secret_in(question, search):
        from kairu.research.conduct import Research
        from kairu.research.store import ResearchStore
        ResearchStore(data_dir).allow(search)  # you approved these words: the search action spends this mark
        found = Research(data_dir).look_up(search)
    _keep(data_dir, ask, source, gateway.send_private(question, provider, source, search, found, started))


def plan(data_dir: str, order: str, ask: str, source: str, brain: dict | None = None) -> None:
    """brain.plan: an order the rules don't know, as steps of Kairu's own skills (kairu/tasks/plan.py). Only text comes back."""
    from kairu.tasks.plan import PLANNABLE, instructions
    _check(ask, source)
    gateway = Gateway(data_dir, brain)
    _keep(data_dir, ask, source, gateway.plan(order, source, instructions(PLANNABLE)))


def _check(ask: str, source: str) -> None:
    if not ASK_ID.fullmatch(ask) or not SOURCE.fullmatch(source):
        print("brain: an answer id is 16 hex digits, and a source is pc, a device id or mission:N", file=sys.stderr)
        raise SystemExit(1)


def _remember_talk(data_dir: str, question: str, source: str, result: Result, brain: dict | None) -> None:
    """Your talk history (MEMORY.md "Talk history"): an answer at the PC goes into brain.db, on this PC only, unless
    brain.talk_history is off in config.yaml. Nothing of it is sent anywhere or written to the audit log."""
    if source != "pc" or result.status != ANSWERED or not (brain or {}).get("talk_history", True):
        return
    from kairu.memory import talks
    kind = result.route.kind if result.route else ""
    if result.route and result.route.name == "summary":  # an AI website's answer, summarised: not your words, not kept
        return
    if talks.kept(question, result.text, result.level, kind):
        BrainStore(data_dir).keep_talk(question, result.text)


def _keep(data_dir: str, ask: str, source: str, result: Result) -> None:
    BrainStore(data_dir).put_answer(Answer(ask, time.time(), source, result.status, result.level, result.provider,
                                           result.text, result.note, result.reasons, round(result.seconds, 3),
                                           result.search))
