"""The Kairu bar's window (Sprint Day 1). Skipped where there is no screen. The core and Guardian are stand-ins here,
except for Stop, which writes the real stop; tests_kairu/test_tasks_program.py runs the core through the real Guardian.
"""

import re
import subprocess
import sys
import threading
import time

import pytest

from kairu import channel, safemode
from kairu.config import ROOT
from kairu.guardian import Approval, Decision, Refused, Verdict, Action
from kairu.policy import Tier
from kairu.store import Store
from kairu.tasks.core import NOT_RUNNING
from tests_kairu.helpers import wait_for
from tests_kairu.program import family_memory_mib, program  # noqa: F401 (a fixture)

SOURCE = (ROOT / "kairu" / "bar" / "app.py").read_text(encoding="utf-8")


class StandInGuardian:
    def __init__(self):
        self.mode, self.down, self.approved = "normal", False, []

    def status(self):
        if self.down:
            raise channel.NotRunning("not running")
        return {"mode": self.mode, "safe_reason": "a test"}

    def approve(self, request_id, confirmation, pin):
        self.approved.append((request_id, confirmation, pin))
        if confirmation.strip().lower() != "yes":
            raise Refused('not approved: you did not type "yes"')
        if pin != "482916":
            raise Refused("wrong PIN")
        return Approval("token", "system.restart", time.time() + 60)


class StandInCore:
    def __init__(self):
        self.orders, self.reply = [], "Done."

    def handle(self, order):
        self.orders.append(order)
        return self.reply


def make_bar(config, **options):
    """The bar, or a skip where there is no screen. Tcl sometimes can't read its own files for a moment, so it tries again."""
    tkinter = pytest.importorskip("tkinter")
    from kairu.bar.app import WINDOW_TRIES, Bar
    for tries_left in range(WINDOW_TRIES - 1, -1, -1):
        try:
            return Bar(config, client=StandInGuardian(), **options)
        except tkinter.TclError as error:
            if not tries_left:
                pytest.skip(f"no screen here ({error})")
            time.sleep(0.5)


@pytest.fixture
def bar(config):
    tkinter = pytest.importorskip("tkinter")
    made = make_bar(config, core=StandInCore())
    yield made
    made.close()


def pump(bar, until, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not until():
        bar.root.update()
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)
    bar.root.update()


def type_in(box, text):
    """What your fingers do; in the tests only. The bar's own code never writes into the two approval boxes."""
    box.insert(0, text)


def test_it_is_borderless_always_on_top_at_the_bottom_centre_where_the_pill_is_and_starts_hidden(bar):
    """The Ember Glow look (owner's GO, 15 Nov 2026): no strip at the top of the screen; a dark rounded bar, 560 wide,
    at the bottom centre, 46 above the taskbar, where the pill is."""
    from kairu.bar.app import FROM_BOTTOM
    root = bar.root
    assert root.overrideredirect() and root.attributes("-topmost") and root.state() == "withdrawn" and not bar.visible
    bar.show()
    root.update()
    left, top, right, bottom = bar._work_area(root)
    assert root.state() == "normal" and bar.visible and root.winfo_width() == 560 and 60 <= root.winfo_height() <= 72
    assert abs(root.winfo_x() - (left + right - 560) // 2) <= 1
    assert abs(root.winfo_y() + root.winfo_height() - (bottom - FROM_BOTTOM)) <= 1
    assert not bar.reply_line.winfo_ismapped()  # no empty line above the one you type in
    bar.say("Done.")
    root.update()
    assert bar.reply_line.winfo_ismapped() and abs(root.winfo_y() + root.winfo_height() - (bottom - FROM_BOTTOM)) <= 1  # grew upwards


def test_saying_kairu_does_not_pop_the_bar_up_and_a_problem_shows_on_the_pill(bar):
    noted = []
    bar.pill.note = noted.append
    bar._show_quietly()
    bar.root.update()
    assert not bar.visible and bar.root.state() == "withdrawn"
    bar.say("The mic can't be used: Guardian refused voice.listen.")
    assert noted == ["The mic can't be used: Guardian refused voice.listen."] and not bar.visible
    bar.show()
    bar.say("Done.")
    assert len(noted) == 1  # with the bar open, its own line shows it


def test_it_has_a_text_box_a_reply_line_a_red_stop_and_a_hide_button(bar):
    assert bar.stop_button.cget("text") == "Stop" and bar.stop_button.cget("bg") == "#d9363e"
    assert bar.hide_button.cget("command")
    bar.show()
    bar.hide_button.invoke()
    assert bar.root.state() == "withdrawn"


def test_the_show_hide_key_toggles_it_from_its_own_thread(bar):
    bar.start_thread(bar.toggle_from_any_thread)
    pump(bar, lambda: bar.visible)
    bar.start_thread(bar.toggle_from_any_thread)
    pump(bar, lambda: not bar.visible)


def test_enter_sends_the_order_to_the_core_and_the_reply_is_one_short_line(bar):
    bar.show()
    type_in(bar.order_box, "open Notepad")
    bar.send()
    pump(bar, lambda: not bar.busy)
    assert bar.core.orders == ["open Notepad"] and bar.reply_line.cget("text") == "Done." and bar.order_box.get() == ""


def test_an_empty_order_sends_nothing_and_one_order_at_a_time(bar):
    bar.send()
    assert bar.core.orders == []
    hold, go = threading.Event(), threading.Event()

    def slow(order):
        hold.set()
        go.wait(5)
        return "Done."

    bar.core.handle = slow
    type_in(bar.order_box, "one")
    bar.send()
    hold.wait(5)
    type_in(bar.order_box, "two")
    bar.send()
    assert bar.reply_line.cget("text") == "Still on the last one." and bar.order_box.get() == "two"
    go.set()
    pump(bar, lambda: not bar.busy)


def test_a_crash_in_the_core_does_not_end_the_bar(bar):
    def broken(order):
        raise RuntimeError("something inside")

    bar.core.handle = broken
    type_in(bar.order_box, "x")
    bar.send()
    pump(bar, lambda: not bar.busy)
    assert "went wrong" in bar.reply_line.cget("text") and "something inside" not in bar.reply_line.cget("text")


def test_it_says_safe_mode_and_that_guardian_is_not_running_when_it_opens(bar):
    bar.client.mode = "safe"
    bar.show()
    pump(bar, lambda: "Safe Mode" in bar.reply_line.cget("text"))
    bar.hide()
    bar.client.down = True
    bar.show()
    pump(bar, lambda: bar.reply_line.cget("text") == NOT_RUNNING)


def test_the_real_core_is_used_when_none_is_given(config):
    from kairu.tasks.core import TaskCore
    made = make_bar(config)
    try:
        assert isinstance(made.core, TaskCore) and made.core.approver == made.ask_approval and made.core.confirmer == made.ask_confirmation
    finally:
        made.close()


# --- Stop -------------------------------------------------------------------------------------------------

def test_stop_is_what_kairu_stop_does(bar, config):
    store = Store(config.data_dir)
    before = safemode.stop_count(store)
    bar.stop_button.invoke()
    assert safemode.stop_count(store) == before + 1 and safemode.is_safe(store) and "Stopped" in bar.reply_line.cget("text")


def test_stop_works_with_the_core_busy(bar, config):
    go = threading.Event()
    bar.core.handle = lambda order: go.wait(5) and "Done."
    type_in(bar.order_box, "x")
    bar.send()
    bar.stop_button.invoke()
    assert safemode.is_safe(Store(config.data_dir))
    go.set()
    pump(bar, lambda: not bar.busy)


def test_the_bars_stop_halts_a_running_action_in_under_1_second(program, config):
    """The real Guardian program and kairu demo's action; the bar's own Stop button."""
    from kairu import audit
    from kairu.guardian import Action as RealAction
    made = make_bar(config, core=StandInCore())
    try:
        run = program.client.run(RealAction("demo.count", {"seconds": 30, "quiet": True}))
        time.sleep(0.5)
        made.stop_button.invoke()
        wait_for(lambda: program.client.run_status(run["run"])["outcome"] == "halted", timeout=5)

        def halted():
            return [row for row in audit.tail(Store(config.data_dir), 50, kind="run") if row["decision"] == "halted" and row["action"] == "demo.count"]

        wait_for(halted, timeout=5)
        took = halted()[0]["details"]["seconds_since_stop"]
        print(f"\n  Stop in the bar -> `kairu demo` inside Guardian halted in {took:.3f} s")
        assert took < 1.0
    finally:
        made.close()


# --- the approval card --------------------------------------------------------------------------------------

DECISION = Decision(Verdict.NEEDS_APPROVAL, Action("system.restart", {"job": "a" * 16, "note": "a detail"}), Tier.HIGH,
                    "High tier", "Restart this PC", "request-1")


def on_a_worker(bar, ask):
    box = {}

    def work():
        try:
            box["result"] = ask()
        except Refused as refusal:
            box["refused"] = str(refusal)
        box["done"] = True

    bar.start_thread(work)  # followed, so the bar waits for it before it closes
    pump(bar, lambda: bar._answer is not None)
    return box


def test_the_card_shows_the_action_its_details_and_its_tier_and_empty_boxes(bar):
    box = on_a_worker(bar, lambda: bar.ask_approval(DECISION))
    text = bar.card_text.cget("text")
    assert "system.restart" in text and "Restart this PC" in text and "note: a detail" in text and "High" in text and "job" not in text
    assert bar.yes_box.get() == "" and bar.pin_box.get() == "" and bar.pin_box.cget("show") and bar.card.winfo_ismapped()
    bar.root.update()
    assert bar.root.winfo_height() > 48
    bar.refuse_button.invoke()
    pump(bar, lambda: box.get("done"))


def test_yes_and_the_pin_go_to_guardian_and_the_boxes_are_emptied(bar):
    box = on_a_worker(bar, lambda: bar.ask_approval(DECISION))
    type_in(bar.yes_box, "yes")
    type_in(bar.pin_box, "482916")
    bar.approve_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["result"].token == "token" and bar.client.approved == [("request-1", "yes", "482916")]
    assert bar.yes_box.get() == "" and bar.pin_box.get() == "" and not bar.card.winfo_ismapped()


def test_refusing_tells_guardian_and_approves_nothing(bar):
    box = on_a_worker(bar, lambda: bar.ask_approval(DECISION))
    type_in(bar.yes_box, "yes")
    type_in(bar.pin_box, "482916")
    bar.refuse_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["result"] is None and bar.client.approved == [("request-1", "", "")]


def test_a_wrong_pin_is_refused_and_says_why(bar):
    box = on_a_worker(bar, lambda: bar.ask_approval(DECISION))
    type_in(bar.yes_box, "yes")
    type_in(bar.pin_box, "000000")
    bar.approve_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["refused"] == "wrong PIN"


def test_a_card_nobody_answers_ends_as_a_refusal(bar, monkeypatch):
    monkeypatch.setattr("kairu.bar.app.CARD_SECONDS", 0.5)  # long enough to see the card open
    box = on_a_worker(bar, lambda: bar.ask_approval(DECISION))
    pump(bar, lambda: box.get("done"))
    pump(bar, lambda: bar._answer is None)
    assert box["result"] is None and bar.client.approved == [("request-1", "", "")]


def test_the_warning_card_needs_yes_and_no_pin(bar):
    box = on_a_worker(bar, lambda: bar.ask_confirmation("Wi-Fi off drops your phone's link."))
    assert not bar.pin_box.winfo_ismapped() and "Wi-Fi" in bar.card_text.cget("text")
    type_in(bar.yes_box, "yes")
    bar.approve_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["result"] is True and bar.client.approved == []
    box = on_a_worker(bar, lambda: bar.ask_confirmation("Wi-Fi off drops your phone's link."))
    bar.approve_button.invoke()
    pump(bar, lambda: box.get("done"))
    assert box["result"] is False


def test_nothing_in_kairu_can_fill_or_press_the_card():
    """Read from the code: the two boxes are only read and emptied, and no button is pressed by code."""
    code = "\n".join(path.read_text(encoding="utf-8") for folder in ("bar", "tasks") for path in (ROOT / "kairu" / folder).glob("*.py"))
    for name in ("yes_box", "pin_box", "approve_button", "refuse_button"):
        uses = set(re.findall(rf"\b{name}\.(\w+)", code))
        assert uses <= {"get", "delete", "pack", "pack_forget", "focus_force", "focus_set", "bind", "winfo_ismapped"}, (name, uses)
    assert ".invoke(" not in code and "event_generate" not in code and "textvariable" not in code
    assert "keybd_event" not in code and "SendInput" not in code


def test_the_key_it_holds_is_not_ctrl_alt_k():
    from kairu import hotkey as guardians_key
    from kairu.bar import hotkey
    assert hotkey.VK_SPACE == 0x20 and hotkey.VK_SPACE != guardians_key.VK_K and hotkey.HOTKEY_ID != guardians_key.HOTKEY_ID
    assert "VK_K" not in (ROOT / "kairu" / "bar" / "hotkey.py").read_text(encoding="utf-8")
    assert hotkey.ShowHideKey(print).name == "Ctrl+Alt+Space" and hotkey.ShowHideKey(print, "q").name == "Ctrl+Alt+Q"
    assert hotkey._virtual_key("q") == 0x51 and hotkey._virtual_key("Space") == 0x20


@pytest.mark.parametrize("key,good", [("Q", True), ("q", True), ("Space", True), ("K", False), ("k", False), ("Ctrl", False), ("1", False), (5, False)])
def test_the_key_can_be_another_letter_and_never_k(tmp_path, key, good):
    import yaml
    from kairu import config as kairu_config
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"tasks": {"bar_key": key}}))
    if good:
        assert kairu_config.load(path).bar_key == key
    else:
        with pytest.raises(kairu_config.ConfigError, match="not K"):
            kairu_config.load(path)
    assert kairu_config.load(tmp_path / "missing.yaml").bar_key == "Space"


def test_when_another_program_holds_the_key_the_bar_shows_itself_and_says_so(bar):
    class Taken:
        state = "Ctrl+Alt+Space is taken by another program"

    bar.key_problem(Taken)
    bar.root.update()
    assert bar.visible and "taken by another program" in bar.reply_line.cget("text") and "tasks.bar_key" in bar.reply_line.cget("text")


def test_closing_waits_for_the_bars_own_threads(bar):
    """Tcl stops the whole program if a thread is the last to let go of a window: so close() waits for them."""
    go = threading.Event()
    worker = bar.start_thread(lambda: go.wait(5))
    threading.Timer(0.3, go.set).start()
    bar.close()
    assert not worker.is_alive()


def test_a_closed_bar_is_freed_on_the_main_thread_after_each_test(config):
    """It is cycle garbage, not freed when the last name for it goes; conftest frees it here instead of on any thread."""
    import weakref
    from tests_kairu.conftest import free_closed_windows_here
    made = make_bar(config)
    made.close()
    gone = weakref.ref(made)
    del made
    assert gone() is not None  # else this test checks nothing: Python would free it at once, on this thread
    free_closed_windows_here()
    assert gone() is None


def test_only_one_bar_at_a_time(tmp_path):
    from kairu.bar.app import OneBar
    first = OneBar(tmp_path)
    try:
        assert first.held is not None
        code = "from kairu.bar.app import OneBar; import sys; print(OneBar(sys.argv[1]).held is None)"
        other = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert other.stdout.strip() == "True", other.stdout + other.stderr
    finally:
        first.release()


# --- the program itself ------------------------------------------------------------------------------------

@pytest.fixture
def screen(config):
    make_bar(config).close()


def test_the_bar_program_stays_under_60_mb_and_ends_when_told(screen, config, config_path):
    process = subprocess.Popen([sys.executable, "-m", "kairu.bar.app", "--config", str(config_path)], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(3)
        assert process.poll() is None, process.stdout.read()
        now, peak = family_memory_mib(process.pid)
        print(f"\n  the Kairu bar's own process: {now:.0f} MiB (peak {peak:.0f} MiB)")
        assert now < 57  # 60 MB
        from kairu.bar.app import QUIT_FILE
        (config.data_dir / QUIT_FILE).write_text("")
        process.wait(10)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()


def test_a_second_bar_says_one_is_running_and_a_crash_of_the_bar_leaves_guardian_alone(screen, config, config_path):
    from kairu.bar.app import ALREADY_RUNNING, QUIT_FILE
    first = subprocess.Popen([sys.executable, "-m", "kairu.bar.app", "--config", str(config_path)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        wait_for(lambda: first.poll() is not None or (config.data_dir / "bar.lock").exists() or time.sleep(2) is None, timeout=10)
        second = subprocess.run([sys.executable, "-m", "kairu.bar.app", "--config", str(config_path)], cwd=ROOT, capture_output=True, timeout=30)
        assert second.returncode == ALREADY_RUNNING, second.stdout + second.stderr
    finally:
        (config.data_dir / QUIT_FILE).write_text("")
        try:
            first.wait(5)
        except subprocess.TimeoutExpired:
            first.kill()
        first.stdout.close()


def _a_bar_runs(data_dir) -> bool:
    """A bar holds its place under this account, looked at without taking it (taking it, even for a moment, could make the
    bar being started say "already running")."""
    if sys.platform != "win32":
        return (data_dir / "bar.lock").exists() and time.sleep(1) is None
    import ctypes
    from kairu import winpipe
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype, kernel32.OpenMutexW.argtypes = ctypes.c_void_p, (ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p)
    handle = kernel32.OpenMutexW(0x00100000, False, f"Local\\KairuBar-{winpipe.current_user_sid()}")  # SYNCHRONIZE
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


def test_kairu_bar_right_after_kairu_bar_quit_waits_for_the_old_bar_and_starts(screen, config, config_path):
    """`kairu bar quit` then `kairu bar` at once: the new bar must not delete the old one's quit note, or the old bar (and
    its old code) runs on and the new one says "already running"."""
    from kairu.bar.app import QUIT_FILE
    first = subprocess.Popen([sys.executable, "-m", "kairu.bar.app", "--config", str(config_path)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    second = None
    try:
        wait_for(lambda: first.poll() is not None or _a_bar_runs(config.data_dir), timeout=30)
        assert first.poll() is None, first.stdout.read()
        (config.data_dir / QUIT_FILE).write_text("")
        second = subprocess.Popen([sys.executable, "-m", "kairu.bar.app", "--config", str(config_path)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        first.wait(10)
        time.sleep(2)
        assert second.poll() is None, second.stdout.read()  # the new bar runs
    finally:
        (config.data_dir / QUIT_FILE).write_text("")
        for bar in (first, second):
            if bar is None:
                continue
            try:
                bar.wait(10)
            except subprocess.TimeoutExpired:
                bar.kill()
            bar.stdout.close()


def test_install_makes_a_sign_in_task_with_normal_rights(config_path):
    if sys.platform != "win32":
        from kairu.autostart import AutostartError
        from kairu.bar import install
        with pytest.raises(AutostartError):
            install.install("data", "python", config_path)
        return
    from kairu.bar import install
    text = install.definition("pythonw.exe", config_path)
    assert "LogonTrigger" in text and "LeastPrivilege" in text and "bar start --hidden" in text and "Repetition" not in text
