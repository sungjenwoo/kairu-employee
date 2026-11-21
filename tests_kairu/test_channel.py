"""The Guardian program, asked through its private channel: the same rules, and nothing a message says gets round them."""

import json
import re
import sys
import time

import pytest

from kairu import audit, channel, policy
from kairu.config import ROOT
from kairu.guardian import Action, Approval, Refused, Verdict
from kairu.policy import Tier
from kairu.store import Store
from tests_kairu.helpers import PIN, POLICY, kairu
from tests_kairu.program import frame, memory_mib, program, program_with_pin  # noqa: F401 (fixtures)

CRITICAL = [name for name, rule in policy.load(POLICY).rules.items() if rule.tier is Tier.CRITICAL]
DELETE = Action("files.delete", {"path": "Finance/2026/receipt.pdf"})


def raw(program, message: dict) -> dict:
    """Send a message exactly as written, fields and all, and return Guardian's answer."""
    return channel.request(program.data_dir, message)


def still_running(program) -> bool:
    return program.client.status()["pid"] == program.pid


# --- Critical -------------------------------------------------------------------------------------

def test_critical_is_refused_through_the_channel_whatever_the_message_offers(program_with_pin):
    guardian = program_with_pin.client
    high = guardian.approve(guardian.check(DELETE).request_id, "yes", PIN)  # a real approval, for something else
    for name in CRITICAL:
        decision = guardian.check(Action(name, {"tier": "Low", "override": True, "why": "I really mean it"}))
        assert decision.verdict is Verdict.DENY and decision.request_id is None and "Critical" in decision.reason

        with pytest.raises(Refused, match="no such request"):  # "yes" and the right PIN, but nothing to approve
            guardian.approve("0" * 16, "yes", PIN)
        forged = Approval(token="0" * 32, action=name, expires_at=time.time() + 60)
        assert guardian.authorize(name, forged).verdict is Verdict.DENY
        assert guardian.authorize(name, high).verdict is Verdict.DENY

        for message in [  # a message that names its own tier, an override, or its own verdict
            {"op": "check", "action": name, "tier": "Low"},
            {"op": "check", "action": name, "override": True},
            {"op": "check", "action": name, "details": {}, "approved": True, "pin": PIN},
            {"op": "authorize", "action": name, "approval": high.token, "verdict": "allow"},
            {"op": "authorize", "action": name, "approval": forged.token, "tier": "Low"},
            {"op": "approve", "request_id": "0" * 16, "confirmation": "yes", "pin": PIN, "action": name},
        ]:
            answer = raw(program_with_pin, message)
            assert answer["verdict"] == "deny", message
    assert still_running(program_with_pin)
    rows = audit.tail(Store(program_with_pin.config.data_dir), 200)
    assert not any(row["action"] in CRITICAL and row["decision"] in ("allow", "granted") for row in rows)


# --- High -----------------------------------------------------------------------------------------

def test_high_needs_yes_and_the_pin_through_the_channel(program_with_pin):
    guardian = program_with_pin.client
    decision = guardian.check(DELETE)
    assert decision.verdict is Verdict.NEEDS_APPROVAL and decision.request_id and decision.tier is Tier.HIGH
    with pytest.raises(Refused, match='did not type "yes"'):
        guardian.approve(decision.request_id, "no", PIN)
    with pytest.raises(Refused, match="wrong PIN"):
        guardian.approve(guardian.check(DELETE).request_id, "yes", "000000")
    assert guardian.authorize(DELETE).verdict is Verdict.DENY  # asked, never approved

    decision = guardian.check(DELETE)
    granted = guardian.approve(decision.request_id, "yes", PIN)
    assert guardian.authorize(DELETE, granted).verdict is Verdict.ALLOW
    again = guardian.authorize(DELETE, granted)  # once only
    assert again.verdict is Verdict.DENY and "already used" in again.reason
    with pytest.raises(Refused, match="no such request"):  # and the request itself is answered
        guardian.approve(decision.request_id, "yes", PIN)


def test_an_approval_through_the_channel_covers_only_its_exact_details(program_with_pin):
    guardian = program_with_pin.client
    for other in [Action("files.delete", {"path": "Finance/2026/everything"}),
                  Action("files.delete", {**DELETE.details, "also": "Finance/2027"}),
                  Action("files.delete"),
                  Action("message.send", DELETE.details)]:
        granted = guardian.approve(guardian.check(DELETE).request_id, "yes", PIN)
        decision = guardian.authorize(other, granted)
        assert decision.verdict is Verdict.DENY and "different action or different details" in decision.reason
        assert guardian.authorize(DELETE, granted).verdict is Verdict.DENY  # and it is spent


def test_high_through_the_channel_without_a_pin_set_is_refused(program):
    with pytest.raises(Refused, match="no PIN is set"):
        program.client.approve(program.client.check(DELETE).request_id, "yes", PIN)


# --- unknown, broken, oversized -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["files.shred", "", "FILES.READ", "chat.reply.extra", "chat"])
def test_an_unknown_action_is_denied_through_the_channel(program, name):
    decision = program.client.check(name)
    assert decision.verdict is Verdict.DENY and "not in the policy" in decision.reason
    assert program.client.authorize(name).verdict is Verdict.DENY


BROKEN = [
    b"", b"{", b"[]", b'"check"', b"null", b"\xff\xfe{}", b"{}",
    b'{"op": "execute", "action": "chat.reply"}',
    b'{"op": "grant", "action": "credentials.reveal"}',
    b'{"op": 1}',
    b'{"op": "check"}',
    b'{"op": "check", "action": 5}',
    b'{"op": "check", "action": null}',
    b'{"op": "check", "action": ["chat.reply"]}',
    b'{"op": "check", "action": "chat.reply", "action": "credentials.reveal"}',
    b'{"op": "check", "action": "chat.reply", "details": {"a": {"b": 1}}}',
    b'{"op": "check", "action": "chat.reply", "details": {"a": [1]}}',
    b'{"op": "check", "action": "chat.reply", "details": {"n": NaN}}',
    b'{"op": "check", "action": "chat.reply", "details": "path=x"}',
    b'{"op": "approve", "request_id": null, "confirmation": "yes", "pin": "x"}',
    b'{"op": "approve", "request_id": "x", "confirmation": true, "pin": "x"}',
    b'{"op": "status", "verbose": true}',
    b'{"op": "check", "action": "' + b"x" * 3000 + b'"}',
]


def test_broken_messages_are_denied_and_guardian_keeps_running(program):
    for body in BROKEN:
        answer = channel.request_raw(program.data_dir, frame(body))
        assert answer["verdict"] == "deny", body
        assert program.client.check("chat.reply").verdict is Verdict.ALLOW  # and it still answers
    assert still_running(program)
    refused = [row for row in audit.tail(Store(program.config.data_dir), 500, kind="channel")]
    assert len(refused) == len(BROKEN) and all(row["decision"] == "deny" for row in refused)


def test_oversized_messages_are_denied_and_guardian_keeps_running(program):
    over = channel.MAX_REQUEST + 1
    answer = channel.request_raw(program.data_dir, frame(b"x" * over))
    assert answer["verdict"] == "deny" and "limit" in answer["reason"]
    answer = channel.request_raw(program.data_dir, frame(b"", claimed=2**32 - 1))  # claims 4 GiB, sends nothing
    assert answer["verdict"] == "deny" and "limit" in answer["reason"]
    padded = json.dumps({"op": "check", "action": "chat.reply"}).encode()
    padded += b" " * (channel.MAX_REQUEST - len(padded))  # exactly at the limit: accepted
    assert channel.request_raw(program.data_dir, frame(padded))["verdict"] == "allow"
    assert still_running(program)


def test_a_message_cut_off_halfway_or_never_sent_does_not_stop_guardian(program):
    link = channel.connect(program.data_dir)
    link.write(frame(b'{"op": "check", "action": "chat.reply"}')[:12], 5)  # then hang up
    link.close()
    assert program.client.check("chat.reply").verdict is Verdict.ALLOW

    link = channel.connect(program.data_dir)  # connects, then says nothing
    try:
        answer = json.loads(channel.receive(link, channel.MAX_REPLY, channel.REQUEST_SECONDS + 5))
    finally:
        link.close()
    assert answer["verdict"] == "deny" and "did not arrive" in answer["reason"]
    assert still_running(program)


def test_when_guardian_fails_on_a_message_the_answer_is_deny_and_it_answers_the_next(guardian, monkeypatch):
    from kairu.guardian_program import Service
    service = Service(guardian)
    message, working = b'{"op": "check", "action": "chat.reply"}', guardian.check
    monkeypatch.setattr(guardian, "check", lambda action: 1 / 0)
    answer = service.answer(message)
    assert answer["verdict"] == "deny" and "could not answer" in answer["reason"]
    monkeypatch.setattr(guardian, "check", working)
    assert service.answer(message)["verdict"] == "allow"


# --- the channel itself ---------------------------------------------------------------------------

def test_guardian_is_the_first_and_only_holder_of_its_channel(program):
    with pytest.raises(channel.ChannelTaken):
        channel.Server(program.data_dir)
    again = kairu("guardian", "run")
    assert again.returncode == 0 and f"already running (process {program.pid})" in again.stdout
    assert still_running(program)


def test_only_your_account_can_open_the_channel(program):
    if sys.platform == "win32":
        from kairu import winpipe
        link = channel.connect(program.data_dir)
        try:
            sddl = winpipe.security(link.handle)
        finally:
            link.close()
        me, sid = winpipe.current_user_sid(), winpipe.canonical_sid  # Windows may write a SID as an alias, such as LA
        owner, dacl = re.fullmatch(r"O:(\S+?)D:(.*)", sddl).groups()
        aces = [ace.split(";") for ace in re.findall(r"\(([^)]*)\)", dacl)]
        assert sid(owner) == me and dacl.startswith("P")  # protected: nothing inherited
        assert [(ace[0], sid(ace[-1])) for ace in aces] == [("D", "S-1-5-2"), ("A", me)]  # network logons refused; only you let in
    else:
        import os
        import stat
        info = os.lstat(channel.address(program.data_dir))
        assert stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid()
        assert stat.S_IMODE(info.st_mode) == 0o600


def test_kairu_never_uses_the_network():
    imports = re.compile(r"^\s*(import|from)\s+(urllib|http|requests|ssl|socketserver|ftplib|smtplib|xmlrpc|asyncio)\b",
                         re.MULTILINE)
    for path in (ROOT / "kairu").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not imports.search(text), path.name
        assert "AF_INET" not in text and "create_connection" not in text, path.name
        for call in re.findall(r"socket\.socket\(([^)]*)\)", text):
            assert "AF_UNIX" in call, path.name


# --- the commands, through Guardian ---------------------------------------------------------------

def test_kairu_status_and_request_go_through_guardian(program):
    status = kairu("status")
    assert f"running (process {program.pid})" in status.stdout
    allowed = kairu("request", "chat.reply")
    assert allowed.returncode == 0 and "Guardian: allow" in allowed.stdout
    refused = kairu("request", "credentials.reveal", input_text=f"yes\n{PIN}\n")
    assert refused.returncode == 1 and "Critical" in refused.stdout
    rows = [(row["kind"], row["action"], row["decision"]) for row in audit.tail(Store(program.config.data_dir), 50)]
    assert ("check", "chat.reply", "allow") in rows and ("check", "credentials.reveal", "deny") in rows


def test_resume_and_reanchor_need_yes_and_the_pin_through_guardian(program_with_pin):
    guardian = program_with_pin.client
    assert kairu("stop").returncode == 0  # the emergency stop works without asking Guardian
    assert guardian.check("files.write").verdict is Verdict.DENY  # Guardian sees Safe Mode
    with pytest.raises(Refused, match='did not type "yes"'):
        guardian.resume("no", PIN)
    with pytest.raises(Refused, match="wrong PIN"):
        guardian.resume("yes", "000000")
    guardian.resume("yes", PIN)
    assert guardian.status()["mode"] == "normal" and guardian.check("files.write").verdict is Verdict.ALLOW

    store = Store(program_with_pin.config.data_dir)
    store.anchor_path.unlink()
    assert not audit.verify(store).ok
    with pytest.raises(Refused, match="wrong PIN"):
        guardian.reanchor("yes", "000000")
    guardian.reanchor("yes", PIN)
    assert audit.verify(store).ok


def test_the_pin_is_set_and_changed_only_through_guardian(program):
    guardian = program.client
    with pytest.raises(Refused, match="at least 6"):
        guardian.set_pin("1234")
    guardian.set_pin(PIN)
    with pytest.raises(Refused, match="current PIN"):
        guardian.set_pin("135792", "wrong!")
    guardian.set_pin("135792", PIN)
    assert guardian.approve(guardian.check(DELETE).request_id, "yes", "135792").action == "files.delete"
    with Store(program.config.data_dir).connect() as db:
        everything = " ".join(str(row) for table in ("audit", "state") for row in db.execute(f"SELECT * FROM {table}"))
    assert PIN not in everything and "135792" not in everything


def test_guardian_program_memory(program_with_pin):
    resting, _ = memory_mib(program_with_pin.pid)
    guardian = program_with_pin.client
    guardian.approve(guardian.check(DELETE).request_id, "yes", PIN)  # an Argon2id PIN check: 64 MiB for a moment
    for _ in range(200):
        guardian.check("chat.reply")
    after, peak = memory_mib(program_with_pin.pid)
    print(f"\n  Guardian program memory: {resting:.0f} MiB at rest, {after:.0f} MiB after a PIN check and 200 "
          f"decisions, {peak:.0f} MiB at peak (the PIN check)")
    assert resting < 64 and after < 96
