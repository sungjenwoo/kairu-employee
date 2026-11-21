"""The Sprint Day 1 gate test (the Kairu bar, PC0 + PC1): you type in the bar, and this tool checks and prints pass or fail.

On Windows, in your Guardian folder, with the bar running (`kairu bar`):
    .venv-guardian\\Scripts\\python tools\\sprint_day1_gate.py              all 8 steps (about 10 minutes)
    .venv-guardian\\Scripts\\python tools\\sprint_day1_gate.py --step 4     only that step

    1  the show/hide key opens and hides the bar over any app
    2  "open Chrome" opens Chrome; "open Notepad" opens Notepad
    3  "close Notepad" closes it; "put Chrome on the left half" works
    4  "volume 30", "brightness 50", "how much RAM is free?" work
    5  "open Notepad and set volume to 20" does both, in order
    6  "restart" shows the approval card; refusing it does nothing
    7  rename a file in Kairu-files, then "undo" brings the old name back; a rename outside is refused
    8  Stop in the bar halts kairu demo in under 1 second

It first lists every skill with its tier, and that no Critical skill exists. It reads Windows and Guardian's audit log to
check each step; where only you can see it, it asks. You type your own orders, "yes", "no" and PIN: this tool never sees your
PIN and types nothing into the bar. It puts your volume and brightness back afterwards.
"""

import argparse
import ctypes
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv-guardian" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
sys.path.insert(0, str(ROOT))

LIMIT = 1.0
WAIT_SECONDS = 120  # for something to happen after an order has reached Guardian
ORDER_SECONDS = 600  # for you to type an order: it waits, and reminds you
REMIND_SECONDS = 60


class Gate:
    def __init__(self):
        from kairu import config as kairu_config
        from kairu.client import GuardianClient
        from kairu.tasks import pc
        self.config_file = kairu_config.config_path()
        self.cfg = kairu_config.load(self.config_file)
        self.client = GuardianClient(self.cfg, start_if_down=False)
        self.pc = pc.backend()
        self.results: dict[int, tuple[bool, str]] = {}
        self.volume_before, self.brightness_before = None, None

    # --- talking to you (the tests answer here instead) -----------------------------------------------------

    def say(self, text: str = "") -> None:
        print(text, flush=True)

    def yes(self, question: str) -> bool:
        """Your answer here. Anything typed into this window before the question is not taken as the answer."""
        self.catch_stray_typing()
        return self.ask_here(question).strip().lower() in ("y", "yes")

    def ask_here(self, question: str) -> str:
        try:
            return input(f"  {question} [y/n] ")
        except EOFError:
            return ""

    def typed_here(self) -> str:
        """What was typed into this window, not the bar, since the last look (Windows' console; elsewhere nothing)."""
        if sys.platform != "win32":
            return ""
        import msvcrt
        typed = []
        while msvcrt.kbhit():
            typed.append(msvcrt.getwch())
        return "".join(typed)

    def catch_stray_typing(self) -> bool:
        stray = " ".join(self.typed_here().split())
        if stray:
            self.say(f"  That went into this window, not the bar: '{stray}'. Click the bar (or press Ctrl+Alt+{self.cfg.bar_key}) "
                     "and type it there.")
        return bool(stray)

    def type_in_the_bar(self, *orders: str) -> None:
        for order in orders:
            self.say(f"  In the bar, type:  {order}   (click the bar first if its box hasn't got the cursor)")

    def order(self, text: str, action: str, wait_for_the_end: bool = True) -> int | None:
        """Ask you to type one order in the bar, and wait until it reaches Guardian as `action`, however long you take.

        The row it was decided at, or None if nothing came within ORDER_SECONDS. With wait_for_the_end, also until it ended.
        """
        before = self.newest()
        self.type_in_the_bar(text)
        started = reminded = time.monotonic()
        while time.monotonic() - started < ORDER_SECONDS:
            decided = [row for row in self.rows(before, "check") if row["action"] == action]
            if decided:
                if wait_for_the_end:
                    self.wait_until(lambda: self.ended(before, action) is not None)
                return decided[0]["id"]
            if not self.catch_stray_typing() and time.monotonic() - reminded > REMIND_SECONDS:
                self.say(f"  Still waiting for '{text}' to reach Guardian. Type it in the bar and press Enter.")
                reminded = time.monotonic()
            time.sleep(0.2)
        self.say(f"  Nothing reached Guardian for '{text}' in {ORDER_SECONDS // 60} minutes.")
        return None

    def press_stop(self) -> None:
        self.say("  >>> Press the red Stop button in the bar now.")

    def press_the_key(self, what: str) -> None:
        self.say(f"  >>> {what}")

    def leave_safe_mode(self) -> None:
        self.say('  Kairu is in Safe Mode now, as after any stop. Type "yes" and your PIN to leave it:')
        subprocess.run([sys.executable, "-m", "kairu", "resume"], cwd=ROOT, timeout=600)

    # --- reading what happened ------------------------------------------------------------------------------

    def rows(self, after: int = 0, kind: str | None = None) -> list[dict]:
        from kairu import audit
        from kairu.store import Store
        return [row for row in audit.tail(Store(self.cfg.data_dir), 500, kind=kind) if row["id"] > after]

    def newest(self) -> int:
        rows = self.rows()
        return rows[-1]["id"] if rows else 0

    def started(self, after: int, *actions: str) -> list[str]:
        return [row["action"] for row in self.rows(after, "run") if row["decision"] == "started" and row["action"] in actions]

    def finished(self, after: int, action: str) -> bool:
        return self.ended(after, action) == "finished"

    def ended(self, after: int, action: str) -> str | None:
        """How the newest run of this action since `after` ended: finished, refused, failed or halted; None while it runs."""
        ends = [row["decision"] for row in self.rows(after, "run") if row["action"] == action and row["decision"] != "started"]
        return ends[-1] if ends else None

    def wait_until(self, what, seconds: float = WAIT_SECONDS) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if what():
                return True
            time.sleep(0.2)
        return False

    def window_of(self, app: str):
        return next((window for window in self.pc.windows() if window.app == app), None)

    def bar_window(self) -> bool:
        """Whether the bar's window is showing now, by its title."""
        if sys.platform != "win32":
            return False
        user32 = ctypes.WinDLL("user32")
        user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
        handle = user32.FindWindowW(None, "Kairu bar")
        return bool(handle) and bool(user32.IsWindowVisible(handle))

    def window_rect(self, window) -> tuple[int, int, int, int]:
        from ctypes import wintypes
        rect = wintypes.RECT()
        user32 = ctypes.WinDLL("user32")
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetWindowRect(window.handle, ctypes.byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom

    def screen_width(self) -> int:
        return ctypes.WinDLL("user32").GetSystemMetrics(0)

    def mark(self, step: int, ok: bool, why: str) -> None:
        self.results[step] = (ok, why)
        self.say(f"  Step {step}: {'PASS' if ok else 'FAIL'}  {why}")
        self.say()

    # --- before anything -----------------------------------------------------------------------------------

    def list_skills(self) -> bool:
        from kairu import policy
        from kairu.tasks import skills
        rules = policy.load(self.cfg.policy_path).rules
        usable, refused = skills.check(skills.SKILLS, rules)
        self.say("Every skill Kairu has, with its tier:")
        for skill in usable:
            self.say(f"  {rules[skill.action].tier:<7} {skill.action}")
        for why in refused:
            self.say(f"  REFUSED {why}")
        critical = [skill.action for skill in skills.SKILLS if skill.action in rules and rules[skill.action].tier == "Critical"]
        self.say(f"  {'No Critical skill exists.' if not critical else 'A CRITICAL SKILL EXISTS: ' + ', '.join(critical)}")
        self.say()
        return not critical and not refused

    def ready(self) -> bool:
        from kairu import channel
        problems = []
        try:
            state = self.client.status()
            if state["mode"] != "normal":
                problems.append(f"Guardian is in Safe Mode ({state.get('safe_reason')}): run `kairu resume`")
            if not state.get("pin_set"):
                problems.append("no PIN is set: run `kairu pin set`")
            if state["policy"].get("actions", 0) and self.client.check("apps.list_open").verdict != "allow":
                problems.append("Guardian does not know the skills yet: restart it on this code (`kairu guardian quit`, `kairu guardian run`)")
        except channel.ChannelError as error:
            problems.append(f"Guardian does not answer ({error}): run `kairu guardian run`")
        for problem in problems:
            self.say(f"  NOT READY: {problem}")
        return not problems

    # --- the steps ---------------------------------------------------------------------------------------

    def step_1(self) -> None:  # pressing keys needs no order, so this step waits for windows, not for Guardian
        name = f"Ctrl+Alt+{self.cfg.bar_key}"
        self.say(f"Step 1: {name} opens and hides the bar over any app. Click into another app first, such as your browser.")
        if self.bar_window():
            self.press_the_key(f"Press {name} to hide the bar first.")
            if not self.wait_until(lambda: not self.bar_window(), 30):
                self.mark(1, False, f"{name} did not hide it. Does the bar say the key is taken? BAR.md says what to do")
                return
        self.press_the_key(f"Press {name}: the bar should open at the top centre.")
        if not self.wait_until(self.bar_window, 30):
            self.mark(1, False, f"the bar did not open. Is it running (`kairu bar`)? If another program holds {name}, set tasks.bar_key (BAR.md)")
            return
        self.press_the_key(f"Press {name} again: it should hide.")
        if not self.wait_until(lambda: not self.bar_window(), 30):
            self.mark(1, False, "it did not hide")
            return
        self.press_the_key(f"Press {name} once more, to open it for the next steps.")
        self.wait_until(self.bar_window, 30)
        self.mark(1, self.yes("Did it open over the app in front, with the cursor ready in its box?"), f"{name} opened and hid it")

    def step_2(self) -> None:
        self.say("Step 2: opening apps (one order at a time: this tool waits for each)")
        before = self.newest()
        chrome_order = self.order("open Chrome", "apps.open")
        chrome = chrome_order is not None and self.wait_until(lambda: self.window_of("chrome"))
        notepad_order = self.order("open Notepad", "apps.open")
        notepad = notepad_order is not None and self.wait_until(lambda: self.window_of("notepad"))
        ran = self.started(before, "apps.open")
        if chrome and notepad and len(ran) == 2:
            self.mark(2, True, "both windows are open, and each order went through Guardian as apps.open")
        else:
            self.mark(2, False, f"Chrome: order reached Guardian {chrome_order is not None}, window {bool(chrome)}; "
                                f"Notepad: order reached Guardian {notepad_order is not None}, window {bool(notepad)}; apps.open runs: {len(ran)}")

    def step_3(self) -> None:
        self.say("Step 3: closing and arranging")
        before = self.newest()
        self.order("close Notepad", "apps.close")
        closed = self.wait_until(lambda: self.window_of("notepad") is None)
        if not closed:
            self.mark(3, False, "Notepad is still open (did it ask you to save?)")
            return
        self.order("put Chrome on the left half", "apps.arrange")
        half = self.screen_width() // 2

        def on_the_left() -> bool:
            window = self.window_of("chrome")
            if window is None:
                return False
            left, _, right, _ = self.window_rect(window)
            return left <= 20 and abs((right - left) - half) < 80

        placed = self.wait_until(on_the_left)
        ran = self.started(before, "apps.close", "apps.arrange")
        self.mark(3, placed and ran == ["apps.close", "apps.arrange"], f"Notepad closed; Chrome on the left half: {placed}; through Guardian: {ran}")

    def step_4(self) -> None:
        self.say("Step 4: sound, the screen, and how much RAM is free")
        self.volume_before, self.brightness_before = self.pc.volume()[0], self.pc.brightness()
        before = self.newest()
        heard = self.order("volume 30", "system.volume") is not None
        volume = heard and self.wait_until(lambda: self.pc.volume()[0] == 30)
        volume_now = self.pc.volume()[0]
        lit = self.order("brightness 50", "system.brightness") is not None
        brightness = lit and self.wait_until(lambda: self.pc.brightness() == 50)
        brightness_now = self.pc.brightness()
        status = self.order("how much RAM is free?", "system.status") is not None and self.finished(before, "system.status")
        said = status and self.yes("Did the bar show the free RAM in one short line?")
        self.mark(4, bool(volume and brightness and said), f"volume 30: {volume} (read {volume_now}); brightness 50: {brightness} "
                                                           f"(read {brightness_now}); RAM line: {bool(said)}")

    def step_5(self) -> None:
        self.say("Step 5: two orders in one line")
        before = self.newest()
        self.order("open Notepad and set volume to 20", "system.volume")
        both = self.wait_until(lambda: self.pc.volume()[0] == 20 and self.window_of("notepad"))
        ran = self.started(before, "apps.open", "system.volume")
        self.mark(5, bool(both) and ran == ["apps.open", "system.volume"], f"both done: {bool(both)}; in this order: {ran}")
        window = self.window_of("notepad")
        if window:
            self.pc.close(window)

    def step_6(self) -> None:
        self.say("Step 6: restart asks first. REFUSE IT: press Refuse on the card. Do not type your PIN.")
        before = self.newest()
        self.order("restart", "system.restart", wait_for_the_end=False)
        asked = self.wait_until(lambda: any(row["action"] == "system.restart" and row["decision"] == "needs_approval" for row in self.rows(before, "check")))
        refused = self.wait_until(lambda: any(row["action"] == "system.restart" and row["decision"] == "refused" for row in self.rows(before, "approval")))
        ran = self.started(before, "system.restart")
        seen = asked and refused and self.yes("Did the card show the action, its tier and the two boxes?")
        self.mark(6, bool(seen) and not ran, f"asked: {asked}; refused: {refused}; ran: {bool(ran)}. Nothing restarted")

    def step_7(self) -> None:
        self.say("Step 7: rename, undo, and a rename outside")
        folder = Path(self.cfg.work_folder)
        folder.mkdir(parents=True, exist_ok=True)
        name = f"gate-{uuid.uuid4().hex[:6]}"
        (folder / f"{name}.txt").write_text("a test file from the gate", encoding="utf-8")
        self.say(f"  This tool made {folder / (name + '.txt')}.")
        self.order(f"rename {name}.txt to {name}-new.txt", "files.rename")
        renamed = self.wait_until(lambda: (folder / f"{name}-new.txt").exists() and not (folder / f"{name}.txt").exists())
        self.order("undo", "task.undo")
        undone = self.wait_until(lambda: (folder / f"{name}.txt").exists() and not (folder / f"{name}-new.txt").exists())
        outside = folder.parent / f"{name}-outside.txt"
        outside.write_text("a test file from the gate, outside your work folder", encoding="utf-8")
        before = self.newest()
        self.order(f"rename {outside} to {name}-stolen.txt", "files.rename")
        ending = self.ended(before, "files.rename")
        kept = outside.exists() and not (folder / f"{name}-stolen.txt").exists()
        (folder / f"{name}.txt").unlink(missing_ok=True)
        outside.unlink(missing_ok=True)
        refused = ending == "refused"
        self.mark(7, bool(renamed and undone and refused and kept),
                  f"renamed: {renamed}; undone: {undone}; the rename outside ended as: {ending}; the file outside untouched: {kept}")

    def step_8(self) -> None:
        self.say("Step 8: Stop in the bar during kairu demo")
        before = self.newest()
        demo = subprocess.Popen([sys.executable, "-m", "kairu", "demo", "--seconds", "90"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not self.wait_until(lambda: self.started(before, "demo.count"), 30):
                self.mark(8, False, "kairu demo did not start")
                return
            time.sleep(1)
            self.press_stop()
            halted = []

            def stopped() -> bool:
                halted[:] = [row for row in self.rows(before, "run") if row["action"] == "demo.count" and row["decision"] == "halted"]
                return bool(halted)

            if not self.wait_until(stopped, 60):
                self.mark(8, False, "no stop came within 60 seconds")
                return
            took = halted[0]["details"].get("seconds_since_stop")
            ok = isinstance(took, (int, float)) and took < LIMIT
            self.mark(8, ok, f"kairu demo halted {took} s after the stop; the limit is {LIMIT:g}")
        finally:
            demo.terminate()
            demo.wait(10)
        self.leave_safe_mode()

    def put_back(self) -> None:
        """Your volume and brightness as they were, through nothing but the same calls the skills use."""
        if self.volume_before is not None:
            self.pc.set_volume(level=self.volume_before)
            self.pc.set_brightness(self.brightness_before)
            self.say(f"  Your volume ({self.volume_before}) and brightness ({self.brightness_before}) are back.")

    def run(self, only: int | None = None) -> int:
        self.say("Kairu Sprint Day 1 gate test (the Kairu bar)")
        fine = self.list_skills()
        if not self.ready():
            self.say("\n  Result: NOT RUN  fix what is listed above, then run this again.")
            return 1
        try:
            for step in [only] if only else range(1, 9):
                getattr(self, f"step_{step}")()
        finally:
            self.put_back()
        self.say("The gate test:")
        for step in sorted(self.results):
            ok, why = self.results[step]
            self.say(f"  {step}  {'PASS' if ok else 'FAIL'}  {why}")
        passed = sum(ok for ok, _ in self.results.values())
        complete = len(self.results) == 8
        verdict = "PASSED" if complete and passed == 8 and fine else "PART PASSED" if passed == len(self.results) and fine else "FAILED"
        self.say(f"\n  Result: {verdict}  {passed} of {len(self.results)} steps run pass{'' if complete else ' (the gate needs all 8)'}")
        if complete:
            self.say("  Please send me this output and `kairu audit show -n 80`.")
        return 0 if passed == len(self.results) and fine else 1


def main() -> int:
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve() and sys.prefix == sys.base_prefix:
        return subprocess.call([str(VENV_PYTHON), __file__, *sys.argv[1:]])
    parser = argparse.ArgumentParser(description="The Sprint Day 1 gate test: the Kairu bar, by hand, on your own PC.")
    parser.add_argument("--step", type=int, choices=range(1, 9), help="only this step")
    return Gate().run(parser.parse_args().step)


if __name__ == "__main__":
    sys.exit(main())
