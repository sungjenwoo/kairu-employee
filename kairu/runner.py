"""The action runner: runs only what Guardian authorizes, and halts all of it on an emergency stop.

Each action runs in its own process (kairu/worker.py), together with every program it starts
(kairu/processes.py: a Job Object on Windows, a process group on Linux). A watcher thread reads the
stop counter in guardian.db every 0.1 s; when it changes, because of `kairu stop` in another
terminal, Ctrl+Alt+K, or stop() here, every running action and all its programs are ended: asked
to end, then killed 0.3 s later at most. A stop from this process skips the wait for the next read.

After a stop, Guardian is in Safe Mode, so only read-only actions can start until you resume.

The watcher does nothing else that can take time. Whatever follows a run's end (its audit row, then on_end,
which Guardian uses to put Mission Mode's lid setting back and to answer your phone) happens on a thread of its
own, in order, so a slow disk or a slow on_end never keeps a stop waiting. A run's `done` means its programs are
gone; `recorded` means its row is written and on_end has returned. close() waits for all of that, so the lid
setting is put back before Guardian ends. seconds_since_stop is the time the programs were really gone, taken
before any row is written.
"""

import itertools
import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from kairu import audit, safemode
from kairu.config import ROOT
from kairu.guardian import Action, Approval, Guardian, Refused
from kairu.processes import ActionProcess
from kairu.worker import REFUSED_EXIT

POLL_SECONDS = 0.1
GRACE_SECONDS = 0.3  # time to end after being asked, before the whole family is killed


@dataclass
class Run:
    run_id: int
    action: str
    process: ActionProcess
    outcome: str | None = None  # finished, refused (the action would not do it), failed or halted
    done: threading.Event = field(default_factory=threading.Event)  # its programs are gone
    recorded: threading.Event = field(default_factory=threading.Event)  # its audit row is written, on_end has returned

    def wait(self, timeout: float | None = None) -> str | None:
        self.done.wait(timeout)
        return self.outcome


class Runner:
    def __init__(self, guardian: Guardian, poll_seconds: float = POLL_SECONDS, on_end=None):
        self.guardian, self.store, self.poll_seconds, self.on_end = guardian, guardian.store, poll_seconds, on_end
        self._runs: dict[int, Run] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._wake, self._closed = threading.Event(), threading.Event()
        self._stops_seen = safemode.stop_count(self.store)
        self._after: queue.SimpleQueue = queue.SimpleQueue()  # (run, row) to record once a run has ended; None: finish
        self._writer = threading.Thread(target=self._write_after, name="kairu-after-run", daemon=True)
        self._writer.start()
        self._watcher = threading.Thread(target=self._watch, name="kairu-stop-watcher", daemon=True)
        self._watcher.start()

    def run(self, action: Action | str, target: str, /, approval: Approval | None = None, **kwargs) -> Run:
        """Run target ("module:function", called with kwargs) as `action`, if Guardian authorizes it. `action` and `target` are
        positional only, so an action's own detail may be called "target" (screen.click's: the button's name)."""
        action = Action(action) if isinstance(action, str) else action
        with self._lock:  # a stop cannot slip between the authorization and the start
            if self._closed.is_set():
                raise Refused("Guardian is ending, so nothing new starts")
            decision = self.guardian.authorize(action, approval)
            if not decision.allowed:
                raise Refused(decision.reason)
            process = ActionProcess([sys.executable, "-m", "kairu.worker", target, json.dumps(kwargs)], cwd=ROOT)
            run = Run(next(self._ids), action.name, process)
            self._runs[run.run_id] = run
            audit.record(self.store, "run", action.name, "started", run=run.run_id, pid=process.pid, target=target)
        return run

    def stop(self, source: str = "api") -> None:
        """Emergency stop: every Kairu process halts its actions; Safe Mode until you resume."""
        self.guardian.emergency_stop(source)
        self._wake.set()

    def running(self) -> list[Run]:
        with self._lock:
            return [run for run in self._runs.values() if run.outcome is None]

    def halt(self, run_id: int, why: str) -> bool:
        """End one running action and all its programs, without entering Safe Mode. False if it is not running."""
        return bool(self._halt_all(why, only=run_id))

    def close(self, why: str = "Kairu closed") -> None:
        """End the watcher and any action still running (without entering Safe Mode)."""
        self._closed.set()
        self._wake.set()
        self._watcher.join()
        self._halt_all(why)
        self._after.put(None)
        self._writer.join()

    # --- the watcher ---------------------------------------------------------------------------

    def _watch(self) -> None:
        while not self._closed.is_set():
            self._wake.wait(self.poll_seconds)
            self._wake.clear()
            try:
                stops = safemode.stop_count(self.store)
            except Exception as error:  # cannot tell whether a stop was asked for, so act as if it was
                self._halt_all(f"the stop flag could not be read ({error})")
                continue
            if stops != self._stops_seen:
                self._stops_seen = stops
                self._halt_all("emergency stop")
            self._reap()

    def _halt_all(self, why: str, only: int | None = None) -> list[Run]:
        with self._lock:
            halting = [run for run in self._runs.values() if run.outcome is None and only in (None, run.run_id)]
            for run in halting:
                run.process.ask_to_end()
            deadline = time.monotonic() + GRACE_SECONDS
            for run in halting:
                try:
                    run.process.wait(max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
            for run in halting:  # the whole family, even if the main process already ended: its children may not have
                run.process.kill()
                run.process.wait()
                run.process.close()
                run.outcome = "halted"
                del self._runs[run.run_id]
                row = {"decision": "halted", "pid": run.process.pid, "why": why, "gone_at": time.time()}
                run.done.set()
                self._after.put((run, row))
        return halting

    def _reap(self) -> None:
        with self._lock:
            ended = [run for run in self._runs.values() if run.process.poll() is not None]
            for run in ended:
                run.process.close()  # anything the action left running ends with it
                code = run.process.returncode
                run.outcome = "finished" if code == 0 else "refused" if code == REFUSED_EXIT else "failed"
                del self._runs[run.run_id]
                run.done.set()
                self._after.put((run, {"decision": run.outcome, "exit_code": run.process.returncode}))

    # --- after a run has ended, off the watcher -----------------------------------------------

    def _write_after(self) -> None:
        while (item := self._after.get()) is not None:
            run, row = item
            try:
                self._record_end(run, row)
                if self.on_end:
                    self.on_end(run)
            except Exception as error:  # what Guardian does after a run never stops the runner
                print(f"kairu: after {run.action} ended: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            finally:
                run.recorded.set()

    def _record_end(self, run: Run, row: dict) -> None:
        decision, gone_at = row.pop("decision"), row.pop("gone_at", None)
        if gone_at is not None:
            requested = safemode.stop_requested_at(self.store) or 0.0
            row["seconds_since_stop"] = round(gone_at - requested, 3) if row["why"] == "emergency stop" else None
        audit.record(self.store, "run", run.action, decision, run=run.run_id, **row)
