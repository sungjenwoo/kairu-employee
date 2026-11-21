"""The bar's side of the light voice (Sprint Day 2, VOICE.md): the mic switch, the voice link, orders, and answers aloud.

The mic is off when the bar starts, and so after every restart and sign-in. Only your own click on the mic button, or your
own Ctrl+Alt+V, switches it on: mic_button() and listen_key() are called by the window's button and the hotkey, and nothing
else in Kairu calls them (a test reads the code to check). The one exception is your own setting voice.listen_at_start in
config.yaml (your GO of 15 Nov 2026): then the bar itself calls listen_at_start() when it starts and when you unlock the PC,
and the mic listens for "Kairu" only (no session opens by itself). Nothing else can call it, and it reads only config.yaml.

voice.barge_in (your GO of 15 Nov 2026): while Kairu speaks, the bar tells the listener what it is saying, and the listener
keeps hearing (Whisper only). What it hears of Kairu's own words is left out; when you talk over Kairu, the listener says
"barge" and the bar ends voice.speak at once. Without it, the listener hears silence while Kairu speaks, as before. No spoken order, Kairu action, phone message, web page or test
switch can turn it on: the listener (voice.listen) hears nothing unless this bar accepts its session token, and the bar
makes a token only when you switch the mic on. The mic goes off on an emergency stop, when the PC locks or sleeps, when
Guardian ends the listener, and when you click the button again.

Each order you say goes to the same task core as a typed one (kairu/tasks/core.py), one at a time and in order, while you
keep talking; Guardian decides each step. A High step still opens the bar's card, and only your typed "yes" and PIN can
answer it: orders said while a card is open are dropped, and a spoken "yes" or PIN is never an order. Kairu speaks Tenmin's
way (kairu/brain/tenmin.py): only to answer a question or to ask one, the answer first and short, then exactly one short
follow-up question; a finished task stays quiet, a line in the bar. It speaks with voice.speak, only when you are not
speaking; the mic is paused meanwhile, so Kairu never hears itself.

With voice.live (VOICE.md "Kairu Live", ADR-052 proposed, the owner's GO of 18 Nov 2026), the same mic button and Ctrl+Alt+V
start Kairu Live instead (the Guardian action live.talk, kairu/live/listener.py): LiveKit hears, Gemini thinks and
ElevenLabs speaks, with no "Kairu" needed while the mic is on. Each order Kairu Live wants done comes here and goes to the
same task core as a typed one, one at a time; Guardian decides each step, and High still waits for "yes" and the PIN typed
in the bar's card (while the card is open, Kairu Live's mic sends silence). What Kairu Live hears back about each order is
only what kairu/live/relay.py lets through. Ctrl+Alt+V switches Kairu Live off again. voice.listen_at_start never starts
Kairu Live: it starts only by your own click or Ctrl+Alt+V.

Today's talk (the owner's choice, 19 Nov 2026: "it should remember"): what you said to Kairu Live and what it said back,
today only, at most TODAY_TURNS turns, is kept in this bar's memory (never on disk, never in the audit log) and handed to
the next Kairu Live session, so it remembers what you talked about earlier today. These words went to Kairu Live's own
services when they were said; nothing else is ever added (no memory line, talk history, window title or page). A line with
a secret is never kept; brain.talk_history: false keeps none; "forget our talks", a new day or the bar closing ends it.

Nothing here decides or approves anything, and nothing here writes words or sound anywhere.
"""

import queue
import re
import secrets
import threading
import time
from pathlib import Path

from kairu import channel
from kairu.brain import privacy, router, tenmin
from kairu.guardian import Action, Refused
from kairu.tasks import core as task_core
from kairu.voice import link

GREETING = "Go ahead, I'm listening."
WELCOME = "You're welcome."
NO_VOICE_APPROVALS = "Type it in the card: I never take a yes or a PIN by voice."
START_SECONDS = 60  # the listener must reach the bar within this (Python, the model, the mic; large-v3-turbo takes 8-15 s)
SPEAK_SECONDS = 20
AT_START_TRIES = 24  # voice.listen_at_start: Guardian may start a little after the bar; it is asked every 5 s for 2 minutes
AT_START_WAIT = 5.0
QUIET_BEFORE_SPEAKING = 0.6  # you have been silent this long
ECHO_TAIL = 0.4  # the mic stays paused this long after Kairu has spoken, for the last sound in the room
NOT_CAUGHT = "Sorry, I didn't catch that. Could you say it again?"
NOT_YOU = {"not yours": "That didn't sound like your voice, so I didn't do it.",  # voice.only_my_voice
           "too short": "I couldn't tell it was you. Please say it a little longer.",
           "lips still": "Your lips weren't moving, so that was someone else. I didn't do it.",  # voice.camera
           "no face": "I couldn't see you at the camera, so I didn't do it. Face the laptop and say it again."}
REPLY_SECONDS = 8  # after Kairu asks a question aloud, with the mic on: it listens this long for your answer (VOICE.md)
SPOKEN_STEPS = ("web.ask", "web.ask_private", "web.read_page", "screen.read_text")  # their reply is an answer, so it is spoken
# only a real answer, never a refusal ("Notepad shows: ..." is screen.read_text's, PC4)
SAYS = re.compile(r"(?:Claude|ChatGPT|Gemini|Perplexity|This page) says: \S|[A-Z][\w .'-]{0,40} shows: \S")
TODAY_TURNS = 30  # today's talk: the last 30 things said, both sides
TODAY_LONGEST = 400  # characters of one turn
LIVE_ON = "Kairu Live is on: just talk. The mic button or Ctrl+Alt+{key} switches it off."
LIVE_CARD_OPEN = "Not done: the Kairu bar has an approval card open. Answer it there first."
# ADR-054 (the owner's GO of 20 Nov 2026): the one place a spoken word answers a card. Only a take-control run's own cards
# ("Is this correct?": yes / no; "Your turn": go on / stop), only a whole utterance that is nothing but that answer, and only
# within the card's own time (kairu/bar/app.py SPOKEN_SECONDS). It is handed to the card, never to the task core as an order.
# A spoken yes reaches a card only through Kairu Live's words; the light voice's listeners still drop every yes and PIN, so
# there "Kairu, go on" works and a yes is typed or clicked.
SPOKEN_YES = re.compile(r"(?:yes|yeah|yep|yup|correct|right|confirm|confirmed|go ahead|yes please|ok|okay|sure)"
                        r"(?:,? (?:it'?s|that'?s|it is|that is) (?:correct|right|fine|ok|okay))?(?:,? (?:go ahead|do it|please))?")
SPOKEN_NO = re.compile(r"(?:no|nope|not correct|that'?s (?:not right|wrong)|it'?s (?:not correct|wrong)|wrong|don'?t|do not|cancel)"
                       r"(?:,? (?:don'?t|stop|cancel))?")
SPOKEN_GO_ON = re.compile(r"(?:go on|carry on|continue|done|i'?m done|i am done|i did it|it'?s done|next|go ahead)")
SPOKEN_STOP = re.compile(r"(?:stop here|stop the run|end it|cancel|forget it)")


def spoken_answer(text: str, card: str) -> str:
    """A spoken answer to a take-control card ("yes", "no", "go on", "stop"), or "" if the words are anything else. A PIN or
    any digits are never one."""
    words = re.sub(r"[^a-z' ]+", " ", (text or "").lower()).split()
    while words and words[0] in ("hey", "ok", "okay", "kairu", "kyru", "kiru") and len(words) > 1:
        words.pop(0)
    said = " ".join(words)
    if not said or re.search(r"\d", text or ""):
        return ""
    if card == "correct":
        return "yes" if SPOKEN_YES.fullmatch(said) else "no" if SPOKEN_NO.fullmatch(said) else ""
    if card == "turn":
        return "go on" if SPOKEN_GO_ON.fullmatch(said) else "stop" if SPOKEN_STOP.fullmatch(said) else ""
    return ""
MIC_ELSEWHERE = "The mic is on in another Kairu window (the bar or the workspace). Switch it off there first."
QUESTION = re.compile(r"(?:what|who|whom|whose|when|where|why|how|which|is|are|was|were|am|can|could|would|will|should|shall|do|"
                      r"does|did|has|have|had|tell|search|find|look|explain|define|give|show|say|translate|calculate|check)\b")
NOT_AN_ANSWER = re.compile(r"(?:Not sent|Guardian refused|Guardian is not running|Your question|I couldn't answer|Safe Mode|"
                           r"Something went wrong)\b")  # shown in the bar, never spoken: Kairu speaks to answer or to ask


class TodayTalk:
    """Kairu Live's talk today, both sides, in memory only: never written, never in the audit log, never a secret."""

    def __init__(self, clock=None):
        self.clock = clock or (lambda: time.strftime("%Y-%m-%d"))
        self._day = self.clock()
        self._turns: list[dict] = []
        self._lock = threading.Lock()

    def add(self, role: str, text: str) -> None:
        text = " ".join(str(text or "").split())[:TODAY_LONGEST]
        if role not in ("user", "assistant") or not text or privacy.secrets_in(text):
            return
        with self._lock:
            self._new_day()
            self._turns = (self._turns + [{"role": role, "text": text}])[-TODAY_TURNS:]

    def turns(self) -> list[dict]:
        with self._lock:
            self._new_day()
            return [dict(turn) for turn in self._turns]

    def forget(self) -> None:
        with self._lock:
            self._turns = []

    def _new_day(self) -> None:
        if self.clock() != self._day:
            self._day, self._turns = self.clock(), []


class VoiceControl:
    """The mic switch and everything the voice does in the bar. ui gives say, heard, show, mic_shown and card_open."""

    def __init__(self, cfg, client, core, ui):
        self.cfg, self.client, self.core, self.ui = cfg, client, core, ui
        self.state = "off"  # off, starting, on
        self.session = False
        self.paused = False
        self.talking = False
        self.working = False  # an order or an answer is in hand
        self.live = bool(getattr(cfg, "voice_live", False))  # voice.live: Kairu Live hears, thinks and speaks (kairu/live/)
        self._results: list[dict] = []  # Kairu Live: what it is told about its orders, on the next answer to its listener
        self.today = TodayTalk()  # Kairu Live's talk today: memory only
        self._earlier_sent = False  # once per session, after "ready"
        self._token: str | None = None
        self._run: int | None = None
        self._want_session = False
        self._want_reply = 0
        self._end = False
        self._last_talk = 0.0
        self._lock = threading.Lock()
        self._orders: queue.SimpleQueue = queue.SimpleQueue()
        self._closed = threading.Event()
        self._speaking = ""  # voice.barge_in: what Kairu is saying now, for the listener to leave out
        self._barge = threading.Event()  # you talked over Kairu: voice.speak ends
        self.server: link.Server | None = None  # the voice link: claimed when the mic switches on, let go when it is off
        self._threads = [threading.Thread(target=self._serve, name="kairu-voice-link", daemon=True),
                         threading.Thread(target=self._work, name="kairu-voice-orders", daemon=True)]
        for thread in self._threads:
            thread.start()

    # --- your own click and keystroke -----------------------------------------------------------------

    def mic_button(self) -> None:
        """The mic button: on (and listening at once), or off."""
        if self.state == "off":
            self._switch_on()
        else:
            self.mic_off("Mic off.")

    def listen_key(self) -> None:
        """Ctrl+Alt+V: start listening now, without "Kairu", switching the mic on if it is off. Kairu Live: on or off."""
        if self.state == "off":
            self._switch_on()
        elif self.live:
            self.mic_off("Mic off.")
        else:
            self._want_session = True
            self.ui.show()

    def listen_at_start(self, why: str = "") -> None:
        """voice.listen_at_start (your setting in config.yaml): the bar calls this when it starts and when you unlock the
        PC. The mic listens for "Kairu"; no session opens by itself. Guardian may not be up yet: asked again for 2 minutes."""
        if not getattr(self.cfg, "voice_listen_at_start", False) or self._closed.is_set():
            return
        if self.live:  # Kairu Live sends what it hears to the cloud: it starts only by your own click or Ctrl+Alt+V
            return
        trying = threading.Thread(target=self._at_start, name="kairu-voice-at-start", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [trying]
        trying.start()

    def _at_start(self) -> None:
        for _ in range(AT_START_TRIES):
            if self._closed.is_set() or self.state != "off":
                return
            try:
                state = self.client.status()
            except channel.ChannelError:
                self._closed.wait(AT_START_WAIT)
                continue
            if state.get("mode") == "safe":
                return  # after a stop the mic stays off until you resume and switch it on yourself
            self._switch_on(session=False, show=False)
            return

    def _switch_on(self, session: bool = True, show: bool = True) -> None:
        with self._lock:
            if self.state != "off" or self._closed.is_set():
                return
            if self.server is None:
                problem = ""
                try:
                    Path(self.cfg.data_dir).mkdir(parents=True, exist_ok=True)
                    self.server = link.Server(self.cfg.data_dir)
                except link.LinkTaken:  # W2 (ADR-036): one mic for the bar and the workspace; the other one has it
                    problem = MIC_ELSEWHERE
                except (link.LinkError, OSError) as error:
                    problem = f"The mic can't be used: {error}."
                if problem:
                    self.ui.say(problem)
                    return
            self.state, self._token, self._want_session, self._end = "starting", secrets.token_hex(16), session, False
            self._earlier_sent = False  # a new Kairu Live session is told today's talk once
        self.ui.mic_shown(True)
        if show:
            self.ui.show()
            self.ui.say("Starting the mic…")
        starter = threading.Thread(target=self._start_listener, args=(self._token,), name="kairu-voice-start", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()] + [starter]  # close() waits for it too
        starter.start()

    def _start_listener(self, token: str) -> None:
        try:
            state = self.client.status()
        except channel.ChannelError:
            self._failed(task_core.NOT_RUNNING)
            return
        if state.get("mode") == "safe":
            self._failed("Safe Mode: the mic stays off until you resume with `kairu resume`.")
            return
        try:
            run = self.client.run(Action("live.talk" if self.live else "voice.listen", {"session": token}))
        except Refused as refusal:
            self._failed(f"Mic off: Guardian refused {'live.talk' if self.live else 'voice.listen'} ({str(refusal).rstrip('.')}).")
            return
        self._run = run["run"]
        deadline = time.monotonic() + START_SECONDS
        while self.state == "starting" and self._token == token:
            try:
                ended = self.client.run_status(self._run)["outcome"]
            except Refused:
                ended = "failed"
            if ended is not None and self.state == "starting":
                self._failed("Mic off: the listener ended before it started; guardian.log says why.")
                return
            if time.monotonic() > deadline:
                self.mic_off("Mic off: the listener did not start in time.")
                return
            time.sleep(0.2)

    def _failed(self, why: str) -> None:
        with self._lock:
            self.state, self._token = "off", None
        self.ui.mic_shown(False)
        self.ui.say(why)

    def mic_off(self, why: str = "Mic off.") -> None:
        """Off now: the listener is ended by Guardian, with the microphone it holds. Also on lock, sleep and every stop."""
        with self._lock:
            was, run = self.state, self._run
            self.state, self._token, self._run, self.session, self._end = "off", None, None, False, True
        self.paused = False
        self.ui.mic_shown(False)
        self.ui.heard("")
        if was != "off":
            self.ui.say(why)
        if run is not None:
            try:
                self.client.end(run)
            except Refused:
                pass  # it has ended already

    # --- the voice link ---------------------------------------------------------------------------------

    def _serve(self) -> None:
        while not self._closed.is_set():
            with self._lock:
                server = self.server
                if server is not None and self.state == "off":  # the mic is off: the line is let go, for the other window
                    self.server = None
                    server.stop()
                    server.close()
                    continue
            if server is None:
                self._closed.wait(0.1)
                continue
            line = server.accept(poll=0.2)
            if line is None:
                continue
            try:
                self._converse(line)
            except link.LinkError:
                pass
            finally:
                line.close()
                if self.state == "on":
                    self._listener_gone()

    def _converse(self, line) -> None:
        hello = line.receive()
        token = self._token
        if not (token and self.state == "starting" and isinstance(hello.get("hello"), str)
                and secrets.compare_digest(hello["hello"], token)):
            line.last({"ok": False})
            return
        line.send({"ok": True})
        while True:
            message = line.receive()
            if self._token != token:
                line.last({"end": True})
                return
            for event in message.get("events") or []:
                if isinstance(event, dict):
                    self._event(event)
            self.talking = bool(message.get("talking"))
            if self.talking:
                self._last_talk = time.monotonic()
            self.session = bool(message.get("session"))
            want, self._want_session = self._want_session, False
            reply, self._want_reply = (self._want_reply, 0) if not self.paused else (0, self._want_reply)
            if self._end or self.state == "off":
                line.last({"end": True})
                return
            answer = {"paused": self.paused, "session": want, "end": False}
            if self.live:  # Kairu Live: silence while the card is open, and what it is told about its orders
                # ADR-054: a take-control card that takes a spoken answer keeps the mic live, for that answer only
                answer["paused"] = bool(self.ui.card_open()) and not self._spoken_card()
                if self.state == "on" and not self._earlier_sent:
                    self._earlier_sent = True
                    earlier = self.today.turns() if getattr(self.cfg, "brain_talk_history", True) else []
                    if earlier:
                        answer["earlier"] = earlier  # today's talk so far, so Kairu Live remembers it
                with self._lock:
                    results, self._results = self._results, []
                if results:
                    answer["results"] = results
            if reply:
                answer["reply"] = reply  # only when Kairu has just asked: listen for the answer, without "Kairu"
            speaking = getattr(self, "_speaking", "") if self.paused and getattr(self.cfg, "voice_barge_in", False) else ""
            if speaking:
                answer["speaking"] = speaking  # voice.barge_in: what Kairu is saying, for the listener to leave out
            line.send(answer)

    def _listener_gone(self) -> None:
        try:
            safe = self.client.status().get("mode") == "safe"
        except channel.ChannelError:
            safe = False
        self.mic_off("Stopped everything, and the mic is off. Safe Mode until `kairu resume`." if safe else "Mic off: the listener ended.")

    def _spoken_card(self) -> str:
        spoken_card = getattr(self.ui, "spoken_card", None)
        return spoken_card() if spoken_card else ""

    def _answered_by_voice(self, text: str) -> bool:
        """ADR-054: words that answer an open take-control card go to that card, and nowhere else."""
        card = self._spoken_card()
        word = spoken_answer(text, card) if card else ""
        if word:
            self.ui.spoken(word)
        return bool(word)

    def _event(self, event: dict) -> None:
        if getattr(self, "live", False) and ("heard" in event or "said" in event):
            self._keep_today(event)
        if self._spoken_card() and self.ui.card_open():
            if "heard" in event and self._answered_by_voice(str(event["heard"])):
                self.ui.heard(str(event["heard"]))
                return
            if "order" in event and self._answered_by_voice(str(event["order"])):
                if self.live and type(event.get("live")) is int:
                    self._told(event["live"], "", True)  # Kairu Live's order was only your answer to the card: quiet
                return

        if "ready" in event:
            with self._lock:
                if self.state == "starting":
                    self.state = "on"
            self.ui.say(LIVE_ON.format(key=self.cfg.voice_key) if self.live
                        else f"Mic on. Say \"Kairu\", or press Ctrl+Alt+{self.cfg.voice_key}.")
        elif "said" in event and self.live:  # what Kairu Live said aloud: shown in the bar's line
            self.ui.say(str(event["said"]))
        elif "order" in event and self.live and type(event.get("live")) is int:
            if self.ui.card_open():
                self._told(event["live"], LIVE_CARD_OPEN, False)
                return
            self._orders.put(("live", (event["live"], str(event["order"]))))
        elif "problem" in event:
            self.ui.show()
            if event.get("soft"):
                self.ui.say(str(event["problem"]))
            else:
                self.mic_off(str(event["problem"]))
        elif "barge" in event:
            self._barge.set()  # you talked over Kairu: speak() ends voice.speak now
        elif "heard" in event:
            self.ui.heard(str(event["heard"]))
        elif "not_you" in event:  # voice.only_my_voice: shown, never spoken, never an order
            self.ui.heard("")
            self.ui.say(NOT_YOU.get(str(event["not_you"]), NOT_YOU["not yours"]))
        elif "hearing" in event:  # voice.live_caption_every: your words so far, in grey; "heard" replaces them
            getattr(self.ui, "hearing", self.ui.heard)(str(event["hearing"]))
        elif "wake" in event:
            self.session = True
            self.ui.show()
            self.ui.say(GREETING)
            if event.get("alone"):
                self._orders.put(("greet", None))
        elif "order" in event:
            if self.ui.card_open():
                self.ui.say(NO_VOICE_APPROVALS)
                return
            self._orders.put(("order", str(event["order"])))
        elif "reply" in event:
            self.session = True  # listening for your answer to Kairu's question (the mic was already on)
        elif "unclear" in event:
            self._orders.put(("say", str(event["unclear"])))
        elif "ignored" in event:
            if self.ui.card_open():
                self.ui.say(NO_VOICE_APPROVALS)
        elif "thanks" in event:
            self.session = False
            self.ui.heard("")
            self._orders.put(("say", WELCOME))
        elif "quiet" in event:
            self.session = False
            self.ui.heard("")
            self.ui.say(f"Quiet now. Say \"Kairu\", or press Ctrl+Alt+{self.cfg.voice_key}.")
        elif "stop" in event:
            self.ui.say("Stopped everything, and the mic is off. Safe Mode until `kairu resume`.")

    # --- orders and answers, one at a time, in order ------------------------------------------------------

    def _work(self) -> None:
        while not self._closed.is_set():
            try:
                kind, text = self._orders.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.state == "off":
                continue
            while self.ui.busy() and not self._closed.is_set():  # a typed order is in hand: one at a time, one card at a time
                time.sleep(0.05)
            self.working = True
            try:
                if kind == "greet":
                    time.sleep(QUIET_BEFORE_SPEAKING)
                    if not self.talking and self._orders.empty():
                        self.speak(GREETING)
                elif kind == "say":
                    self.ui.say(text)
                    self.speak(text)
                elif kind == "live":
                    self._live_order(*text)
                else:
                    self._order(text)
            except Exception as error:  # the bar and the mic keep working; what runs belongs to Guardian
                self.ui.say(f"Something went wrong with that order ({type(error).__name__}).")
            finally:
                self.working = False

    def _order(self, text: str) -> None:
        """Tenmin (kairu/brain/tenmin.py): a finished task stays quiet, a short line in the bar (K-7); Kairu speaks only to
        answer a question, Tenmin's way, or to ask one."""
        task = task_core.understand(text, getattr(self.core, "skills", ()))
        if task.question and not task.steps and not QUESTION.match(text):
            reply = NOT_CAUGHT  # neither a skill nor a question: never guessed at, and one short question back
            self.ui.say(reply)
            self.speak(reply)
            return
        self.ui.say("…")
        reply = self.core.handle(text)
        if self.state == "off":
            return
        self.ui.say(reply)
        if task.question and not task.steps and not NOT_AN_ANSWER.match(reply):
            self.speak(tenmin.spoken(reply, text))
        elif task.summarise and reply.startswith(task_core.IN_SHORT) and not NOT_AN_ANSWER.match(reply[len(task_core.IN_SHORT):]):
            self.speak(tenmin.spoken(reply.split("\n\n")[0], text))  # "ask Claude X and summarise it": the summary is said
        elif len(task.steps) == 1 and task.steps[0].action in SPOKEN_STEPS and SAYS.match(reply):
            self.speak(tenmin.spoken(reply, text))  # what the page answered is an answer, not a finished task: said, with who says it

    def _keep_today(self, event: dict) -> None:
        if not getattr(self.cfg, "brain_talk_history", True):
            return
        text = str(event.get("heard") if "heard" in event else event.get("said"))
        if "heard" in event and router.TALKS_FORGET.fullmatch(router.plain(text)):
            self.today.forget()  # "forget our talks": today's talk too
            return
        self.today.add("user" if "heard" in event else "assistant", text)

    def _live_order(self, order_id: int, text: str) -> None:
        """Kairu Live's order: the same task core as a typed one (Guardian decides each step), the reply in the bar, and
        only what kairu/live/relay.py lets through back to Kairu Live."""
        from kairu.live import relay
        if relay.approval_like(text):  # a yes or a PIN is never an order, and never an approval
            self.ui.say(NO_VOICE_APPROVALS)
            self._told(order_id, NO_VOICE_APPROVALS, False)
            return
        self.ui.say("…")
        try:
            reply = self.core.handle(text)
        except Exception as error:  # the bar and the mic keep working; what runs belongs to Guardian
            reply = f"Something went wrong with that order ({type(error).__name__})."
        if self.state == "off":
            return
        self.ui.say(reply)
        last = getattr(self.core, "last_answer", None)  # the bar's and the workspace's give a method, the task core a value
        said, quiet = relay.told(text, reply, last() if callable(last) else last)
        self._told(order_id, said, quiet)

    def _told(self, order_id: int, text: str, quiet: bool) -> None:
        with self._lock:
            self._results.append({"id": order_id, "text": text, "quiet": quiet})

    def speak(self, line: str) -> None:
        """Say one short line with voice.speak, when you are not speaking. The mic is paused meanwhile."""
        if not line or self.state != "on":
            return
        deadline = time.monotonic() + 3
        while (self.talking or time.monotonic() - self._last_talk < QUIET_BEFORE_SPEAKING) and time.monotonic() < deadline:
            time.sleep(0.05)
        barge = self.__dict__.setdefault("_barge", threading.Event())  # also for a control made without __init__ (tests)
        barge.clear()
        self._speaking = line
        self.paused = True
        try:
            run = self.client.run(Action("voice.speak", {"text": line}))
            ends = time.monotonic() + SPEAK_SECONDS
            while self.client.run_status(run["run"])["outcome"] is None and time.monotonic() < ends:
                if barge.is_set():  # voice.barge_in: you talked over Kairu, so it stops talking
                    self.client.end(run["run"])  # the answer stays in the bar; only the speaking ends
                    break
                time.sleep(0.05)
        except Refused:
            pass  # shown already; the voice is only a second way to say it
        finally:
            time.sleep(0 if barge.is_set() else ECHO_TAIL)
            if self.state == "on" and line.rstrip().endswith("?"):
                self._want_reply = REPLY_SECONDS  # Kairu asked: your answer needs no "Kairu" for a few seconds
            self.paused = False
            self._speaking = ""

    def close(self) -> None:
        """The mic off, and every thread of the voice ended (they hold the task core, which holds the bar's card)."""
        self.mic_off("Mic off.")
        with self._lock:
            self._closed.set()
            server, self.server = self.server, None
        if server is not None:
            server.stop()
        for thread in self._threads:
            thread.join(5)
        if server is not None:
            server.close()
