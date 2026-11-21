"""One command to install Kairu (Guardian, protection, Kairu Link, the brain, research, the bar, the voice) and run all its tests, with a short summary.

On Windows (PowerShell or Command Prompt), in the project folder:
    py -3.12 tools\\check_guardian.py
On Linux:
    python3.12 tools/check_guardian.py

It makes a private Python environment in .venv-guardian (first run only), installs Kairu and its
packages from PyPI into it (PyYAML, argon2-cffi, PyNaCl, segno, ddgs, vosk, faster-whisper, pytest), sets up the small voice
model in data/voice/ if it is not there yet (VOICE.md), runs every Guardian test, and prints the summary. The full
test output goes to guardian-check-report.txt. The voice tests use recorded sounds, never your microphone.

During the run, some tests press Ctrl+Alt+K for you (Windows only). Do not type until it finishes.
If your own Guardian is running, the check ends it for the tests and starts it again afterwards; so too your Kairu bar,
which holds the one-bar lock the bar's tests need.
"""

import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv-guardian"
REPORT = ROOT / "guardian-check-report.txt"
HOTKEY_TEST = "test_pressing_ctrl_alt_k_on_windows_halts_everything_within_1_second"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def step(text: str) -> None:
    print(f"  {text} ...", end=" ", flush=True)


def run(args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True, text=True, **kwargs)


def main() -> int:
    print("Kairu Guardian check")
    print(f"  Python {platform.python_version()} on {platform.system()} {platform.release()} ({platform.version()})")
    if sys.version_info[:2] != (3, 12):
        print("  FAILED: this needs Python 3.12. On Windows, install it from python.org, then run: py -3.12 tools\\check_guardian.py")
        return 1

    if not venv_python().exists():
        step("Making the private environment .venv-guardian")
        made = run([sys.executable, "-m", "venv", VENV])
        if made.returncode:
            print("FAILED\n" + made.stderr)
            return 1
        print("done")
    step("Installing Kairu, PyYAML, argon2-cffi, PyNaCl, segno, ddgs, vosk, faster-whisper and pytest")
    installed = run([venv_python(), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-e", ".[test]"])
    if installed.returncode:
        print("FAILED\n" + installed.stdout + installed.stderr)
        return 1
    print("done")
    set_up_the_voice_model()

    paused = pause_your_guardian()
    if paused is None:
        return 1
    bar = pause_your_bar()
    if bar is None:
        restart_your_guardian(paused)
        return 1
    try:
        if sys.platform == "win32":
            print("  The Ctrl+Alt+K tests will press the keys for you: please do not type until this finishes.")
        step("Running all Guardian tests (about two minutes)")
        results = Path(tempfile.mkdtemp()) / "results.xml"
        started = time.monotonic()
        keeping = keep_your_guardian_paused(paused)
        try:
            tests = run([venv_python(), "-m", "pytest", "tests_kairu", "-v", "-rs", "-p", "no:cacheprovider",
                         f"--junitxml={results}", "-o", "junit_logging=system-out"])
        finally:
            keeping.set()
        print(f"done in {time.monotonic() - started:.0f} s")
    finally:
        restart_your_guardian(paused)
        restart_your_bar(bar)
    REPORT.write_text(f"{platform.platform()}\n\n{tests.stdout}\n{tests.stderr}", encoding="utf-8")
    return summarize(results, tests.returncode)


VOICE_MODEL = ("import sys; from kairu.voice import models; from pathlib import Path\n"
               "quiet, data = (lambda text: None), Path('data')\n"
               "try:\n"
               "    models.setup(data, models.DEFAULT, say=quiet)\n"
               "    if sys.platform == 'win32':\n"
               "        models.setup_piper(data, say=quiet); models.setup_voice(data, models.DEFAULT_VOICE, say=quiet)\n"
               "    print('ready')\n"
               "except models.SetupError as error: print(f'not set up: {error}')")


def set_up_the_voice_model() -> None:
    """The voice tests hear recorded sounds with the real small model, and on Windows measure the real Piper voice, from this
    folder's data/voice/ (as `kairu voice setup` puts them there): downloaded once from alphacephei.com, github.com/rhasspy/piper
    and huggingface.co/rhasspy/piper-voices, each SHA-256 checked. They never go into the repository."""
    step("The voice model, and on Windows Piper and one voice, for the voice tests (once, about 135 MiB)")
    answer = run([venv_python(), "-c", VOICE_MODEL]).stdout.strip() or "not set up: the check could not run"
    print(answer if answer.startswith("not set up") else f"{answer}, SHA-256 checked")


def pause_your_guardian() -> bool | None:
    """Your own Guardian, if it runs, holds Ctrl+Alt+K and the one-Guardian lock the tests need: end it while they run.

    Task Scheduler is kept from starting it again meanwhile (for 15 minutes at most). True if it was running;
    None if it is running actions, which ending it would end too.
    """
    paused = run([venv_python(), "-c", "from kairu import client, config; from kairu.guardian import Refused\n"
                  "try: print('running' if client.pause_for_check(config.load()) else 'not running')\n"
                  "except Refused as error: print(f'refused: {error}')"])
    answer = paused.stdout.strip()
    if answer == "running":
        print("  Your Guardian was running: it is ended while the tests run, and started again after them.")
        return True
    if answer.startswith("refused"):
        print(f"  FAILED: {answer.split(': ', 1)[1]}.")
        return None
    return False


RENEW_SECONDS = 300  # the pause lasts 15 minutes; while the tests still run, it is renewed every 5


def keep_your_guardian_paused(paused: bool) -> threading.Event:
    """The tests can take longer than the 15-minute pause (18 minutes on the owner's PC, 13 Nov 2026): Task Scheduler then
    started the real Guardian mid-run, and every later test that starts its own Guardian found "another Guardian". So the
    pause is renewed every 5 minutes while the tests run. It still runs out by itself within 15 minutes should this check
    die. Set the returned event to stop renewing."""
    done = threading.Event()
    renew = ("from kairu import autostart, config, client\n"
             "cfg = config.load()\n"
             "if autostart.installed(cfg.data_dir): autostart.pause(cfg.data_dir, 900)")

    def keep() -> None:
        while not done.wait(RENEW_SECONDS):
            run([venv_python(), "-c", renew])

    if paused is not None:
        threading.Thread(target=keep, daemon=True).start()
    return done


BAR_RUNS = ("from kairu.bar.app import OneBar; import sys, tempfile\n"
            "one = OneBar(tempfile.mkdtemp()); print('free' if one.held is not None else 'held'); one.release()")


def pause_your_bar() -> bool | None:
    """Your Kairu bar, if it runs, holds the one-bar lock: end it while the tests run (it keeps nothing). True if it ran;
    None if a bar from another folder runs, which this check cannot end."""
    if run([venv_python(), "-c", BAR_RUNS]).stdout.strip() != "held":
        return False
    run([venv_python(), "-m", "kairu", "bar", "quit"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if run([venv_python(), "-c", BAR_RUNS]).stdout.strip() == "free":
            print("  Your Kairu bar was running: it is ended while the tests run, and started again, hidden, after them.")
            return True
        time.sleep(0.5)
    print("  FAILED: a Kairu bar from another folder is running. End it there with `kairu bar quit`, then check again.")
    return None


def restart_your_bar(was_running: bool | None) -> None:
    if was_running:
        done = run([venv_python(), "-m", "kairu", "bar", "start", "--hidden"])
        print("  Your Kairu bar is running again (hidden)." if done.returncode == 0 else "  Your Kairu bar did not start again; run `kairu bar`.")


def restart_your_guardian(was_running: bool) -> None:
    done = run([venv_python(), "-c", "from kairu import client, config\n"
                f"client.resume_after_check(config.load(), config.config_path(), {was_running})"])
    if was_running:
        print("  Your Guardian is running again." if done.returncode == 0
              else f"  Your Guardian did not start again; run `kairu guardian run`. {done.stderr.strip()[-300:]}")


def summarize(results: Path, exit_code: int) -> int:
    if not results.exists():
        print(f"\n  Result: FAILED, the tests could not run. See {REPORT.name}.")
        return 1
    passed, failed, skipped, timings, memory, hotkey = [], [], [], [], [], "not run"
    for case in ElementTree.parse(results).getroot().iter("testcase"):
        name = case.get("name")
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        if problem is not None:
            failed.append((name, (problem.get("message") or "").splitlines()[0][:150]))
            outcome = "FAILED"
        elif case.find("skipped") is not None:
            skipped.append((name, case.find("skipped").get("message", "")))
            outcome = "skipped"
        else:
            passed.append(name)
            outcome = "passed"
        if name == HOTKEY_TEST:
            hotkey = outcome
        output = case.findtext("system-out") or ""
        timings += [line.strip() for line in output.splitlines()
                    if re.search(r"(halted|gone) in|halted \d|reply in|answer in|heard \d", line)]
        memory += [line.strip() for line in output.splitlines()
                   if "Guardian program memory" in line or "Voice process memory" in line or "with voice on" in line]

    ok = exit_code == 0 and not failed
    print(f"\n  Result: {'PASSED' if ok else 'FAILED'}   {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    if os.environ.get("GITHUB_ACTIONS") == "true":  # the summary on the pull request's checks, without the full log
        print(f"::notice title=Kairu check ({platform.system()})::{'PASSED' if ok else 'FAILED'}: {len(passed)} passed, "
              f"{len(failed)} failed, {len(skipped)} skipped")
    print(f"  Real Ctrl+Alt+K test: {hotkey}")
    if timings:
        print("  Timings (stops, and the phone's replies and answers):")
        for line in timings:
            print(f"    {line}")
    for line in memory:
        print(f"  {line}")
    for name, why in failed:
        print(f"  FAILED  {name}: {why}")
        if os.environ.get("GITHUB_ACTIONS") == "true":  # shown on the pull request's checks, without the full log
            print(f"::error title=FAILED {name}::{why.replace('%', '%25').replace(chr(10), ' ')}")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")
    print(f"  Full output: {REPORT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
