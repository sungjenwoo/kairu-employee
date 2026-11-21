"""Stage 2 and 3 of the meeting agent (HACKATHON.md): the decision ledger, the conflict check, "what did we decide about X?"
and the brief that hands a meeting's open actions to Main Kairu's split.

Read only, on this PC: everything here reads data/meetings.db (and the team board for workload) and sends nothing. The
conflicts between meetings come from two places:

    Gemini, inside meeting.read (High, the card you approved): it is shown the earlier open decisions and actions (the ledger)
        and names each clash - a dropped thing back, a moved date, a changed owner, someone overloaded - with the newer
        meeting's words. Kept in the conflicts table (kairu/meeting/store.py), read strictly (kairu/meeting/read.py).
    Kairu's own rules, here, at the moment you look (nothing to trust): an open action nobody owns, the same work held by two
        people, an owner with too many open actions or too many busy minutes on the team board, and an action due before
        the action it says it waits on.

The manager decides each conflict (`kairu meeting resolve M C new|old`); nothing is changed by itself, and nothing runs.
"""

import re
from datetime import date, datetime

from kairu.meeting.store import MeetingStore, exists

MOST_OPEN_ACTIONS = 3       # an owner with more open actions than this, due within WITHIN_DAYS, is overloaded
WITHIN_DAYS = 7
MOST_BUSY_MINUTES = 240     # or with more than this many minutes of unfinished Clone work on the team board
SAME_WORK = 0.6             # word overlap above which two actions are the same work
STOP = set("""a an the and or of to for in on at by with from is are be was were will this that these those it its we our
you your they their he she his her them do does did done make made get got go going have has had not no new now all any
some one two can should would could need needs needed by""".split())
AFTER = re.compile(r"\b(?:after|once|when|depends on|waits? (?:on|for)|blocked by)\b(?P<rest>.+)", re.I)


def words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9']+", text.lower()) if len(word) > 2 and word not in STOP}


def overlap(one: str, two: str) -> float:
    a, b = words(one), words(two)
    return len(a & b) / max(1, min(len(a), len(b))) if a and b else 0.0


def _ref(item: dict) -> str:
    return f"meeting {item['meeting']} ({_day(item['held'])}), {item['kind']} {item['number']}"


def _day(held: str) -> str:
    try:
        day = datetime.strptime(held, "%Y-%m-%d")
        return f"{day.day} {day.strftime('%b')}"
    except ValueError:
        return held


def rule_conflicts(ledger: list[dict], busy: dict | None = None, today: date | None = None) -> list[dict]:
    """Kairu's own checks over the open actions of every meeting. Each: {"kind", "what", "items": [refs]}."""
    today = today or date.today()
    actions = [item for item in ledger if item["kind"] == "action" and item["status"] == "open"]
    out = []
    for item in actions:
        if not item["owner"]:
            out.append({"kind": "owner", "what": f"Nobody owns \"{item['what']}\" ({_ref(item)}).", "items": [_ref(item)]})
    for index, one in enumerate(actions):
        for two in actions[index + 1:]:
            if one["owner"] and two["owner"] and one["owner"].lower() != two["owner"].lower() and \
                    overlap(one["what"], two["what"]) >= SAME_WORK:
                out.append({"kind": "owner", "what": f"The same work has two owners: {one['owner']} (\"{one['what']}\", "
                            f"{_ref(one)}) and {two['owner']} (\"{two['what']}\", {_ref(two)}).",
                            "items": [_ref(one), _ref(two)]})
    by_owner: dict[str, list[dict]] = {}
    for item in actions:
        if item["owner"]:
            by_owner.setdefault(item["owner"].lower(), []).append(item)
    for owner, held in by_owner.items():
        soon = [item for item in held if not item["due"] or _days(item["due"], today) <= WITHIN_DAYS]
        minutes = next((value for name, value in (busy or {}).items() if name.lower() == owner), 0)
        if len(soon) > MOST_OPEN_ACTIONS or minutes > MOST_BUSY_MINUTES:
            name = held[0]["owner"]
            said = f"{name} holds {len(soon)} open action{'s' if len(soon) != 1 else ''} due within {WITHIN_DAYS} days"
            if minutes:
                said += f" and about {int(minutes)} minutes of unfinished Clone work on the team board"
            out.append({"kind": "workload", "what": said + ".", "items": [_ref(item) for item in soon]})
    for item in actions:
        waits = AFTER.search(item["what"])
        if not waits or not item["due"]:
            continue
        for other in actions:
            if other is item or not other["due"] or overlap(waits.group("rest"), other["what"]) < 0.5:
                continue
            if item["due"] < other["due"]:
                out.append({"kind": "dependency", "what": f"\"{item['what']}\" is due {_day(item['due'])}, before "
                            f"\"{other['what']}\" it waits on (due {_day(other['due'])}).", "items": [_ref(item), _ref(other)]})
    return out


def _days(due: str, today: date) -> int:
    try:
        return (datetime.strptime(due, "%Y-%m-%d").date() - today).days
    except ValueError:
        return 0


def busy(data_dir) -> dict:
    """Minutes of unfinished work each Clone has on the team board ({} when there is no team yet)."""
    try:
        from kairu.team.conduct import busy_minutes
        from kairu.team.store import TeamStore, exists as team_exists
        return busy_minutes(TeamStore(data_dir)) if team_exists(data_dir) else {}
    except Exception:  # the team board is only extra information here
        return {}


def check(data_dir) -> dict:
    """Everything the conflict check knows: Gemini's open conflicts between meetings and Kairu's own rule checks."""
    if not exists(data_dir):
        return {"between": [], "rules": []}
    from kairu.meeting import proof
    store = MeetingStore(data_dir)
    return {"between": store.conflicts("open"), "rules": rule_conflicts(proof.ledger(data_dir), busy(data_dir))}


def told_check(found: dict) -> str:
    between, rules = found["between"], found["rules"]
    if not between and not rules:
        return "No conflicts: every open decision and action across your meetings fits together."
    out = [f"{len(between) + len(rules)} conflict{'s' if len(between) + len(rules) != 1 else ''} to decide."]
    for clash in between:
        line = f"[{clash['meeting']}.{clash['number']}] {clash['kind']}: {clash['what']}"
        if clash.get("earlier"):
            line += f" (earlier: \"{clash['earlier']['what']}\", {clash['earlier']['title']}, {_day(clash['earlier']['held'])})"
        out.append(line)
    out += [f"- {clash['kind']}: {clash['what']}" for clash in rules]
    if between:
        out.append("Decide each numbered one: `kairu meeting resolve MEETING.CONFLICT new` keeps the new decision, `old` keeps "
                   "the earlier one.")
    return "\n".join(out)


def told_ledger(ledger: list[dict]) -> str:
    if not ledger:
        return "The ledger is empty: read a meeting first."
    out = ["The decision ledger, oldest meeting first:"]
    current = None
    for item in ledger:
        if item["meeting"] != current:
            current = item["meeting"]
            out.append(f"Meeting {item['meeting']}: {item['meeting_title']} ({_day(item['held'])})")
        extra = "".join((f", {item['owner']}" if item["owner"] else ", nobody yet" if item["kind"] == "action" else "",
                         f", due {_day(item['due'])}" if item["due"] else ""))
        work = item.get("work")
        if work and item["status"] != "done":
            extra += f", Clones {work['done']} of {work['total']} tasks done"
        out.append(f"  {item['number']}. [{item['status']}] {item['kind']}: {item['what']}{extra}")
        if item["status"] == "done" and item.get("proof"):
            out.append(f"     Proof: {item['proof']}")
    return "\n".join(out)


def ask(data_dir, topic: str) -> str:
    """"What did we decide about X?": the decisions (and actions) whose words fit X best, newest first, each with its meeting,
    its day, its status and the words that show it."""
    topic = " ".join(topic.split()).strip(" ?.")
    if not exists(data_dir):
        return "No meetings yet, so nothing was decided about that."
    wanted = words(topic)
    if not wanted:
        return "Say what it's about, for example: what did we decide about the launch date?"
    from kairu.meeting import proof
    ledger = proof.ledger(data_dir)
    scored = []
    for item in ledger:
        shared = wanted & (words(item["what"]) | words(item.get("quote", "")))
        if shared:
            scored.append((len(shared) + (0.5 if item["kind"] == "decision" else 0), item))
    if not scored:
        return f"I don't find anything decided about {topic} in your meetings."
    best = max(score for score, _ in scored)
    found = sorted((item for score, item in scored if score >= best - 0.5), key=lambda item: (item["held"], item["meeting"]),
                   reverse=True)[:4]
    newest = found[0]
    out = [f"About {topic}: {newest['what']} ({newest['meeting_title']}, {_day(newest['held'])}, {newest['status']})."]
    if newest.get("quote"):
        out.append(f"Said{' at ' + newest['at'] if newest.get('at') else ''}: \"{newest['quote']}\"")
    if newest["status"] == "done" and newest.get("proof"):
        out.append(f"Proof: {newest['proof']}")
    for item in found[1:]:
        out.append(f"Before that: {item['what']} ({item['meeting_title']}, {_day(item['held'])}, {item['status']}).")
    return "\n".join(out)


def brief(data_dir, meeting: int | None = None) -> tuple[str, str]:
    """Stage 3: the open actions (and the decisions they serve) as a brief for Main Kairu's split (team.split). Returns
    (name, brief). meeting None: every meeting's open actions. Raises ValueError with what to tell you."""
    name, text, _ = brief_and_rest(data_dir, meeting)
    return name, text


def brief_and_rest(data_dir, meeting: int | None = None) -> tuple[str, str, int]:
    """The brief, and how many open actions did not fit in it (they go in the next split).

    Stage 5: each line starts with its id ([A2.3] an action, [D2.1] a decision), so team.split can link every Clone task
    back to the item it does (kairu/meeting/proof.py). An item whose Clone work is done, or that is already split to a
    project that wasn't stopped, is left out. The brief goes through the brain's privacy filter (kairu/brain/privacy.py) as
    a public order, so it is built to pass it, never by loosening it: as many actions as fit (a longer text counts as maybe
    pasted, so personal), then the decisions they serve, as room allows. What doesn't fit waits for the next split."""
    if not exists(data_dir):
        raise ValueError("No meetings yet: read one first.")
    from kairu.brain import privacy
    from kairu.meeting import proof
    ledger = [item for item in proof.ledger(data_dir) if item["status"] == "open" and (meeting is None or item["meeting"] == meeting)]
    split = proof.split_already(data_dir)
    every = [item for item in ledger if item["kind"] == "action"]
    actions = [item for item in every if (item["meeting"], item["number"]) not in split]
    if not actions:
        if every:
            raise ValueError("Every open action is already split to the Clones: start it with `kairu team start` (or say "
                             "\"start the project\"), and watch it on the Clones page.")
        raise ValueError("There are no open actions to split.")
    decisions = [item for item in ledger if item["kind"] == "decision"]
    title = ledger[-1]["meeting_title"] if meeting else "the meetings"

    def text(acts: list[dict], decs: list[dict]) -> str:
        parts = [f"Work agreed in {title}."]
        if decs:
            parts.append("Decided: " + "; ".join(f"[D{item['meeting']}.{item['number']}] {item['what']}" for item in decs) + ".")
        parts.append("Tasks: " + "; ".join(
            f"[A{item['meeting']}.{item['number']}] {item['what']}" + (f" (owner {item['owner']})" if item["owner"] else "")
            + (f" (due {item['due']})" if item["due"] else "") for item in acts) + ".")
        return " ".join(parts)

    def passes(candidate: str) -> bool:
        verdict = privacy.classify(candidate)
        return not verdict.secret and not verdict.personal

    chosen = []
    for item in actions[:12]:
        if passes(text(chosen + [item], [])):
            chosen.append(item)
    if not chosen:
        verdict = privacy.classify(text(actions[:1], []))
        raise ValueError(f"The first open action can't go to the cloud AI to be split: it has {verdict.why()}. Change its "
                         "words, or give the work to a Clone yourself.")
    kept = []
    for item in reversed(decisions[-6:]):
        if passes(text(chosen, [item] + kept)):
            kept.insert(0, item)
    return f"From {title}"[:60], text(chosen, kept), len(actions) - len(chosen)
