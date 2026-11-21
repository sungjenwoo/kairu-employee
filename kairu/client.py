"""How Kairu asks the Guardian program, over the private channel (kairu/channel.py).

GuardianClient answers check, approve, authorize and resume like Guardian itself, so the terminal
prompt (kairu/approval.py) works with it unchanged, and run() asks Guardian to start an action.
Every answer comes from the Guardian program.
When it is not running, cannot be reached, is not really Guardian, or answers with something that
cannot be read, the request is refused.

start_guardian() is `kairu guardian run`: it starts the Guardian program in the background, with no window.
When Kairu is used while Guardian is down and `kairu guardian install` made a task for it, the
client asks Task Scheduler to start Guardian (kairu/autostart.py), and still refuses until it answers.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from kairu import autostart, channel
from kairu.config import ROOT
from kairu.guardian import Action, Approval, Decision, Refused, Verdict
from kairu.policy import Tier

RESTARTED_WITH_GUARDIAN = ("protect.watch", "link.receive", "mission.run")  # actions Guardian starts again itself
START_SECONDS = 20  # how long `kairu guardian run` waits for Guardian to answer
LOG_NAME = "guardian.log"  # in the data folder: what Guardian programs printed, newest last
LOG_KEEP = 256 * 1024  # bytes; a longer log moves to guardian.log.1 at the next start


def unavailable(error: channel.ChannelError) -> str:
    if isinstance(error, channel.NotRunning):
        if getattr(error, "start_requested", False):
            return ("Guardian is not running, so Kairu refuses every request. Kairu asked Task Scheduler to start it; "
                    "try again in a few seconds")
        return "Guardian is not running, so Kairu refuses every request. Start it with `kairu guardian run`"
    return str(error)


class GuardianClient:
    def __init__(self, cfg, start_if_down: bool = True):
        self.config = cfg
        self.data_dir = Path(cfg.data_dir).resolve()
        self.start_if_down = start_if_down  # ask Task Scheduler to start Guardian when it is down (if installed)

    def ask(self, message: dict) -> dict:
        """Guardian's answer. Raises channel.ChannelError (NotRunning, NotGuardian, ...) when there is none."""
        try:
            return channel.request(self.data_dir, message)
        except channel.NotRunning as error:
            if self.start_if_down and autostart.request_start(self.data_dir):
                error.start_requested = True  # this request is still refused; Guardian answers the next ones
            raise

    def alive(self) -> bool:
        """True if Guardian answers, checked as for any request; False if it is not running. Asks nothing."""
        try:
            channel.connect(self.data_dir).close()
        except channel.NotRunning:
            return False
        return True

    def check(self, action: Action | str) -> Decision:
        action = Action(action) if isinstance(action, str) else action
        return self._decision(action, {"op": "check", "action": action.name, "details": dict(action.details)})

    def authorize(self, action: Action | str, approval: Approval | None = None) -> Decision:
        action = Action(action) if isinstance(action, str) else action
        return self._decision(action, {"op": "authorize", "action": action.name, "details": dict(action.details),
                                       "approval": approval.token if approval else None})

    def approve(self, request_id: str, confirmation: str, pin: str) -> Approval:
        """Raises Refused unless Guardian approved."""
        reply = self._ok({"op": "approve", "request_id": request_id or "", "confirmation": confirmation, "pin": pin})
        token, action, expires = reply.get("approval"), reply.get("action"), reply.get("expires_at")
        if not (isinstance(token, str) and isinstance(action, str) and type(expires) in (int, float)):
            raise Refused("Guardian's answer could not be read")
        return Approval(token, action, float(expires))

    def run(self, action: Action | str, approval: Approval | None = None) -> dict:
        """Ask Guardian to start the action, with its details as the arguments: {"run": id, "pid": its process}.

        Guardian decides first, then runs its own code for the action. Raises Refused otherwise.
        """
        action = Action(action) if isinstance(action, str) else action
        reply = self._ok({"op": "run", "action": action.name, "details": dict(action.details),
                          "approval": approval.token if approval else None})
        if type(reply.get("run")) is not int or type(reply.get("pid")) is not int:
            raise Refused("Guardian's answer could not be read")
        return reply

    def run_status(self, run_id: int) -> dict:
        """{"outcome": None while it runs, then "finished", "refused", "failed" or "halted", ...}. Raises Refused."""
        reply = self._ok({"op": "run_status", "run": run_id})
        if reply.get("outcome") not in (None, "finished", "refused", "failed", "halted"):
            raise Refused("Guardian's answer could not be read")
        return reply

    def end(self, run_id: int) -> None:
        """End one running action and all its programs (no Safe Mode). Raises Refused if it is not running."""
        self._ok({"op": "end", "run": run_id})

    def resume(self, confirmation: str, pin: str) -> None:
        self._ok({"op": "resume", "confirmation": confirmation, "pin": pin})

    def link_card(self, request_id: str, device: str, plan: str | None = None) -> int:
        """D3: show a paired phone the card for one waiting step; its fingerprint answers it. The card's number."""
        return int(self._ok({"op": "link_card", "request_id": request_id, "device": device, "plan": plan})["number"])

    def link_card_result(self, number: int) -> dict:
        """D3: {"state": waiting | approved | refused | gone, "approval": token when approved (given once)}."""
        return self._ok({"op": "link_card_result", "number": number})

    def link_waiting(self) -> list[dict]:
        """The High requests from your phone waiting for "yes" and your PIN here. Raises Refused."""
        waiting = self._ok({"op": "link_waiting"}).get("waiting")
        if not isinstance(waiting, list):
            raise Refused("Guardian's answer could not be read")
        return waiting

    def link_approve(self, number: int, confirmation: str, pin: str) -> dict:
        """Approve one waiting phone request: Guardian runs it. {"run": id or None, "pid": ...}. Raises Refused."""
        return self._ok({"op": "link_approve", "number": number, "confirmation": confirmation, "pin": pin})

    def link_refuse(self, number: int) -> None:
        self._ok({"op": "link_refuse", "number": number})

    def set_pin(self, new_pin: str, current_pin: str | None = None) -> None:
        self._ok({"op": "set_pin", "new_pin": new_pin, "current_pin": current_pin})

    def reanchor(self, confirmation: str, pin: str) -> str:
        return str(self._ok({"op": "reanchor", "confirmation": confirmation, "pin": pin}).get("note", ""))

    def status(self) -> dict:
        """Guardian's own view (kairu.guardian_program.describe, with its pid and channel). Raises ChannelError."""
        reply = self.ask({"op": "status"})
        if (reply.get("verdict") != "ok" or type(reply.get("pid")) is not int or not isinstance(reply.get("policy"), dict)
                or not isinstance(reply.get("audit"), dict)):
            raise channel.ChannelError("Guardian's answer could not be read")
        return reply

    def quit(self) -> None:
        """Raises ChannelError if Guardian was not asked."""
        if self.ask({"op": "quit"}).get("verdict") != "ok":
            raise channel.ChannelError("Guardian did not agree to quit")

    def _ok(self, message: dict) -> dict:
        try:
            reply = self.ask(message)
        except channel.ChannelError as error:
            raise Refused(unavailable(error)) from None
        if reply.get("verdict") != "ok":
            raise Refused(reply["reason"] if isinstance(reply.get("reason"), str) else "Guardian refused")
        return reply

    def _decision(self, action: Action, message: dict) -> Decision:
        try:
            reply = self.ask(message)
        except channel.ChannelError as error:
            return Decision(Verdict.DENY, action, None, unavailable(error))
        try:
            verdict = Verdict(reply["verdict"])
            tier = None if reply.get("tier") is None else Tier(reply["tier"])
            reason, description, request_id = reply.get("reason"), reply.get("description", ""), reply.get("request_id")
            if not isinstance(reason, str) or not isinstance(description, str):
                raise ValueError
            if verdict is Verdict.NEEDS_APPROVAL and not isinstance(request_id, str):
                raise ValueError
        except (KeyError, ValueError, TypeError):
            return Decision(Verdict.DENY, action, None, "Guardian's answer could not be read")
        return Decision(verdict, action, tier, reason, description,
                        request_id if verdict is Verdict.NEEDS_APPROVAL else None,
                        pin=not (verdict is Verdict.NEEDS_APPROVAL and reply.get("pin") is False))  # only shapes the card


# --- kairu guardian run / quit --------------------------------------------------------------------

def start_guardian(cfg, config_file) -> tuple[dict, bool]:
    """Start the Guardian program in the background, with no window, unless it runs already.

    (its status, True only if this call started the Guardian that answers). Raises channel.NotGuardian if
    another program holds Guardian's channel, and channel.ChannelError if Guardian did not start.
    """
    client = GuardianClient(cfg, start_if_down=False)
    if client.alive():
        return client.status(), False
    client.data_dir.mkdir(parents=True, exist_ok=True)
    log = client.data_dir / LOG_NAME
    python, environment = guardian_python()
    argv = [python, "-m", channel.GUARDIAN_MODULE, "--config", str(Path(config_file).resolve())]
    if log.exists() and log.stat().st_size > LOG_KEEP:  # keep what earlier Guardians wrote, within reason
        os.replace(log, log.with_name(LOG_NAME + ".1"))
    with open(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "ab") as output:
        process = _spawn(argv, output, environment)
    deadline = time.monotonic() + START_SECONDS
    while True:
        try:
            state = client.status()
            return state, _started_by(process, state["pid"])  # or another Guardian, started meanwhile
        except channel.NotRunning:
            pass
        except channel.NotGuardian:
            if process.poll() is not None:
                raise
        if process.poll() is not None:
            raise channel.ChannelError(f"Guardian ended as it started: {_tail(log)}")
        if time.monotonic() > deadline:
            raise channel.ChannelError(f"Guardian did not answer within {START_SECONDS} s; see {log}")
        time.sleep(0.1)


def quit_guardian(cfg, wait: float = 10.0) -> None:
    """Ask Guardian to end, and wait until it has. Raises ChannelError (NotRunning if it was not running)."""
    client = GuardianClient(cfg, start_if_down=False)  # and not ask Task Scheduler to start it again
    client.quit()
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            client.status()
        except channel.NotRunning:
            return
        except channel.ChannelError:
            pass
        time.sleep(0.05)
    raise channel.ChannelError(f"Guardian agreed to quit but was still running after {wait:g} s")


def pause_for_check(cfg, seconds: float = 900) -> bool:
    """tools/check_guardian.py: end your Guardian while the tests run, and keep Task Scheduler from starting it.

    True if it was running. Refuses (Refused) if it is running actions, which ending it would end too.
    Guardian's own monitors (protect.watch), the Link receiver (link.receive) and the missions (mission.run) do not
    count: they start again with Guardian; the monitors report the time they were not running as a gap, the
    receiver reads what waited in the Gate meanwhile, and a mission goes on from its last checkpoint.
    """
    client = GuardianClient(cfg, start_if_down=False)
    running = client.alive()
    if not running and not autostart.installed(cfg.data_dir):
        return False  # nothing to pause
    if running and [run for run in client.status()["running"] if run["action"] not in RESTARTED_WITH_GUARDIAN]:
        raise Refused("your Guardian is running actions; wait until they end, or stop them, then check again")
    autostart.pause(cfg.data_dir, seconds)  # runs out by itself, should the check never get to the end
    try:
        quit_guardian(cfg)
    except channel.NotRunning:
        return False
    return True


def resume_after_check(cfg, config_file, was_running: bool) -> None:
    autostart.unpause(cfg.data_dir)
    if was_running:
        start_guardian(cfg, config_file)


def _started_by(process: subprocess.Popen, pid: int) -> bool:
    """True if `pid` is this process, or its child (as when a venv's starter runs the real Python)."""
    if pid == process.pid:
        return True
    try:
        if sys.platform == "win32":
            from kairu import winpipe
            return winpipe.parent_pid(pid) == process.pid
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1]) == process.pid
    except (OSError, ValueError, IndexError):
        return False


def windowless_python() -> str:
    if sys.platform == "win32":  # pythonw.exe is Python without a console window
        quiet = Path(sys.executable).with_name("pythonw.exe")
        if quiet.exists():
            return str(quiet)
    return sys.executable


def guardian_python() -> tuple[str, dict | None]:
    """The program Guardian runs as, and its environment (None: this one's).

    On Windows, a venv's pythonw.exe is only a small starter: it runs the real pythonw.exe as its
    child, which dies with it. The starter has no window, so at sign-out Windows ends it without
    asking, and Guardian with it, before Guardian could record a clean exit. So Guardian runs the
    real pythonw.exe directly, told by __PYVENV_LAUNCHER__ to use the venv, as the starter would.
    """
    quiet = windowless_python()
    if sys.platform != "win32" or sys.prefix == sys.base_prefix:
        return quiet, None
    real = Path(getattr(sys, "_base_executable", "") or sys.executable).with_name("pythonw.exe")
    if not real.exists():
        return quiet, None
    return str(real), {**os.environ, "__PYVENV_LAUNCHER__": quiet}


def _spawn(argv: list[str], output, environment: dict | None = None) -> subprocess.Popen:
    common = dict(cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output, env=environment)
    if sys.platform != "win32":
        return subprocess.Popen(argv, start_new_session=True, **common)  # no terminal: it outlives this one
    # no console at all with pythonw; a hidden one otherwise. Its own process group, so Ctrl+C here does not reach it
    flags = (subprocess.DETACHED_PROCESS if argv[0].lower().endswith("pythonw.exe") else subprocess.CREATE_NO_WINDOW)
    flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(argv, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **common)
    except OSError:  # this terminal's job does not let programs leave it; Guardian then ends with the terminal
        return subprocess.Popen(argv, creationflags=flags, **common)


def _tail(log: Path, lines: int = 8) -> str:
    try:
        text = log.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "(no output)"
    return " | ".join(text.splitlines()[-lines:]) or "(no output)"
