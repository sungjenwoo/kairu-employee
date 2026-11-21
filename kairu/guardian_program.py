"""The Guardian program: Guardian on its own, in the background, answering Kairu over the private channel.

    python -m kairu.guardian_program --config config.yaml     (`kairu guardian run` starts it for you)

It alone holds the policy, the PIN hash and the audit log, and makes every decision, with the same
Guardian as before (kairu/guardian.py). It also starts every action: `run` decides, then starts the
action's code from kairu/executors.py in its own process, inside a Job Object (Windows) or process
group (Linux) that belongs to Guardian, and an emergency stop halts it from here (kairu/runner.py).
Kairu reaches it only through kairu/channel.py.

Every message is checked before Guardian looks at it. A message that is not a JSON object of at
most 16 KiB, names an unknown request, lacks a field, has a field of the wrong type, or has any
field beyond those listed in REQUESTS (a "tier", an "override", a "verdict" or a "target" of its
own) is refused with "deny", and recorded in the audit log. Guardian keeps running whatever arrives.

Protection (Phase J): Guardian's monitors run as the action protect.watch. With protect.enabled in
config.yaml, Guardian starts it by itself (Protector, below): when Guardian starts, after a resume,
and again after a crash, waiting longer each time. A monitor's only request is `report`: one alert's
number, source, kind, severity and fingerprint, from fixed lists (kairu/protect/kinds.py). Guardian
writes it to the audit log and shows a tray pop-up; it grants nothing and runs nothing.

Kairu Link (Phase C, LINK.md): with link.enabled, Guardian keeps link.receive running while a device is
paired (Linker, below). The receiver's only request is `link`: which paired device, the message type,
the message's hash and, for a command, the action and its details; or why it refused the message.
Guardian treats it as a request from that device and decides as for any other: Low and Medium run if
Guardian has code for them, High waits for "yes" and your PIN typed at this PC (`kairu link approve N`),
Critical is refused. The phone's text never reaches the audit log: a command's details are recorded as
a hash. Every reply goes out as Guardian's own link.send action. A phone can never send a PIN, an
approval or a rule change: no request carries one.

Mission Mode: whenever mission_mode.on ends, however it ends, Guardian puts the lid setting back
(kairu/mission.py), and it does so again when it starts, should the PC have crashed while it was on.

Kairu's brain (Phase B, BRAIN.md): a question from your phone (Link type "ask") is run as brain.ask, like a
question typed here, and its answer goes back as Guardian's own link.send. A question with personal data
is not sent: it becomes a High request for brain.send_private that waits for "yes" and your PIN at this PC
(`kairu link approve N`), showing the exact text and where it would go, and the words it would search for if it
needs the web (stage R1, RESEARCH.md: the question asks Guardian for research.web_search and research.web_read
itself, and Guardian decides those like any other action). Mission Cards: with a card queued,
Guardian keeps mission.run going (Missioner, below), after a restart too; a card that was running when a
stop halted it is marked stopped and keeps its checkpoint; when a card ends, you are told in the tray
and/or on your phone, as the card asks.
"""

import argparse
import base64
import itertools
import json
import math
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kairu import audit, autostart, channel, config as kairu_config, executors, hotkey, mission, pin as kairu_pin, safemode, session
from kairu.guardian import Action, Approval, Guardian, Refused, Verdict, fingerprint, logged_details
from kairu.policy import NO_PIN_ACTIONS
from kairu.brain.store import BrainStore
from kairu.link import approver as link_approver, kinds as link_kinds, store as link_store
from kairu.missions import store as missions_store
from kairu.protect import kinds
from kairu.runner import Run, Runner
from kairu.store import MissingDatabase

YES_PIN = {"confirmation": str, "pin": str}
REQUESTS = {  # request -> its fields and their types; a field marked optional may be left out or null
    "check": {"action": str, "details": "details?"},
    "approve": {"request_id": str, **YES_PIN},
    "authorize": {"action": str, "details": "details?", "approval": "str?"},
    "run": {"action": str, "details": "details?", "approval": "str?"},
    "run_status": {"run": int},
    "end": {"run": int},
    "resume": YES_PIN,
    "set_pin": {"new_pin": str, "current_pin": "str?"},
    "reanchor": YES_PIN,
    "status": {},
    "quit": {},
    "report": {"source": str, "kind": str, "severity": str, "alert": int, "fingerprint": str},
    "link": {"device": str, "type": str, "digest": str, "problem": "str?", "action": "str?", "details": "details?"},
    "link_waiting": {},
    "link_approve": {"number": int, **YES_PIN},
    "link_refuse": {"number": int},
    "link_card": {"request_id": str, "device": str, "plan": "str?"},
    "link_card_result": {"number": int},
}
FINGERPRINT = re.compile(r"[0-9a-f]{64}")
WATCH = "protect.watch"
RECEIVE, SEND, PAIR, MISSION = "link.receive", "link.send", "device.pair", "mission_mode.on"
APPROVER = "device.approver"  # turning fingerprint approval on: only ever with your PIN at the PC
PHONE_STOP, PHONE_APPROVE, PHONE_REFUSE = "guardian.stop", "link.approve", "link.refuse"  # the phone's own commands (D2)
ORDER = "task.order"  # D3: an order typed on the phone, run here by the task core
VERIFY_SECONDS = 15
ASK, SEND_PRIVATE, RUN_MISSIONS = "brain.ask", "brain.send_private", "mission.run"
PHONE_WAIT_SECONDS = 600  # a phone's High request waits this long for "yes" and your PIN at the PC
HEAVY_ENDINGS = ("heat", "cpu", "time")  # Mission Mode ended for one of these: what the phone started is stopped too
POPUP_MERGE_SECONDS = 20  # tray pop-ups this close together become one
RETRY_SECONDS = (30, 120, 600, 1800)  # waits before starting protect.watch again after it failed; the last repeats
SETTLED_SECONDS = 600  # a protect.watch that ran this long before failing starts the waits again from the first
LONGEST_TEXT = 2000  # characters in any one field
MOST_DETAILS = 50
MOST_RUNNING = 8  # actions running at once
REMEMBERED_RUNS = 100  # finished runs whose outcome Guardian can still tell


class BadMessage(Exception):
    pass


def parse(body: bytes) -> dict:
    """The message as a dict, if it is exactly a request Guardian knows. Raises BadMessage otherwise.

    The reasons name fields, never their values, which may hold a PIN.
    """
    try:
        message = json.loads(body.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except UnicodeDecodeError:
        raise BadMessage("the message is not UTF-8 text") from None
    except (ValueError, RecursionError):
        raise BadMessage("the message is not valid JSON") from None
    if not isinstance(message, dict):
        raise BadMessage("the message is not a JSON object")
    name = message.get("op")
    if not isinstance(name, str) or name not in REQUESTS:
        raise BadMessage("unknown request: Guardian answers only " + ", ".join(REQUESTS))
    fields = REQUESTS[name]
    extra = sorted(set(message) - {"op", *fields})
    if extra:
        named = ", ".join(repr(field[:40]) for field in extra[:5])
        raise BadMessage(f"{name}: Guardian does not accept the field(s) {named}; only {', '.join(fields) or 'none'}")
    for field, kind in fields.items():
        value = message.get(field)
        if value is None:
            if kind in ("details?", "str?"):
                continue
            raise BadMessage(f"{name}: {field} is missing")
        if kind == "details?":
            _check_details(name, value)
        elif kind is int:
            if type(value) is not int or not 0 < value < 2**31:
                raise BadMessage(f"{name}: {field} must be a {'run' if field == 'run' else 'whole'} number")
        elif type(value) is not str:
            raise BadMessage(f"{name}: {field} must be text")
        elif len(value) > LONGEST_TEXT:
            raise BadMessage(f"{name}: {field} is too long")
    return message


def _no_duplicates(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a field is given twice")
    return dict(pairs)


def _no_constants(name):
    raise ValueError(f"{name} is not a number")


def _check_details(name: str, details) -> None:
    if type(details) is not dict:
        raise BadMessage(f"{name}: details must be an object")
    if len(details) > MOST_DETAILS:
        raise BadMessage(f"{name}: more than {MOST_DETAILS} details")
    for key, value in details.items():
        if len(key) > 100:
            raise BadMessage(f"{name}: a detail's name is too long")
        if value is not None and type(value) not in (str, int, float, bool):
            raise BadMessage(f"{name}: details must be text, numbers, true/false or null, not lists or objects")
        if type(value) is str and len(value) > LONGEST_TEXT:
            raise BadMessage(f"{name}: a detail is too long")
        if type(value) is float and not math.isfinite(value):
            raise BadMessage(f"{name}: a detail is not a finite number")


def decision_reply(decision) -> dict:
    reply = {"verdict": decision.verdict.value, "tier": decision.tier.value if decision.tier else None,
             "reason": decision.reason, "description": decision.description, "request_id": decision.request_id}
    if not decision.pin:
        reply["pin"] = False  # ADR-054: the card asks "yes" alone (policy.NO_PIN_ACTIONS); Guardian checks it again on approve
    return reply


def describe(store, cfg, policy, policy_error: str) -> dict:
    """What `kairu status` shows: from Guardian when it runs, or read from the files when it does not."""
    verdict = audit.verify(store)
    return {
        "mode": safemode.mode(store), "safe_reason": safemode.reason(store), "pin_set": kairu_pin.is_set(store),
        "policy": {"file": cfg.policy_path.name, "actions": len(policy.rules)} if policy else {"error": policy_error},
        "voice": cfg.voice_enabled, "research": cfg.research_enabled,
        "audit": {"ok": verdict.ok, "rows": verdict.rows, "kind": verdict.kind, "problem": verdict.problem,
                  "bad_row": verdict.bad_row},
        "data": str(store.path),
        "autostart": autostart.installed(cfg.data_dir),
        "link": {"enabled": cfg.link_enabled, "relay": cfg.link_relay, "devices": len(link_store.paired(cfg.data_dir))},
        "mission_mode": mission.saved(cfg.data_dir) is not None,
    }


@dataclass
class PhoneRequest:
    """A High-tier request from a paired device, waiting for "yes" and your PIN at the PC."""
    number: int
    device: str
    action: str
    details: dict
    digest: str
    description: str
    expires: float
    request_id: str = ""  # D3: a step of a phone's order, waiting in Guardian; its approval goes to task.order's task core
    state: str = "waiting"  # D3 cards: waiting, approved, refused
    token: str = ""


class Service:
    """Answers one message at a time. Nothing that arrives can stop it answering the next one.

    It holds the runner that starts every action and halts them all on an emergency stop.
    """

    def __init__(self, guardian: Guardian, server: channel.Server | None = None):
        self.guardian, self.store, self.server = guardian, guardian.store, server
        self.data_dir = guardian.config.data_dir
        self.runner = Runner(guardian, on_end=self._run_ended)
        self.runs: dict[int, Run] = {}  # the runs Guardian can still tell about, oldest first
        self.keeper: hotkey.Keeper | None = None  # Ctrl+Alt+K, when this Service is the Guardian program's
        self.tray = None  # the tray icon (Windows), likewise
        self.quit_requested = False
        self._runs_lock = threading.RLock()  # the Protector starts protect.watch from its own thread
        self._popups: list[float] = []  # when recent tray pop-ups were shown
        self.phone_waiting: dict[int, PhoneRequest] = {}  # High requests from a phone, in memory only
        self.phone_runs: dict[int, str] = {}  # run -> the device that asked for it, told when it ends
        self.phone_asks: dict[int, tuple[str, str, str, str]] = {}  # run -> (device, answer id, question, digest)
        self._phone_numbers = itertools.count(1)
        self.ending = False  # Guardian is ending: a mission cut off now goes on when it starts again

    def supplied(self) -> dict:
        """What Guardian fills in itself for an action's `supplied` arguments: from its own config.yaml, never a request."""
        cfg = self.guardian.config
        return {"data_dir": str(cfg.data_dir), "check_seconds": cfg.protect_check_seconds,
                "gmail_seconds": cfg.protect_gmail_seconds, "relay": cfg.link_relay,
                "max_hours": cfg.mission_max_hours, "cpu_percent": cfg.mission_cpu_percent,
                "cpu_minutes": cfg.mission_cpu_minutes, "max_celsius": cfg.mission_max_celsius,
                "brain": cfg.brain_settings(), "work_folder": str(cfg.work_folder), "voice_model": cfg.voice_model,
                "voice_engine": cfg.voice_engine, "voice_voice": cfg.voice_voice, "voice_style": cfg.voice_style,
                "voice_tts": cfg.voice_tts, "voice_kokoro": cfg.voice_kokoro, "voice_live_every": cfg.voice_live_every,
                "voice_fast": cfg.voice_fast, "voice_only_mine": cfg.voice_only_mine, "voice_hearing": cfg.voice_hearing,
                "voice_gemini_model": cfg.voice_gemini_model, "voice_camera": cfg.voice_camera,
                "voice_live": cfg.voice_live, "voice_live_folder": cfg.voice_live_folder}

    def close(self, why: str = "Guardian quit") -> None:
        """End every action still running, with all its programs."""
        self.ending = True  # first: a mission halted now was cut off by Guardian's end, not stopped by you
        for keeper in (self.protector, self.linker, self.missioner):
            if keeper:
                keeper.close()  # first, so nothing starts the monitors or the receiver again while Guardian ends
        self.runner.close(why)

    protector = None  # the Protector, when protect.enabled
    linker = None  # the Linker, when link.enabled
    missioner = None  # the Missioner: Mission Cards

    def answer(self, body: bytes) -> dict:
        try:
            message = parse(body)
        except BadMessage as error:
            return self.refuse(str(error))
        name = message.pop("op")
        try:
            return getattr(self, f"_{name}")(**message)
        except Refused as refusal:  # Guardian refused, and has recorded why
            return {"verdict": "deny", "reason": str(refusal)}
        except Exception as error:  # fail closed, keep running
            return self.refuse(f"Guardian could not answer {name} ({type(error).__name__}: {error})", name)

    def refuse(self, reason: str, request: str | None = None) -> dict:
        """Deny something that is not a request Guardian can answer, and record it."""
        try:
            audit.record(self.store, "channel", decision="deny", request=request, reason=reason)
        except Exception as error:
            print(f"guardian: refused, but the audit row could not be written ({error}): {reason}", file=sys.stderr, flush=True)
        return {"verdict": "deny", "reason": reason}

    def _check(self, action, details=None):
        return decision_reply(self.guardian.check(Action(action, details or {})))

    def _approve(self, request_id, confirmation, pin):
        granted = self.guardian.approve(request_id, confirmation, pin)
        return {"verdict": "ok", "approval": granted.token, "action": granted.action, "expires_at": granted.expires_at}

    def _authorize(self, action, details=None, approval=None):
        offered = Approval(approval, action, 0.0) if approval is not None else None  # only the token is trusted
        return decision_reply(self.guardian.authorize(Action(action, details or {}), offered))

    def _run(self, action, details=None, approval=None, private=False):
        """Decide, then start the action's own code with exactly these details. Kairu never names the code.

        Arguments the executor lists as `supplied` come from Guardian's own settings, after the details.
        private: the details came from a Kairu Link message, or are a reply to one; the audit log keeps their hash.
        """
        details = details or {}
        private = self.guardian.marked(Action(action, details, private)).private  # the policy may keep them as a hash
        executor = executors.EXECUTORS.get(action)
        with self._runs_lock:
            problem = (f"Guardian has no code that performs {action!r}, so it runs nothing" if executor is None
                       else executors.argument_problem(action, executor, details))
            running = self.runner.running()
            if not problem and executor.single and any(run.action == action for run in running):
                problem = f"{action} is already running"
            if not problem and len(running) >= MOST_RUNNING:
                problem = f"{MOST_RUNNING} actions are already running; wait for one to end"
            if problem:  # refused before the decision, so an approval is not spent on it
                audit.record(self.store, "run", action, "refused", reason=problem,
                             **logged_details(Action(action, details, private)))
                raise Refused(problem)
            offered = Approval(approval, action, 0.0) if approval is not None else None  # only the token is trusted
            supplied = self.supplied()
            arguments = {**details, **{name: supplied[name] for name in executor.supplied}}
            run = self.runner.run(Action(action, details, private), executor.target, offered, **arguments)  # authorizes first
            self.runs[run.run_id] = run
            for old in [old for old in self.runs.values() if old.outcome][:max(0, len(self.runs) - REMEMBERED_RUNS)]:
                del self.runs[old.run_id]
        return {"verdict": "ok", "run": run.run_id, "pid": run.process.pid}

    def _report(self, source, kind, severity, alert, fingerprint):
        """A monitor's report of one alert: recorded, and shown in the tray. It grants nothing and runs nothing."""
        if source not in kinds.SOURCES or kind not in kinds.KINDS or severity not in kinds.SEVERITIES:
            raise Refused(self.refuse(f"report: not a known source, kind or severity ({source[:20]!r}, {kind[:30]!r}, "
                                      f"{severity[:10]!r})", "report")["reason"])
        if not FINGERPRINT.fullmatch(fingerprint):
            raise Refused(self.refuse("report: the fingerprint must be 64 hex digits", "report")["reason"])
        audit.record(self.store, "alert", f"protect.{source}", kind, severity=severity, alert=alert, fingerprint=fingerprint)
        if severity != "info":
            self.popup(kinds.KINDS[kind], severity)
        return {"verdict": "ok"}

    def popup(self, title: str, severity: str) -> None:
        """The tray pop-up for an alert (Windows). Several within a short time become one: "3 new alerts"."""
        now = time.monotonic()
        self._popups = [moment for moment in self._popups if now - moment < POPUP_MERGE_SECONDS] + [now]
        many = len(self._popups)
        heading = f"Kairu: {title}" if many == 1 else f"Kairu: {many} new alerts"
        self.last_popup = [heading, "Run `kairu alerts` to see what was found. Kairu changed nothing."]
        if self.tray is not None:
            self.tray.notify(*self.last_popup, warning=severity == "high" or many > 1)

    last_popup: list | None = None  # what the last pop-up said (shown in the tray on Windows)

    def notify(self, heading: str, text: str, warning: bool = False) -> None:
        """A tray pop-up that is not an alert (Windows); kept for `kairu status` everywhere."""
        self.last_popup = [heading, text]
        if self.tray is not None:
            self.tray.notify(heading, text, warning=warning)

    # --- Kairu Link: requests from a paired device ---------------------------------------------

    def _link(self, device, type, digest, problem=None, action=None, details=None):
        """One message from the Gate, as link.receive saw it. A request only: Guardian decides, and replies."""
        if (not link_kinds.DIGEST.fullmatch(digest) or type not in (*link_kinds.TYPES, "?")
                or (problem is not None and problem not in link_kinds.PROBLEMS)
                or (device and not link_kinds.DEVICE_ID.fullmatch(device))):
            raise Refused(self.refuse("link: not a message report Guardian accepts", "link")["reason"])
        known = link_store.find(self.data_dir, device) if device else None
        if problem is not None:
            audit.record(self.store, "link", type, "rejected", device=device if known else "", problem=problem,
                         digest=digest)
            if known and problem in link_kinds.TELL_SENDER:
                self.tell(device, "report", f"Kairu refused your message: {link_kinds.PROBLEMS[problem]}. "
                                            "Nothing ran. Send it again if you still want it.")
            return {"verdict": "ok"}
        if known is None:
            raise Refused(self.refuse("link: not from a paired device", "link")["reason"])
        audit.record(self.store, "link", type, "received", device=device, digest=digest)
        if type == "status":
            self.tell(device, "status", self.phone_status())
        elif type == "command":
            if action is None:
                raise Refused(self.refuse("link: a command names no action", "link")["reason"])
            if action == PHONE_STOP:  # a stop is always allowed, from any paired device: it only ever halts things
                self.phone_stop(device, digest)
            elif action == PHONE_APPROVE:
                self.tell(device, "report", self.phone_fingerprint(device, details or {}))
            elif action == PHONE_REFUSE:
                self.tell(device, "report", self.phone_refuse(device, details or {}))
            else:
                said = self.phone_command(device, action, details or {}, digest)
                if said:
                    self.tell(device, "report", said)
        elif type == "ask":
            question = (details or {}).get("question")
            if action is not None or not isinstance(question, str) or not question.strip():
                raise Refused(self.refuse("link: a question has no words", "link")["reason"])
            problem = self.phone_ask(device, question, digest)
            if problem:
                self.tell(device, "report", problem)
        elif type == "mission" and action is not None:  # D4: a mission that is an order, which may have waited in the Gate
            if action != ORDER:
                raise Refused(self.refuse("link: a mission can only be an order for the task core", "link")["reason"])
            self.tell(device, "report", "Your mission reached the PC: Kairu runs it now, each step decided by Guardian.")
            said = self.phone_command(device, ORDER, details or {}, digest)
            if said:
                self.tell(device, "report", said)
        else:  # a plain mission, doubt, report or call request is kept as a request only; its words stay with the receiver
            self.tell(device, "report", f"Received your {type.replace('_', ' ')}. Kairu keeps it as a request only: "
                                        "nothing was started (missions run from Phase I).")
        return {"verdict": "ok"}

    def phone_status(self) -> str:
        decision = self.guardian.check(Action("status.show"))
        if not decision.allowed:
            return f"Refused: {decision.reason}"
        self._expire()  # a request whose 10 minutes have passed is not waiting any more
        mode = f"Safe Mode ({safemode.reason(self.store)})" if safemode.is_safe(self.store) else "normal"
        running = ", ".join(sorted({run.action for run in self.runner.running()} - {RECEIVE, SEND})) or "nothing else"
        on = mission.saved(self.data_dir) is not None
        return (f"Kairu on your PC is running. Mode: {mode}. Mission Mode: {'on' if on else 'off'}. "
                f"Running: {running}. Waiting for your PIN: {len(self.phone_waiting)}. "
                f"PC time {datetime.now().astimezone().strftime('%H:%M:%S')}.")

    def phone_command(self, device: str, action: str, details: dict, digest: str) -> str:
        """Decide a phone's request for one action, as for any request; what to tell the phone."""
        if action == APPROVER:  # a phone can only ever turn fingerprint approval on for itself
            details = {"device": device, "key": str(details.get("key", ""))[:200]}
        if action == ORDER:  # the order's words, and the phone its answers go to (never another device)
            details = {"order": str(details.get("order", ""))[:2000], "device": device}
        if action in NO_PIN_ACTIONS:  # ADR-054: "yes" without the PIN is only for a take-control run at this PC
            self.refuse(f"link: {action} is only for a take-control run at the PC", "link")
            return f"Refused {action}: it is only for a take-control run at the PC."
        request = Action(action, details, private=True)
        decision = self.guardian.check(request)
        if decision.verdict is Verdict.DENY:
            return f"Refused {action}: {decision.reason}."
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            number = next(self._phone_numbers)
            entry = PhoneRequest(number, device, action, dict(details), digest, decision.description,
                                 time.time() + PHONE_WAIT_SECONDS)
            self.phone_waiting[number] = entry
            self.notify(f"Kairu: your phone asks for {action}",
                        f"High tier. Approve it at this PC within 10 minutes: `kairu link approve {number}` "
                        f"(yes and your PIN), or `kairu link refuse {number}`.")
            if action != APPROVER and link_store.approver(self.data_dir, device):
                return self.approval_card(entry)
            return (f"{action} is High tier: it waits up to 10 minutes for your \"yes\" and PIN typed at the PC "
                    f"(`kairu link approve {number}`). Nothing runs before that.")
        if action not in executors.EXECUTORS:
            return f"Allowed ({decision.reason}), but Kairu has no code that does {action} yet, so nothing ran."
        try:
            started = self._run(action, details, private=True)
        except Refused as refusal:
            return f"{action} did not start: {refusal}"
        if action == ORDER:
            return ""  # the task core answers the phone itself, step by step
        self.phone_runs[started["run"]] = device
        return f"Started {action} (run {started['run']}). Kairu tells you when it ends."

    def approval_card(self, entry: PhoneRequest) -> str:
        """What the phone shows for a High request it may approve with its fingerprint (PHONE.md, D2): JSON, read by the app."""
        return json.dumps({"kairu_card": {
            "number": entry.number, "action": entry.action, "description": entry.description,
            "details": {key: value for key, value in entry.details.items() if key not in ("ask", "source")},
            "tier": "High", "expires": int(entry.expires), "fingerprint": fingerprint(Action(entry.action, entry.details)),
        }}, separators=(",", ":"))[:1500]

    def phone_stop(self, device: str, digest: str) -> None:
        """STOP from the phone: what Ctrl+Alt+K does. Everything halts within a second and Safe Mode begins; the receiver
        stops too, so the PC hears the phone again only after `kairu resume` at the PC."""
        audit.record(self.store, "link", PHONE_STOP, "stop from a paired device", device=device, digest=digest)
        self.guardian.emergency_stop(f"phone {device}")

    def phone_refuse(self, device: str, details: dict) -> str:
        number = details.get("number")
        self._expire()
        entry = self.phone_waiting.get(number) if type(number) is int else None
        if entry is None or entry.device != device:
            return "That request isn't waiting any more. Nothing ran."
        if entry.request_id:  # a step of the phone's order: its task core hears the refusal
            entry.state = "refused"
            audit.record(self.store, "link", entry.action, "refused on the phone", device=device, digest=entry.digest)
            return f"Refused on your phone: {entry.action} did not run."
        del self.phone_waiting[number]
        audit.record(self.store, "link", entry.action, "refused on the phone", device=device, digest=entry.digest)
        return f"Refused on your phone: {entry.action} did not run."

    def phone_fingerprint(self, device: str, details: dict) -> str:
        """The phone approves one of its own High requests with its fingerprint: checked, then run once (ADR-035)."""
        number, signature = details.get("number"), details.get("signature")
        if type(number) is not int or not isinstance(signature, str) or len(signature) > 200:
            return "That approval can't be read. Nothing ran."
        key = link_store.approver(self.data_dir, device)
        if key is None:
            return "Fingerprint approval isn't on for this phone. Nothing ran."
        self._expire()
        entry = self.phone_waiting.get(number)
        if entry is None or entry.device != device:
            return "That request isn't waiting any more (it may have ended after 10 minutes). Nothing ran."
        if entry.action == APPROVER:
            return "Turning fingerprint approval on needs your PIN at the PC. Nothing ran."
        signed = link_approver.statement(device, number, fingerprint(Action(entry.action, entry.details)), int(entry.expires))
        if not self.verified(key, signed, signature):
            audit.record(self.store, "link", entry.action, "fingerprint refused", device=device, digest=entry.digest)
            return "Refused: that approval wasn't signed by this phone's fingerprint key. Nothing ran."
        if entry.request_id:  # a step of the phone's order: its task core takes the approval and runs the step
            if entry.state != "waiting":
                return "That request was already answered. Nothing more ran."
            try:
                granted = self.guardian.approve_verified(entry.request_id, f"fingerprint on {device}")
            except Refused as refusal:
                entry.state = "refused"
                return f"{entry.action} can no longer be approved: {refusal}."
            entry.state, entry.token = "approved", granted.token
            return f"Approved {entry.action} with your fingerprint."
        decision = self.guardian.check(Action(entry.action, entry.details, private=True))  # decided again now
        if decision.verdict is not Verdict.NEEDS_APPROVAL:
            del self.phone_waiting[number]
            return f"{entry.action} can no longer be approved: {decision.reason}."
        granted = self.guardian.approve_verified(decision.request_id, f"fingerprint on {device}")
        del self.phone_waiting[number]
        try:
            return self.start_approved(entry, granted, "with your fingerprint")[0]
        except Refused as refusal:
            return f"Approved with your fingerprint, but {entry.action} did not start: {refusal}"

    @staticmethod
    def verified(key: str, signed: bytes, signature: str) -> bool:
        """The signature, checked in a short program of its own (kairu/link/approver.py): Guardian never loads PyNaCl."""
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            done = subprocess.run([sys.executable, "-m", "kairu.link.approver"], capture_output=True, text=True,
                                  timeout=VERIFY_SECONDS, cwd=str(Path(__file__).resolve().parent.parent),
                                  input=json.dumps({"key": key, "statement": base64.b64encode(signed).decode("ascii"),
                                                    "signature": signature}), **flags)
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0 and done.stdout.strip() == "valid"

    def start_approved(self, entry: PhoneRequest, granted: Approval, how: str) -> tuple[str, dict | None]:
        """Run a phone's High request that was just approved: what to tell the phone, and the run (None if nothing ran).
        Raises Refused if it can't start."""
        if entry.action not in executors.EXECUTORS:
            return f"Approved {how}, but Kairu has no code that does {entry.action} yet, so nothing ran.", None
        started = self._run(entry.action, entry.details, granted.token, private=True)
        if entry.action == SEND_PRIVATE:  # its answer goes to the phone when it comes
            self.phone_asks[started["run"]] = (entry.device, entry.details["ask"], entry.details["question"], entry.digest)
            return f"Approved {how}: your question goes to {entry.details['provider']}.", started
        self.phone_runs[started["run"]] = entry.device
        if entry.action == APPROVER:
            return "Approved with your PIN: this phone can now approve its own High requests with its fingerprint.", started
        return f"Approved {how}: {entry.action} started (run {started['run']}).", started

    def phone_ask(self, device: str, question: str, digest: str) -> str:
        """A question from your phone: brain.ask, as for one typed here. "" once it runs; otherwise why not."""
        ask = secrets.token_hex(8)
        try:
            started = self._run(ASK, {"question": question, "ask": ask, "source": device}, private=True)
        except Refused as refusal:
            return f"Kairu could not answer: {refusal}"
        self.phone_asks[started["run"]] = (device, ask, question, digest)
        return ""

    def answer_phone(self, run: Run, device: str, ask: str, question: str, digest: str) -> None:
        """A question from your phone was answered (or not): tell the phone. Personal: wait for you at the PC."""
        answer = BrainStore(self.data_dir).take_answer(ask) if run.outcome == "finished" else None
        if run.outcome == "halted":
            self.tell(device, "report", "Your question was stopped at the PC (a stop, or Guardian ending). Nothing more "
                                        "was sent.")
        elif answer is None:
            self.tell(device, "report", "Kairu could not answer that (Guardian's log on the PC says why).")
        elif answer.status != "needs_approval" or run.action != ASK:
            self.tell(device, "report", answer.text)
        elif not answer.provider:
            self.tell(device, "report", "Not sent: your question has personal data, and no free AI provider is set up "
                                        "yet (`kairu provider add groq` at the PC).")
        else:
            details = {"question": question, "provider": answer.provider, "ask": secrets.token_hex(8), "source": device}
            if answer.search:
                details["search"] = answer.search
            decision = self.guardian.check(Action(SEND_PRIVATE, details, private=True))
            if decision.verdict is not Verdict.NEEDS_APPROVAL:
                self.tell(device, "report", f"Not sent: {decision.reason}.")
                return
            number = next(self._phone_numbers)
            self.phone_waiting[number] = PhoneRequest(number, device, SEND_PRIVATE, details, digest, decision.description,
                                                      time.time() + PHONE_WAIT_SECONDS)
            self.notify("Kairu: your phone's question has personal data",
                        f"It goes to {answer.provider} only if you approve it here within 10 minutes: "
                        f"`kairu link approve {number}` (yes and your PIN), or `kairu link refuse {number}`.")
            self.tell(device, "report", f"Your question has {', '.join(answer.reasons) or 'personal data'}, so it was "
                                        f"not sent. It waits up to 10 minutes for your \"yes\" and PIN at the PC "
                                        f"(`kairu link approve {number}`) to go to {answer.provider}.")

    def _expire(self) -> None:
        now = time.time()
        for old in [entry for entry in self.phone_waiting.values() if entry.expires <= now]:
            del self.phone_waiting[old.number]
            audit.record(self.store, "link", old.action, "approval expired", device=old.device, digest=old.digest)
            self.tell(old.device, "report", f"Your request for {old.action} waited 10 minutes without approval at the "
                                            "PC, so it ended. Nothing ran.")

    def _waiting(self, number: int) -> PhoneRequest:
        self._expire()
        if number not in self.phone_waiting:
            raise Refused(f"no request {number} from a phone is waiting (it may have ended after 10 minutes)")
        return self.phone_waiting[number]

    def _link_waiting(self):
        self._expire()
        now = time.time()
        names = {device.id: device.name for device in link_store.paired(self.data_dir)}
        return {"verdict": "ok", "waiting": [
            {"number": entry.number, "device": entry.device, "name": names.get(entry.device, "a removed device"),
             "action": entry.action, "details": entry.details, "description": entry.description,
             "seconds_left": int(entry.expires - now)} for entry in self.phone_waiting.values()]}

    def _link_approve(self, number, confirmation, pin):
        """Your answer, typed at this PC, to a phone's High request: "yes" and your PIN, then Guardian runs it."""
        entry = self._waiting(number)
        if entry.request_id:  # D3: a step of the phone's order; your PIN here approves it for its task core
            if entry.state != "waiting":
                raise Refused("that request was already answered")
            granted = self.guardian.approve(entry.request_id, confirmation, pin)  # "yes" and the PIN, or Refused
            entry.state, entry.token = "approved", granted.token
            self.tell(entry.device, "report", f"Approved {entry.action} at the PC with your PIN.")
            return {"verdict": "ok", "run": None, "pid": None, "step": True}  # its task core runs it now
        if confirmation.strip().lower() != "yes":
            del self.phone_waiting[number]
            audit.record(self.store, "link", entry.action, "refused at the PC", device=entry.device, digest=entry.digest)
            self.tell(entry.device, "report", f"Not approved at the PC: {entry.action} did not run.")
            raise Refused('not approved: you did not type "yes"')
        request = Action(entry.action, entry.details, private=True)
        decision = self.guardian.check(request)  # decided again now: things may have changed, e.g. Safe Mode
        if decision.verdict is not Verdict.NEEDS_APPROVAL:
            del self.phone_waiting[number]
            self.tell(entry.device, "report", f"{entry.action} can no longer be approved: {decision.reason}.")
            raise Refused(decision.reason)
        granted = self.guardian.approve(decision.request_id, confirmation, pin)  # a wrong PIN: it keeps waiting
        del self.phone_waiting[number]
        if entry.action not in executors.EXECUTORS:
            self.tell(entry.device, "report", f"Approved at the PC, but Kairu has no code that does {entry.action} yet, "
                                              "so nothing ran.")
            return {"verdict": "ok", "run": None, "pid": None}
        try:
            said, started = self.start_approved(entry, granted, "at the PC with your PIN")
        except Refused as refusal:
            self.tell(entry.device, "report", f"Approved at the PC, but {entry.action} did not start: {refusal}")
            raise
        self.tell(entry.device, "report", said)
        return started

    def _link_card(self, request_id, device, plan=None):
        """D3: a step of a phone's order needs approval: the phone's card (its fingerprint), or your PIN here."""
        waiting = self.guardian.waiting_action(request_id)
        if waiting is None:
            raise Refused("no such request is waiting for approval")
        if not link_kinds.DEVICE_ID.fullmatch(device) or link_store.find(self.data_dir, device) is None:
            raise Refused("not a paired device")
        action, expires = waiting
        if action.name == APPROVER:
            raise Refused("turning fingerprint approval on needs your PIN at the PC")
        if any(entry.request_id == request_id for entry in self.phone_waiting.values()):
            raise Refused("that request already has a card")
        rule = self.guardian.policy.rule(action.name) if self.guardian.policy else None
        number = next(self._phone_numbers)
        entry = PhoneRequest(number, device, action.name, dict(action.details), "0" * 64,
                             (rule.description if rule else "") + (f" ({plan[:300]})" if plan else ""), expires, request_id)
        self.phone_waiting[number] = entry
        audit.record(self.store, "link", action.name, "approval asked", device=device, request=request_id)
        if link_store.approver(self.data_dir, device):
            self.tell(device, "report", self.approval_card(entry))
        else:
            self.tell(device, "report", f"{action.name} is High tier: approve it at the PC with `kairu link approve {number}` "
                                        "(yes and your PIN). Turn on fingerprint approval to approve it here.")
        self.notify(f"Kairu: your phone's order needs {action.name}",
                    f"High tier. `kairu link approve {number}` (yes and your PIN), or approve it on the phone.")
        return {"verdict": "ok", "number": number}

    def _link_card_result(self, number):
        """D3: how a card ended: waiting, approved (with the approval for the task core, given once), refused or gone."""
        self._expire()
        entry = self.phone_waiting.get(number)
        if entry is None or not entry.request_id:
            return {"verdict": "ok", "state": "gone"}
        if entry.state == "waiting":
            return {"verdict": "ok", "state": "waiting"}
        del self.phone_waiting[number]
        return {"verdict": "ok", "state": entry.state, "approval": entry.token or None}

    def _link_refuse(self, number):
        entry = self._waiting(number)
        del self.phone_waiting[number]
        audit.record(self.store, "link", entry.action, "refused at the PC", device=entry.device, digest=entry.digest)
        self.tell(entry.device, "report", f"Refused at the PC: {entry.action} did not run.")
        return {"verdict": "ok"}

    def tell(self, device: str, kind: str, text: str) -> None:
        """Send a paired device a reply, as Guardian's own link.send action (decided and recorded like any)."""
        if not self.guardian.config.link_enabled:
            return
        try:
            self._run(SEND, {"device": device, "type": kind, "text": text[:1500]}, private=True)
        except Refused as refusal:
            log(f"no reply to {device}: {refusal}")

    def tell_all(self, text: str) -> None:
        for device in link_store.paired(self.data_dir):
            self.tell(device.id, "report", text)

    # --- after a run ends ----------------------------------------------------------------------

    def _run_ended(self, run: Run) -> None:
        """Told by the runner once any run has ended, however it ended."""
        if run.action == MISSION:
            put_back = self.put_lid_back(f"mission_mode.on {run.outcome}")
            ending = mission.last_ending(self.data_dir) or {}
            ending = ending if run.outcome == "finished" and time.time() - ending.get("at", 0) < 60 else {}
            if ending.get("reason") in HEAVY_ENDINGS:  # too hot, too busy or too long: what a phone started stops too
                for run_id in list(self.phone_runs):
                    self.runner.halt(run_id, f"Mission Mode ended: {mission.ENDINGS[ending['reason']]}")
            put_back = put_back or ending.get("put_back") or "the lid setting was not changed"
            if run.outcome == "halted":
                why = "it was ended at the PC, or by a stop"
            elif ending:
                why = mission.ENDINGS.get(ending.get("reason"), "it ended")
            else:
                why = "it could not start or it failed (Guardian's log says why; is the PC plugged in?)"
            self.tell_all(f"Mission Mode ended: {why}. {put_back[:1].upper()}{put_back[1:]}.")
        if run.action == PAIR:
            link_store.forget_offer(self.data_dir)
        asked = self.phone_asks.pop(run.run_id, None)
        if asked:
            self.answer_phone(run, *asked)
        if run.action == RUN_MISSIONS and run.outcome == "halted" and not self.ending:
            why = "an emergency stop" if safemode.is_safe(self.store) else "it was ended at the PC"
            for card in missions_store.MissionStore(self.data_dir).halt_running(
                    f"stopped by {why}; `kairu mission continue` goes on from its last checkpoint"):
                audit.record(self.store, "mission", RUN_MISSIONS, "card stopped", card=card, why=why)
        device = self.phone_runs.pop(run.run_id, None)
        if device and run.action != MISSION:  # Mission Mode's ending was told above, to every device
            self.tell(device, "report", f"{run.action} (run {run.run_id}) {run.outcome}.")

    def report_missions(self) -> None:
        """Tell you about each Mission Card that ended since: the tray, your phone, or both, as the card asks."""
        if not missions_store.exists(self.data_dir) or safemode.is_safe(self.store):
            return
        store = missions_store.MissionStore(self.data_dir)
        for card in store.unreported():
            text = missions_store.report_text(card)
            if card.report in ("pc", "both"):
                self.notify(f"Kairu: mission {card.id} {card.status}", text.splitlines()[0][:200], warning=card.status != "done")
            if card.report in ("phone", "both"):
                self.tell_all(text)
            store.mark_reported(card.id)
            audit.record(self.store, "mission", RUN_MISSIONS, f"card {card.status}", card=card.id, told=card.report)

    def put_lid_back(self, why: str) -> str | None:
        """Mission Mode's lid setting back to yours, if it is changed. What was done, recorded; None if nothing."""
        try:
            done = mission.restore(self.data_dir)
        except mission.MissionError as error:
            audit.record(self.store, "mission_mode", decision="restore failed", why=why, error=str(error)[:300])
            log(f"Mission Mode's lid setting could not be put back yet ({error}); trying again at the next start")
            return None
        if done:
            audit.record(self.store, "mission_mode", decision="restored", why=why, note=done)
            log(f"Mission Mode: {done} ({why})")
        return done

    def _run_status(self, run):
        known = self.runs.get(run)
        if known is None:
            raise Refused(f"Guardian knows no run {run}")
        return {"verdict": "ok", "run": run, "action": known.action, "pid": known.process.pid, "outcome": known.outcome}

    def _end(self, run):
        if run not in self.runs or not self.runner.halt(run, "ended at Kairu's request"):
            raise Refused(f"run {run} is not running")
        return {"verdict": "ok"}

    def _resume(self, confirmation, pin):
        self.guardian.resume(confirmation, pin)
        return {"verdict": "ok"}

    def _set_pin(self, new_pin, current_pin=None):
        try:
            kairu_pin.set_pin(self.store, new_pin, current_pin)
        except kairu_pin.PinError as error:
            raise Refused(str(error)) from None
        return {"verdict": "ok"}

    def _reanchor(self, confirmation, pin):
        verdict = audit.verify(self.store)
        if verdict.ok:
            return {"verdict": "ok", "note": "the audit log and its anchor already agree"}
        try:
            if verdict.kind == audit.CHAIN_BROKEN:
                raise Refused(f"rows inside the audit log were changed (row {verdict.bad_row}); re-anchoring cannot fix that")
            if confirmation.strip().lower() != "yes":
                raise Refused('not re-anchored: you did not type "yes"')
            ok, why = kairu_pin.check(self.store, pin)
            if not ok:
                raise Refused(why)
        except Refused as refusal:
            audit.record(self.store, "anchor", decision="re-anchor refused", reason=str(refusal))
            raise
        audit.reanchor(self.store, verdict)
        return {"verdict": "ok", "note": f"accepted the audit log as it is now ({verdict.rows} rows)"}

    def _status(self):
        guardian = self.guardian
        state = describe(self.store, guardian.config, guardian.policy, guardian.policy_error)
        running = [{"run": run.run_id, "action": run.action, "pid": run.process.pid} for run in self.runner.running()]
        return {"verdict": "ok", **state, "running": running, "pid": os.getpid(),
                "hotkey": self.keeper.state if self.keeper else "not held by this Guardian",
                "tray": self.tray.status if self.tray else "Windows only",
                "last_popup": self.last_popup, "tray_popup": list(self.tray.last_popup or []) if self.tray else None,
                "protect": "on" if self.protector else "off",
                "phone_waiting": len(self.phone_waiting),
                "shutdown_level": session.shutdown_level() if sys.platform == "win32" else None,
                "channel": self.server.address if self.server else ""}

    def _quit(self):
        audit.record(self.store, "guardian", decision="quit requested")
        self.quit_requested = True  # a clean exit
        if self.server:
            self.server.stop()
        return {"verdict": "ok"}


class Protector:
    """With protect.enabled in config.yaml: keeps Guardian's monitors (protect.watch) running.

    It starts them when Guardian starts in normal mode and when Safe Mode ends (`kairu resume`).
    After they fail, it starts them again after 30 s, 2 min, 10 min, then every 30 min. When they end
    by themselves (nothing to watch) or are halted (a stop, or `end`), it waits: for a resume, or
    for `kairu protect start` and the commands that give them something to watch. In Safe Mode it
    starts nothing. Every start goes through Guardian's decision and audit log, like any action.
    """

    POLL = 1.0
    ACTION = WATCH

    def __init__(self, service: "Service", log=print):
        self.service, self.log = service, log
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"kairu-{self.ACTION}", daemon=True)
        self._failures, self._next, self._watch, self._since, self._was_safe = 0, 0.0, None, 0.0, None

    def wanted(self) -> bool:
        """Whether there is anything for the action to do now (the Linker: a paired device)."""
        return True

    def look_again(self) -> None:
        """Start the action at the next chance if what it works on changed (the Linker: devices; the Missioner: cards)."""

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._closed.wait(self.POLL):
            try:
                self.tick()
            except Exception as error:  # keep watching over the monitors whatever happens
                self.log(f"protector: {type(error).__name__}: {error}")

    def tick(self) -> None:
        service, now = self.service, time.monotonic()
        safe = safemode.is_safe(service.store)
        if self._was_safe and not safe:  # resumed: start the monitors again now
            self._next, self._failures = 0.0, 0
        self._was_safe = safe
        running = [run for run in service.runner.running() if run.action == self.ACTION]
        if running:
            if self._watch is not running[0]:
                self._watch, self._since = running[0], now  # also one started with `kairu protect start`
            return
        if self._watch is not None:  # it ended
            outcome, ran, self._watch = self._watch.outcome, now - self._since, None
            if outcome == "failed":
                self._failures = 1 if ran > SETTLED_SECONDS else self._failures + 1
                wait = RETRY_SECONDS[min(self._failures, len(RETRY_SECONDS)) - 1]
                self._next = now + wait
                self.log(f"{self.ACTION} failed after {ran:.0f} s; Guardian starts it again in {wait} s")
            else:  # finished: nothing to watch; halted: a stop or `end`
                self._next = math.inf
        self.look_again()  # after the above, so that what changed meanwhile is not lost to "it ended: wait"
        if safe or now < self._next or service.quit_requested or self._closed.is_set() or not self.wanted():
            return
        try:
            started = service._run(self.ACTION)
        except Refused as refusal:
            self._next = now + 60
            self.log(f"{self.ACTION} was not started: {refusal}")
            return
        # followed from here, even if it ends before the next look
        self._watch, self._since, self._next = service.runs.get(started["run"]), now, math.inf


class Linker(Protector):
    """With link.enabled in config.yaml: keeps link.receive running while a device is paired.

    The same rules as the Protector: it starts the receiver when Guardian starts in normal mode (so the
    messages waiting in the Gate's queue are read), after a resume, and again after a failure, waiting
    longer each time; in Safe Mode it starts nothing. It also starts the receiver when a device is
    paired, and lets it end by itself when the last one is removed.
    """

    ACTION = RECEIVE

    def __init__(self, service: "Service", log=print):
        super().__init__(service, log)
        self._version = None

    def wanted(self) -> bool:
        return bool(link_store.paired(self.service.data_dir))

    def look_again(self) -> None:
        version = link_store.version(self.service.data_dir)
        if version != self._version:  # a device was paired or removed: start the receiver now, if it is wanted
            self._version, self._next, self._failures = version, 0.0, 0


class Missioner(Protector):
    """Keeps mission.run going while a Mission Card is queued, or was cut off half-way (BRAIN.md, B3).

    The same rules as the Protector: it starts mission.run when Guardian starts in normal mode (so a mission
    that a restart or a crash cut off goes on from its last checkpoint), after a resume, when a card is
    queued or continued, and again after a failure, waiting longer each time; in Safe Mode it starts
    nothing. When a card ends, it tells you as the card asks: the tray (pc), your phone (phone), or both.
    """

    ACTION = RUN_MISSIONS

    def __init__(self, service: "Service", log=print):
        super().__init__(service, log)
        self._version = None

    def wanted(self) -> bool:
        return missions_store.runnable(self.service.data_dir)

    def look_again(self) -> None:
        version = missions_store.version(self.service.data_dir)
        if version != self._version:  # a card was queued, continued or stopped: look again now
            self._version, self._next, self._failures = version, 0.0, 0

    def tick(self) -> None:
        super().tick()
        self.service.report_missions()


class OneGuardian:
    """Only one Guardian runs under your account at a time, whatever its data folder (so Ctrl+Alt+K reaches it).

    Windows: a named mutex in your session; Linux: a lock on a file only you can open. Both go away
    by themselves when the Guardian holding them ends, however it ends.
    """

    def __init__(self):
        if sys.platform == "win32":
            from kairu import winpipe
            self._held = winpipe.claim_mutex(f"Local\\KairuGuardian-{winpipe.current_user_sid()}")
            if self._held is None:
                raise channel.ChannelTaken("another Guardian is already running under your account")
            return
        import fcntl
        folder = Path(os.environ.get("XDG_RUNTIME_DIR") or Path.home() / ".local" / "state") / "kairu"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._held = os.open(folder / "guardian.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self._held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._held)
            raise channel.ChannelTaken("another Guardian is already running under your account") from None

    def release(self) -> None:
        if self._held is None:
            return
        if sys.platform == "win32":
            from kairu import winpipe
            winpipe.close(self._held)
        else:
            os.close(self._held)
        self._held = None


RUNNING = "guardian_running"  # in guardian.db: set while Guardian runs, cleared only by a clean exit
CLEAN_EXIT = "guardian_clean_exit"  # how it ended cleanly, until the audit log has a row saying so


def log(text: str) -> None:
    """One line in guardian.log, with the time, written at once."""
    if sys.stderr is not None:
        print(f"{datetime.now().isoformat(timespec='milliseconds')} guardian: {text}", file=sys.stderr, flush=True)


class Lifetime:
    """Guardian's start and its end, and whether that end was clean.

    Clean: `kairu guardian quit`, or Windows saying you sign out, shut down or restart. Anything
    else (End task, a crash, a kill, a power cut) leaves RUNNING set, and the next Guardian then
    starts in Safe Mode, because it cannot be sure what happened in between.

    A clean exit is recorded first, as one small write (RUNNING cleared, CLEAN_EXIT saying why),
    before anything else is ended, because at a sign-out Windows may end Guardian at any moment.
    Its audit row follows; if Windows ends Guardian before that, the next start writes it.
    """

    def __init__(self, guardian: Guardian, server: channel.Server, service: Service, one: OneGuardian):
        self.guardian, self.store, self.server, self.service, self.one = guardian, guardian.store, server, service, one
        self.keeper: hotkey.Keeper | None = None
        self.unclean_reason = "it ended without a clean exit"
        self.running_since = ""
        self._lock, self._ended = threading.Lock(), False

    def begin(self) -> None:
        previous, clean = self.store.get(RUNNING, ""), self.store.get(CLEAN_EXIT, "")
        if previous:
            audit.record(self.store, "guardian", decision="unclean exit found", previous=previous)
            safemode.enter(self.store, f"the last Guardian ({previous}) ended without a clean exit")
        elif clean:  # the last one recorded its clean exit, but was ended before its audit row
            with self.store.transaction() as db:
                audit.record(self.store, "guardian", decision="stopped", db=db, clean=True, why=clean,
                             note="recorded at the next start")
                self.store.put(CLEAN_EXIT, "", db)
        with self.store.transaction() as db:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.running_since = f"process {os.getpid()}, started {now}"
            self.store.put(RUNNING, self.running_since, db)
            self.store.put(CLEAN_EXIT, "", db)
            audit.record(self.store, "guardian", decision="started", db=db, pid=os.getpid(), channel=self.server.address)

    def record_clean(self, why: str) -> None:
        """The clean exit, in one small write and nothing else: no audit row, no anchor, no waiting."""
        began = time.perf_counter()
        with self.store.transaction() as db:
            self.store.put(RUNNING, "", db)
            self.store.put(CLEAN_EXIT, f"{why} ({self.running_since})", db)
        log(f"clean exit recorded ({why}) in {(time.perf_counter() - began) * 1000:.0f} ms")

    def take_back(self) -> None:
        """The end of the session was cancelled: Guardian runs on, so a clean exit recorded early no longer holds."""
        with self._lock:
            if self._ended:
                return
            with self.store.transaction() as db:
                self.store.put(RUNNING, self.running_since, db)
                self.store.put(CLEAN_EXIT, "", db)
        log("the clean exit recorded early was taken back")

    def ending(self) -> None:
        """Windows itself says the session is ending (not only a message saying so): record the clean exit now."""
        with self._lock:
            if not self._ended:
                self.record_clean("sign-out, shutdown or restart (asked)")

    def interrupt(self, why: str) -> None:
        """Linux `kill`: end, but not cleanly; Guardian cannot tell it from a kill that was not a sign-out."""
        self.unclean_reason = why
        self.server.stop()

    def end(self, why: str, clean: bool, halt: str) -> None:
        """Record a clean exit first; then stop answering, end every action, let go of Ctrl+Alt+K. Once only."""
        with self._lock:
            if self._ended:
                return
            self._ended = True
            if clean:
                try:
                    self.record_clean(why)
                except Exception as error:  # then RUNNING is still set, and the next start is in Safe Mode
                    log(f"the clean exit could not be recorded ({error})")
        self.server.stop()
        self.service.close(halt)
        if self.keeper:
            self.keeper.close()
        try:
            with self.store.transaction() as db:
                audit.record(self.store, "guardian", decision="stopped", db=db, pid=os.getpid(), why=why, clean=clean)
                self.store.put(CLEAN_EXIT, "", db)
        except Exception as error:
            log(f"the exit's audit row could not be written ({error})")
        log(f"stopped: {why} ({'clean' if clean else 'not clean'})")
        self.one.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kairu.guardian_program", description="The Guardian program.")
    parser.add_argument("--config", help="config.yaml to use")
    args = parser.parse_args(argv)
    try:
        cfg = kairu_config.load(args.config)
        if args.config:  # the actions Guardian starts (task.order's task core) read the same config.yaml
            os.environ["KAIRU_CONFIG"] = str(Path(args.config).resolve())
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        if sys.stderr is None:  # pythonw with nowhere to write: keep Guardian's messages in the data folder
            sys.stderr = open(cfg.data_dir / "guardian.log", "a", encoding="utf-8", buffering=1)
        one = OneGuardian()  # first: the only Guardian under this account
    except (kairu_config.ConfigError, channel.ChannelError, OSError) as error:
        log(f"not started: {error}")
        return 1
    try:
        try:
            server = channel.Server(cfg.data_dir)  # then: claim the channel, or refuse to start
        except (channel.ChannelError, OSError) as error:
            log(f"not started: {error}")
            return 1
        try:
            return _run(cfg, server, one)
        finally:
            server.close()
    finally:
        one.release()


def _run(cfg, server: channel.Server, one: OneGuardian) -> int:
    try:
        guardian = Guardian(cfg)
    except MissingDatabase as error:
        log(f"not started: {error}")
        return 2
    early = session.notify_early()  # told among the first programs when the session ends
    service = Service(guardian, server)
    lifetime = Lifetime(guardian, server, service, one)
    lifetime.begin()
    service.put_lid_back("found at Guardian's start: the PC or Guardian ended while Mission Mode was on")
    link_store.forget_offer(cfg.data_dir)  # a pairing offer cannot outlive the Guardian that made it
    service.keeper = lifetime.keeper = hotkey.Keeper(lambda: service.runner.stop(hotkey.NAME))
    service.keeper.start()
    tray = None
    if sys.platform == "win32":
        from kairu import tray as kairu_tray

        def tray_state():
            return kairu_tray.describe(safemode.mode(service.store), safemode.reason(service.store),
                                       len(service.runner.running()), service.keeper.held)

        tray = kairu_tray.Tray(tray_state, lambda: service.runner.stop("tray: Stop everything"), log)
    service.tray = tray
    window = session.GuardianWindow(os.getpid(), lambda kind: lifetime.end(kind, clean=True, halt=f"Guardian ended: {kind}"),
                                    lifetime.ending, lifetime.take_back, tray, log)
    window.start()
    signal.signal(signal.SIGTERM, lambda signum, frame: lifetime.interrupt("ended by a signal (kill)"))
    if cfg.protect_enabled:
        service.protector = Protector(service, log)
        service.protector.start()
    if cfg.link_enabled:
        service.linker = Linker(service, log)
        service.linker.start()
    service.missioner = Missioner(service, log)
    service.missioner.start()
    log(f"running as process {os.getpid()} on {server.address}; Ctrl+Alt+K: {service.keeper.state}; "
        f"told early at the end of the session: {early}; tray: {tray.status if tray else 'Windows only'}; "
        f"protection: {'on' if cfg.protect_enabled else 'off'}; link: {cfg.link_relay if cfg.link_enabled else 'off'}")
    try:
        server.serve(service.answer, service.refuse)
    finally:
        if service.quit_requested:
            lifetime.end("kairu guardian quit", clean=True, halt="Guardian quit")
        else:
            lifetime.end(lifetime.unclean_reason, clean=False, halt="Guardian ended")
        window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
