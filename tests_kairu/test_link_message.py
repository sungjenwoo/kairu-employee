"""Kairu Link messages (Phase C): signed, encrypted, and refused when unknown, tampered, badly signed, old or replayed.

Also: pairing requests, this PC's sealed keys, and the stand-in phone's own crypto checked against libsodium.
"""

import base64
import json
import os
import sys
import time

import pytest
from nacl.public import Box, PrivateKey
from nacl.signing import SigningKey

from kairu.link import keys, kinds, pairing, testclient
from kairu.link.message import Rejected, open_envelope, seal
from kairu.link.store import Device, LinkStore
from kairu.protect import sealed


@pytest.fixture
def pc():
    return keys.new_identity("pc")


@pytest.fixture
def phone():
    return keys.new_identity("dev")


@pytest.fixture
def store(tmp_path, phone):
    links = LinkStore(tmp_path)
    links.add_device(as_device(phone))
    return links


def as_device(identity, topic="0" * 32) -> Device:
    return Device(identity.id, "test phone", identity.sign_public, identity.box_public, topic, time.time())


def receive(envelope, pc, store, relay_time=None, now=None):
    return open_envelope(envelope, pc, store.device, store.new_nonce, relay_time, now)


def refused(envelope, pc, store, **when) -> str:
    with pytest.raises(Rejected) as caught:
        receive(envelope, pc, store, **when)
    return caught.value.problem


def test_a_message_from_a_paired_phone_opens_with_its_words_intact(pc, phone, store):
    body = "Kairu, ఈ రోజు వాతావరణం ఎలా ఉంది? Is my PC awake?"
    message = receive(seal(phone, pc.id, pc.box_public, "mission", body), pc, store)
    assert (message.sender, message.receiver, message.type, message.body) == (phone.id, pc.id, "mission", body)
    assert len(message.nonce) == 32 and len(message.digest) == 64


def test_the_relay_sees_two_ids_and_a_sealed_box_and_nothing_else(pc, phone):
    envelope = seal(phone, pc.id, pc.box_public, "command", '{"action": "demo.count"}')
    outer = json.loads(envelope)
    assert set(outer) == {"v", "from", "to", "box"} and (outer["from"], outer["to"]) == (phone.id, pc.id)
    assert "demo.count" not in envelope and b"demo.count" not in base64.b64decode(outer["box"])
    assert len(envelope) <= kinds.MAX_ENVELOPE_BYTES


def test_a_message_from_an_unpaired_device_is_refused_before_anything_is_opened(pc, phone, store):
    stranger = keys.new_identity("dev")
    assert refused(seal(stranger, pc.id, pc.box_public, "status", ""), pc, store) == "unknown_sender"


def test_a_stranger_using_a_paired_phones_id_cannot_open_the_box(pc, phone, store):
    stranger = keys.new_identity("dev")
    forged = json.loads(seal(stranger, pc.id, pc.box_public, "command", '{"action": "demo.count"}'))
    forged["from"] = phone.id  # claims to be the paired phone; its box was made with the stranger's key
    assert refused(json.dumps(forged), pc, store) == "tampered"


def test_a_changed_byte_is_noticed(pc, phone, store):
    outer = json.loads(seal(phone, pc.id, pc.box_public, "status", "hello"))
    boxed = bytearray(base64.b64decode(outer["box"]))
    boxed[60] ^= 0x01
    outer["box"] = base64.b64encode(bytes(boxed)).decode()
    assert refused(json.dumps(outer), pc, store) == "tampered"


def test_a_message_for_another_device_is_refused(pc, phone, store):
    other_pc = keys.new_identity("pc")
    assert refused(seal(phone, other_pc.id, other_pc.box_public, "status", ""), pc, store) == "wrong_receiver"


def test_a_box_from_the_phone_but_signed_by_another_key_is_refused(pc, phone, store):
    payload = json.dumps({"from": phone.id, "to": pc.id, "type": "command", "tier": "Low", "ts": int(time.time() * 1000),
                          "nonce": os.urandom(16).hex(), "body": "{}"}).encode()
    signed = SigningKey.generate().sign(payload).signature + payload  # not the phone's signing key
    boxed = Box(phone.private, PrivateKey(bytes(pc.private)).public_key).encrypt(signed)
    envelope = json.dumps({"v": 1, "from": phone.id, "to": pc.id, "box": base64.b64encode(boxed).decode()})
    assert refused(envelope, pc, store) == "bad_signature"


def test_messages_older_than_5_minutes_are_refused(pc, phone, store):
    now = time.time()
    assert refused(seal(phone, pc.id, pc.box_public, "status", "", now=now - 301), pc, store) == "expired"
    assert receive(seal(phone, pc.id, pc.box_public, "status", "", now=now - 240), pc, store).type == "status"
    assert refused(seal(phone, pc.id, pc.box_public, "status", "", now=now + 120), pc, store) == "from_future"


def test_a_message_received_twice_is_refused_the_second_time(pc, phone, store, tmp_path):
    envelope = seal(phone, pc.id, pc.box_public, "command", '{"action": "demo.count"}')
    receive(envelope, pc, store)
    assert refused(envelope, pc, store) == "replayed"
    assert refused(envelope, pc, LinkStore(tmp_path)) == "replayed"  # remembered on disk, across restarts


def test_queued_types_may_wait_in_the_gate_but_commands_may_not(pc, phone, store):
    """C3: a mission that reached the Gate in time may be read hours later; a command must still be fresh."""
    signed_at = time.time() - 2 * 3600  # sent while the PC was off, two hours ago
    mission = seal(phone, pc.id, pc.box_public, "mission", "while I was away", now=signed_at)
    assert receive(mission, pc, store, relay_time=signed_at + 3).type == "mission"
    command = seal(phone, pc.id, pc.box_public, "command", '{"action": "demo.count"}', now=signed_at)
    assert refused(command, pc, store, relay_time=signed_at + 3) == "expired"
    late = seal(phone, pc.id, pc.box_public, "mission", "held back by the relay", now=signed_at)
    assert refused(late, pc, store, relay_time=signed_at + 400) == "expired"  # reached the Gate 6+ minutes after signing
    old = seal(phone, pc.id, pc.box_public, "mission", "", now=time.time() - 13 * 3600)
    assert refused(old, pc, store, relay_time=time.time() - 13 * 3600) == "expired"


def test_nonces_are_kept_longer_than_any_message_stays_acceptable(pc, phone, store):
    signed_at = time.time() - 3600
    mission = seal(phone, pc.id, pc.box_public, "mission", "", now=signed_at)
    receive(mission, pc, store, relay_time=signed_at)
    assert refused(mission, pc, store, relay_time=signed_at, now=time.time() + kinds.QUEUE_SECONDS - 3700) == "replayed"
    assert kinds.NONCE_SECONDS > kinds.QUEUE_SECONDS > kinds.MAX_AGE_SECONDS


@pytest.mark.parametrize("envelope", ["not json", "[]", '{"v": 2, "from": "dev-0000000000000000", "to": "x", "box": ""}',
                                      '{"v": 1, "from": "dev-0000000000000000", "to": "x", "box": "", "tier": "Low"}',
                                      "x" * 5000], ids=["text", "list", "version", "extra field", "too long"])
def test_anything_else_is_refused_as_malformed(pc, store, envelope):
    assert refused(envelope, pc, store) == "malformed"


def test_the_message_tier_and_type_must_be_known_words(pc, phone, store):
    with pytest.raises(ValueError):
        seal(phone, pc.id, pc.box_public, "approve", "")
    with pytest.raises(ValueError):
        seal(phone, pc.id, pc.box_public, "status", "", tier="Root")
    with pytest.raises(ValueError):
        seal(phone, pc.id, pc.box_public, "mission", "x" * (kinds.MAX_BODY_BYTES + 1))


# --- the stand-in phone's crypto, against libsodium -----------------------------------------------------

def test_the_stand_in_phones_crypto_matches_libsodium():
    for size in (0, 1, 63, 64, 65, 1000, 3000):
        seed, secret, message = os.urandom(32), os.urandom(32), os.urandom(size)
        assert testclient.ed25519_public(seed) == bytes(SigningKey(seed).verify_key)
        assert testclient.ed25519_sign(seed, message) == SigningKey(seed).sign(message).signature
        assert testclient.ed25519_verify(bytes(SigningKey(seed).verify_key), message, SigningKey(seed).sign(message).signature)
        assert not testclient.ed25519_verify(bytes(SigningKey(seed).verify_key), message + b"!",
                                             SigningKey(seed).sign(message).signature)
        assert testclient.x25519_public(secret) == bytes(PrivateKey(secret).public_key)
        a, b = PrivateKey.generate(), PrivateKey.generate()
        assert testclient.box_decrypt(bytes(b), bytes(a.public_key), bytes(Box(a, b.public_key).encrypt(message))) == message
        assert Box(a, b.public_key).decrypt(testclient.box_encrypt(bytes(b), bytes(a.public_key), message)) == message
        broken = bytearray(testclient.box_encrypt(bytes(b), bytes(a.public_key), message))
        broken[30] ^= 1
        with pytest.raises(ValueError):
            testclient.box_decrypt(bytes(a), bytes(b.public_key), bytes(broken))


def test_the_stand_in_phone_and_the_pc_understand_each_other(pc, tmp_path):
    phone = testclient.Phone(tmp_path / "phone.json")
    phone.state.update(pc={"id": pc.id, "sign": base64.b64encode(pc.sign_public).decode(),
                           "box": base64.b64encode(pc.box_public).decode()})
    links = LinkStore(tmp_path / "pc")
    links.add_device(Device(phone.id, "stand-in", phone.sign_public, phone.box_public, "1" * 32, time.time()))
    message = receive(phone.envelope("status", "how are you?"), pc, links)
    assert (message.sender, message.body) == (phone.id, "how are you?")
    answer = phone.open(seal(pc, phone.id, phone.box_public, "report", "fine, thank you"))
    assert (answer["type"], answer["body"]) == ("report", "fine, thank you")
    replayed = seal(pc, phone.id, phone.box_public, "report", "once")
    phone.open(replayed)
    with pytest.raises(ValueError, match="replay"):
        phone.open(replayed)


# --- pairing requests ---------------------------------------------------------------------------------

def offer_for(pc) -> dict:
    return testclient.Phone.read_offer(pairing.offer_text(pc, "2" * 32, "https://ntfy.sh", time.time() + 600))


def test_a_pairing_request_with_the_right_code_gives_the_device_its_own_new_topic(pc, tmp_path):
    phone = testclient.Phone(tmp_path / "phone.json")
    device = pairing.open_request(phone.pair_request(offer_for(pc), "123456", "Sai's\x1b[31m phone"), pc, "123456")
    assert (device.id, device.sign, device.box) == (phone.id, phone.sign_public, phone.box_public)
    assert device.name == "Sai's[31m phone"  # no control characters reach your terminal
    assert kinds.TOPIC.fullmatch(device.topic) and device.topic != "2" * 32


def test_a_pairing_request_with_a_wrong_code_counts_as_a_try(pc, tmp_path):
    phone = testclient.Phone(tmp_path / "phone.json")
    with pytest.raises(pairing.NotAPairing) as caught:
        pairing.open_request(phone.pair_request(offer_for(pc), "654321", "phone"), pc, "123456")
    assert caught.value.wrong_code


def test_an_old_or_mismatched_pairing_request_is_refused(pc, tmp_path):
    phone = testclient.Phone(tmp_path / "phone.json")
    with pytest.raises(pairing.NotAPairing):
        pairing.open_request(phone.pair_request(offer_for(pc), "123456", "phone", age=400), pc, "123456")
    forged = json.loads(phone.pair_request(offer_for(pc), "123456", "phone"))
    forged["pair"] = "dev-0123456789abcdef"  # an id that is not made from its key
    with pytest.raises(pairing.NotAPairing) as caught:
        pairing.open_request(json.dumps(forged), pc, "123456")
    assert not caught.value.wrong_code
    other_pc = keys.new_identity("pc")
    with pytest.raises(pairing.NotAPairing):
        pairing.open_request(phone.pair_request(offer_for(pc), "123456", "phone"), other_pc, "123456")


def test_the_pairing_code_is_not_in_the_qr_code(pc):
    text = pairing.offer_text(pc, "2" * 32, "https://ntfy.sh", time.time() + 600)
    assert set(testclient.Phone.read_offer(text)) == {"pc", "sign", "box", "topic", "relay", "expires"}


# --- this PC's keys -----------------------------------------------------------------------------------

def test_the_pcs_keys_are_made_once_and_kept_sealed(tmp_path):
    made = keys.load_or_create(tmp_path)
    assert keys.load_or_create(tmp_path).id == made.id == keys.device_id(made.sign_public, "pc")
    raw = (tmp_path / keys.KEY_NAME).read_bytes()
    if sys.platform == "win32":  # DPAPI: the private keys are not in the file as written
        assert base64.b64encode(bytes(made.signing)) not in raw and base64.b64encode(bytes(made.private)) not in raw
        with pytest.raises(sealed.SealBroken):
            sealed.read(tmp_path / keys.KEY_NAME)  # sealed for the Link, so the Gmail key's purpose cannot open it
    else:
        assert (tmp_path / keys.KEY_NAME).stat().st_mode & 0o077 == 0
