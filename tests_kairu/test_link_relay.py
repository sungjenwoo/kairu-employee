"""The Gate's relay client (ntfy) and the receiver, against a stand-in relay on this PC: publish, long poll, the
queue, "too many requests", and what the receiver tells Guardian. No Guardian program here (test_link_program.py)."""

import json
import threading
import time

import pytest
import yaml

from kairu import config as kairu_config
from kairu.link import keys, receive
from kairu.link.message import seal
from kairu.link.relay import Backoff, RateLimited, Relay, RelayError
from kairu.link.store import Device, LinkStore
from tests_kairu.fake_relay import FakeRelay
from tests_kairu.helpers import wait_for

TOPIC, OTHER = "a" * 32, "b" * 32


@pytest.fixture
def relay():
    fake = FakeRelay(keepalive=0.2)
    yield fake
    fake.close()


def test_publish_then_read_what_waits_and_then_what_comes(relay):
    gate = Relay(relay.url)
    first = gate.publish(TOPIC, "one")
    assert first["event"] == "message" and [m["message"] for m in gate.poll([TOPIC])] == ["one"]
    got = []
    subscription = gate.subscribe([TOPIC, OTHER], since=first["time"] - 1)

    def read():
        for event in subscription:
            if event.get("event") == "message":
                got.append(event["message"])

    reader = threading.Thread(target=read)
    reader.start()
    gate.publish(OTHER, "two")
    wait_for(lambda: got == ["one", "two"], timeout=5)
    started = time.monotonic()
    subscription.close()  # from another thread: the long poll ends at once
    reader.join(5)
    assert not reader.is_alive() and time.monotonic() - started < 2


def test_too_many_requests_is_told_with_the_relays_wait_and_backoff_grows(relay):
    relay.refuse_next, relay.retry_after = 2, 7
    gate = Relay(relay.url)
    with pytest.raises(RateLimited) as caught:
        gate.publish(TOPIC, "x")
    assert caught.value.retry_after == 7
    with pytest.raises(RateLimited):
        gate.subscribe([TOPIC])
    assert gate.publish(TOPIC, "x")["message"] == "x"
    backoff = Backoff()
    assert [backoff.next() for _ in range(4)] == [2, 4, 8, 16]
    assert backoff.next(retry_after=60) == 60 and Backoff().next(rate_limited=True) == 10
    assert max(backoff.next() for _ in range(20)) == 300


def test_only_gate_topics_and_relay_addresses_are_accepted(relay):
    gate = Relay(relay.url)
    for bad in ("short", "../" + "a" * 29, "A" * 32, "a" * 31 + "/"):
        with pytest.raises(RelayError):
            gate.publish(bad, "x")
    with pytest.raises(RelayError):
        Relay("ftp://ntfy.sh")
    with pytest.raises(RelayError):
        Relay("http://127.0.0.1:1").publish(TOPIC, "x")  # nothing listens there


def test_config_takes_the_relay_and_mission_limits(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"link": {"enabled": True, "relay": "http://192.168.1.20:8080/"},
                                    "mission_mode": {"max_hours": 2, "cpu_percent": 70}}))
    cfg = kairu_config.load(path)
    assert (cfg.link_enabled, cfg.link_relay, cfg.mission_max_hours, cfg.mission_cpu_percent, cfg.mission_max_celsius) == \
        (True, "http://192.168.1.20:8080", 2.0, 70.0, 85.0)
    assert kairu_config.load(tmp_path / "missing.yaml").link_relay == "https://ntfy.sh"
    for bad in ({"link": {"relay": "https://ntfy.sh?x=1"}}, {"link": {"relay": "javascript:alert(1)"}},
                {"link": {"enabled": "yes"}}, {"link": {"topic": "x"}}, {"mission_mode": {"max_hours": 48}},
                {"mission_mode": {"cpu_percent": 5}}):
        path.write_text(yaml.safe_dump(bad))
        with pytest.raises(kairu_config.ConfigError):
            kairu_config.load(path)


# --- the receiver, with a stand-in for Guardian ------------------------------------------------------

@pytest.fixture
def paired(tmp_path):
    pc = keys.load_or_create(tmp_path)
    phone = keys.new_identity("dev")
    LinkStore(tmp_path).add_device(Device(phone.id, "phone", phone.sign_public, phone.box_public, TOPIC, time.time() - 60))
    return pc, phone


@pytest.fixture
def receivers():
    started = []
    yield started
    for receiver in started:
        receiver.close()


def run_receiver(tmp_path, relay, told, receivers, sleep=None):
    receiver = receive.Receiver(str(tmp_path), relay.url, tell=told.append, sleep=sleep)
    receivers.append(receiver)
    thread = threading.Thread(target=receiver.run, daemon=True)
    thread.start()
    return receiver, thread


def test_the_receiver_reads_what_waited_first_then_tells_guardian_only_the_request(tmp_path, relay, paired, receivers):
    pc, phone = paired
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "mission", "Book the train, my PIN is 482916"))
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "command", json.dumps(
        {"action": "demo.count", "details": {"seconds": 2}})))
    told = []
    run_receiver(tmp_path, relay, told, receivers)
    wait_for(lambda: len(told) == 2, timeout=10)
    mission, command = told
    assert set(mission) == {"op", "device", "type", "digest"} and mission["type"] == "mission"
    assert "482916" not in json.dumps(told) and "train" not in json.dumps(told)  # the words stay here
    assert (command["action"], command["details"]) == ("demo.count", {"seconds": 2})
    relay.publish(TOPIC, seal(pc, phone.id, phone.box_public, "report", "the PC's own reply"))  # skipped quietly
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "status", ""))
    wait_for(lambda: len(told) == 3, timeout=10)
    assert told[2]["type"] == "status"


def test_the_receiver_refuses_replays_and_strangers_and_says_why(tmp_path, relay, paired, receivers):
    pc, phone = paired
    envelope = seal(phone, pc.id, pc.box_public, "status", "")
    relay.publish(TOPIC, envelope)
    relay.publish(TOPIC, envelope)  # the same message, posted again
    stranger = keys.new_identity("dev")
    relay.publish(TOPIC, seal(stranger, pc.id, pc.box_public, "command", '{"action": "security.disable"}'))
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "command", "not json"))
    relay.publish(TOPIC, "hello")
    told = []
    run_receiver(tmp_path, relay, told, receivers)
    wait_for(lambda: len(told) == 5, timeout=10)
    assert [(t["type"], t.get("problem"), t["device"]) for t in told] == [
        ("status", None, phone.id), ("?", "replayed", phone.id), ("?", "unknown_sender", ""),
        ("command", "malformed", phone.id), ("?", "malformed", "")]


def test_the_receiver_never_handles_a_gate_message_twice_after_a_reconnect(tmp_path, relay, paired, receivers):
    pc, phone = paired
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "status", ""))
    told = []
    receiver, _ = run_receiver(tmp_path, relay, told, receivers)
    wait_for(lambda: len(told) == 1, timeout=10)
    newer = keys.new_identity("dev")  # pairing a device makes the receiver read again, from its cursor
    LinkStore(tmp_path).add_device(Device(newer.id, "tablet", newer.sign_public, newer.box_public, OTHER, time.time()))
    wait_for(lambda: sum(1 for method, path in relay.requests if method == "GET") >= 2, timeout=10)
    relay.publish(OTHER, seal(newer, pc.id, pc.box_public, "status", ""))
    wait_for(lambda: len(told) == 2, timeout=10)
    time.sleep(0.5)
    assert [t["device"] for t in told] == [phone.id, newer.id] and not any(t.get("problem") for t in told)


def test_the_receiver_ends_by_itself_when_no_device_is_paired(tmp_path, relay, paired, receivers):
    pc, phone = paired
    told = []
    receiver, thread = run_receiver(tmp_path, relay, told, receivers)
    wait_for(lambda: any(method == "GET" for method, _ in relay.requests), timeout=10)
    LinkStore(tmp_path).remove_device(phone.id)
    thread.join(10)
    assert not thread.is_alive()
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "status", ""))
    time.sleep(0.3)
    assert told == []


def test_the_receiver_waits_and_tries_again_when_the_relay_says_too_many_requests(tmp_path, relay, paired, receivers):
    pc, phone = paired
    waits = []
    relay.refuse_next, relay.retry_after = 2, 3
    relay.publish(TOPIC, seal(phone, pc.id, pc.box_public, "status", ""))
    told = []
    run_receiver(tmp_path, relay, told, receivers, sleep=waits.append)
    wait_for(lambda: len(told) == 1, timeout=10)
    assert waits[:2] == [10, 20]  # rate limited: at least 10 s, then longer, never hammering the relay


# --- Guardian's side, in this process ---------------------------------------------------------------

def test_the_phones_status_no_longer_counts_a_request_whose_10_minutes_passed(guardian):
    """Seen in the gate test: at 18:45 the status said "Waiting for your PIN: 1" for a request that ended at 18:42."""
    from kairu import audit
    from kairu.guardian_program import PhoneRequest, Service
    service = Service(guardian)
    try:
        phone = "dev-0123456789abcdef"
        service.phone_waiting[1] = PhoneRequest(1, phone, "device.pair", {}, "a" * 64, "Pair", time.time() - 1)
        service.phone_waiting[2] = PhoneRequest(2, phone, "device.pair", {}, "b" * 64, "Pair", time.time() + 600)
        assert "Waiting for your PIN: 1." in service.phone_status()
        assert list(service.phone_waiting) == [2]
        ended = [row for row in audit.tail(guardian.store, 50, kind="link") if row["decision"] == "approval expired"]
        assert [row["details"]["digest"] for row in ended] == ["a" * 64]
    finally:
        service.close()
