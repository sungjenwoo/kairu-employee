"""The Sprint Day 4 gate test (files, Kairu's own browser, free-form orders): you TYPE in the bar; this tool checks each step.

On Windows, in your Guardian folder, with Guardian restarted on this code and the bar running (`kairu bar`), charger in:
    .venv-guardian\\Scripts\\python tools\\sprint_day4_gate.py              all 11 steps (about 15 minutes)
    .venv-guardian\\Scripts\\python tools\\sprint_day4_gate.py --step 9     only that step

     1  "find ..." finds a file in Kairu-files by its name
     2  "move ... to ..." moves it; "undo" puts it back
     3  "delete ..." asks for "yes" and your PIN, puts it in the Recycle Bin; "undo" brings it back from the Bin
     4  "delete the folder ..." asks for "yes" and your PIN too
     5  a delete naming a path outside your work folder is refused at once: no card, no PIN, Guardian never asked
     6  "open github.com" opens it in Kairu's own browser profile
     7  a public search ("google the weather in Hyderabad") opens Google at once
     8  a personal-looking search asks first (refuse it: nothing is searched)
     9  one free-form order becomes a plan you see before it runs (needs a free AI provider: `kairu provider add groq`)
    10  Ctrl+Alt+K during a plan stops it in under 1 second; the rest never runs
    11  "what's open?" still works
    then the audit log: its chain is whole, and no file name or search word of the gate is in it

Voice steps come after PR #16 merges (marked below); phone steps belong to the phone app. You type your own orders, "yes" and
PIN: this tool never sees your PIN and types nothing into the bar. It makes its own test files (names start with "gate-") and
takes them away at the end; it never touches your other files. If the bar's reply line shows an error, note it for me.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("sprint_day1_gate", ROOT / "tools" / "sprint_day1_gate.py")
day1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(day1)

VENV_PYTHON = day1.VENV_PYTHON
LIMIT = 1.0
STEPS = 11
NEW_SKILLS = ("files.find", "files.move", "files.delete", "web.open", "web.search", "web.search_private", "task.wait", "brain.plan")
RESTART = ("  If Guardian doesn't know the new skills yet, restart it on this code, in your Guardian folder:\n"
           "      .venv-guardian\\Scripts\\python -m kairu guardian quit\n"
           "      .venv-guardian\\Scripts\\python -m kairu guardian run\n"
           "  then `kairu bar quit` and `kairu bar`, so the bar has the new code too.")


class Gate(day1.Gate):
    def __init__(self):
        super().__init__()
        self.tag = f"gate-{uuid.uuid4().hex[:6]}"
        self.folder = Path(self.cfg.work_folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.made: list[Path] = []  # the gate's own test files, taken away at the end

    # --- the gate's own files --------------------------------------------------------------------------

    def make(self, name: str, text: str = "a test file from the Day 4 gate") -> Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.made.append(path)
        return path

    def tidy_up(self) -> None:
        """Only what this gate made: files it wrote, and folders named with its tag once they are empty. Never a file of
        yours: if a plan moved one of your files into a gate folder, the folder stays, and the gate says where it is."""
        ours = set(self.made) | {path for path in self.folder.rglob(f"{self.tag}*") if path.is_file()}
        for path in ours:
            try:
                if path.is_file() and (path in self.made or path.name.startswith(self.tag)):
                    path.unlink()
            except OSError:
                pass
        folders = sorted((path for path in self.folder.rglob(f"{self.tag}*") if path.is_dir()), key=lambda p: len(str(p)), reverse=True)
        for place in folders:
            for inner in sorted((p for p in place.rglob("*") if p.is_dir()), key=lambda p: len(str(p)), reverse=True):
                try:
                    inner.rmdir()  # only an empty folder goes
                except OSError:
                    pass
            try:
                place.rmdir()
            except OSError:
                self.say(f"  Left {place}: it holds files that aren't the gate's.")

    def in_the_bin(self, path: Path, since: float) -> bool:
        from kairu.tasks import recycle
        bin_ = recycle.backend()
        if isinstance(bin_, recycle.WindowsBin):
            return bin_.find(path, since - 5) is not None
        if isinstance(bin_, recycle.FakeBin):
            wanted = os.path.normcase(os.path.realpath(path))
            return any(os.path.normcase(json.loads(note.read_text(encoding="utf-8"))["path"]) == wanted
                       for note in bin_.folder.glob("*/from.json"))
        return False

    def ended_as(self, before: int, action: str) -> str | None:
        self.wait_until(lambda: self.ended(before, action) is not None)
        return self.ended(before, action)

    # --- before anything ------------------------------------------------------------------------------

    def ready(self) -> bool:
        fine = super().ready()
        if fine:
            unknown = [name for name in NEW_SKILLS if self.client.check(name).verdict == "deny"
                       and "not in the policy" in (self.client.check(name).reason or "").lower()]
            if unknown:
                self.say(f"  NOT READY: Guardian does not know {', '.join(unknown)} yet.")
                self.say(RESTART)
                return False
        return fine

    # --- the steps ---------------------------------------------------------------------------------------

    def step_1(self) -> None:
        self.say("Step 1: find a file by its name")
        self.make(f"{self.tag}-report.txt")
        before = self.newest()
        self.order(f"find {self.tag}", "files.find")
        ending = self.ended_as(before, "files.find")
        seen = ending == "finished" and self.yes(f"Did the bar say it found {self.tag}-report.txt?")
        self.mark(1, bool(seen), f"files.find ended as: {ending}; the bar named the file: {bool(seen)}")

    def step_2(self) -> None:
        self.say("Step 2: move a file into a folder, then undo")
        name, place = f"{self.tag}-move.txt", f"{self.tag}-folder"
        self.make(name)
        self.order(f"move {name} to {place}", "files.move")
        moved = self.wait_until(lambda: (self.folder / place / name).exists() and not (self.folder / name).exists())
        self.order("undo", "task.undo")
        undone = self.wait_until(lambda: (self.folder / name).exists() and not (self.folder / place).exists())
        self.mark(2, bool(moved and undone), f"moved into {place} (made for it): {moved}; undo put it back and took the folder away: {undone}")

    def step_3(self) -> None:
        self.say('Step 3: delete a file. On the card, type "yes" and your PIN, then Go on.')
        path = self.make(f"{self.tag}-delete.txt", "bring me back")
        before, started = self.newest(), time.time()
        self.order(f"delete {path.name}", "files.delete", wait_for_the_end=False)
        asked = self.wait_until(lambda: any(row["action"] == "files.delete" and row["decision"] == "needs_approval"
                                            for row in self.rows(before, "check")))
        gone = self.wait_until(lambda: not path.exists() and self.ended(before, "files.delete") == "finished")
        binned = gone and self.in_the_bin(path, started)
        self.say("  Now undo it: it comes back from the Recycle Bin.")
        self.order("undo", "task.undo")
        back = self.wait_until(lambda: path.exists() and path.read_text(encoding="utf-8") == "bring me back")
        self.mark(3, bool(asked and gone and binned and back),
                  f"asked for yes and PIN: {asked}; deleted: {gone}; in the Recycle Bin: {binned}; undo brought it back: {back}")

    def step_4(self) -> None:
        self.say('Step 4: delete a folder. On the card, type "yes" and your PIN, then Go on.')
        place = self.folder / f"{self.tag}-dir"
        self.make(f"{place.name}/inside.txt")
        before, started = self.newest(), time.time()
        self.order(f"delete the folder {place.name}", "files.delete", wait_for_the_end=False)
        asked = self.wait_until(lambda: any(row["action"] == "files.delete" and row["decision"] == "needs_approval"
                                            for row in self.rows(before, "check")))
        gone = self.wait_until(lambda: not place.exists() and self.ended(before, "files.delete") == "finished")
        binned = gone and self.in_the_bin(place, started)
        self.say("  Now undo it, so the gate can take its folder away again.")
        self.order("undo", "task.undo")
        back = self.wait_until(lambda: (place / "inside.txt").exists())
        self.mark(4, bool(asked and gone and binned),
                  f"asked for yes and PIN: {asked}; the folder went to the Recycle Bin: {bool(gone and binned)}; undo: {back}")

    def step_5(self) -> None:
        self.say("Step 5: a delete naming a path outside your work folder is refused at once, before Guardian is asked")
        outside = self.folder.parent / f"{self.tag}-outside.txt"
        outside.write_text("a test file from the Day 4 gate, outside your work folder", encoding="utf-8")
        self.made.append(outside)
        before = self.newest()
        self.type_in_the_bar(f"delete ..\\{outside.name}")
        said = self.yes("Did the bar say \"Refused: ... outside your work folder\" at once, with no card asking for your PIN?")
        asked = [row for row in self.rows(before) if row["action"] == "files.delete"]
        kept = outside.exists()
        outside.unlink(missing_ok=True)
        self.mark(5, bool(said) and not asked and kept, f"refused in the bar: {bool(said)}; Guardian asked: {bool(asked)} (it should "
                                                        f"not be); the file outside untouched: {kept}")

    def step_6(self) -> None:
        self.say("Step 6: open a web address in Kairu's own browser")
        before = self.newest()
        self.order("open github.com", "web.open")
        ending = self.ended_as(before, "web.open")
        profile = Path(self.cfg.data_dir) / "browser-profile"
        made = self.wait_until(lambda: profile.is_dir(), 20)
        seen = ending == "finished" and self.yes("Did GitHub open in a browser window that has none of your own bookmarks or sign-ins?")
        self.mark(6, bool(seen and made), f"web.open ended as: {ending}; Kairu's profile folder is {profile}: {made}; "
                                          f"a separate window: {bool(seen)}")

    def step_7(self) -> None:
        self.say("Step 7: a public search")
        before = self.newest()
        self.order("google the weather in Hyderabad", "web.search")
        ending = self.ended_as(before, "web.search")
        asked = [row for row in self.rows(before, "check") if row["decision"] == "needs_approval"]
        seen = ending == "finished" and self.yes("Did Google's results for the weather in Hyderabad open in Kairu's browser?")
        self.mark(7, bool(seen) and not asked, f"web.search ended as: {ending}; asked first: {bool(asked)} (it should not); seen: {bool(seen)}")

    def step_8(self) -> None:
        self.say("Step 8: a personal-looking search asks first. REFUSE IT: press Refuse on the card. Do not type your PIN.")
        before = self.newest()
        self.order("google Ravi 9876543210 home address", "web.search_private", wait_for_the_end=False)
        asked = self.wait_until(lambda: any(row["action"] == "web.search_private" and row["decision"] == "needs_approval"
                                            for row in self.rows(before, "check")))
        refused = self.wait_until(lambda: any(row["action"] == "web.search_private" and row["decision"] == "refused"
                                              for row in self.rows(before, "approval")))
        searched = self.started(before, "web.search", "web.search_private")
        self.mark(8, bool(asked and refused) and not searched, f"asked: {asked}; you refused: {refused}; searched: {bool(searched)}")

    def step_9(self) -> None:
        self.say('Step 9: a free-form order. The bar shows the plan first; type "yes" on the card to run it.')
        others = [p.name for p in self.folder.glob("*.pdf") if not p.name.startswith(self.tag)]
        if others:
            self.say(f"  Note: Kairu-files already has other PDFs ({', '.join(others[:3])}); the plan may move them too, and "
                     "the gate leaves those where the plan puts them.")
        for letter in "ab":
            self.make(f"{self.tag}-{letter}.pdf")
        place = f"{self.tag}-pdfs"
        before = self.newest()
        self.order(f"put all the pdfs in Kairu-files into a folder called {place}", "files.find", wait_for_the_end=False)
        planned = self.ended(before, "brain.plan")  # the plan was made before its steps were checked
        moved = planned == "finished" and self.wait_until(
            lambda: all((self.folder / place / f"{self.tag}-{letter}.pdf").exists() for letter in "ab"))
        ran = self.started(before, "brain.plan", "task.plan", "files.find", "files.move")
        kept = self.finished(before, "task.plan") and ran.index("task.plan") < ran.index("files.find") if "files.find" in ran else False
        shown = bool(moved) and self.yes("Did the bar show the plan, and wait for your yes, before anything moved?")
        self.mark(9, bool(moved and shown and kept), f"brain.plan ended as: {planned}; through Guardian: {ran}; the plan kept in the "
                                                     f"audit log before its steps: {bool(kept)}; both PDFs in {place}: {bool(moved)}; "
                                                     f"plan shown first: {bool(shown)}")

    def step_10(self) -> None:
        self.say("Step 10: Ctrl+Alt+K during a plan")
        self.volume_before = self.volume_before if self.volume_before is not None else self.pc.volume()[0]
        self.brightness_before = self.brightness_before if self.brightness_before is not None else self.pc.brightness()
        before = self.newest()
        self.order("wait 20 seconds then volume 20", "task.wait", wait_for_the_end=False)
        if not self.wait_until(lambda: self.started(before, "task.wait"), 60):
            self.mark(10, False, "the wait never started")
            return
        time.sleep(1)
        self.press_the_key("Press Ctrl+Alt+K now.")
        halted = []

        def stopped() -> bool:
            halted[:] = [row for row in self.rows(before, "run") if row["action"] == "task.wait" and row["decision"] == "halted"]
            return bool(halted)

        if not self.wait_until(stopped, 60):
            self.mark(10, False, "no stop came within 60 seconds")
            return
        time.sleep(1.5)  # time for a volume step to start, if the stop had not ended the plan
        took = halted[0]["details"].get("seconds_since_stop")
        rest = self.started(before, "system.volume")
        ok = isinstance(took, (int, float)) and took < LIMIT and not rest
        self.mark(10, ok, f"the wait halted {took} s after the stop (limit {LIMIT:g}); the volume step ran: {bool(rest)}")
        self.leave_safe_mode()

    def step_11(self) -> None:
        self.say("Step 11: \"what's open?\" still works")
        before = self.newest()
        self.order("what's open?", "apps.list_open")
        ending = self.ended_as(before, "apps.list_open")
        seen = ending == "finished" and self.yes("Did the bar list your open apps in one short line?")
        self.mark(11, bool(seen), f"apps.list_open ended as: {ending}; listed: {bool(seen)}")

    # --- VOICE STEPS: placeholder, added after PR #16 (voice-lite) merges -----------------------------------
    # The owner adds them here: the same orders said aloud ("Kairu, find ...", "Kairu, open github", "Kairu, stop" during a
    # plan). Phone steps are not here: they belong to the phone app's own gate.
    VOICE_STEPS: tuple = ()

    # --- the audit log -------------------------------------------------------------------------------------

    def audit_check(self) -> tuple[bool, str]:
        from kairu import audit
        from kairu.store import Store
        store = Store(self.cfg.data_dir)
        whole = audit.verify(store).ok
        with store.connect() as db:
            text = " ".join(str(row) for row in db.execute("SELECT * FROM audit"))
        leaked = [word for word in (self.tag, "Hyderabad", "9876543210", "github.com") if word in text]
        return whole and not leaked, f"chain whole: {whole}; gate words found in the log: {leaked or 'none'}"

    def run(self, only: int | None = None) -> int:
        self.say("Kairu Sprint Day 4 gate test (files, Kairu's own browser, free-form orders)")
        self.say(RESTART)
        self.say()
        fine = self.list_skills()
        if not self.ready():
            self.say("\n  Result: NOT RUN  fix what is listed above, then run this again.")
            return 1
        try:
            for number in [only] if only else range(1, STEPS + 1):
                getattr(self, f"step_{number}")()
        finally:
            self.put_back()
            self.tidy_up()
        audited, why = self.audit_check()
        self.say("The gate test:")
        for number in sorted(self.results):
            ok, said = self.results[number]
            self.say(f"  {number:>2}  {'PASS' if ok else 'FAIL'}  {said}")
        self.say(f"  log {'PASS' if audited else 'FAIL'}  {why}")
        self.say("  voice  NOT YET  the voice steps are added after PR #16 merges")
        passed = sum(ok for ok, _ in self.results.values())
        complete = len(self.results) == STEPS
        all_pass = passed == len(self.results) and fine and audited
        verdict = "PASSED" if complete and all_pass else "PART PASSED" if all_pass else "FAILED"
        self.say(f"\n  Result: {verdict}  {passed} of {len(self.results)} steps run pass{'' if complete else f' (the gate needs all {STEPS})'}")
        if complete:
            self.say("  Please send me this output and `kairu audit show -n 120`.")
        return 0 if all_pass else 1


def main() -> int:
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve() and sys.prefix == sys.base_prefix:
        return subprocess.call([str(VENV_PYTHON), __file__, *sys.argv[1:]])
    parser = argparse.ArgumentParser(description="The Sprint Day 4 gate test: files, Kairu's browser and plans, typed in the bar.")
    parser.add_argument("--step", type=int, choices=range(1, STEPS + 1), help="only this step")
    return Gate().run(parser.parse_args().step)


if __name__ == "__main__":
    sys.exit(main())
