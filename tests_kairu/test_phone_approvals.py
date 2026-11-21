"""Phase D2 (PHONE.md, ADR-035): STOP from the phone, and the phone approving its own High requests with its fingerprint.

Through the real Guardian program, the stand-in relay and the stand-in phone (as in test_link_program.py). The phone's
fingerprint key is an Ed25519 key made here; on the real phone it lives in Android's Keystore and signs only after a
fingerprint.
"""

import base64
import json
import time

import pytest
from nacl.signing import SigningKey

from kairu import audit, safemode
from kairu.guardian import fingerprint, Action, Refused
from kairu.guardian_program import REQUESTS
from kairu.link import approver, store as link_store
from kairu.store import Store
from tests_kairu.helpers import PIN, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_link_program import ask, command, config_path, pair_phone, power, relay, rows, running  # noqa: F401


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def enrolled(program, phone, key: SigningKey):
    """Turn fingerprint approval on for the phone: its request, then "yes" and the PIN at the PC."""
    [reply] = ask(phone, "command", command("device.approver", key=b64(bytes(key.verify_key)), device="dev-0000000000000000"))
    assert "kairu link approve" in reply["body"]
    [waiting] = [entry for entry in program.client.link_waiting() if entry["action"] == "device.approver"]
    assert waiting["details"]["device"] == phone.id  # only ever for itself
    program.client.link_approve(waiting["number"], "yes", PIN)
    wait_for(lambda: link_store.approver(program.data_dir, phone.id) == b64(bytes(key.verify_key)), timeout=20)


def card_of(message) -> dict:
    return json.loads(message["body"])["kairu_card"]


def signed(key: SigningKey, phone, card) -> str:
    return b64(key.sign(approver.statement(phone.id, card["number"], card["fingerprint"], card["expires"])).signature)


# --- the statement and the check -------------------------------------------------------------------------

def test_a_statement_names_one_request_exactly():
    fp = "a" * 64
    assert approver.statement("dev-0123456789abcdef", 3, fp, 1762850600) == f"kairu-approve-v1|dev-0123456789abcdef|3|{fp}|1762850600".encode()
    for bad in (("phone", 3, fp, 1), ("dev-0123456789abcdef", "3", fp, 1), ("dev-0123456789abcdef", 3, "x", 1)):
        with pytest.raises(ValueError):
            approver.statement(*bad)


def test_the_check_takes_raw_and_androids_x509_keys_and_nothing_else():
    key = SigningKey.generate()
    raw = bytes(key.verify_key)
    message = b"kairu-approve-v1|x"
    signature = b64(key.sign(message).signature)
    x509 = bytes.fromhex("302a300506032b6570032100") + raw
    assert approver.verify(b64(raw), message, signature) and approver.verify(b64(x509), message, signature)
    assert not approver.verify(b64(raw), message + b"!", signature)
    assert not approver.verify(b64(bytes(SigningKey.generate().verify_key)), message, signature)
    assert not approver.verify("not base64!", message, signature) and not approver.verify(b64(raw[:31]), message, signature)


def test_no_request_on_guardians_channel_can_approve_without_a_pin():
    assert "approve_verified" not in REQUESTS and all("verified" not in name for name in REQUESTS)
    assert set(REQUESTS["link"]) == {"device", "type", "digest", "problem", "action", "details"}


# --- through the Guardian program -----------------------------------------------------------------------

def test_turning_fingerprint_approval_on_needs_the_pin_typed_at_the_pc(program_with_pin, tmp_path):
    phone = pair_phone(program_with_pin, tmp_path)
    key = SigningKey.generate()
    [reply] = ask(phone, "command", command("device.approver", key=b64(bytes(key.verify_key))))
    assert "High tier" in reply["body"] and "kairu_card" not in reply["body"]  # never approvable by a fingerprint
    [waiting] = program_with_pin.client.link_waiting()
    with pytest.raises(Refused, match="wrong PIN"):
        program_with_pin.client.link_approve(waiting["number"], "yes", "000000")
    assert link_store.approver(program_with_pin.data_dir, phone.id) is None
    program_with_pin.client.link_approve(waiting["number"], "yes", PIN)
    wait_for(lambda: link_store.approver(program_with_pin.data_dir, phone.id) is not None, timeout=20)


def test_a_high_request_from_the_phone_is_approved_with_its_fingerprint_once(program_with_pin, tmp_path, power):
    phone = pair_phone(program_with_pin, tmp_path)
    key = SigningKey.generate()
    enrolled(program_with_pin, phone, key)
    since = int(time.time()) - 1
    phone.send("command", command("mission_mode.on"))
    [message] = phone.replies(since, 30, until=lambda got: any("kairu_card" in m["body"] for m in got))[-1:]
    card = card_of(message)
    assert (card["action"], card["tier"]) == ("mission_mode.on", "High")
    assert card["fingerprint"] == fingerprint(Action("mission_mode.on", {}))
    time.sleep(0.5)
    assert not running(program_with_pin, "mission_mode.on")  # nothing runs before the fingerprint
    since = int(time.time()) - 1
    phone.send("command", command("link.approve", number=card["number"], signature=signed(key, phone, card)))
    told = phone.replies(since, 30, until=lambda got: any("Approved with your fingerprint" in m["body"] for m in got))
    assert any("mission_mode.on started" in m["body"] for m in told)
    wait_for(lambda: power.lid_of("x") == 0, timeout=15)
    granted = [row for row in rows(program_with_pin.data_dir, "approval") if row["decision"] == "granted"]
    assert granted[-1]["action"] == "mission_mode.on" and granted[-1]["details"]["how"] == f"fingerprint on {phone.id}"
    # the same approval again: the request is gone, nothing more runs
    [again] = ask(phone, "command", command("link.approve", number=card["number"], signature=signed(key, phone, card)))
    assert "isn't waiting" in again["body"]


def test_fake_approvals_are_refused_and_nothing_runs(program_with_pin, tmp_path, power):
    phone = pair_phone(program_with_pin, tmp_path)
    key = SigningKey.generate()
    since = int(time.time()) - 1
    phone.send("command", command("mission_mode.on"))
    phone.replies(since, 30, until=lambda got: any("High tier" in m["body"] for m in got))
    [waiting] = program_with_pin.client.link_waiting()
    card = {"number": waiting["number"], "fingerprint": fingerprint(Action("mission_mode.on", {})),
            "expires": int(time.time() + waiting["seconds_left"])}
    [before] = ask(phone, "command", command("link.approve", number=card["number"], signature=signed(key, phone, card)))
    assert "isn't on for this phone" in before["body"]  # not enrolled: a signature means nothing

    enrolled(program_with_pin, phone, key)
    since = int(time.time()) - 1
    phone.send("command", command("mission_mode.on"))
    card = card_of(phone.replies(since, 30, until=lambda got: any("kairu_card" in m["body"] for m in got))[-1])
    stranger = SigningKey.generate()
    other = dict(card, fingerprint=fingerprint(Action("mission_mode.on", {"x": 1})))
    for fake in (signed(stranger, phone, card), signed(key, phone, other), signed(key, phone, dict(card, expires=card["expires"] + 60)),
                 b64(b"\0" * 64), "not base64!"):
        since = int(time.time()) - 1
        phone.send("command", command("link.approve", number=card["number"], signature=fake))
        told = phone.replies(since, 30, until=lambda got: any("Refused" in m["body"] or "can't be read" in m["body"] for m in got))
        assert any("Refused" in m["body"] or "can't be read" in m["body"] for m in told), told
        assert not any("Approved" in m["body"] for m in told)
    time.sleep(0.5)
    assert not running(program_with_pin, "mission_mode.on") and power.lid_of("x") == 1
    assert any(row["decision"] == "fingerprint refused" for row in rows(program_with_pin.data_dir, "link"))
    assert any(entry["number"] == card["number"] for entry in program_with_pin.client.link_waiting())  # still waiting
    since = int(time.time()) - 1
    phone.send("command", command("link.approve", number=card["number"], signature=signed(key, phone, card)))
    told = phone.replies(since, 30, until=lambda got: any("Approved with your fingerprint" in m["body"] for m in got))
    assert any("Approved with your fingerprint" in m["body"] for m in told)  # the real one still works, once


def test_a_phone_can_refuse_its_own_request_but_not_another_phones(program_with_pin, tmp_path):
    phone = pair_phone(program_with_pin, tmp_path)
    since = int(time.time()) - 1
    phone.send("command", command("mission_mode.on"))
    phone.replies(since, 30, until=lambda got: any("High tier" in m["body"] for m in got))
    [waiting] = program_with_pin.client.link_waiting()
    [reply] = ask(phone, "command", command("link.refuse", number=waiting["number"]))
    assert "Refused on your phone" in reply["body"] and program_with_pin.client.link_waiting() == []


def test_stop_from_the_phone_halts_everything_and_starts_safe_mode(program_with_pin, tmp_path):
    phone = pair_phone(program_with_pin, tmp_path)
    store = Store(program_with_pin.data_dir)
    before = safemode.stop_count(store)
    phone.send("command", command("guardian.stop"))
    wait_for(lambda: safemode.is_safe(store), timeout=20)
    assert safemode.stop_count(store) == before + 1 and phone.id in safemode.reason(store)
    wait_for(lambda: not running(program_with_pin, "link.receive"), timeout=10)  # the PC stops listening until `kairu resume`
    assert any(row["action"] == "guardian.stop" for row in audit.tail(store, 200, kind="link"))
