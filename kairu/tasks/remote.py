"""task.order: an order typed on your paired phone (Phase D3, PHONE.md), run on this PC by the same task core as the bar.

Guardian starts it for a phone's `task.order` command, with the order's words and the phone it came from (Guardian fills
that in; the phone can't name another). It holds no authority: every step is decided by Guardian as if you had typed the
order in the bar. A High step waits for its card: your fingerprint on that phone (D2), or `kairu link approve N` with "yes"
and your PIN at the PC. A warning that needs "yes" is not answered from the phone, so that step isn't done. What happens is
told to the phone with Guardian's own link.send. Exit code 0 when the order is answered.

Clones (TEAM.md): an order from Main Kairu starts with its step's tag, such as "[K3.2.1] open notepad". The tag is only a
label: it is taken off before the task core sees the order, and put back on what this PC says about it ("[K3.2.1] On it:
..." while it runs, "[K3.2.1 finished] ..." at the end), so Main Kairu knows which task each report is about. It changes
nothing about how the order is decided.

Main Kairu's note (TEAM.md "Talk and sync"): an order from Main Kairu may end with a line "NOTE ..." (a welcome, a
hand-off, a heads-up). It is taken off before the task core sees the order and kept in this laptop's team inbox with
team.note (Low); it is only words to show you, never part of the order.
"""

import re
import time

from kairu import config as kairu_config
from kairu.client import GuardianClient
from kairu.guardian import Action, Approval, Refused

CARD_SECONDS = 115  # a little less than Guardian's own two minutes for an approval
POLL_SECONDS = 0.5
TEAM_TAG = re.compile(r"\[K(\d{1,6})\.(\d{1,2})\.(\d{1,2})\] ?")


def split_tag(order: str) -> tuple[str, str]:
    """("[K3.2.1]", "open notepad") for an order from Main Kairu; ("", order) for any other."""
    found = TEAM_TAG.match(order or "")
    if not found:
        return "", order
    return found.group(0).strip(), order[found.end():]


NOTE = "\nNOTE "


def split_note(order: str) -> tuple[str, str]:
    """(order, Main Kairu's note) for a tagged order; the note is "" when there is none."""
    if NOTE not in order:
        return order, ""
    order, note = order.split(NOTE, 1)
    return order, " ".join(note.split())


def main(data_dir: str, order: str, device: str) -> None:
    cfg = kairu_config.load()
    client = GuardianClient(cfg)
    label, order = split_tag(order)
    if label:
        order, note = split_note(order)
        if note:
            try:
                client.run(Action("team.note", {"text": note[:600], "device": device}))
            except Refused:
                pass  # an older policy without team.note: the order still runs

    def tell(text: str, finished: bool = False) -> None:
        if label:
            text = f"{label[:-1]} finished] {text}" if finished else f"{label} {text}"
        try:
            client.run(Action("link.send", {"device": device, "type": "report", "text": text[:1500]}))
        except Refused:
            pass

    def approve(decision, plan: str = ""):
        try:
            number = client.link_card(decision.request_id, device, plan or None)
        except Refused as refusal:
            tell(f"{decision.action.name} needs your approval, but {refusal}.")
            return None
        deadline = time.monotonic() + CARD_SECONDS
        while time.monotonic() < deadline:
            result = client.link_card_result(number)
            if result.get("state") == "approved" and result.get("approval"):
                return Approval(result["approval"], decision.action.name, time.time() + 60)
            if result.get("state") in ("refused", "gone"):
                return None
            time.sleep(POLL_SECONDS)
        return None

    def progress(event: dict) -> None:
        if event.get("kind") == "steps" and len(event.get("steps", [])) > 1:
            tell("On it: " + " → ".join(step["label"] for step in event["steps"]))

    from kairu.tasks.core import TaskCore
    core = TaskCore(cfg, client, approver=approve, confirmer=lambda text: False, source=device,
                    plan_approver=approve, progress=progress)
    tell(core.handle(order) or "Done.", finished=True)
