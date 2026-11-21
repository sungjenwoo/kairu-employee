"""High tier: shown in full, then "yes" and the PIN; nothing less runs it."""

import sqlite3

import pytest

from kairu import approval, audit, pin, safemode
from kairu.guardian import Action, Refused, Verdict
from tests_kairu.helpers import PIN

DELETE = Action("files.delete", {"path": "Finance/2026/receipt.pdf"})


def test_high_needs_approval(guardian):
    decision = guardian.check(DELETE)
    assert decision.verdict is Verdict.NEEDS_APPROVAL and decision.request_id


def test_high_without_a_pin_set_is_refused(guardian, runner):
    decision = guardian.check(DELETE)
    with pytest.raises(Refused, match="no PIN is set"):
        guardian.approve(decision.request_id, "yes", "")
    with pytest.raises(Refused, match="not approved"):
        runner.run(DELETE, "kairu.demo:count", seconds=0)


@pytest.mark.parametrize("typed_pin", ["", "000000", PIN + " ", PIN[:-1]])
def test_high_with_the_wrong_pin_is_refused(guardian, with_pin, typed_pin):
    decision = guardian.check(DELETE)
    with pytest.raises(Refused, match="wrong PIN"):
        guardian.approve(decision.request_id, "yes", typed_pin)


@pytest.mark.parametrize("typed", ["", "y", "no", "ok", "yes please"])
def test_high_without_yes_is_refused_and_the_pin_is_not_even_checked(guardian, with_pin, typed):
    decision = guardian.check(DELETE)
    with pytest.raises(Refused, match='did not type "yes"'):
        guardian.approve(decision.request_id, typed, PIN)
    assert guardian.store.get("pin_failures", "0") == "0"


def test_high_cannot_run_without_an_approval(guardian, runner, with_pin):
    guardian.check(DELETE)  # asked, but never approved
    assert guardian.authorize(DELETE).verdict is Verdict.DENY
    with pytest.raises(Refused, match="not approved"):
        runner.run(DELETE, "kairu.demo:count", seconds=0)


def test_yes_and_the_pin_approve_it_once(guardian, runner, with_pin):
    decision = guardian.check(DELETE)
    granted = guardian.approve(decision.request_id, "yes", PIN)
    run = runner.run(DELETE, "kairu.demo:count", approval=granted, seconds=0, quiet=True)
    assert run.wait(10) == "finished"
    with pytest.raises(Refused, match="already used"):  # single use
        runner.run(DELETE, "kairu.demo:count", approval=granted, seconds=0)
    with pytest.raises(Refused, match="no such request"):  # and the request itself is answered
        guardian.approve(decision.request_id, "yes", PIN)


def test_an_approval_covers_only_the_details_you_were_shown(guardian, with_pin):
    granted = guardian.approve(guardian.check(DELETE).request_id, "yes", PIN)
    other = Action("files.delete", {"path": "Finance/2026/everything"})
    decision = guardian.authorize(other, granted)
    assert decision.verdict is Verdict.DENY and "different action or different details" in decision.reason


def test_the_terminal_prompt_shows_the_details_then_asks_yes_then_the_pin(guardian, with_pin):
    shown, asked = [], []
    granted = approval.ask(guardian, guardian.check(DELETE), write=shown.append,
                           read=lambda prompt: asked.append(prompt) or "yes",
                           read_pin=lambda prompt: asked.append(prompt) or PIN)
    assert granted is not None
    text = "\n".join(shown)
    assert "files.delete" in text and "Recycle Bin" in text and "Finance/2026/receipt.pdf" in text and "High" in text
    assert asked == ['Type "yes" to approve, anything else to refuse: ', "Your Kairu PIN: "]


def test_the_terminal_prompt_does_not_ask_for_the_pin_unless_you_typed_yes(guardian, with_pin):
    shown = []
    refused = approval.ask(guardian, guardian.check(DELETE), write=shown.append, read=lambda prompt: "no",
                           read_pin=lambda prompt: pytest.fail("asked for the PIN"))
    assert refused is None and "Refused" in shown[-1]


def test_five_wrong_pins_enter_safe_mode_and_lock_the_pin(guardian, with_pin):
    for _ in range(pin.MAX_FAILURES):
        with pytest.raises(Refused):
            guardian.approve(guardian.check(DELETE).request_id, "yes", "999999")
    assert safemode.is_safe(guardian.store)
    assert "wrong PINs" in safemode.reason(guardian.store)
    ok, why = pin.check(guardian.store, PIN)  # even the right PIN waits out the lock
    assert not ok and "too many wrong PINs" in why


def test_the_pin_is_stored_only_as_an_argon2id_hash(guardian, with_pin):
    stored = guardian.store.get("pin_hash")
    assert stored.startswith("$argon2id$") and PIN not in stored
    guardian.approve(guardian.check(DELETE).request_id, "yes", PIN)
    with sqlite3.connect(guardian.store.path) as db:
        everything = " ".join(str(row) for table in ("audit", "state") for row in db.execute(f"SELECT * FROM {table}"))
    assert PIN not in everything
    assert all(PIN not in str(row) for row in audit.tail(guardian.store, 1000))


def test_changing_the_pin_needs_the_current_one(guardian, with_pin):
    with pytest.raises(pin.PinError, match="current PIN"):
        pin.set_pin(guardian.store, "135792", "wrong!")
    pin.set_pin(guardian.store, "135792", PIN)
    assert pin.check(guardian.store, "135792") == (True, "")


def test_a_short_pin_is_refused(guardian):
    with pytest.raises(pin.PinError, match="at least 6"):
        pin.set_pin(guardian.store, "1234")
