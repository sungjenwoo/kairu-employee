"""The Kairu bar's window: Tkinter, borderless, always on top, bottom centre where the pill is, dark and rounded, with no
taskbar button.

    python -m kairu.bar.app --config config.yaml [--show]     (`kairu bar` starts it for you, in the background)

A text box, a one-line reply, a red Stop and a hide button. Enter sends the order to the task core (kairu/tasks/core.py),
which sends each step to Guardian. The bar is its own program: if it crashes, Guardian and every running action carry on.

Stop does what `kairu stop` does. It writes the stop to Guardian's database at once, so it works with Guardian down too.

The approval card shows a High action, its details and its tier, with a "yes" box and a PIN box. Those two are filled only
by your own keystrokes: no code in Kairu writes into them or presses their buttons, and a test reads this code to check.
What you type goes to GuardianClient.approve, then the boxes are emptied. Guardian decides; the bar only asks.

The bar's work runs on threads of its own, and only the main thread touches the window. close() waits for those threads
before it lets the window go: Tcl stops the whole program if a thread is the last to let go of one.

With voice.enabled (VOICE.md), the bar also has a mic button, off at every start, and holds Ctrl+Alt+V: only your own click
or keystroke switches the mic on (kairu/bar/voice.py). While the mic is on, a second line shows your words as you say them.
The mic goes off on Stop, on every emergency stop, and when the PC locks or sleeps (kairu/bar/session_watch.py).
A plan for a free-form order (Sprint Day 4) is shown on the same card before anything runs: "yes" runs it, and if one of
its steps is High, the card has the PIN box too, once for the whole plan. Typing "stop" (or "Kairu, stop") does what Stop
does, even while a task is running: the step that runs halts, and the rest of the plan never starts.

The Ember Glow pill (kairu/bar/pill.py, the owner's design of 15 Nov 2026) shows what Kairu is doing at the bottom centre
of the screen: blue while it listens, warm red while it works, "Done" when the order has ended. It only shows.
"""

import argparse
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

from kairu import config as kairu_config
from kairu.client import GuardianClient
from kairu.guardian import Refused
from kairu.tasks.core import NOT_RUNNING, TaskCore

WIDTH, HEIGHT = 560, 64
FROM_BOTTOM = 46  # the typing bar sits where the Ember Glow pill is: bottom centre, this far above the taskbar
INSET_X, INSET_Y = 22, 12  # the bar's contents, inside its round ends
CARD_SECONDS = 110  # a little less than Guardian's own limit on an approval
BACKGROUND, FIELD, TEXT, QUIET, RED, GREEN = "#1a1a1d", "#26262a", "#f2f3f5", "#a9adb4", "#d9363e", "#2e8b57"
RING, SEE_THROUGH = "#3a3a40", "#010203"  # the bar's hairline edge; the colour Windows leaves out, for its round ends
LISTENING, ON_LISTENING = "#4fc3ff", "#0b0b0c"  # Ember Glow (W2): the mic and the strip are blue while Kairu listens
GLOW_MS = 150
HIDDEN_FROM_THE_CARD = ("job", "ask", "source")
QUIT_FILE, LOG_FILE, ALREADY_RUNNING = "bar.quit", "bar.log", 3
QUIT_WAIT_SECONDS = 4  # `kairu bar` right after `kairu bar quit` waits this long for the old bar to end
KEY_LOOK_MS = 1500
STOP_WORDS = re.compile(r"(?:(?:hey )?kairu[,.!]? )?(?:stop|stop it|stop everything|cancel)[.!]?", re.IGNORECASE)
# ADR-054: the take-control run's own cards. "correct": "Is this correct?" (yes alone, typed, clicked or said; no PIN);
# "turn": "Your turn" (go on, typed, clicked or said). Every other card is as before: a spoken yes or PIN goes nowhere.
GO_ON_WORDS = re.compile(r"(?:(?:hey )?kairu[,.!]? )?(?:go on|carry on|continue|done|i'?m done|i did it|next)[.!]?",
                         re.IGNORECASE)
SPOKEN_CARDS = ("correct", "turn")
SPOKEN_SECONDS = 60  # a spoken answer counts only this long after the card opened
SPOKEN_AFTER = 0.3  # ... and not in the first moment (words said before the card opened)
WINDOW_TRIES = 3


class Bar:
    def __init__(self, cfg, core=None, client=None, show: bool = False, config_file=None):
        import tkinter as tk
        self.tk, self.cfg, self.config_file = tk, cfg, config_file
        self.client = client or GuardianClient(cfg)
        self.core = core or TaskCore(cfg, self.client, approver=self.ask_approval, confirmer=self.ask_confirmation,
                                     plan_approver=self.ask_plan_approval, progress=self._progress,
                                     handover=self.ask_handover)
        self.busy, self.visible = False, False
        self._in_run, self._step_labels = False, []  # a take-control run is going on (ADR-054): the bar stays out of the way
        self._card_kind, self._card_opened = "", 0.0
        self._threads: list[threading.Thread] = []
        self._ui: queue.SimpleQueue = queue.SimpleQueue()
        self.root = root = tk.Tk()
        root.title("Kairu bar")
        root.overrideredirect(True)  # no border, no title bar, no taskbar button
        root.attributes("-topmost", True)
        root.configure(bg=SEE_THROUGH)
        if sys.platform == "win32":
            root.attributes("-transparentcolor", SEE_THROUGH)  # round ends, like the Ember Glow pill
        font, small = ("Segoe UI", 10), ("Segoe UI", 9)
        # The Ember Glow look (owner's GO, 15 Nov 2026): no strip at the top of the screen any more. The bar is a dark
        # rounded bar at the bottom centre, where the pill is; replies and the card open above the line you type in.
        self.backdrop = tk.Canvas(root, bg=SEE_THROUGH, highlightthickness=0, bd=0)
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = inner = tk.Frame(root, bg=BACKGROUND)
        inner.pack(fill="both", expand=True, padx=INSET_X, pady=INSET_Y)

        top = tk.Frame(inner, bg=BACKGROUND)
        top.pack(side="bottom", fill="x")
        self.order_box = tk.Entry(top, bg=BACKGROUND, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 12),
                                  highlightthickness=0, bd=0)
        self.order_box.pack(side="left", fill="x", expand=True, ipady=6)
        self.order_box.bind("<Return>", lambda event: self.send())
        self.order_box.bind("<Escape>", lambda event: self.hide())
        self.hide_button = tk.Button(top, text="–", command=self.hide, bg=FIELD, fg=TEXT, relief="flat", width=2, font=small)
        self.hide_button.pack(side="right", padx=(4, 0))
        self.stop_button = tk.Button(top, text="Stop", command=self.stop, bg=RED, fg="white", activebackground=RED, relief="flat",
                                     width=5, font=small)
        self.stop_button.pack(side="right", padx=(4, 0))
        self.voice = self.watch = self.mic_button = self.heard_line = None
        if cfg.voice_enabled:
            self.mic_button = tk.Button(top, text="Mic", command=self._mic_clicked, bg=FIELD, fg=QUIET, relief="flat", width=6, font=small)
            self.mic_button.pack(side="right", padx=(4, 0))
            self.heard_line = tk.Label(inner, text="", bg=BACKGROUND, fg=TEXT, font=small, anchor="w", justify="left",
                                       wraplength=WIDTH - 2 * INSET_X)
        self.reply_line = tk.Label(inner, text="", bg=BACKGROUND, fg=QUIET, font=small, anchor="w", justify="left",
                                   wraplength=WIDTH - 2 * INSET_X)  # shown above the line you type in, when it has words
        from kairu.bar.pill import Pill
        self.pill = Pill(root.after, root.after_cancel)
        self._pill_raises = 0
        self.card = self._build_card(font, small)
        self._answer = None
        self._fit()
        root.withdraw()
        if cfg.voice_enabled:
            self._start_voice()
        if show:
            self.show()
        root.after(30, self._drain)
        root.after(1000, self._look_for_quit)
        root.after(GLOW_MS, self._glow)

    # --- the window --------------------------------------------------------------------------------

    def _glow(self) -> None:
        """Ember Glow: the pill at the bottom centre is blue while Kairu listens, red while it works, gone when there is no
        work. It only shows."""
        from kairu.bar.ember import mode_of
        try:
            self.pill.show(mode_of(self.busy, self.voice), bool(self.voice and self.voice.state == "on" and self.voice.session))
            if self.visible and self.pill.raises != self._pill_raises:  # the pill came over every app: the bar goes over it
                self._pill_raises = self.pill.raises
                self.root.lift()
            self.root.after(GLOW_MS, self._glow)
        except self.tk.TclError:
            pass

    @staticmethod
    def _work_area(root) -> tuple:
        """The screen without the taskbar, as the bar's window counts it: (left, top, right, bottom)."""
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            area = wintypes.RECT()
            if ctypes.WinDLL("user32").SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):  # SPI_GETWORKAREA
                return area.left, area.top, area.right, area.bottom
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()

    def _fit(self) -> None:
        """Bottom centre, where the pill is; taller upwards when a reply or the card is shown."""
        self.root.update_idletasks()
        height = max(HEIGHT, self.inner.winfo_reqheight() + 2 * INSET_Y)
        left, top, right, bottom = self._work_area(self.root)
        self.root.geometry(f"{WIDTH}x{height}+{(left + right - WIDTH) // 2}+{bottom - FROM_BOTTOM - height}")
        self._draw_backdrop(height)

    def _draw_backdrop(self, height: int) -> None:
        """The dark rounded bar behind the contents: a pill while it is one line, rounded corners when it is taller."""
        canvas, radius = self.backdrop, min(HEIGHT // 2, height // 2)
        canvas.delete("all")
        x1, y1, x2, y2, r = 0, 0, WIDTH - 1, height - 1, radius
        points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
                  x1, y1 + r, x1, y1]
        canvas.create_polygon(points, smooth=True, fill=BACKGROUND, outline=RING, width=1)

    def show(self) -> None:
        self.visible = True
        self.say("")  # a line left from before (an old "Safe Mode") is not shown again; _say_state says it if still true
        self.pill.cover(True)
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self._fit()
        self._take_focus()
        self.order_box.focus_force()
        self.start_thread(self._say_state)

    def hide(self) -> None:
        self.visible = False
        self.root.withdraw()
        self.pill.cover(False)

    def _show_quietly(self) -> None:
        """When you say "Kairu" or press the listen key: the Ember Glow pill shows the talk, so the bar stays hidden (the
        owner's GO of 15 Nov 2026: no bar popping up). A problem the voice reports reaches the pill through say()."""

    def toggle(self) -> None:
        self.hide() if self.visible else self.show()

    def toggle_from_any_thread(self) -> None:
        self._ui.put(self.toggle)

    def _take_focus(self) -> None:
        if sys.platform != "win32":
            return
        import ctypes
        user32 = ctypes.WinDLL("user32")
        user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
        user32.SetForegroundWindow(user32.GetAncestor(self.root.winfo_id(), 2))  # GA_ROOT

    def _drain(self) -> None:
        while True:
            try:
                self._ui.get_nowait()()
            except queue.Empty:
                break
        self.root.after(30, self._drain)

    def _look_for_quit(self) -> None:
        quit_file = Path(self.cfg.data_dir) / QUIT_FILE
        if quit_file.exists():
            quit_file.unlink(missing_ok=True)
            self.close()
            return
        self.root.after(1000, self._look_for_quit)

    def say(self, text: str) -> None:
        """The reply line, above the line you type in. With the bar hidden, a problem shows on the pill instead."""
        self.reply_line.configure(text=text)
        if text and not self.reply_line.winfo_manager():
            self.reply_line.pack(fill="x", pady=(0, 6))
        elif not text and self.reply_line.winfo_manager():
            self.reply_line.pack_forget()
        if text and not self.visible:
            self.pill.note(text)
        self._fit()

    def _say_from_worker(self, text: str) -> None:
        self._ui.put(lambda: self.say(text))

    def _say_state(self) -> None:
        from kairu import channel
        try:
            state = self.client.status()
        except channel.ChannelError:
            self._say_from_worker(NOT_RUNNING)
            return
        if state.get("mode") == "safe":
            self._say_from_worker("Safe Mode: nothing runs until you resume with `kairu resume`.")

    # --- an order ----------------------------------------------------------------------------------

    def send(self) -> None:
        order = self.order_box.get().strip()
        if not order:
            return
        if STOP_WORDS.fullmatch(order):  # also while a task runs: what Stop does
            self.order_box.delete(0, "end")
            self.stop()
            return
        if self._answer is not None and self._card_kind == "turn" and GO_ON_WORDS.fullmatch(order):  # ADR-054: your turn is done
            self.order_box.delete(0, "end")
            self._answered(True)
            return
        if self.busy or (self.voice and self.voice.working):
            self.say("Still on the last one.")
            return
        self.order_box.delete(0, "end")
        self.busy = True
        self.say("…")
        self._let_actions_come_to_the_front()
        self.start_thread(self._work, order)

    def handle(self, order: str) -> str:
        """An order, typed or said: "open the workspace" opens Kairu's own window (W2, ADR-036); anything else goes to the
        task core, so Guardian decides it. The pill is told that an order is in hand, and its reply: it only shows them."""
        self._ui.put(lambda: self.pill.order(order))
        reply = self._handle(order)
        self._ui.put(lambda: self.pill.done(reply))
        return reply

    def _handle(self, order: str) -> str:
        from kairu.workspace import app as workspace
        if workspace.OPEN_WORKSPACE.fullmatch(" ".join(order.split())):
            return workspace.open_or_start(self.cfg, self.config_file)[1]
        return self.core.handle(order)

    def _work(self, order: str) -> None:
        try:
            reply = self.handle(order)
        except Exception as error:  # the bar keeps working; what is running belongs to Guardian
            print(f"kairu bar: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            reply = "Something went wrong in the bar; bar.log says what."

        def finish():
            self.busy = False
            self.say(reply)
        self._ui.put(finish)

    @staticmethod
    def _let_actions_come_to_the_front() -> None:
        """The bar is in front now, and Windows lets it pass that on, for "bring Chrome to the front" and the like."""
        if sys.platform == "win32":
            import ctypes
            ctypes.WinDLL("user32").AllowSetForegroundWindow(-1)  # ASFW_ANY

    def stop(self) -> None:
        """What `kairu stop` does: every running action halts within a second, then Safe Mode. The mic goes off too."""
        from kairu import safemode
        from kairu.store import MissingDatabase, Store
        try:
            safemode.emergency_stop(Store(self.cfg.data_dir), "the Kairu bar")
        except MissingDatabase as error:
            self.say(f"The stop could not be written: {error}")
            return
        self.say("Stopped everything. Safe Mode until `kairu resume`.")
        if self.voice:
            self.start_thread(self.voice.mic_off, "Stopped everything, and the mic is off. Safe Mode until `kairu resume`.")
        self.start_thread(self._after_stop)

    def _after_stop(self) -> None:
        from kairu import cli
        try:
            cli._stop_mission_mode(self.cfg)
        except Exception as error:
            print(f"kairu bar: after the stop: {type(error).__name__}", file=sys.stderr, flush=True)

    # --- the card: only your own keystrokes fill it ---------------------------------------------------

    def _build_card(self, font, small):
        tk = self.tk
        card = tk.Frame(self.inner, bg=FIELD)
        self.card_heading = tk.Label(card, bg=FIELD, fg=TEXT, font=(font[0], font[1], "bold"), anchor="w", justify="left",
                                     wraplength=WIDTH - 2 * INSET_X - 16)
        self.card_heading.pack(fill="x", padx=8, pady=(6, 0))
        self.card_text = tk.Label(card, bg=FIELD, fg=TEXT, font=small, anchor="w", justify="left", wraplength=WIDTH - 2 * INSET_X - 16)
        self.card_text.pack(fill="x", padx=8, pady=(2, 4))
        row = tk.Frame(card, bg=FIELD)
        row.pack(fill="x", padx=8, pady=(0, 8))
        self.yes_label = tk.Label(row, text='Type "yes":', bg=FIELD, fg=QUIET, font=small)
        self.yes_label.pack(side="left")
        self.yes_box = tk.Entry(row, width=6, bg=BACKGROUND, fg=TEXT, insertbackground=TEXT, relief="flat", font=font)
        self.yes_box.pack(side="left", padx=(4, 10))
        self.pin_label = tk.Label(row, text="PIN:", bg=FIELD, fg=QUIET, font=small)
        self.pin_label.pack(side="left")
        self.pin_box = tk.Entry(row, width=10, show="•", bg=BACKGROUND, fg=TEXT, insertbackground=TEXT, relief="flat", font=font)
        self.pin_box.pack(side="left", padx=(4, 10))
        self.refuse_button = tk.Button(row, text="Refuse", command=lambda: self._answered(False), bg=BACKGROUND, fg=TEXT, relief="flat", font=small)
        self.refuse_button.pack(side="right")
        self.approve_button = tk.Button(row, text="Go on", command=lambda: self._answered(True), bg=BACKGROUND, fg=TEXT, relief="flat", font=small)
        self.approve_button.pack(side="right", padx=(0, 6))
        # ADR-054: "Is this correct?" has a Yes button (your own click is your yes; no code ever presses it)
        self.yes_button = tk.Button(row, text="Yes", command=self._clicked_yes, bg=GREEN, fg="white", activebackground=GREEN,
                                    relief="flat", font=small, width=5)
        self.yes_box.bind("<Return>", lambda event: self._next_box())
        self.pin_box.bind("<Return>", lambda event: self._answered(True))
        return card

    def _next_box(self) -> None:
        if self.pin_box.winfo_ismapped():
            self.pin_box.focus_set()
        else:
            self._answered(True)

    def _open_card(self, heading: str, text: str, with_pin: bool, answer: dict, kind: str = "") -> None:
        self._answer, self._card_kind, self._card_opened = answer, kind, time.monotonic()
        self.card_heading.configure(text=heading)
        self.card_text.configure(text=text)
        self.yes_box.delete(0, "end")
        self.pin_box.delete(0, "end")
        if with_pin:
            self.pin_label.pack(side="left", after=self.yes_box)
            self.pin_box.pack(side="left", padx=(4, 10), after=self.pin_label)
        else:
            self.pin_box.pack_forget()
            self.pin_label.pack_forget()
        self.yes_button.pack_forget()
        if kind == "turn":  # your turn: no boxes; Go on or Refuse (or say "go on" / "stop here")
            self.yes_label.pack_forget()
            self.yes_box.pack_forget()
        else:
            if not self.yes_label.winfo_manager():
                self.yes_label.pack(side="left", before=self.pin_label if with_pin else None)
                self.yes_box.pack(side="left", padx=(4, 10), after=self.yes_label)
            if kind == "correct":
                self.yes_button.pack(side="right", padx=(0, 6), before=self.refuse_button)
        self.card.pack(fill="x", pady=(0, 8), before=self.heard_line if self.heard_line and self.heard_line.winfo_manager()
                       else self.reply_line if self.reply_line.winfo_manager() else None)
        self.visible = True
        self.pill.cover(True)
        self.root.deiconify()
        self.root.lift()
        self._fit()
        if kind == "turn":
            return  # your turn: the keyboard stays where you are working (a password box, a captcha)
        self._take_focus()
        self.yes_box.focus_force()

    def _close_card(self) -> None:
        self.yes_box.delete(0, "end")
        self.pin_box.delete(0, "end")
        self.card.pack_forget()
        self._answer, self._card_kind = None, ""
        self._fit()
        self.order_box.focus_set()
        if self._in_run:
            self.hide()  # back out of the way of the run (ADR-054)

    def _answered(self, go_on: bool) -> None:
        answer = self._answer
        if answer is None:
            return
        answer["yes"], answer["pin"] = (self.yes_box.get(), self.pin_box.get()) if go_on else ("", "")
        answer["go_on"] = go_on
        self._close_card()
        answer["done"].set()

    def _clicked_yes(self) -> None:
        """The Yes button's own command: your click is your yes ("Is this correct?" only)."""
        answer = self._answer
        if answer is None or self._card_kind != "correct":
            return
        answer["yes"], answer["pin"], answer["go_on"] = "yes", "", True
        self._close_card()
        answer["done"].set()

    def spoken(self, word: str) -> bool:
        """ADR-054: a spoken answer to a take-control card only ("yes" / "no" to "Is this correct?", "go on" / "stop" to
        "Your turn"), within SPOKEN_SECONDS of the card opening. Every other card ignores it. Main thread."""
        answer, kind = self._answer, self._card_kind
        if answer is None or kind not in SPOKEN_CARDS:
            return False
        if not SPOKEN_AFTER <= time.monotonic() - self._card_opened <= SPOKEN_SECONDS:
            return False
        if kind == "correct" and word == "yes":
            self._clicked_yes()
        elif kind == "correct" and word == "no":
            self._answered(False)
        elif kind == "turn" and word == "go on":
            self._answered(True)
        elif kind == "turn" and word == "stop":
            self._answered(False)
        else:
            return False
        return True

    def _ask(self, heading: str, text: str, with_pin: bool, kind: str = "", seconds: float = CARD_SECONDS) -> dict | None:
        """From the worker: open the card and wait for you. What you typed, or None if the time ran out."""
        answer = {"done": threading.Event(), "yes": "", "pin": "", "go_on": False}
        self._ui.put(lambda: self._open_card(heading, text, with_pin, answer, kind))
        if answer["done"].wait(seconds):
            return answer
        self._ui.put(self._close_card)
        return None

    def ask_plan_approval(self, decision, plan: str):
        """The core's plan approver: the whole plan on the card, with the one High step's "yes" and PIN."""
        return self.ask_approval(decision, plan)

    def ask_approval(self, decision, plan: str = ""):
        """The core's approver: a High action's card, then GuardianClient.approve. An Approval, or None."""
        if not plan and getattr(decision, "pin", True) is False:
            return self.ask_correct(decision)
        lines = [plan, "This step needs your PIN:"] if plan else []
        lines += [f"{decision.action.name}: {decision.description}"]
        lines += [f"{key}: {value}" for key, value in decision.action.details.items() if key not in HIDDEN_FROM_THE_CARD]
        lines.append(f"Tier: {decision.tier}. This approves it once." + (" Yes runs the whole plan." if plan else ""))
        answer = self._ask("Guardian asks for your approval of this plan" if plan else "Guardian asks for your approval",
                           "\n".join(lines), True)
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

    def ask_correct(self, decision):
        """ADR-054: a careful step inside a take-control run (screen.agent_confirm): "Is this correct?", with what will be
        clicked and on which site, and the boxes Kairu filled with your details (their values read here, on this PC, only to
        show you). Your yes, typed, clicked or said, goes to GuardianClient.approve with no PIN; Guardian checks again that
        this action needs no PIN."""
        from kairu.tasks import details as my_details
        from kairu.tasks.plan import _careful
        d = decision.action.details
        site = str(d.get("site", ""))
        try:
            step = _careful({key: str(value) for key, value in d.items()})
        except (KeyError, TypeError):
            step = decision.description
        lines = [f"On {site}: {step}." if site else f"{step[:1].upper()}{step[1:]}."]
        filled = [part.rsplit(": ", 1) for part in str(d.get("filled", "")).split("; ") if ": " in part]
        if filled:
            saved = my_details.load(self.cfg.data_dir)
            shown = []
            for box, key in filled[:12]:
                value = saved.get(key, "") if key != my_details.USERNAME else my_details.value(self.cfg.data_dir, key, site)
                shown.append(f"{box}: {value or my_details.LABELS.get(key, key)}")
            lines.append("Kairu filled: " + "; ".join(shown) + ".")
        lines.append('Say "yes" or click Yes; "no" or Refuse stops here. (No PIN inside a run you started.)')
        answer = self._ask("Is this correct?", "\n".join(lines), False, kind="correct")
        typed = answer["yes"] if answer else ""
        try:
            return self.client.approve(decision.request_id, typed, "")  # Guardian records your answer, also a refusal
        except Refused:
            if typed.strip().lower() == "yes":
                raise
            return None
        finally:
            if answer:
                answer["yes"] = ""

    def ask_handover(self, text: str, seconds: float) -> bool:
        """ADR-054: the screen agent's "Your turn". Kairu takes no picture meanwhile. True when you say, type or press Go on."""
        answer = self._ask("Your turn", f'{text}\nWhen you are done, say or type "go on" (or press Go on). Refuse (or '
                                        'saying "stop here") ends the run.', False, kind="turn", seconds=max(5.0, seconds))
        return bool(answer and answer.get("go_on"))

    def _progress(self, event: dict) -> None:
        """What the task core says is happening, from the worker (ADR-054: the live steps of a take-control run). Only
        shown: what it does never changes what runs."""
        kind = event.get("kind")
        if kind == "control":
            on = bool(event.get("on"))
            self._ui.put(lambda: self._control(on))
        elif kind == "steps" and self._in_run:
            self._step_labels = [str(step.get("label", "")) for step in event.get("steps", [])]
        elif kind == "step" and self._in_run:
            number, state, text = int(event.get("number") or 0), str(event.get("state", "")), str(event.get("text", ""))
            label = self._step_labels[number - 1] if 0 < number <= len(self._step_labels) else ""
            line = f"Step {number}: {label}" if label else f"Step {number}"
            line += {"running": f" … ({text})" if text else " …", "waiting": f" — {text}", "done": " ✓",
                     "not done": f" ✗ {text[:120]}"}.get(state, "")
            self._ui.put(lambda: self._show_step(line, number))

    def _control(self, on: bool) -> None:
        """A take-control run starts (the bar steps aside, so you see the screen and the bar never covers a button Kairu
        clicks; the pill shows the step) or ends (the bar comes back with the answer)."""
        self._in_run = on
        self._step_labels = []
        if on:
            self.hide()
        else:
            self.visible = True
            self.pill.cover(True)
            self.root.deiconify()
            self.root.lift()
            self._fit()

    def _show_step(self, line: str, number: int) -> None:
        self.reply_line.configure(text=line)
        if not self.reply_line.winfo_manager():
            self.reply_line.pack(fill="x", pady=(0, 6))
        self._fit()
        self.pill.step(number)

    def ask_confirmation(self, text: str) -> bool:
        """The core's confirmer: something you should know before a Medium step goes on. "yes" and no PIN."""
        answer = self._ask("Before I do that", text, False)
        return bool(answer) and answer["yes"].strip().lower() == "yes"

    def key_problem(self, key, setting: str = "tasks.bar_key in config.yaml (BAR.md)") -> None:
        """If another program holds the show/hide key, you would never find a hidden bar: show it, and say so."""
        if key.state not in ("held", "not started") and "Windows only" not in key.state:
            self.show()
            self.say(f"{key.state}. Close it, or set {setting}.")

    # --- the mic (VOICE.md): only your own click or keystroke switches it on --------------------------------

    def _start_voice(self) -> None:
        from kairu.bar.session_watch import SessionWatch
        from kairu.bar.voice import VoiceControl
        from kairu.voice.link import LinkError
        try:
            self.voice = VoiceControl(self.cfg, self.client, _Orders(self), _Screen(self))
        except LinkError as error:
            self.mic_button.configure(state="disabled")
            self.say(f"The mic can't be used: {error}.")
            return
        voice = self.voice  # not the bar: the watch's thread must never hold the window
        self.watch = SessionWatch(lambda why: voice.mic_off(f"Mic off: {why}."), voice.listen_at_start)
        voice.listen_at_start("the bar started")  # only with voice.listen_at_start: true in config.yaml (VOICE.md)

    def _mic_clicked(self) -> None:
        """The mic button's own command: your click."""
        if self.voice:
            self.voice.mic_button()

    def listen_key_pressed(self) -> None:
        """Ctrl+Alt+V's own handler: your keystroke."""
        if self.voice:
            self.voice.listen_key()

    def _mic_look(self, on: bool) -> None:
        if not self.mic_button:
            return
        self.mic_button.configure(text="Mic on" if on else "Mic", bg=LISTENING if on else FIELD, fg=ON_LISTENING if on else QUIET,
                                  activebackground=LISTENING if on else FIELD)
        if on:
            self.heard_line.pack(fill="x", pady=(0, 4), **({"before": self.reply_line} if self.reply_line.winfo_manager() else {}))
        else:
            self.heard_line.configure(text="")
            self.heard_line.pack_forget()
        self._fit()

    def _show_heard(self, text: str, live: bool = False) -> None:
        """What you said, in the words line: grey and with "…" while you are still speaking (voice.live_caption_every),
        white once the whole sentence is heard."""
        if self.heard_line:
            self.heard_line.configure(text=f"\N{STUDIO MICROPHONE} {text}{' …' if live else ''}" if text else "",
                                      fg=QUIET if live else TEXT)
            self._fit()
            self.pill.heard(text, live)

    def start_thread(self, target, *args) -> threading.Thread:
        """Work off the main thread, followed so close() can wait for it."""
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        thread = threading.Thread(target=target, args=args, daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    def close(self, seconds: float = 5.0) -> None:
        """Let the window go, once the bar's own threads have ended (each gets up to `seconds`). The mic goes off first."""
        if self.voice:
            self.voice.close()
        if self.watch:
            self.watch.close()
        self.pill.close()
        for thread in self._threads:
            while thread.is_alive() and seconds > 0:  # the window keeps answering meanwhile, so a card can still close
                thread.join(0.05)
                seconds -= 0.05
                try:
                    self._drain_once()
                    self.root.update()
                except self.tk.TclError:
                    break
        try:
            self.root.destroy()
        except self.tk.TclError:
            pass

    def _drain_once(self) -> None:
        while True:
            try:
                self._ui.get_nowait()()
            except queue.Empty:
                return

    def run(self) -> None:
        self.root.mainloop()


class _Orders:
    """The task core as the voice sees it: its skills, and the bar's handle() (so "open the workspace" works said too)."""

    def __init__(self, bar: Bar):
        import weakref
        self._bar, self.skills = weakref.ref(bar), getattr(bar.core, "skills", ())

    def handle(self, order: str) -> str:
        bar = self._bar()
        return bar.handle(order) if bar is not None else ""

    def last_answer(self):
        """The brain's answer to the last order, if it was a question: for Kairu Live (kairu/live/relay.py)."""
        bar = self._bar()
        return getattr(bar.core, "last_answer", None) if bar is not None else None


class _Screen:
    """What the voice may do to the window, from its own threads: each goes through the main thread's queue.

    It holds the bar only weakly, so a voice thread is never the last to let go of the window (Tcl stops the whole program
    when that happens); what it posts finds the bar again on the main thread.
    """

    def __init__(self, bar: Bar):
        import weakref
        self._bar, self._queue = weakref.ref(bar), bar._ui

    def _post(self, method: str, *args) -> None:
        bar_ref = self._bar

        def run():
            bar = bar_ref()
            if bar is not None:
                getattr(bar, method)(*args)
        self._queue.put(run)

    def say(self, text: str) -> None:
        self._post("say", text)

    def heard(self, text: str) -> None:
        self._post("_show_heard", text)

    def hearing(self, text: str) -> None:
        self._post("_show_heard", text, True)

    def show(self) -> None:
        self._post("_show_quietly")

    def mic_shown(self, on: bool) -> None:
        self._post("_mic_look", on)

    def card_open(self) -> bool:
        bar = self._bar()
        return bar is not None and bar._answer is not None

    def spoken_card(self) -> str:
        """ADR-054: "correct" or "turn" while a take-control card that takes a spoken answer is open; "" otherwise."""
        bar = self._bar()
        return bar._card_kind if bar is not None and bar._answer is not None and bar._card_kind in SPOKEN_CARDS else ""

    def spoken(self, word: str) -> None:
        self._post("spoken", word)

    def busy(self) -> bool:
        bar = self._bar()
        return bar is not None and bar.busy


class OneBar:
    """Only one bar under your account at a time."""

    def __init__(self, data_dir):
        if sys.platform == "win32":
            from kairu import winpipe
            self.held = winpipe.claim_mutex(f"Local\\KairuBar-{winpipe.current_user_sid()}")
        else:
            import fcntl
            self.held = os.open(Path(data_dir) / "bar.lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(self.held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(self.held)
                self.held = None

    def release(self) -> None:
        if self.held is None:
            return
        if sys.platform == "win32":
            from kairu import winpipe
            winpipe.close(self.held)
        else:
            os.close(self.held)
        self.held = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kairu.bar.app", description="The Kairu bar.")
    parser.add_argument("--config", help="config.yaml to use")
    parser.add_argument("--show", action="store_true", help="show it at once; otherwise Ctrl+Alt+Space does")
    args = parser.parse_args(argv)
    cfg = kairu_config.load(args.config)
    Path(cfg.data_dir).mkdir(parents=True, exist_ok=True)
    quit_file = Path(cfg.data_dir) / QUIT_FILE
    one = OneBar(cfg.data_dir)
    waits = QUIT_WAIT_SECONDS * 10 if one.held is None and quit_file.exists() else 0
    while one.held is None and waits:  # `kairu bar quit` just now: the old bar takes its note, then ends
        time.sleep(0.1)
        waits -= 1
        one = OneBar(cfg.data_dir)
    if one.held is None:
        return ALREADY_RUNNING  # its quit note stays, for it to find
    quit_file.unlink(missing_ok=True)  # a note left from before, with no bar to read it
    import tkinter
    for tries_left in range(WINDOW_TRIES - 1, -1, -1):
        try:
            bar = Bar(cfg, show=args.show, config_file=args.config)
            break
        except tkinter.TclError as error:  # Tcl sometimes can't read its own files for a moment on Windows
            if not tries_left:
                print(f"kairu bar: no window could be made ({error})", file=sys.stderr, flush=True)
                return 1
            time.sleep(0.5)
    from kairu.bar.hotkey import LISTEN_ID, ShowHideKey
    key = ShowHideKey(bar.toggle_from_any_thread, cfg.bar_key)
    key.start()
    bar.root.after(KEY_LOOK_MS, lambda: bar.key_problem(key))
    listen = None
    if bar.voice:
        listen = ShowHideKey(bar.listen_key_pressed, cfg.voice_key, LISTEN_ID)
        listen.start()
        bar.root.after(KEY_LOOK_MS + 200, lambda: bar.key_problem(listen, "voice.key in config.yaml (VOICE.md)"))
    try:
        bar.run()
    finally:
        key.close()
        if listen:
            listen.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
