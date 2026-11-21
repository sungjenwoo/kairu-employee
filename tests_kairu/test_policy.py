"""Policy: tiers, unknown actions denied, Critical refused with no way around it."""

import dataclasses
import time

import pytest

from kairu import policy
from kairu.guardian import Action, Approval, Guardian, Refused, Verdict
from kairu.policy import Tier
from tests_kairu.helpers import PIN, POLICY

CRITICAL = [name for name, rule in policy.load(POLICY).rules.items() if rule.tier is Tier.CRITICAL]


def test_the_shipped_policy_has_every_tier():
    rules = policy.load(POLICY).rules
    assert {rule.tier for rule in rules.values()} == set(Tier)
    assert rules["chat.reply"].tier is Tier.LOW and rules["files.delete"].tier is Tier.HIGH


@pytest.mark.parametrize("name,verdict", [("chat.reply", Verdict.ALLOW), ("files.write", Verdict.ALLOW),
                                          ("files.delete", Verdict.NEEDS_APPROVAL), ("credentials.reveal", Verdict.DENY)])
def test_each_tier_gets_its_decision(guardian, name, verdict):
    assert guardian.check(name).verdict is verdict


@pytest.mark.parametrize("name", ["files.shred", "", "FILES.READ", "chat.reply.extra", "chat"])
def test_an_unknown_action_is_denied(guardian, runner, name):
    decision = guardian.check(name)
    assert decision.verdict is Verdict.DENY
    assert "not in the policy" in decision.reason
    assert guardian.authorize(name).verdict is Verdict.DENY
    with pytest.raises(Refused):
        runner.run(name, "kairu.demo:count", seconds=0)


@pytest.mark.parametrize("name", CRITICAL)
def test_a_critical_action_is_refused_and_nothing_unlocks_it(guardian, runner, with_pin, name):
    decision = guardian.check(Action(name, {"why": "I really mean it"}))
    assert decision.verdict is Verdict.DENY and decision.request_id is None
    assert "Critical" in decision.reason

    with pytest.raises(Refused):  # there is no request to approve, even with "yes" and the right PIN
        guardian.approve(decision.request_id, "yes", with_pin)
    forged = Approval(token="0" * 32, action=name, expires_at=time.time() + 60)
    assert guardian.authorize(name, forged).verdict is Verdict.DENY
    with pytest.raises(Refused):
        runner.run(name, "kairu.demo:count", approval=forged, seconds=0)


def test_critical_is_refused_even_when_an_approval_for_another_action_is_offered(guardian, with_pin):
    high = guardian.check("files.delete")
    approval = guardian.approve(high.request_id, "yes", PIN)
    assert guardian.authorize("credentials.reveal", approval).verdict is Verdict.DENY


def test_a_tier_cannot_be_changed_while_kairu_runs(guardian):
    with pytest.raises(TypeError):
        guardian.policy.rules["credentials.reveal"] = policy.Rule("credentials.reveal", Tier.LOW, "")
    with pytest.raises(dataclasses.FrozenInstanceError):
        guardian.policy.rules["credentials.reveal"].tier = Tier.LOW
    assert guardian.check("credentials.reveal").verdict is Verdict.DENY


def write_policy(tmp_path, text):
    path = tmp_path / "policy.yaml"
    path.write_text(text)
    return path


@pytest.mark.parametrize("text,problem", [
    ("version: 1\nactions:\n  files.delete: {tier: High}\n  files.delete: {tier: Low}\n", "listed twice"),
    ("version: 1\nactions:\n  files.delete: {tier: Severe}\n", "tier must be"),
    ("version: 1\nactions:\n  files.delete: {tier: Low, override: true}\n", "allowed keys"),
    ("version: 1\nactions:\n  voice.speak: {tier: Low, feature: camera}\n", "feature must be"),
    ("actions:\n  files.read: {tier: Low}\n", "version: 1"),
])
def test_a_policy_with_a_mistake_is_refused(tmp_path, text, problem):
    with pytest.raises(policy.PolicyError, match=problem):
        policy.load(write_policy(tmp_path, text))


def test_when_the_policy_cannot_be_read_every_action_is_denied(tmp_path, write_config):
    bad = write_policy(tmp_path, "version: 1\nactions:\n  chat.reply: {tier: Low}\n  chat.reply: {tier: Low}\n")
    from kairu import config
    guardian = Guardian(config.load(write_config(policy=bad)))
    assert guardian.policy is None
    for name in ("chat.reply", "files.read", "files.delete"):
        decision = guardian.check(name)
        assert decision.verdict is Verdict.DENY and "policy could not be read" in decision.reason


def test_when_a_decision_cannot_be_recorded_the_answer_is_deny(guardian, monkeypatch):
    from kairu import audit

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(audit, "record", broken)
    for name in ("chat.reply", "files.delete"):
        assert guardian.check(name).verdict is Verdict.DENY
        assert guardian.authorize(name).verdict is Verdict.DENY
