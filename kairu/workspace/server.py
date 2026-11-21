"""The workspace's server: the window's page and the small API behind it, on 127.0.0.1 only, for one key per start.

    Workspace       what the window shows and does: projects, missions, the order that runs, Guardian's approval card
    serve(...)      the HTTP server around it (the standard library's ThreadingHTTPServer)

The workspace holds no authority. An order goes to the task core (kairu/tasks/core.py) exactly as from the bar, so Guardian
decides every step: Low and Medium run, High waits for "yes" and your PIN on the card, Critical is refused, and an unknown
action is denied. The card's two boxes are filled only by your own typing in the window: no code here or in the page fills
them or presses their buttons (a test reads both to check). What you typed goes to GuardianClient.approve, as in the bar,
and is then forgotten. A card nobody answers ends as a refusal.

Who may talk to it. The server listens on 127.0.0.1 only. Every API call must carry the key made for this start (header
X-Kairu-Key), and its Host must be this server's own address, so a web page in any browser can't reach it, even through a
name that points at 127.0.0.1. The key is in workspace.json in Guardian's data folder (yours only) and in the window's
address after the #, which never goes over the network. It does not keep out a program that already runs as you: such a
program could also type into the bar. That is why the PIN stays Guardian's, and the server never sees or keeps it.

What you type in a mission is kept in data/workspace.db on this PC (kairu/workspace/store.py), never in the audit log.

The voice (W2, ADR-036; VOICE.md's rules, kairu/bar/voice.py's code). With voice.enabled the workspace has the bar's mic
switch too, off at every start. Only your own click on the page's mic button or your own Ctrl+M in the window switches it on:
the page sends /api/mic from those two places only, and mic_pressed() is the one caller here (a test reads both). Each
order you say goes into the mission open in the window (or a new one) through the same task core, so Guardian decides every
step, and a spoken "yes" or PIN is never an answer to the card. The mic goes off on Stop and every emergency stop, when the
PC locks or sleeps, when no window has asked the server anything for WINDOW_GONE_SECONDS, and when the workspace ends.
One mic for the bar and the workspace: whichever switched on first holds the voice link while its mic is on.
"""

import hmac
import json
import re
import secrets
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kairu import channel
from kairu.client import GuardianClient
from kairu.guardian import Refused
from kairu.workspace.store import BadName, NotFound, WorkspaceStore, title_for

PAGE = Path(__file__).with_name("page.html")
CARD_SECONDS = 110  # a little less than Guardian's own limit on an approval, as in the bar
LONGEST_BODY = 64 * 1024
DRAIN_MOST = 1024 * 1024  # a too-long body up to this is read and dropped before the refusal
LONGEST_ORDER = 2000
HIDDEN_FROM_THE_CARD = ("job", "ask", "source")
STOP_WORDS = re.compile(r"(?:(?:hey )?kairu[,.!]? )?(?:stop|stop it|stop everything|cancel)[.!]?", re.IGNORECASE)
HOSTS = ("127.0.0.1", "localhost")
WINDOW_GONE_SECONDS = 15  # no window has asked for /api/state this long: the last one has closed, so the mic goes off
YOU_ARE_IN_IT = "You're in the workspace already."


class Busy(Exception):
    """Kairu is still on the last order."""


class Workspace:
    """Everything the window can see and do. The HTTP handler only turns requests into these calls."""

    def __init__(self, cfg, client=None, core=None, store=None):
        self.cfg = cfg
        self.client = client or GuardianClient(cfg)
        self.store = store or WorkspaceStore(cfg.data_dir)
        self._lock = threading.Lock()
        self._run: dict | None = None  # the order that runs: {"mission", "order", "steps", "thinking", "started"}
        self._card: dict | None = None  # the card waiting for you
        self._threads: list[threading.Thread] = []
        self.open_window = None  # set by the program: opens one more window
        self.voice = None  # VoiceControl (kairu/bar/voice.py), with voice.enabled: start_voice()
        self._watch = None
        self._voice_where: tuple[int | None, int | None] = (None, None)  # the mission (or project) open in the window
        self._voice_line = ""  # what the voice last said in the window: "Mic on", an answer, a problem
        self._heard = ""
        self._seen = time.monotonic()  # the last time a window asked for the state
        self._voice_closed = threading.Event()
        if core is None:
            from kairu.tasks.core import TaskCore
            core = TaskCore(cfg, self.client, approver=self.ask_approval, confirmer=self.ask_confirmation,
                            plan_approver=self.ask_plan_approval, progress=self._progress)
        self.core = core

    # --- what the window shows ---------------------------------------------------------------------

    def guardian(self) -> dict:
        try:
            state = self.client.status()
        except channel.ChannelError:
            return {"state": "down", "text": "Guardian is not running"}
        if state.get("mode") == "safe":
            return {"state": "safe", "text": f"Safe Mode: {state.get('safe_reason') or 'a stop'}"}
        return {"state": "running", "text": "Guardian is on"}

    def overview(self) -> dict:
        self._seen = time.monotonic()
        with self._lock:
            run = _copy(self._run)
            card = _public_card(self._card)
        return {"guardian": self.guardian(), "projects": self.store.projects(), "archived": self.store.projects(archived=True),
                "recent": self.store.missions(most=30), "run": run, "card": card, "voice": self.voice_state()}

    def mission(self, number: int, after: int = 0) -> dict:
        mission = self.store.mission(number)
        project = self.store.project(mission["project"]) if mission["project"] is not None else None
        with self._lock:
            run = _copy(self._run) if self._run and self._run["mission"] == number else None
            card = _public_card(self._card) if self._run and self._run["mission"] == number else None
        return {"mission": mission, "project": project, "messages": self.store.messages(number, after), "run": run, "card": card,
                "files": self.store.files(number)}

    def protection(self) -> dict:
        """Guardian's page: its state and the newest open alerts from its monitors (PROTECTION.md). Read only."""
        alerts, deadlines = [], []
        try:
            from kairu.protect.store import ProtectStore
            if (Path(self.cfg.data_dir) / "protect.db").exists():
                protect = ProtectStore(self.cfg.data_dir)
                alerts = [{"id": alert.id, "title": alert.title, "severity": alert.severity, "source": alert.source,
                           "created": alert.created.isoformat(), "you_can": alert.you_can} for alert in protect.alerts(limit=20)]
                deadlines = [{"title": item.get("title"), "due": str(item.get("due"))} for item in protect.deadlines()][:10]
        except Exception as error:  # the page still shows Guardian's state
            print(f"kairu workspace: alerts: {type(error).__name__}", file=sys.stderr, flush=True)
        return {"guardian": self.guardian(), "alerts": alerts, "deadlines": deadlines}

    def devices(self) -> dict:
        """The paired devices (LINK.md). Read only: pairing and removing stay `kairu link` commands."""
        try:
            from kairu.link import store as link_store
            found = link_store.paired(self.cfg.data_dir) if link_store.exists(self.cfg.data_dir) else []
        except Exception as error:
            print(f"kairu workspace: devices: {type(error).__name__}", file=sys.stderr, flush=True)
            found = []
        return {"devices": [{"name": device.name, "paired": device.paired_at, "seen": device.last_seen} for device in found]}

    def team(self, project: int | None = None) -> dict:
        """The Clones page (TEAM.md): the team board from data/team.db. Read only: adding Clones and starting projects stay
        `kairu team` commands, so this window still holds no authority."""
        try:
            from kairu.team.board import board
            return board(self.cfg.data_dir, project)
        except Exception as error:
            print(f"kairu workspace: team: {type(error).__name__}", file=sys.stderr, flush=True)
            return {"clones": [], "projects": [], "project": None}

    def meetings(self, number: int | None = None) -> dict:
        """The Meetings page (HACKATHON.md stage 1): what came out of each meeting, from data/meetings.db. Read only: reading
        or recording a meeting is an order ("read the meeting NAME", "record the meeting"), decided by Guardian."""
        try:
            from kairu.meeting.conduct import live
            from kairu.meeting.store import MeetingStore, exists
            found = MeetingStore(self.cfg.data_dir).meetings() if exists(self.cfg.data_dir) else []
            chosen = number or (found[0]["number"] if found else None)
            meeting = MeetingStore(self.cfg.data_dir).meeting(chosen, transcript=True) if chosen else None
            return {"meetings": found, "meeting": meeting, "live": live(self.cfg.data_dir),
                    "work_folder": str(self.cfg.work_folder)}
        except Exception as error:
            print(f"kairu workspace: meetings: {type(error).__name__}", file=sys.stderr, flush=True)
            return {"meetings": [], "meeting": None, "live": None, "work_folder": str(self.cfg.work_folder)}

    # --- an order ----------------------------------------------------------------------------------

    def order(self, mission: int | None, text: str, project: int | None = None) -> dict:
        """Give Kairu an order in a mission (a new one if mission is None). It runs on a thread of its own."""
        text = " ".join(str(text or "").split())
        if STOP_WORDS.fullmatch(text):  # also while an order runs: what Stop does
            return {"stopped": self.stop()}
        mission = self._begin(mission, text, project)
        self._start(self._work, mission, text)
        return {"mission": mission}

    def _begin(self, mission: int | None, text: str, project: int | None) -> int:
        """The order is kept in its mission (made if None) and becomes the one that runs. Busy if one runs already."""
        if not text:
            raise BadName("Type an order first")
        if len(text) > LONGEST_ORDER:
            raise BadName(f"An order can have at most {LONGEST_ORDER} characters")
        with self._lock:
            if self._run is not None:
                raise Busy("Kairu is still on the last order. Say stop to end it.")
            if mission is None:
                mission = self.store.add_mission(title_for(text), project)["id"]
            else:
                self.store.mission(mission)
            self.store.say(mission, "you", text)
            self._run = {"mission": mission, "order": text, "steps": [], "thinking": False, "started": time.time()}
        return mission

    def _work(self, mission: int, text: str) -> str:
        try:
            from kairu.workspace.app import OPEN_WORKSPACE
            reply = YOU_ARE_IN_IT if OPEN_WORKSPACE.fullmatch(text) else self.core.handle(text)
        except Exception as error:  # the workspace keeps working; what is running belongs to Guardian
            print(f"kairu workspace: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            reply = "Something went wrong in the workspace; workspace.log says what."
        try:
            self.store.say(mission, "kairu", reply or "Done.")
        except NotFound:  # the mission was deleted while it ran
            pass
        finally:
            with self._lock:
                self._run = None
        return reply

    def _progress(self, event: dict) -> None:
        """The task core's progress: shown on the right, and each finished step kept in the mission."""
        with self._lock:
            run = self._run
            if run is None:
                return
            if event.get("kind") == "thinking":
                run["thinking"] = True
            elif event.get("kind") == "steps":
                run["thinking"] = False
                run["steps"] = [{"label": str(step.get("label", "")), "state": "waiting", "text": ""} for step in event.get("steps", [])]
                run["files"] = [[dict(item) for item in step.get("files") or [] if isinstance(item, dict)]
                                for step in event.get("steps", [])]  # kept for the Files panel, not shown with the steps
            elif event.get("kind") == "step":
                number = int(event.get("number", 0)) - 1
                if 0 <= number < len(run["steps"]):
                    run["steps"][number].update(state=str(event.get("state")), text=str(event.get("text", "")))
                    step, mission = dict(run["steps"][number]), run["mission"]
                    files = (run.get("files") or [])[number] if number < len(run.get("files") or []) else []
                else:
                    return
            else:
                return
        if event.get("kind") == "step" and step["state"] in ("done", "not done"):
            try:
                self.store.say(mission, "step", step["label"], step["state"])
                for item in files if step["state"] == "done" else []:
                    self.store.note_file(mission, str(item.get("name", "")), str(item.get("how", "")))
            except NotFound:
                pass

    def stop(self) -> str:
        """What `kairu stop` does: every running action halts within a second, then Safe Mode. The mic goes off too."""
        from kairu import safemode
        from kairu.store import MissingDatabase, Store
        if self.voice is not None:
            self._start(self.voice.mic_off, "Stopped everything, and the mic is off. Safe Mode until `kairu resume`.")
        try:
            safemode.emergency_stop(Store(self.cfg.data_dir), "the Kairu workspace")
        except MissingDatabase as error:
            return f"The stop could not be written: {error}"
        self._start(self._after_stop)
        return "Stopped everything. Safe Mode until `kairu resume`."

    def _after_stop(self) -> None:
        from kairu import cli
        try:
            cli._stop_mission_mode(self.cfg)
        except Exception as error:
            print(f"kairu workspace: after the stop: {type(error).__name__}", file=sys.stderr, flush=True)

    # --- the voice (W2): only your own click or Ctrl+M switches the mic on ---------------------------------

    def start_voice(self) -> bool:
        """With voice.enabled: the mic switch, off. The voice link is claimed only when you switch the mic on."""
        if not self.cfg.voice_enabled or self.voice is not None:
            return False
        from kairu.bar.session_watch import SessionWatch
        from kairu.bar.voice import VoiceControl
        self.voice = voice = VoiceControl(self.cfg, self.client, _SpokenOrders(self), _VoiceScreen(self))
        self._watch = SessionWatch(lambda why: voice.mic_off(f"Mic off: {why}."))
        threading.Thread(target=self._watch_windows, name="kairu-workspace-windows", daemon=True).start()
        return True

    def mic_pressed(self, how: str) -> None:
        """/api/mic: your click on the mic button ("button") or your Ctrl+M in the window ("key"). The one caller here."""
        if self.voice is None:
            raise BadName("Voice is off: voice.enabled in config.yaml (VOICE.md)")
        self._seen = time.monotonic()
        if how == "key":
            self.voice.listen_key()
        else:
            self.voice.mic_button()

    def voice_where(self, mission: int | None, project: int | None) -> None:
        """Which mission (or project, for a new one) is open in the window: where the next spoken order goes."""
        self._voice_where = (mission, project)

    def voice_state(self) -> dict:
        voice = self.voice
        if voice is None:
            return {"enabled": False}
        return {"enabled": True, "state": voice.state, "session": bool(voice.session), "heard": self._heard,
                "line": self._voice_line, "mission": self._voice_where[0], "key": "Ctrl+M"}

    def spoken(self, text: str) -> str:
        """A spoken order, from the voice's own thread: into the open mission, run here and now, and its answer back."""
        text = " ".join(str(text or "").split())
        mission, project = self._voice_where
        if mission is not None:
            try:
                self.store.mission(mission)
            except NotFound:
                mission = None
        try:
            mission = self._begin(mission, text, project)
        except Busy as busy:
            return str(busy)
        except BadName as problem:
            return str(problem)
        self._voice_where = (mission, project)
        return self._work(mission, text)

    def _watch_windows(self) -> None:
        while not self._voice_closed.wait(1.0):
            voice = self.voice
            if voice is not None and voice.state != "off" and time.monotonic() - self._seen > WINDOW_GONE_SECONDS:
                voice.mic_off("Mic off: no workspace window is open.")

    def close_voice(self) -> None:
        """The mic off, the voice's threads ended and the voice link let go (when the workspace ends)."""
        self._voice_closed.set()
        if self._watch is not None:
            self._watch.close()
        if self.voice is not None:
            self.voice.close()

    # --- the card: only your own typing fills it ----------------------------------------------------

    def _ask(self, heading: str, lines: list[str], with_pin: bool) -> dict | None:
        """From the worker: open the card and wait for you. What you typed, or None if the time ran out."""
        card = {"id": secrets.token_hex(8), "heading": heading, "lines": lines, "with_pin": with_pin,
                "done": threading.Event(), "yes": "", "pin": "", "opened": time.time()}
        with self._lock:
            self._card = card
        try:
            return card if card["done"].wait(CARD_SECONDS) else None
        finally:
            with self._lock:
                if self._card is card:
                    self._card = None

    def answer(self, card_id: str, go_on: bool, yes: str = "", pin: str = "") -> bool:
        """Your answer to the card, from the window. False if that card is no longer open."""
        with self._lock:
            card = self._card
            if card is None or not hmac.compare_digest(str(card_id), card["id"]):
                return False
            card["yes"], card["pin"] = (str(yes), str(pin)) if go_on else ("", "")
            self._card = None
        card["done"].set()
        return True

    def ask_plan_approval(self, decision, plan: str):
        """The core's plan approver: the whole plan on the card, with the one High step's "yes" and PIN."""
        return self.ask_approval(decision, plan)

    def ask_approval(self, decision, plan: str = ""):
        """The core's approver: a High action's card, then GuardianClient.approve. An Approval, or None."""
        lines = [plan, "This step needs your PIN:"] if plan else []
        lines += [f"{decision.action.name}: {decision.description}"]
        lines += [f"{key}: {value}" for key, value in decision.action.details.items() if key not in HIDDEN_FROM_THE_CARD]
        lines.append(f"Tier: {decision.tier}. This approves it once." + (" Yes runs the whole plan." if plan else ""))
        answer = self._ask("Guardian asks for your approval of this plan" if plan else "Guardian asks for your approval", lines, True)
        typed, pin = (answer["yes"], answer["pin"]) if answer else ("", "")
        try:
            return self.client.approve(decision.request_id, typed, pin)  # Guardian records your answer, also a refusal
        except Refused:
            if typed.strip().lower() == "yes":  # you said yes, and something else stood in the way: a wrong PIN
                raise
            return None
        finally:
            if answer:
                answer["yes"], answer["pin"] = "", ""

    def ask_confirmation(self, text: str) -> bool:
        """The core's confirmer: something you should know before a Medium step goes on. "yes" and no PIN."""
        answer = self._ask("Before I do that", [text], False)
        try:
            return bool(answer) and answer["yes"].strip().lower() == "yes"
        finally:
            if answer:
                answer["yes"], answer["pin"] = "", ""

    # --- threads -----------------------------------------------------------------------------------

    def _start(self, target, *args) -> threading.Thread:
        thread = threading.Thread(target=target, args=args, daemon=True)
        self._threads = [alive for alive in self._threads if alive.is_alive()] + [thread]
        thread.start()
        return thread

    def wait(self, seconds: float = 5.0) -> None:
        """For tests and for quitting: let the order that runs finish."""
        deadline = time.monotonic() + seconds
        for thread in list(self._threads):
            thread.join(max(0.0, deadline - time.monotonic()))


class _SpokenOrders:
    """The task core as the voice sees it (kairu/bar/voice.py): its skills, and handle(), which runs a spoken order in the
    mission open in the window, through Workspace._begin and _work like a typed one."""

    def __init__(self, workspace: "Workspace"):
        self.workspace = workspace

    @property
    def skills(self):
        return getattr(self.workspace.core, "skills", ())

    def handle(self, text: str) -> str:
        return self.workspace.spoken(text)

    def last_answer(self):
        """The brain's answer to the last order, if it was a question: for Kairu Live (kairu/live/relay.py)."""
        return getattr(self.workspace.core, "last_answer", None)


class _VoiceScreen:
    """What the voice may show in the window: a line, the words it hears. It can't open, fill or answer the card."""

    def __init__(self, workspace: "Workspace"):
        self.workspace = workspace

    def say(self, text: str) -> None:
        text = str(text or "").replace(f"Ctrl+Alt+{self.workspace.cfg.voice_key}", "Ctrl+M")  # the window's own key
        self.workspace._voice_line = text[:400]

    def heard(self, text: str) -> None:
        self.workspace._heard = str(text or "")[:400]

    def show(self) -> None:
        pass

    def mic_shown(self, on: bool) -> None:
        if not on:
            self.workspace._heard = ""

    def card_open(self) -> bool:
        return self.workspace._card is not None

    def busy(self) -> bool:
        return self.workspace._run is not None


def _copy(run: dict | None) -> dict | None:
    if run is None:
        return None
    return {**{key: value for key, value in run.items() if key != "files"}, "steps": [dict(step) for step in run["steps"]]}


def _public_card(card: dict | None) -> dict | None:
    """What the window may know of the card: never what was typed."""
    if card is None:
        return None
    return {"id": card["id"], "heading": card["heading"], "lines": list(card["lines"]), "with_pin": card["with_pin"],
            "seconds_left": max(0, int(CARD_SECONDS - (time.time() - card["opened"])))}


# --- HTTP ------------------------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "Kairu"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args) -> None:  # no request lines, bodies or addresses in any log
        pass

    # --- checks ------------------------------------------------------------------------------------

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in {f"{host}:{port}" for host in HOSTS}

    def _key_ok(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-Kairu-Key", ""), self.server.key)

    def _send(self, status: int, body: bytes, kind: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, text: str) -> None:
        self._json(status, {"error": text})

    def _take_body(self) -> bytes | None:
        """The request's body, read first of all: a reply sent before the body is read can reach the caller as a broken
        connection on Windows (WinError 10053, the owner's check run, 11 Nov 2026). A body over LONGEST_BODY (up to DRAIN_MOST)
        is read and dropped, never looked at; one longer than that, or with no sensible length, ends the connection."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if 0 <= length <= LONGEST_BODY:
            return self.rfile.read(length) if length else b""
        self.close_connection = True
        if 0 < length <= DRAIN_MOST:
            while length > 0:
                chunk = self.rfile.read(min(length, 64 * 1024))
                if not chunk:
                    break
                length -= len(chunk)
        return None

    def _body(self, raw: bytes | None) -> dict | None:
        if raw is None or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return None
        try:
            data = json.loads(raw or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # --- requests ----------------------------------------------------------------------------------

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "not this server's address")
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            nonce = secrets.token_urlsafe(16)
            page = PAGE.read_text(encoding="utf-8").replace("{{NONCE}}", nonce).encode("utf-8")
            policy = (f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; "
                      "img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            return self._send(HTTPStatus.OK, page, "text/html; charset=utf-8", {"Content-Security-Policy": policy})
        if not path.startswith("/api/"):
            return self._error(HTTPStatus.NOT_FOUND, "not here")
        if not self._key_ok():
            return self._error(HTTPStatus.UNAUTHORIZED, "this window's key is missing or old: open it again with `kairu workspace`")
        query = dict(part.split("=", 1) for part in self.path.split("?", 1)[1].split("&") if "=" in part) if "?" in self.path else {}
        workspace = self.server.workspace
        try:
            if path == "/api/ping":
                return self._json(HTTPStatus.OK, {"ok": True})
            if path == "/api/state":
                return self._json(HTTPStatus.OK, workspace.overview())
            if path == "/api/protection":
                return self._json(HTTPStatus.OK, workspace.protection())
            if path == "/api/devices":
                return self._json(HTTPStatus.OK, workspace.devices())
            if path == "/api/team":
                number = query.get("project", "")
                return self._json(HTTPStatus.OK, workspace.team(int(number) if number.isdigit() else None))
            if path == "/api/meetings":
                number = query.get("meeting", "")
                return self._json(HTTPStatus.OK, workspace.meetings(int(number) if number.isdigit() else None))
            if path == "/api/search":
                from urllib.parse import unquote_plus
                return self._json(HTTPStatus.OK, {"missions": workspace.store.search(unquote_plus(query.get("q", "")))})
            found = re.fullmatch(r"/api/projects/(\d+)", path)
            if found:
                number = int(found.group(1))
                return self._json(HTTPStatus.OK, {"project": workspace.store.project(number),
                                                  "missions": workspace.store.missions(project=number)})
            found = re.fullmatch(r"/api/missions/(\d+)", path)
            if found:
                return self._json(HTTPStatus.OK, workspace.mission(int(found.group(1)), int(query.get("after", "0") or 0)))
        except NotFound as error:
            return self._error(HTTPStatus.NOT_FOUND, str(error))
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "that isn't a number")
        return self._error(HTTPStatus.NOT_FOUND, "not here")

    def do_POST(self) -> None:
        raw = self._take_body()  # before any answer, even a refusal
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "not this server's address")
        if not self._key_ok():
            return self._error(HTTPStatus.UNAUTHORIZED, "this window's key is missing or old: open it again with `kairu workspace`")
        body = self._body(raw)
        if body is None:
            return self._error(HTTPStatus.BAD_REQUEST, "send JSON")
        path, workspace = self.path.split("?")[0], self.server.workspace
        try:
            if path == "/api/stop":
                return self._json(HTTPStatus.OK, {"text": workspace.stop()})
            if path == "/api/answer":
                done = workspace.answer(body.get("card", ""), bool(body.get("go_on")), body.get("yes", ""), body.get("pin", ""))
                body.clear()  # what you typed is not kept here
                return self._json(HTTPStatus.OK if done else HTTPStatus.CONFLICT, {"ok": done})
            if path == "/api/mic":
                workspace.mic_pressed("key" if body.get("how") == "key" else "button")
                return self._json(HTTPStatus.OK, {"voice": workspace.voice_state()})
            if path == "/api/voice-where":
                mission, project = body.get("mission"), body.get("project")
                workspace.voice_where(int(mission) if mission is not None else None, int(project) if project is not None else None)
                return self._json(HTTPStatus.OK, {"ok": True})
            if path == "/api/open":
                if workspace.open_window:
                    workspace.open_window()
                return self._json(HTTPStatus.OK, {"ok": True})
            if path == "/api/order":
                mission = body.get("mission")
                project = body.get("project")
                return self._json(HTTPStatus.OK, workspace.order(int(mission) if mission is not None else None, body.get("text", ""),
                                                                 int(project) if project is not None else None))
            if path == "/api/projects":
                return self._json(HTTPStatus.OK, {"project": workspace.store.add_project(body.get("name", ""), body.get("notes", ""))})
            found = re.fullmatch(r"/api/projects/(\d+)", path)
            if found:
                number = int(found.group(1))
                if body.get("delete"):
                    workspace.store.delete_project(number)
                    return self._json(HTTPStatus.OK, {"ok": True})
                archived = body.get("archived")
                return self._json(HTTPStatus.OK, {"project": workspace.store.change_project(
                    number, body.get("name"), body.get("notes"), None if archived is None else bool(archived))})
            found = re.fullmatch(r"/api/missions/(\d+)", path)
            if found:
                number = int(found.group(1))
                if body.get("delete"):
                    with workspace._lock:
                        running = workspace._run is not None and workspace._run["mission"] == number
                    if running:
                        raise Busy("This mission's order is still running.")
                    workspace.store.delete_mission(number)
                    return self._json(HTTPStatus.OK, {"ok": True})
                project = body.get("project")
                return self._json(HTTPStatus.OK, {"mission": workspace.store.change_mission(
                    number, body.get("title"), int(project) if project not in (None, "") else None, project == "")})
        except NotFound as error:
            return self._error(HTTPStatus.NOT_FOUND, str(error))
        except (BadName, Busy) as error:
            return self._error(HTTPStatus.CONFLICT if isinstance(error, Busy) else HTTPStatus.BAD_REQUEST, str(error))
        except (TypeError, ValueError):
            return self._error(HTTPStatus.BAD_REQUEST, "that request can't be read")
        return self._error(HTTPStatus.NOT_FOUND, "not here")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, workspace: Workspace, port: int = 0, key: str | None = None):
        self.workspace, self.key = workspace, key or secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#key={self.key}"
