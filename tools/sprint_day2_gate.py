"""The Sprint Day 2 gate test (the light voice): you speak to Kairu, and this tool checks and prints pass or fail.

On Windows, in your Guardian folder, with voice on, the model set up and the bar running (VOICE.md, "The gate test"):
    .venv-guardian\\Scripts\\python tools\\sprint_day2_gate.py              all 11 steps (about 20 minutes)
    .venv-guardian\\Scripts\\python tools\\sprint_day2_gate.py --step 6     only that step

    1  Enter keeps Kairu's voice as it is (uk-jenny by default; indian-svbi before 14 Nov 2026); or type p to hear each of Kairu's voices say one line
       and pick one by number: it is saved as voice.voice, only its file stays downloaded, and Guardian and the bar start again
    2  the mic starts off; Ctrl+Alt+V and the mic button start listening with "Go ahead, I'm listening"
    3  "Kairu, open Chrome and set volume to 30", hands-free: both steps through Guardian, in order, and no speech
    4  your words appear in the bar (with Whisper once you have said them; with Vosk word by word)
    5  "Kairu, search the weather": a short spoken answer
    6  Kairu answers three questions aloud, and you judge whether each is short (only that, for now: the expressive
       Tenmin-like voice comes after the phone app)
    7  "Kairu, restart": the card appears, a spoken "yes" is ignored, you click Refuse, nothing restarts
    8  a sentence without "Kairu" runs nothing, and Kairu's own spoken answer never wakes it
    9  "Kairu, stop" during kairu demo: halted in under 1 second, the mic off
    10 "thank you" ends the session
    11 the voice stays under 200 MB at rest and under 400 MB while Kairu speaks

It asks for one spoken order at a time and waits until it reaches Guardian, however long you take. It reads Guardian's
audit log and Windows to check each step; where only you can hear or see it, it asks. It never hears you itself, never
types into the bar, and never sees your PIN; what you type into this window is never taken as an answer to a question it has
not asked yet. It puts your volume back afterwards. In step 6 it asks whether to keep Kairu's three replies (their text only,
to public questions it chose) as future test inputs, in tests_kairu/tenmin_real_replies.json; nothing is kept unless you say yes.
"""

import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from sprint_day1_gate import LIMIT, VENV_PYTHON, Gate as Day1Gate  # noqa: E402 (the same reading and asking)

QUIET_SECONDS = 15  # after a sentence without "Kairu": nothing may reach Guardian in this long
AT_REST_MB, SPEAKING_MB = 200, 400  # the voice's memory: the listener alone, and the listener with voice.speak and Piper
SENTENCE = "The weather was lovely yesterday, so we walked to the market and bought some fruit and fresh bread."
SAMPLE = "Hello, I'm Kairu. Narendra Modi is the Prime Minister of India. Want to know more about him?"
LONG_LINE = ("Rain forms when the sun warms water and it rises as vapour. High up, the vapour cools and joins into tiny drops that "
             "make clouds. For example, steam from a kettle turns into drops on a cold plate. Isn't that neat?")
TENMIN_QUESTIONS = ("who is the prime minister of India?", "what is photosynthesis?", "explain it simply")
KEPT_REPLIES = ROOT / "tests_kairu" / "tenmin_real_replies.json"
STEPS = 11


def with_voice(text: str, key: str) -> str:
    """config.yaml's text with voice.voice set to key, under the voice section; every other line as it was."""
    lines = text.splitlines()
    start = next((number for number, line in enumerate(lines) if re.match(r"voice:\s*(#.*)?$", line)), None)
    if start is None:
        return text.rstrip("\n") + f"\nvoice:\n  voice: {key}\n"
    end = next((number for number in range(start + 1, len(lines)) if lines[number] and not lines[number][0].isspace()), len(lines))
    for number in range(start + 1, end):
        if re.match(r"\s*#?\s*voice:\s", lines[number]):
            lines[number] = f"  voice: {key}   # Kairu's voice, picked in the Day 2 gate test"
            break
    else:
        lines.insert(start + 1, f"  voice: {key}   # Kairu's voice, picked in the Day 2 gate test")
    return "\n".join(lines) + "\n"


def tree_mb(pid: int) -> float:
    """Working set of a process and every process under it, in MB."""
    total, waiting = 0.0, [pid]
    while waiting:
        member = waiting.pop()
        total += family_mb(member, children=False)
        waiting += child_pids(member)
    return total


def spoken_after(rows: list[dict], action: str) -> bool:
    """A voice.speak run started after the first check of `action`: the answer was said aloud."""
    asked = next((row["id"] for row in rows if row["kind"] == "check" and row["action"] == action), None)
    return asked is not None and any(row["id"] > asked and row["kind"] == "run" and row["action"] == "voice.speak"
                                     and row["decision"] == "started" for row in rows)


def orders_reaching_guardian(rows: list[dict]) -> list[str]:
    """What reached Guardian as an order: every check, except the voice's own listening and speaking."""
    return [row["action"] for row in rows if row["kind"] == "check" and not row["action"].startswith("voice.")]


def in_order(rows: list[dict], first: str, second: str) -> bool:
    started = [row["action"] for row in rows if row["kind"] == "run" and row["decision"] == "started" and row["action"] in (first, second)]
    return started[:2] == [first, second]


class Gate(Day1Gate):
    def speak(self, words: str, action: str | None, seconds: float = 600) -> int | None:
        """Ask you to say one order, and wait until it reaches Guardian as `action`. The row it was decided at, or None."""
        before = self.newest()
        self.say(f'  >>> Say:  "{words}"')
        if action is None:
            return before
        started = reminded = time.monotonic()
        while time.monotonic() - started < seconds:
            decided = [row for row in self.rows(before, "check") if row["action"] == action]
            if decided:
                return decided[0]["id"]
            if not self.catch_stray_typing() and time.monotonic() - reminded > 60:
                self.say(f'  Still waiting for "{words}" to reach Guardian. Is the mic on (the button says "Mic on")? '
                         f'Say it again, a little slower, or press Ctrl+Alt+{self.cfg.voice_key} first.')
                reminded = time.monotonic()
            time.sleep(0.2)
        self.say(f'  Nothing reached Guardian for "{words}".')
        return None

    def listening(self) -> list[dict]:
        try:
            return [run for run in self.client.status()["running"] if run["action"] == "voice.listen"]
        except Exception:
            return []

    def ready(self) -> bool:
        from kairu.voice import models
        fine = super().ready()
        problems = []
        if not self.cfg.voice_enabled:
            problems.append("voice is off: set voice.enabled: true in config.yaml, then restart Guardian and the bar (VOICE.md)")
        checks = [lambda: models.hearing_ready(self.cfg.data_dir, self.cfg.voice_engine, self.cfg.voice_model),
                  lambda: models.piper_ready(self.cfg.data_dir),
                  lambda: models.voice_ready(self.cfg.data_dir, self.cfg.voice_voice)]  # step 1 downloads others only to pick
        for check in checks:
            try:
                check()
            except models.NotSetUp as error:
                problems.append(str(error))
        for problem in problems:
            self.say(f"  NOT READY: {problem}")
        return fine and not problems

    # --- the steps ---------------------------------------------------------------------------------------

    def step_2(self) -> None:
        key = f"Ctrl+Alt+{self.cfg.voice_key}"
        self.say(f"Step 2: the mic is off at first; {key} and the mic button start listening")
        off_first = not self.listening()
        if not off_first:
            self.say('  The mic is on now. Click the mic button in the bar once, so it says "Mic" (off).')
            self.wait_until(lambda: not self.listening(), 120)
        before = self.newest()
        self.press_the_key(f"Press {key} (no need to click the bar first).")
        by_key = self.wait_until(lambda: self.listening() and self.started(before, "voice.speak"), 60)
        heard_key = by_key and self.yes('Did the bar open and say "Go ahead, I\'m listening." aloud?')
        self.say('  >>> Now click the mic button in the bar: it goes off ("Mic").')
        went_off = self.wait_until(lambda: not self.listening(), 60)
        before = self.newest()
        self.say('  >>> Click the mic button again: it comes on ("Mic on").')
        by_button = self.wait_until(lambda: self.listening() and self.started(before, "voice.speak"), 60)
        heard_button = by_button and self.yes('Did it say "Go ahead, I\'m listening." again?')
        self.mark(2, bool(off_first and heard_key and went_off and heard_button),
                  f"off at first: {off_first}; {key}: {bool(heard_key)}; button off: {went_off}; button on: {bool(heard_button)}")

    def step_3(self) -> None:
        self.say("Step 3: two orders in one breath, hands-free. Leave the keyboard and mouse alone.")
        self.volume_before = self.pc.volume()[0] if self.volume_before is None else self.volume_before
        before = self.newest()
        reached = self.speak("Kairu, open Chrome and set volume to 30", "system.volume") is not None
        volume = reached and self.wait_until(lambda: self.pc.volume()[0] == 30)
        chrome = reached and self.wait_until(lambda: self.window_of("chrome") is not None)
        time.sleep(4)  # time enough for any speech to start: a finished task must stay quiet (Tenmin, K-7)
        rows = self.rows(before)
        ordered = in_order(rows, "apps.open", "system.volume")
        quiet = not self.started(before, "voice.speak")
        self.mark(3, bool(volume and chrome and ordered and quiet), f"Chrome open: {bool(chrome)}; volume 30: {bool(volume)} "
                  f"(read {self.pc.volume()[0]}); apps.open then system.volume: {ordered}; no speech after the tasks: {quiet}")

    def step_4(self) -> None:
        self.say("Step 4: your words, live. Watch the bar's second line while you speak.")
        reached = self.speak("Kairu, set volume to 40", "system.volume") is not None
        self.wait_until(lambda: self.pc.volume()[0] == 40, 30)
        asked = ("Did your words appear in the bar once you had said them?" if self.cfg.voice_engine != "vosk"  # Whisper: heard whole
                 else "Did your words appear in the bar as you said them, word by word?")
        seen = reached and self.yes(asked)
        self.mark(4, bool(seen), "words shown live" if seen else "not seen live")

    def step_5(self) -> None:
        self.say("Step 5: a question, answered aloud")
        before = self.newest()
        reached = self.speak("Kairu, search the weather", "brain.ask") is not None
        answered = reached and self.wait_until(lambda: self.ended(before, "brain.ask") is not None, 180)
        aloud = answered and self.wait_until(lambda: spoken_after(self.rows(before), "brain.ask"), 60)
        heard = aloud and self.yes("Did Kairu say a short answer about the weather, and show it in the bar?")
        self.mark(5, bool(heard), f"brain.ask: {self.ended(before, 'brain.ask')}; spoken: {bool(aloud)}")

    def step_7(self) -> None:
        self.say('Step 7: restart asks first. When the card is up, SAY "yes" (it must be ignored), then click Refuse. Do not type your PIN.')
        before = self.newest()
        self.speak("Kairu, restart", "system.restart")
        asked = self.wait_until(lambda: any(row["action"] == "system.restart" and row["decision"] == "needs_approval"
                                            for row in self.rows(before, "check")), 60)
        self.say('  >>> Now say:  "yes"   (out loud; do not type it)')
        time.sleep(8)
        approved_by_voice = any(row["decision"] == "granted" for row in self.rows(before, "approval"))
        self.say("  >>> Now click Refuse on the card.")
        refused = self.wait_until(lambda: any(row["action"] == "system.restart" and row["decision"] == "refused"
                                              for row in self.rows(before, "approval")), 180)
        ran = self.started(before, "system.restart")
        said = refused and self.yes('After your spoken "yes", did the bar say it never takes a yes or a PIN by voice?')
        self.mark(7, bool(asked and refused and not approved_by_voice and not ran and said),
                  f"card: {asked}; approved by voice: {approved_by_voice}; refused: {refused}; restarted: {bool(ran)}")

    def step_8(self) -> None:
        self.say('Step 8: a sentence without "Kairu" does nothing, and Kairu\'s own voice never wakes it.')
        self.say('  >>> First say "thank you", so Kairu stops listening for orders.')
        before = self.newest()
        self.wait_until(lambda: self.started(before, "voice.speak"), 60)
        time.sleep(3)
        before = self.newest()
        self.say(f'  >>> Read this aloud, at your normal pace:\n      "{SENTENCE}"')
        time.sleep(QUIET_SECONDS)
        woken = orders_reaching_guardian(self.rows(before))
        self.say('  >>> Now say "Kairu" alone, and listen: Kairu answers aloud. Then stay quiet for a few seconds.')
        spoke = self.wait_until(lambda: self.started(before, "voice.speak"), 60)
        time.sleep(8)
        echoed = orders_reaching_guardian(self.rows(before))
        self.mark(8, not woken and spoke and not echoed,
                  f"orders from the sentence: {woken or 'none'}; Kairu spoke: {spoke}; orders after its own voice: {echoed or 'none'}")

    def step_9(self) -> None:
        self.say('Step 9: "Kairu, stop" during kairu demo')
        before = self.newest()
        demo = subprocess.Popen([sys.executable, "-m", "kairu", "demo", "--seconds", "120"], cwd=ROOT, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            if not self.wait_until(lambda: self.started(before, "demo.count"), 30):
                self.mark(9, False, "kairu demo did not start")
                return
            self.speak("Kairu, stop", None)
            halted = []

            def stopped() -> bool:
                halted[:] = [row for row in self.rows(before, "run") if row["action"] == "demo.count" and row["decision"] == "halted"]
                return bool(halted)

            if not self.wait_until(stopped, 120):
                self.mark(9, False, "no stop came within 2 minutes")
                return
            took = halted[0]["details"].get("seconds_since_stop")
            mic_off = self.wait_until(lambda: not self.listening(), 10)
            by_voice = any(row["kind"] == "emergency_stop" and "voice" in str(row["details"].get("source", "")) for row in self.rows(before))
            ok = isinstance(took, (int, float)) and took < LIMIT and mic_off and by_voice
            self.mark(9, ok, f"kairu demo halted {took} s after the stop (limit {LIMIT:g}); the stop came from your voice: {by_voice}; "
                             f"mic off: {mic_off}")
        finally:
            demo.terminate()
            demo.wait(10)
        self.leave_safe_mode()

    def step_10(self) -> None:
        self.say('Step 10: "thank you" ends the session')
        if not self.listening():
            before = self.newest()
            self.say('  >>> Click the mic button to switch the mic on (it said "Go ahead, I\'m listening.").')
            self.wait_until(lambda: self.listening() and self.started(before, "voice.speak"), 120)
            time.sleep(3)
        before = self.newest()
        self.say('  >>> Say:  "thank you"')
        thanked = self.wait_until(lambda: self.started(before, "voice.speak"), 60)
        time.sleep(3)
        after = self.newest()
        self.say('  >>> Now say, without "Kairu":  "open Notepad"')
        time.sleep(QUIET_SECONDS)
        ran = orders_reaching_guardian(self.rows(after))
        self.mark(10, bool(thanked) and not ran, f"Kairu answered the thanks: {thanked}; orders after it: {ran or 'none'}")

    def step_1(self) -> None:
        from kairu.voice import models
        keys = list(models.VOICES)
        current = self.cfg.voice_voice
        self.catch_stray_typing()
        if self.ask_here(f"Step 1: Kairu's voice is {current} ({models.VOICES[current].label}). Press Enter to keep it, or "
                         f"type p to hear all {len(keys)} voices and pick one:").strip().lower() != "p":
            self.mark(1, True, f"kept voice.voice: {current} (the pick was skipped)")
            return
        self.say(f"Step 1: Kairu's voice. You will hear the same short line in each of {len(keys)} voices; then pick one by its"
                 " number. Each voice not set up yet is downloaded first (about 60-75 MiB each, SHA-256 checked); once you"
                 " pick, only the voice you picked stays downloaded.")
        try:
            piper = models.piper_ready(self.cfg.data_dir)
            samples = {}
            for number, key in enumerate(keys, 1):
                samples[key] = self.sample_of(piper, key)
                self.say(f"  {number:>2}  {key}: {models.VOICES[key].label}")
                self.play(*samples[key])
                time.sleep(0.6)
        except (models.NotSetUp, models.SetupError) as error:
            self.mark(1, False, f"{error}")
            return
        self.catch_stray_typing()
        ask = f"Which voice should Kairu use? 1-{len(keys)}; r hears them all again, r and a number (r5) hears one again:"
        choice = self.ask_choice(ask, len(keys))
        while isinstance(choice, str):
            again = [int(choice[1:])] if choice[1:] else range(1, len(keys) + 1)
            for number in again:
                self.say(f"  {number:>2}  {keys[number - 1]}: {models.VOICES[keys[number - 1]].label}")
                self.play(*samples[keys[number - 1]])
                time.sleep(0.6)
            choice = self.ask_choice(ask, len(keys))
        if choice is None:  # Enter: the voice stays as it is
            self.mark(1, True, f"no voice was picked: voice.voice stays {current}")
            return
        key = keys[choice - 1]
        self.config_file.write_text(with_voice(self.config_file.read_text(encoding="utf-8"), key), encoding="utf-8")
        removed = keep_only(self.cfg.data_dir, key)
        self.say(f"  Saved voice.voice: {key} in {self.config_file}. Removed the other voices' files ({removed}).")
        self.say("  Starting Guardian and the bar again, so they use it ...")
        self.restart_kairu()
        from kairu import config as kairu_config
        self.cfg = kairu_config.load(self.config_file)
        heard = self.cfg.voice_voice == key and self.yes(f"Did {key} sound warm and natural, at a natural speed with small pauses?")
        self.mark(1, bool(heard), f"voice.voice is {self.cfg.voice_voice}")

    def sample_of(self, piper, key: str) -> tuple[int, bytes]:
        """The sample line in this voice, made in memory (never written to disk); the voice is downloaded first if needed."""
        from kairu.voice import models, speak
        models.setup_voice(self.cfg.data_dir, key, say=lambda text: self.say(f"      {text}"))
        onnx, config, speaker = models.voice_ready(self.cfg.data_dir, key)
        return speak.sample_rate(config), b"".join(speak.synthesize(SAMPLE, piper, onnx, speaker))

    def play(self, rate: int, sound: bytes) -> None:
        from kairu.voice import speak
        out = speak.WaveOut(rate)
        try:
            for start in range(0, len(sound), 8820):
                out.play(sound[start:start + 8820])
            out.wait()
        finally:
            out.close()

    def ask_choice(self, question: str, most: int):
        """A number from 1 to most, "r" (all again), "r5" (that one again), or None."""
        answer = self.ask_here(question + " ").strip().lower().replace(" ", "")
        if answer == "r" or (answer[:1] == "r" and answer[1:].isdigit() and 1 <= int(answer[1:]) <= most):
            return answer
        return int(answer) if answer.isdigit() and 1 <= int(answer) <= most else None

    def restart_kairu(self) -> None:
        for command in (["guardian", "quit"], ["guardian", "run"], ["bar", "quit"]):
            subprocess.run([sys.executable, "-m", "kairu", *command], cwd=ROOT, capture_output=True, timeout=60)
        time.sleep(3)  # the old bar lets go of its lock
        subprocess.run([sys.executable, "-m", "kairu", "bar"], cwd=ROOT, capture_output=True, timeout=60)

    def step_6(self) -> None:
        """Tenmin with real AI answers: the questions go through the same task core and brain as yours, and each spoken line
        goes through Guardian's voice.speak, in your voice."""
        from kairu.brain import tenmin
        from kairu.guardian import Action
        from kairu.tasks.core import TaskCore
        self.say("Step 6: Tenmin. Kairu answers three questions aloud; you judge each one. (Typed by this tool, so the "
                 "answers are real and the same for everyone.)")
        core, kept, good = TaskCore(self.cfg, self.client, source="pc"), [], 0
        for question in TENMIN_QUESTIONS:
            self.say(f'\n  Question: "{question}"')
            reply = core.handle(question)
            line = tenmin.spoken(reply, question)
            self.say(f"  Kairu's answer (shown): {reply}\n  Kairu says aloud: {line}")
            run = self.client.run(Action("voice.speak", {"text": line}))
            self.wait_until(lambda: self.client.run_status(run["run"])["outcome"] is not None, 60)
            answers = [self.yes("Short?")]  # only this for now: the expressive Tenmin-like voice comes after the phone app
            good += sum(answers)
            kept.append({"question": question, "reply": reply, "spoken": line, "judged": answers})
        if self.yes("Keep these three replies (their text only, no sound) as future test inputs?"):
            KEPT_REPLIES.write_text(json.dumps({"kept": date.today().isoformat(), "replies": kept}, indent=1, ensure_ascii=False),
                                    encoding="utf-8")
            self.say(f"  Kept in {KEPT_REPLIES}.")
        self.mark(6, good == len(TENMIN_QUESTIONS), f"{good} of {len(TENMIN_QUESTIONS)} short")

    def step_11(self) -> None:
        from kairu.guardian import Action
        self.say("Step 11: the voice's memory, at rest and while Kairu speaks its longest kind of answer")
        if not self.listening():
            self.say("  >>> Click the mic button to switch the mic on.")
            self.wait_until(lambda: bool(self.listening()), 120)
        time.sleep(5)
        runs = self.listening()
        if not runs:
            self.mark(11, False, "the mic is not on")
            return
        at_rest = tree_mb(runs[0]["pid"])
        speaking = self.client.run(Action("voice.speak", {"text": LONG_LINE}))
        most = 0.0
        while self.client.run_status(speaking["run"])["outcome"] is None:
            most = max(most, tree_mb(speaking["pid"]))
            time.sleep(0.05)
        whole = tree_mb(runs[0]["pid"]) + most
        self.mark(11, at_rest < AT_REST_MB and whole < SPEAKING_MB,
                  f"at rest {at_rest:.0f} MB (limit {AT_REST_MB}); while Kairu speaks {whole:.0f} MB (limit {SPEAKING_MB})")
        self.say("  You can switch the mic off now (the mic button).")

    def run(self, only: int | None = None) -> int:
        self.say("Kairu Sprint Day 2 gate test (the light voice)")
        if not self.ready():
            self.say("\n  Result: NOT RUN  fix what is listed above, then run this again.")
            return 1
        try:
            for step in [only] if only else range(1, STEPS + 1):
                getattr(self, f"step_{step}")()
        finally:
            self.put_back()
        self.say("The gate test:")
        for step in sorted(self.results):
            ok, why = self.results[step]
            self.say(f"  {step}  {'PASS' if ok else 'FAIL'}  {why}")
        passed = sum(ok for ok, _ in self.results.values())
        complete = len(self.results) == STEPS
        verdict = "PASSED" if complete and passed == STEPS else "PART PASSED" if passed == len(self.results) else "FAILED"
        self.say(f"\n  Result: {verdict}  {passed} of {len(self.results)} steps run pass{'' if complete else f' (the gate needs all {STEPS})'}")
        if complete:
            self.say("  Please send me this output and `kairu audit show -n 80`.")
        return 0 if passed == len(self.results) else 1

    def put_back(self) -> None:
        if self.volume_before is not None:
            self.pc.set_volume(level=self.volume_before)
            self.say(f"  Your volume ({self.volume_before}) is back.")


def child_pids(pid: int) -> list[int]:
    """The processes this one started (Windows)."""
    if sys.platform != "win32":
        return []
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    found, snapshot = [], kernel32.CreateToolhelp32Snapshot(0x2, 0)
    try:
        entry = Entry(dwSize=ctypes.sizeof(Entry))
        more = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        while more:
            if entry.th32ParentProcessID == pid:
                found.append(entry.th32ProcessID)
            more = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))
    return found


def keep_only(data_dir, key: str) -> str:
    """Delete every Piper voice file but the one key's voice uses (several voices may share one file). Says what went."""
    from kairu.voice import models
    keep = models.VOICES[key].name
    place = Path(data_dir) / models.FOLDER / models.VOICE_FOLDER
    gone = sorted({voice.name for voice in models.VOICES.values() if voice.name != keep
                   and any((place / f"{voice.name}{end}").exists() for end in (".onnx", ".onnx.json", ".kairu.json"))})
    for name in gone:
        for end in (".kairu.json", ".onnx", ".onnx.json"):  # the mark first: a half-removed voice is never "ready"
            (place / f"{name}{end}").unlink(missing_ok=True)
    return ", ".join(gone) or "none were there"


def family_mb(pid: int, children: bool = True) -> float:
    """Working set of a process (and, with children, the processes it started), in MB (Windows)."""
    if sys.platform != "win32":
        return 0.0
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                                 "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
    total = 0
    for member in [pid, *(child_pids(pid) if children else [])]:
        handle = kernel32.OpenProcess(0x1000 | 0x0010, False, member)
        if not handle:
            continue
        counters = Counters(cb=ctypes.sizeof(Counters))
        if kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            total += counters.WorkingSetSize
        kernel32.CloseHandle(wintypes.HANDLE(handle))
    return total / 1e6


def main() -> int:
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve() and sys.prefix == sys.base_prefix:
        return subprocess.call([str(VENV_PYTHON), __file__, *sys.argv[1:]])
    parser = argparse.ArgumentParser(description="The Sprint Day 2 gate test: the light voice, by voice, on your own PC.")
    parser.add_argument("--step", type=int, choices=range(1, STEPS + 1), help="only this step")
    return Gate().run(parser.parse_args().step)


if __name__ == "__main__":
    sys.exit(main())
