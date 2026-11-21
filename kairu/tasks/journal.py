"""PC7: a plan's journal (BAR.md "When a plan is cut off"), so a Guardian restart or a stop mid-plan leaves nothing half-done.

While a plan you said yes to runs, data/plan-journal.json holds its steps and how many are done. Each step is one Guardian
action that either finished or was ended whole (a stop ends its programs together), and what a finished step changed is in
the undo log as always. If the plan is cut off (Guardian ended or restarted, Safe Mode, a stop, the bar closed), the
journal stays, and Kairu tells you which steps were done and which were not. "go on with the plan" shows you the steps
left and runs them only after your "yes" again, each decided by Guardian again; "forget the plan" empties the journal.
The journal is a file on this PC only: never sent, never in the audit log, and never a permission.
"""

import json
import os
import sys
import time
from pathlib import Path

NAME = "plan-journal.json"
KEEP_HOURS = 24  # an older journal is forgotten


class PlanJournal:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / NAME

    def start(self, steps, label) -> None:
        self._write({"steps": [{"action": step.action, "details": step.details} for step in steps],
                     "labels": [label(step) for step in steps], "done": 0, "at": time.time()})

    def step_done(self, done: int) -> None:
        data = self.read()
        if data is not None:
            data["done"] = done
            self._write(data)

    def read(self) -> dict | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or type(data.get("done")) is not int:
            return None
        if time.time() - float(data.get("at", 0)) > KEEP_HOURS * 3600:
            self.clear()
            return None
        return data

    def clear(self) -> None:
        """Emptied, not deleted (the task code deletes no file for good): an empty journal is no plan."""
        if self.path.exists():
            self._write({})

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as out:
            json.dump(data, out)
        for attempt in range(10):  # on Windows a virus scanner may hold the file a moment
            try:
                os.replace(temp, self.path)
                return
            except PermissionError:
                if attempt == 9 or sys.platform != "win32":
                    raise
                time.sleep(0.1)


def cut_off_note(data: dict) -> str:
    done, labels = data["done"], data.get("labels") or [step["action"] for step in data["steps"]]
    left = labels[done:]
    did = f"Done: {', '.join(labels[:done])}. " if done else ""
    return (f"Your last plan was cut off after {done} of {len(labels)} steps. {did}Not done: {', '.join(left)}. "
            'Say "go on with the plan" to do the rest (you\'ll see it first), or "forget the plan".')
