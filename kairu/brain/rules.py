"""L0: the answers Kairu gives from fixed rules on this PC, with no AI and nothing sent anywhere.

They only read: the clock, Kairu's own status (asked of Guardian), the brain's usage notes, the pages the last
answer used and the Mission Cards. Short and warm, like every Kairu answer.
"""

from datetime import datetime

from kairu.brain import usage
from kairu.brain.store import BrainStore

HELP = ("Ask me anything and I answer short. Try \"who is the prime minister of India\", \"what time is it\" or "
        "\"usage\". Say \"search\" and a question to look it up, \"sources?\" for the pages I used. Long jobs: "
        "`kairu mission new` (BRAIN.md).")
NO_SOURCES = "I have no pages to show: my last answer did not come from the web, or it was a while ago."


def answer(rule: str, data_dir, settings: dict, source: str, ask_guardian) -> str:
    now = datetime.now().astimezone()
    if rule == "time":
        hour = now.hour % 12 or 12
        return f"It's {hour}:{now.minute:02d} {'am' if now.hour < 12 else 'pm'}."
    if rule == "date":
        return f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}."
    if rule == "greeting":
        return "Hi! I'm here. What would you like to know?"
    if rule == "thanks":
        return "You're welcome! Anything else?"
    if rule == "help":
        return HELP
    if rule == "usage":
        return usage.short(data_dir, settings)
    if rule == "missions":
        return _missions(data_dir)
    if rule == "stop":
        if source.startswith("dev-"):
            return ("Stopping from the phone comes with the phone app (Phase D). At the PC: Ctrl+Alt+K, STOP EVERYTHING "
                    "in the tray, or `kairu stop`.")
        return "To stop everything now: press Ctrl+Alt+K, choose STOP EVERYTHING in the tray, or run `kairu stop`."
    if rule == "call":
        return "I can't make calls yet; that comes with the phone app."
    if rule == "sources":
        return _sources(data_dir, source)
    if rule == "status":
        return _status(ask_guardian)
    raise ValueError(f"no rule {rule!r}")


def _status(ask_guardian) -> str:
    try:
        state = ask_guardian({"op": "status"})
    except Exception:
        return "I'm here, but Guardian did not answer, so I can't say more. `kairu status` shows why."
    if state.get("verdict") != "ok":
        return "I'm here, but Guardian did not answer, so I can't say more. `kairu status` shows why."
    mode = "normal" if state.get("mode") != "safe" else f"Safe Mode ({state.get('safe_reason')})"
    running = sorted({run.get("action") for run in state.get("running") or []} -
                     {"link.receive", "link.send", "brain.ask", "protect.watch", "research.web_search", "research.web_read"})
    return (f"I'm running well. Mode: {mode}. Working on: {', '.join(running) or 'nothing else'}. "
            f"Waiting for your PIN: {state.get('phone_waiting', 0)}.")


def _sources(data_dir, source: str) -> str:
    """The pages the last answer used. Titles and links only; none of it is an order, and links are never opened here."""
    items = BrainStore(data_dir).sources(source)
    if not items:
        return NO_SOURCES
    lines = [f"{number}. {item['title']}\n   {item['url']}" for number, item in enumerate(items, 1)]
    return "I used these pages:\n" + "\n".join(lines)


def _missions(data_dir) -> str:
    from kairu.missions import store as missions
    cards = missions.summary(data_dir)
    if not cards:
        return "No missions yet. `kairu mission new` starts one."
    open_ones = [card for card in cards if card["status"] in ("queued", "running", "waiting", "stopped")]
    if not open_ones:
        return f"All {len(cards)} mission{'s are' if len(cards) != 1 else ' is'} finished. `kairu mission list` shows them."
    words = "; ".join(f"#{card['id']} {card['status']} ({card['done']} of {card['steps']} steps)" for card in open_ones[:5])
    return f"Missions: {words}. `kairu mission show N` for one."
