"""Phase B's entries in the policy: their tiers, and the `private` key that keeps your words out of the audit log."""

import pytest

from kairu import audit, executors, policy
from kairu.guardian import Action, Verdict
from kairu.policy import Tier
from tests_kairu.helpers import PIN, POLICY

RULES = policy.load(POLICY).rules
BAR_SKILLS = ("apps.list_open", "apps.open", "apps.close", "apps.arrange", "files.rename", "task.undo", "system.volume",
              "system.brightness", "system.wifi", "system.status", "system.lock", "system.sleep", "system.restart", "system.shutdown")
DAY_4 = ("files.find", "files.move", "files.delete", "web.open", "web.search", "web.search_private", "task.wait", "brain.plan", "task.plan")


@pytest.mark.parametrize("name,tier", [
    ("brain.ask", Tier.LOW), ("brain.send_private", Tier.HIGH), ("provider.add", Tier.HIGH),
    ("provider.remove", Tier.LOW), ("provider.pause", Tier.LOW), ("mission.create", Tier.LOW), ("mission.run", Tier.LOW),
    ("mission.stop", Tier.LOW), ("mission.continue", Tier.LOW), ("mission.remove", Tier.LOW),
])
def test_phase_b_actions_have_the_planned_tiers(name, tier):
    assert RULES[name].tier is tier and not RULES[name].read_only


def test_your_words_are_kept_as_a_hash_wherever_they_are_details():
    assert {name for name, rule in RULES.items() if rule.private} == {"brain.ask", "brain.send_private", "mission.create",
                                                                       "link.send", "research.web_search",
                                                                       "research.web_read", "research.weather", "research.location", *BAR_SKILLS,
                                                                       "voice.listen", "voice.speak", *DAY_4,
                                                                       "files.write", "files.open", "files.show",  # W2
                                                                       "task.order",  # D3
                                                                       "shadow.create", "pack.run",  # Phase H
                                                                       "screen.read", "screen.type", "screen.press",  # PC4 hands
                                                                       "screen.click", "screen.confirm",
                                                                       "screen.read_text", "screen.numbers",  # PC4, the rest
                                                                       "memory.remember", "memory.forget",  # M1
                                                                       "web.read_page", "web.ask", "web.ask_private",  # ASK.md
                                                                       "team.add", "team.split", "team.note",  # Clones (TEAM.md, ADR-048)
                                                                       "terminal.run", "terminal.run_work", "terminal.run_any",  # PC5
                                                                       "apps.install", "apps.uninstall",
                                                                       "meeting.read", "meeting.record", "meeting.show", "meeting.forget",  # Meeting in (ADR-055)
                                                                           "meeting.check", "meeting.ask", "meeting.resolve",  # stage 2
                                                                           "meeting.brief",  # stage 5
                                                                       "build.draft", "build.write", "build.test",  # the Builder
                                                                       "forge.draft", "forge.test", "forge.save", "forge.forget",
                                                                       "paths.draft",
                                                                       "screen.look",  # Kairu's eyes (ADR-051)
                                                                       "live.talk",  # Kairu Live (ADR-052)
                                                                       # the screen agent, finished (ADR-054)
                                                                       "screen.scroll", "screen.choose", "screen.tick",
                                                                       "screen.point", "screen.fill", "screen.saved_password",
                                                                       "screen.agent_confirm", "details.keep", "details.forget",
                                                                       "details.show"}


def test_every_action_guardian_can_run_is_in_the_policy():
    assert set(executors.EXECUTORS) <= set(RULES)


def test_a_private_actions_details_never_reach_the_audit_log(guardian, with_pin):
    question = "my friend Ravi's number is 9876543210, what should I tell him"
    asked = guardian.check(Action("brain.ask", {"question": question, "ask": "0" * 16, "source": "pc"}))
    assert asked.verdict is Verdict.ALLOW
    high = guardian.check(Action("brain.send_private", {"question": question, "provider": "groq", "ask": "1" * 16,
                                                        "source": "pc"}))
    guardian.approve(high.request_id, "yes", PIN)
    logged = str(audit.tail(guardian.store, 50))
    assert "Ravi" not in logged and "9876543210" not in logged and logged.count("details_sha256") == 3


def test_private_is_only_about_logging_never_a_decision(guardian):
    plain = guardian.check(Action("provider.add", {"provider": "groq"}))
    marked = guardian.check(Action("provider.add", {"provider": "groq"}, private=True))
    assert plain.verdict is marked.verdict is Verdict.NEEDS_APPROVAL


def test_a_policy_with_a_wrong_private_is_refused(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("version: 1\nactions:\n  chat.reply: {tier: Low, private: maybe}\n")
    with pytest.raises(policy.PolicyError, match="private must be true or false"):
        policy.load(path)


def test_without_a_brain_section_every_cloud_send_waits(config):
    """Fail closed: option A is on only where config.yaml says so (the shipped one does)."""
    from kairu import config as kairu_config
    from kairu.config import ROOT
    assert config.brain_public_to_cloud is False and config.brain_settings()["providers"] == ["groq", "cloudflare",
                                                                                               "openrouter"]
    shipped = kairu_config.load(ROOT / "config.yaml")
    assert shipped.brain_public_to_cloud is True and shipped.brain_daily_cap == 0


@pytest.mark.parametrize("brain,problem", [
    ({"public_to_cloud": "yes"}, "true or false"),
    ({"providers": ["groq", "claude"]}, "brain.providers"),
    ({"providers": ["groq", "groq"]}, "brain.providers"),
    ({"daily_cap": -1}, "daily_cap"),
    ({"models": {"groq": "a model; rm -rf"}}, "brain.models"),
    ({"paid_api": True}, "brain takes only"),
])
def test_a_brain_section_with_a_mistake_is_refused(tmp_path, brain, problem):
    import yaml
    from kairu import config as kairu_config
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"brain": brain}))
    with pytest.raises(kairu_config.ConfigError, match=problem):
        kairu_config.load(path)
