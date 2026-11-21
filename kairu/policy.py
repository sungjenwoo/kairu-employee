"""The Guardian policy (policy.yaml): every known action and its risk tier.

The policy is read once and cannot be changed afterwards: the action table is read-only, so
nothing in Kairu can raise or lower a tier while it runs (plan test T17). Any mistake in the
file is refused, including an action listed twice, because a second entry could quietly lower
the tier of the first.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

from kairu.config import FEATURES

ENTRY_KEYS = {"tier", "description", "read_only", "feature", "private", "pin"}
# The only action whose "yes" needs no PIN (ADR-054, the owner's GO of 20 Nov 2026): a step inside a take-control run that
# you started with your own "yes". `pin: false` on any other action, or on one that isn't High, refuses the whole policy.
NO_PIN_ACTIONS = frozenset({"screen.agent_confirm"})


class PolicyError(Exception):
    pass


class Tier(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


@dataclass(frozen=True)
class Rule:
    action: str
    tier: Tier
    description: str
    read_only: bool = False
    feature: str | None = None
    private: bool = False  # its details are your own words: the audit log keeps only their hash (never a decision)
    pin: bool = True  # High: "yes" and the PIN; False only for NO_PIN_ACTIONS (ADR-054): "yes" alone


@dataclass(frozen=True)
class Policy:
    version: int
    rules: Mapping[str, Rule]

    def rule(self, action: str) -> Rule | None:
        """The rule for an action, or None when the action is not in the policy."""
        return self.rules.get(action)


class _NoDuplicatesLoader(yaml.SafeLoader):
    pass


def _mapping_without_duplicates(loader, node, deep=False):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise PolicyError(f"line {key_node.start_mark.line + 1}: {key!r} is listed twice")
        keys.add(key)
    return loader.construct_mapping(node, deep=deep)


_NoDuplicatesLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates)


def load(path: Path) -> Policy:
    try:
        raw = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_NoDuplicatesLoader)
    except (OSError, yaml.YAMLError) as error:
        raise PolicyError(f"{path}: {error}") from error
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("actions"), dict):
        raise PolicyError(f"{path}: expected 'version: 1' and an 'actions' section")

    tiers = {tier.value.lower(): tier for tier in Tier}
    rules = {}
    for action, entry in raw["actions"].items():
        where = f"{path}: {action}"
        if not isinstance(entry, dict) or not ENTRY_KEYS.issuperset(entry):
            raise PolicyError(f"{where}: allowed keys are {', '.join(sorted(ENTRY_KEYS))}")
        tier = tiers.get(str(entry.get("tier", "")).lower())
        if tier is None:
            raise PolicyError(f"{where}: tier must be Low, Medium, High or Critical")
        if not isinstance(entry.get("read_only", False), bool):
            raise PolicyError(f"{where}: read_only must be true or false")
        if entry.get("feature") not in (None, *FEATURES):
            raise PolicyError(f"{where}: feature must be one of {', '.join(FEATURES)}")
        if not isinstance(entry.get("private", False), bool):
            raise PolicyError(f"{where}: private must be true or false")
        if not isinstance(entry.get("pin", True), bool):
            raise PolicyError(f"{where}: pin must be true or false")
        if entry.get("pin", True) is False and (action not in NO_PIN_ACTIONS or tier is not Tier.HIGH):
            raise PolicyError(f"{where}: only {', '.join(sorted(NO_PIN_ACTIONS))} (High) may have pin: false")
        rules[action] = Rule(
            action=action,
            tier=tier,
            description=str(entry.get("description", "")),
            read_only=entry.get("read_only", False),
            feature=entry.get("feature"),
            private=entry.get("private", False),
            pin=entry.get("pin", True),
        )
    return Policy(version=1, rules=MappingProxyType(rules))
