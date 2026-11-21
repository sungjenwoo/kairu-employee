"""Asking you in the terminal: the action's details, then "yes", then your PIN (not shown as you type).

`guardian` is a GuardianClient, which hands your answers to the Guardian program (kairu/client.py),
or a Guardian in this process; both answer approve() and resume() the same way.
"""

import getpass

from kairu.guardian import APPROVAL_SECONDS, Approval, Decision, Guardian, Refused


def ask(guardian: Guardian, decision: Decision, read=input, read_pin=getpass.getpass, write=print) -> Approval | None:
    """Show a needs_approval decision and ask for "yes" and the PIN. The approval, or None if refused."""
    write(f"\nGuardian: this action needs your approval ({decision.tier} tier).")
    write(f"  action:   {decision.action.name}")
    write(f"  what:     {decision.description}")
    for key, value in decision.action.details.items():
        write(f"  {key + ':':<9} {value}")
    write(f"  The approval covers this action with these details, once, within {APPROVAL_SECONDS // 60} minutes.")
    answer = read_answer(read, 'Type "yes" to approve, anything else to refuse: ')
    secret = read_answer(read_pin, "Your Kairu PIN: ") if answer.strip().lower() == "yes" else ""
    try:
        approval = guardian.approve(decision.request_id, answer, secret)
    except Refused as refusal:
        write(f"Refused: {refusal}")
        return None
    write("Approved.")
    return approval


def ask_resume(guardian: Guardian, read=input, read_pin=getpass.getpass, write=print) -> bool:
    """Leave Safe Mode after "yes" and the PIN."""
    answer = read_answer(read, 'Leave Safe Mode? Type "yes" to resume, anything else to stay in Safe Mode: ')
    secret = read_answer(read_pin, "Your Kairu PIN: ") if answer.strip().lower() == "yes" else ""
    try:
        guardian.resume(answer, secret)
    except Refused as refusal:
        write(f"Still in Safe Mode: {refusal}")
        return False
    write("Resumed: Safe Mode is off.")
    return True


def read_answer(read, prompt: str) -> str:
    """What you typed; nothing if the input was closed or you pressed Ctrl+C, which refuses."""
    try:
        return read(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
