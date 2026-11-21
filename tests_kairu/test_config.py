"""config.yaml: voice and research are switched off, and the spike code stays separate."""

import re

import pytest

from kairu import config
from kairu.config import ROOT
from kairu.guardian import Guardian, Verdict


def test_the_shipped_config_switches_voice_and_research_off():
    shipped = config.load(ROOT / "config.yaml")
    assert shipped.voice_enabled is False and shipped.research_enabled is False


def test_switched_off_features_are_denied(guardian):
    for name in ("voice.listen", "voice.speak", "research.web_search"):
        decision = guardian.check(name)
        assert decision.verdict is Verdict.DENY and "switched off" in decision.reason


def test_switched_on_features_follow_their_tier(write_config):
    guardian = Guardian(config.load(write_config(voice=True, research=True)))
    assert guardian.check("voice.speak").verdict is Verdict.ALLOW
    assert guardian.check("research.web_search").verdict is Verdict.ALLOW


def test_no_config_file_means_voice_and_research_off(tmp_path):
    cfg = config.load(tmp_path / "missing.yaml")
    assert not cfg.voice_enabled and not cfg.research_enabled


@pytest.mark.parametrize("text", ["voice:\n  enabled: 'no'\n", "voice:\n  enabled: 1\n", "camera:\n  enabled: true\n"])
def test_a_config_with_a_mistake_is_refused(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(config.ConfigError):
        config.load(path)


def test_kairu_never_imports_the_spike_code():
    for path in (ROOT / "kairu").glob("*.py"):
        assert not re.search(r"^\s*(from|import)\s+spike\b", path.read_text(), re.MULTILINE), path.name
