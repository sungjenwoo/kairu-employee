"""live.talk, the Guardian action that runs Kairu Live for the bar (VOICE.md "Kairu Live", ADR-052 proposed, the owner's
GO of 18 Nov 2026).

Guardian starts it (kairu/executors.py) when you switch the mic on in the Kairu bar with voice.live: true in config.yaml,
and an emergency stop ends it with everything it started (its Job Object on Windows, its process group on Linux), the
talking program too. It first says hello to the bar with the session token the bar gave for it, and starts Kairu Live
only once the bar accepts that token: started any other way, nothing hears and it ends.

Then it starts kairu/live/talk.py with the Python in your Kairu Live folder (voice.live_folder: its .venv, where LiveKit is
installed), with only the keys and settings it needs from that folder's .env, and relays between it and the bar:
what you said and what Kairu said, to be shown; each order Kairu Live wants done, for the bar to hand to the task core and
Guardian; and back, what relay.py lets Kairu Live hear of each answer. While the bar's approval card is open, Kairu Live's
mic sends silence. It never runs anything itself. The one thing it does itself is "Kairu, stop": the same emergency stop
as Ctrl+Alt+K, written straight to Guardian's database.

What you say goes to Deepgram (the words), Groq (the thinking; Google Gemini if Groq can't) and ElevenLabs (Kairu's
voice): that is what
voice.live means, and it is off unless you switch it on. Nothing here writes sound or words anywhere: Kairu Live's own
warnings stay in memory, and only its last error line (cut short) is told to the bar and to guardian.log.
"""

import collections
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from kairu.voice import link
from kairu.voice.words import KAIRU_LIKE, is_stop
from kairu.worker import FAILED, REFUSED

TALK = Path(__file__).with_name("talk.py")
TICK = 0.1  # the bar hears from this listener this often (the link's limit is 5 s)
READY_SECONDS = 55  # LiveKit, the hearing model and the mic must be ready within this (the bar waits 60 s)
IDLE_SECONDS = 600  # no talk for 10 minutes: the mic goes off (Deepgram, Groq and Gemini's free allowances)
SESSION_TAIL = 4.0  # the pill stays blue this long after the last word
END_SECONDS = 1.5
MOST = 600
KEYS = ("DEEPGRAM_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY", "ELEVEN_API_KEY", "GROQ_MODEL", "GROQ_FALLBACK_MODEL",
        "GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "ELEVEN_VOICE_ID", "ELEVEN_FALLBACK_VOICE_ID", "ELEVEN_MODEL",
        "DEEPGRAM_VOICE", "MASTER_NAME")
SAME_AS = {"GEMINI_API_KEY": "GOOGLE_API_KEY", "ELEVENLABS_API_KEY": "ELEVEN_API_KEY"}
NEEDED = ("DEEPGRAM_API_KEY",)
BRAINS = ("GROQ_API_KEY", "GOOGLE_API_KEY")  # one of them: Groq thinks first, Gemini if Groq can't (the owner, 19 Nov 2026)
STATES = {"user": ("speaking", "listening", "away"), "agent": ("initializing", "idle", "listening", "thinking", "speaking")}
ENV_LINE = re.compile(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*")
LEADING = frozenset({"hey", "hi", "ok", "okay", "kairu", "kyru", "kiru", *KAIRU_LIKE})
NO_FOLDER = ("Kairu Live needs voice.live_folder in config.yaml: the folder with its .venv and .env, such as "
             r"C:\Users\you\kairu-live\kairu-live. The mic stays off.")
NOT_WITH_CHECKS = ("Kairu Live can't check your voice print or your lips, so it doesn't start while voice.only_my_voice or "
                   "voice.camera is on in config.yaml. The mic stays off.")
IDLE = "Mic off: no talk with Kairu Live for 10 minutes."


def main(session: str, data_dir: str, voice_live: bool = False, voice_live_folder: str = "", voice_only_mine: bool = False,
         voice_camera: bool = False):
    if not voice_live:
        print("live.talk: voice.live is off in Guardian's config.yaml; nothing hears", file=sys.stderr, flush=True)
        return REFUSED
    try:
        line = link.connect(data_dir)
    except link.LinkError as error:
        print(f"live.talk: {error}; the mic stays off", file=sys.stderr, flush=True)
        return REFUSED
    try:
        try:
            line.send({"hello": session, "pid": os.getpid()})
            accepted = line.receive().get("ok") is True
        except link.LinkError:
            accepted = False
        if not accepted:
            print("live.talk: the Kairu bar did not switch this mic on; it stays off", file=sys.stderr, flush=True)
            return REFUSED
        if voice_only_mine or voice_camera:
            _tell(line, [{"problem": NOT_WITH_CHECKS}])
            return FAILED
        place = folder_problem(voice_live_folder)
        if isinstance(place, str):
            _tell(line, [{"problem": place}])
            return FAILED
        python, folder, keys = place
        return Relay(line, data_dir, python, folder, keys).run()
    except link.LinkError as error:
        print(f"live.talk: {error}; the mic is off", file=sys.stderr, flush=True)
        return None
    finally:
        line.close()


def _tell(line, events: list[dict], **state) -> dict:
    line.send({"events": events, **state})
    return line.receive()


# --- the Kairu Live folder ------------------------------------------------------------------------------------------------

def python_in(folder: Path) -> Path:
    return folder / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def read_keys(env_file: Path) -> dict:
    """Only the keys and settings Kairu Live uses, from its .env; nothing else in it is read."""
    found = {}
    for raw in env_file.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        matched = ENV_LINE.fullmatch(raw)
        if not matched or raw.lstrip().startswith("#"):
            continue
        name, value = SAME_AS.get(matched[1], matched[1]), matched[2]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if name in KEYS and value and (name not in found or matched[1] == name):
            found[name] = value
    return found


def folder_problem(setting: str):
    """(python, folder, keys) for voice.live_folder, or what is wrong with it, said simply."""
    if not setting:
        return NO_FOLDER
    folder = Path(setting).expanduser()
    python, env_file = python_in(folder), folder / ".env"
    if not python.is_file():
        return f"Kairu Live's Python isn't at {python}: set voice.live_folder to the folder with its .venv. The mic stays off."
    if not env_file.is_file():
        return f"Kairu Live's keys aren't at {env_file}. The mic stays off."
    try:
        keys = read_keys(env_file)
    except OSError as error:
        return f"Kairu Live's .env can't be read ({type(error).__name__}). The mic stays off."
    missing = [name for name in NEEDED if name not in keys]
    if not any(name in keys for name in BRAINS):
        missing.append("GROQ_API_KEY (or GOOGLE_API_KEY)")
    if missing:
        return f"Kairu Live needs {' and '.join(missing)} in {env_file}. The mic stays off."
    return python, folder, keys


# --- the relay -----------------------------------------------------------------------------------------------------------

def plain(text: str) -> str:
    """Your sentence as words only, without "hey Kairu" in front: for "Kairu, stop"."""
    spoken = re.sub(r"[^a-z' ]+", " ", text.lower()).split()
    while spoken and spoken[0] in LEADING:
        spoken.pop(0)
    return " ".join(spoken)


def from_talk(raw: str) -> dict | None:
    """One line from the talking program, read strictly: anything else is dropped."""
    try:
        message = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(message, dict) or len(message) not in (1, 2):
        return None
    if message == {"ready": True}:
        return message
    if len(message) == 1:
        (kind, value), = message.items()
        if kind in ("hearing", "heard", "said") and isinstance(value, str) and value.strip():
            return {kind: " ".join(value.split())[:MOST]}
        if kind in STATES and value in STATES[kind]:
            return message
        if kind == "problem" and isinstance(value, str):
            return {"problem": " ".join(value.split())[:200]}
        return None
    if set(message) == {"order", "id"} and isinstance(message["order"], str) and type(message["id"]) is int \
            and 0 < message["id"] < 10 ** 9 and message["order"].strip():
        return {"order": " ".join(message["order"].split())[:400], "id": message["id"]}
    if set(message) == {"problem", "soft"} and isinstance(message["problem"], str) and isinstance(message["soft"], bool):
        return {"problem": " ".join(message["problem"].split())[:200]}
    return None


EARLIER_TURNS, EARLIER_LONGEST = 30, 400  # today's talk (kairu/bar/voice.py TodayTalk)


def earlier_turns(earlier) -> list[dict]:
    """Today's talk from the bar, read strictly: at most 30 turns of role user or assistant and plain words."""
    if not isinstance(earlier, list):
        return []
    turns = []
    for turn in earlier[-EARLIER_TURNS:]:
        if isinstance(turn, dict) and set(turn) == {"role", "text"} and turn["role"] in ("user", "assistant") \
                and isinstance(turn["text"], str) and turn["text"].strip():
            turns.append({"role": turn["role"], "text": " ".join(turn["text"].split())[:EARLIER_LONGEST]})
    return turns


class Relay:
    def __init__(self, line, data_dir: str, python: Path, folder: Path, keys: dict, clock=time.monotonic):
        self.line, self.data_dir, self.python, self.folder, self.keys, self.clock = line, data_dir, python, folder, keys, clock
        self.inbox: queue.SimpleQueue = queue.SimpleQueue()
        self.errors: collections.deque = collections.deque(maxlen=20)
        self.ready, self.paused = False, False
        self.user, self.agent = "listening", "initializing"
        self.orders: set[int] = set()
        self.told_earlier = False  # today's talk goes to the talking program once
        self.started = self.last_word = self.last_activity = clock()
        self.child = None

    def run(self):
        try:
            self.child = self._start()
        except OSError as error:
            _tell(self.line, [{"problem": f"Kairu Live couldn't start ({type(error).__name__}). The mic stays off."}])
            return FAILED
        try:
            return self._relay()
        finally:
            self._end()

    def _start(self):
        env = {name: value for name, value in os.environ.items() if not name.startswith("KAIRU_")}
        env.update(self.keys)
        env["PYTHONIOENCODING"] = "utf-8"
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: no console window pops up
        child = subprocess.Popen([str(self.python), "-I", str(TALK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, cwd=str(self.folder), env=env, creationflags=flags,
                                 encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._read, args=(child.stdout,), name="kairu-live-out", daemon=True).start()
        threading.Thread(target=self._warnings, args=(child.stderr,), name="kairu-live-err", daemon=True).start()
        return child

    def _read(self, stream) -> None:
        for raw in stream:
            message = from_talk(raw)
            if message is not None:
                self.inbox.put(message)

    def _warnings(self, stream) -> None:
        for raw in stream:  # kept in memory only: the last error line is told if Kairu Live ends
            if raw.startswith("ERROR"):
                self.errors.append(" ".join(raw.split())[:160])

    def _write(self, message: dict) -> None:
        try:
            self.child.stdin.write(json.dumps(message) + "\n")
            self.child.stdin.flush()
        except (OSError, ValueError):
            pass  # it has ended; the next look notices

    def _relay(self):
        while True:
            events, stopped = self._events()
            now = self.clock()
            if stopped:
                _emergency_stop(self.data_dir)
                self.line.send({"events": events + [{"stop": True}], "talking": False, "session": False})
                return None
            ended = self.child.poll()
            if ended is not None:
                while not self.inbox.empty():  # its last words first
                    more, _ = self._events()
                    events += more
                why = self.errors[-1] if self.errors else f"it ended ({ended})"
                print(f"live.talk: Kairu Live ended: {why}", file=sys.stderr, flush=True)
                _tell(self.line, events + [{"problem": f"Mic off: Kairu Live stopped ({why})."}])
                return FAILED
            if not self.ready and now - self.started > READY_SECONDS:
                _tell(self.line, events + [{"problem": "Mic off: Kairu Live didn't start in time; check the Wi-Fi and its keys."}])
                return FAILED
            if self.ready and now - self.last_word > IDLE_SECONDS and not self.orders:
                _tell(self.line, events + [{"problem": IDLE}])
                return None
            talking = self.user == "speaking"
            session = talking or self.agent in ("thinking", "speaking") or bool(self.orders) \
                or now - self.last_activity < SESSION_TAIL
            reply = _tell(self.line, events, talking=talking, session=session)
            if reply.get("end"):
                return None
            self._answer(reply)
            time.sleep(TICK)

    def _events(self) -> tuple[list[dict], bool]:
        """What the talking program said since the last look, as the bar's events; and whether you said "Kairu, stop"."""
        events, now = [], self.clock()
        while True:
            try:
                message = self.inbox.get_nowait()
            except queue.Empty:
                return events, False
            if "ready" in message:
                self.ready = True
                self.last_word = now
                events.append({"ready": True})
            elif "user" in message:
                self.user = message["user"]
                if self.user == "speaking":
                    self.last_word = self.last_activity = now
            elif "agent" in message:
                self.agent = message["agent"]
                self.last_activity = now
            elif "heard" in message:
                self.last_word = self.last_activity = now
                if is_stop(plain(message["heard"])):
                    return events + [{"heard": message["heard"]}], True
                events.append({"heard": message["heard"]})
            elif "hearing" in message:
                self.last_activity = now
                events.append({"hearing": message["hearing"]})
            elif "said" in message:
                self.last_activity = now
                events.append({"said": message["said"]})
            elif "order" in message:
                self.orders.add(message["id"])
                events.append({"order": message["order"], "live": message["id"]})
            elif "problem" in message:
                events.append({"problem": message["problem"], "soft": True})

    def _answer(self, reply: dict) -> None:
        """The bar's answer: the card (paused), and what Kairu Live is told about its orders."""
        paused = reply.get("paused") is True
        if paused != self.paused:
            self.paused = paused
            self._write({"paused": paused})
        earlier = reply.get("earlier")
        if earlier is not None and not self.told_earlier:
            self.told_earlier = True
            turns = earlier_turns(earlier)
            if turns:
                self._write({"earlier": turns})
        for result in reply.get("results") or []:
            if not (isinstance(result, dict) and type(result.get("id")) is int and result["id"] in self.orders
                    and isinstance(result.get("text"), str) and isinstance(result.get("quiet"), bool)):
                continue
            self.orders.discard(result["id"])
            self.last_activity = self.clock()
            self._write({"result": result["text"][:4000], "id": result["id"], "quiet": result["quiet"]})

    def _end(self) -> None:
        child = self.child
        if child is None or child.poll() is not None:
            return
        self._write({"end": True})
        try:
            child.stdin.close()
        except OSError:
            pass
        try:
            child.wait(END_SECONDS)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(END_SECONDS)


def _emergency_stop(data_dir: str) -> None:
    """The same stop as Ctrl+Alt+K and the bar's Stop: every action halts, Safe Mode until `kairu resume`."""
    from kairu import safemode
    from kairu.store import Store
    safemode.emergency_stop(Store(data_dir), "Kairu, stop (Kairu Live)")
