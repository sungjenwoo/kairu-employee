"""Guardian: the only authority in Kairu. No model; the same request always gets the same answer.

    check(action)    -> allow / needs_approval / deny, recorded in the audit log
    approve(...)     -> High tier only: "yes" plus your PIN gives a single-use approval
    authorize(...)   -> the re-check just before an action runs; spends the approval
    emergency_stop() -> halt everything and enter Safe Mode
    resume(...)      -> leave Safe Mode with "yes" plus your PIN

The rules, in the order they are applied:
  1. no policy, or an action the policy does not list: deny
  2. Critical: deny, always; nothing unlocks it (decision D4)
  3. an action whose feature (voice, research) is switched off in config.yaml: deny
  4. Safe Mode: deny anything that is not read-only
  5. High: needs approval
  6. Low and Medium: allow

Guardian fails closed: if the policy cannot be read, or a decision cannot be written to the
audit log, the answer is deny.
"""

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Mapping

from kairu import audit, config as kairu_config, pin as kairu_pin, policy as kairu_policy, safemode
from kairu.policy import NO_PIN_ACTIONS, Tier
from kairu.store import Store

APPROVAL_SECONDS = 120  # how long a request waits for your approval, and how long an approval stays usable


class Verdict(StrEnum):
    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    DENY = "deny"


@dataclass(frozen=True)
class Action:
    name: str
    details: Mapping[str, Any] = field(default_factory=dict)  # what you are shown before approving
    # private: the details came in a Kairu Link message (LINK.md), or the policy marks the action private
    # (its details are your own words, such as a question for the brain), so the audit log keeps only their
    # hash. It changes nothing else: not the decision, not what an approval covers.
    private: bool = field(default=False, compare=False)


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    action: Action
    tier: Tier | None
    reason: str
    description: str = ""
    request_id: str | None = None  # set for needs_approval: pass it to approve()
    pin: bool = True  # needs_approval: False only for policy.NO_PIN_ACTIONS (ADR-054): "yes" alone, no PIN box on the card

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


@dataclass(frozen=True)
class Approval:
    """Proof that you approved one High-tier action. Valid once, for that action and those details."""
    token: str
    action: str
    expires_at: float


class Refused(Exception):
    pass


def fingerprint(action: Action) -> str:
    return hashlib.sha256(json.dumps([action.name, action.details], sort_keys=True, default=str).encode()).hexdigest()


def logged_details(action: Action) -> dict:
    """What the audit log keeps of an action's details: the details, or for a private action only their hash."""
    if not action.private:
        return {"details": action.details}
    return {"details_sha256": hashlib.sha256(json.dumps(action.details, sort_keys=True, default=str).encode()).hexdigest()}


class Guardian:
    def __init__(self, config: kairu_config.Config | None = None):
        self.config = config or kairu_config.load()
        self.store = Store(self.config.data_dir, self.config.anchor_path)
        self._lock = threading.Lock()
        self._waiting: dict[str, tuple[Action, float]] = {}  # request_id -> (action, expires), in memory only
        self._approved: dict[str, tuple[str, float]] = {}  # token -> (fingerprint, expires), in memory only
        self.policy_error = ""
        try:
            self.policy = kairu_policy.load(self.config.policy_path)
            policy_hash = hashlib.sha256(self.config.policy_path.read_bytes()).hexdigest()
            audit.record(self.store, "policy", decision="loaded", file=str(self.config.policy_path),
                         sha256=policy_hash, actions=len(self.policy.rules))
        except kairu_policy.PolicyError as error:
            self.policy, self.policy_error = None, str(error)
            audit.record(self.store, "policy", decision="refused", error=self.policy_error)

    # --- decisions ---------------------------------------------------------------------------

    def check(self, action: Action | str) -> Decision:
        """Decide one request, and record the request and the decision."""
        action = self.marked(Action(action) if isinstance(action, str) else action)
        decision = self._decide(action)
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            decision = replace(decision, request_id=secrets.token_hex(8))
        try:
            audit.record(self.store, "check", action.name, decision.verdict, tier=decision.tier,
                         reason=decision.reason, request=decision.request_id, **logged_details(action))
        except Exception as error:  # an unrecorded decision is not a decision
            return self._deny(action, decision.tier, f"the audit log could not be written ({error})")
        with self._lock:
            now = time.time()  # forget requests and approvals that expired unused
            self._waiting = {key: entry for key, entry in self._waiting.items() if entry[1] > now}
            self._approved = {key: entry for key, entry in self._approved.items() if entry[1] > now}
            if decision.request_id:
                self._waiting[decision.request_id] = (action, now + APPROVAL_SECONDS)
        return decision

    def _decide(self, action: Action) -> Decision:
        try:
            if self.policy is None:
                return self._deny(action, None, f"the policy could not be read: {self.policy_error}")
            rule = self.policy.rule(action.name)
            if rule is None:
                return self._deny(action, None, "this action is not in the policy, and unknown actions are refused")
            if rule.tier is Tier.CRITICAL:
                return self._deny(action, rule.tier, "Critical tier: always refused; no approval or PIN unlocks it", rule)
            if rule.feature and not self.config.feature_enabled(rule.feature):
                return self._deny(action, rule.tier, f"{rule.feature} is switched off ({rule.feature}.enabled: false in config.yaml)", rule)
            if not rule.read_only and safemode.is_safe(self.store):
                return self._deny(action, rule.tier, f"Safe Mode ({safemode.reason(self.store)}): only read-only actions "
                                  "run until you resume with `kairu resume`", rule)
            if rule.tier is Tier.HIGH and not rule.pin and rule.action in NO_PIN_ACTIONS:
                return Decision(Verdict.NEEDS_APPROVAL, action, rule.tier,
                                "High tier, in a take-control run you started: needs \"yes\" (no PIN, ADR-054)",
                                rule.description, pin=False)
            if rule.tier is Tier.HIGH:
                return Decision(Verdict.NEEDS_APPROVAL, action, rule.tier, "High tier: needs \"yes\" and your PIN", rule.description)
            return Decision(Verdict.ALLOW, action, rule.tier, f"{rule.tier} tier: allowed", rule.description)
        except Exception as error:  # for example guardian.db unreadable
            return self._deny(action, None, f"Guardian could not decide ({error})")

    def marked(self, action: Action) -> Action:
        """The action, marked private if the policy says its details are your own words (logging only)."""
        rule = self.policy.rule(action.name) if self.policy else None
        return replace(action, private=True) if rule and rule.private and not action.private else action

    @staticmethod
    def _deny(action, tier, reason, rule=None) -> Decision:
        return Decision(Verdict.DENY, action, tier, reason, rule.description if rule else "")

    # --- approvals ---------------------------------------------------------------------------

    def approve(self, request_id: str, confirmation: str, pin: str) -> Approval:
        """Approve a needs_approval request with "yes" and your PIN. Raises Refused otherwise.

        Each request can be answered once; if it is refused, ask again with check().
        """
        with self._lock:
            waiting = self._waiting.pop(request_id or "", None)
        action = waiting[0] if waiting else None
        try:
            if waiting is None or time.time() > waiting[1]:
                raise Refused("there is no such request waiting for approval, or it expired; ask again")
            if confirmation.strip().lower() != "yes":
                raise Refused('not approved: you did not type "yes"')
            again = self._decide(action)  # things may have changed while you read the details, e.g. Safe Mode
            if again.verdict is not Verdict.NEEDS_APPROVAL:
                raise Refused(again.reason)
            if again.pin or action.name not in NO_PIN_ACTIONS:  # only policy.NO_PIN_ACTIONS skip the PIN (ADR-054)
                ok, why = kairu_pin.check(self.store, pin)
                if not ok:
                    raise Refused(why)
        except Refused as refusal:
            audit.record(self.store, "approval", action and action.name, "refused", request=request_id, reason=str(refusal))
            raise
        token, expires = secrets.token_hex(16), time.time() + APPROVAL_SECONDS
        with self._lock:
            self._approved[token] = (fingerprint(action), expires)
        audit.record(self.store, "approval", action.name, "granted", request=request_id, **logged_details(action))
        return Approval(token, action.name, expires)

    def waiting_action(self, request_id: str) -> tuple[Action, float] | None:
        """The action a needs_approval request is waiting with, and until when; None if none waits (for a phone's card)."""
        with self._lock:
            waiting = self._waiting.get(request_id or "")
        return waiting if waiting and waiting[1] > time.time() else None

    def approve_verified(self, request_id: str, how: str) -> Approval:
        """Approve a needs_approval request whose approval the Guardian program has already verified another way: a
        paired phone's fingerprint signature over exactly this request (kairu/link/approver.py, ADR-035). Raises Refused.

        Only the Guardian program calls this, after the check; no request on Guardian's channel can reach it. The decision
        is made again first, so Safe Mode or a Critical tier still refuse. Each request can be approved once.
        """
        with self._lock:
            waiting = self._waiting.pop(request_id or "", None)
        action = waiting[0] if waiting else None
        try:
            if waiting is None or time.time() > waiting[1]:
                raise Refused("there is no such request waiting for approval, or it expired; ask again")
            again = self._decide(action)
            if again.verdict is not Verdict.NEEDS_APPROVAL:
                raise Refused(again.reason)
        except Refused as refusal:
            audit.record(self.store, "approval", action and action.name, "refused", request=request_id, how=how,
                         reason=str(refusal))
            raise
        token, expires = secrets.token_hex(16), time.time() + APPROVAL_SECONDS
        with self._lock:
            self._approved[token] = (fingerprint(action), expires)
        audit.record(self.store, "approval", action.name, "granted", request=request_id, how=how, **logged_details(action))
        return Approval(token, action.name, expires)

    def authorize(self, action: Action | str, approval: Approval | None = None) -> Decision:
        """The final check right before an action runs. A High-tier action needs, and spends, its approval."""
        action = Action(action) if isinstance(action, str) else action
        decision = self._decide(action)
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            decision = self._spend(action, decision, approval)
        try:
            audit.record(self.store, "authorize", action.name, decision.verdict, tier=decision.tier, reason=decision.reason)
        except Exception as error:
            return self._deny(action, decision.tier, f"the audit log could not be written ({error})")
        return decision

    def _spend(self, action: Action, decision: Decision, approval: Approval | None) -> Decision:
        if approval is None:
            return self._deny(action, decision.tier, "High tier: not approved (needs \"yes\" and your PIN)")
        with self._lock:
            granted = self._approved.pop(approval.token, None)
        if granted is None:
            return self._deny(action, decision.tier, "this approval is not valid here, or was already used")
        if time.time() > granted[1]:
            return self._deny(action, decision.tier, "this approval expired; ask again")
        if granted[0] != fingerprint(action):
            return self._deny(action, decision.tier, "this approval was for a different action or different details")
        return Decision(Verdict.ALLOW, action, decision.tier, "High tier: approved with \"yes\" and your PIN", decision.description)

    # --- stop and Safe Mode -------------------------------------------------------------------

    def emergency_stop(self, source: str = "api") -> int:
        return safemode.emergency_stop(self.store, source)

    def resume(self, confirmation: str, pin: str) -> None:
        """Leave Safe Mode with "yes" and your PIN. Raises Refused otherwise."""
        try:
            if not safemode.is_safe(self.store):
                raise Refused("Kairu is not in Safe Mode")
            if confirmation.strip().lower() != "yes":
                raise Refused('not resumed: you did not type "yes"')
            ok, why = kairu_pin.check(self.store, pin)
            if not ok:
                raise Refused(why)
        except Refused as refusal:
            audit.record(self.store, "resume", decision="refused", reason=str(refusal))
            raise
        with self.store.transaction() as db:
            safemode.leave(self.store, db)
            audit.record(self.store, "resume", decision="resumed", db=db)
