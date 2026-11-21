"""The small protection actions Guardian runs for you, each with exactly the details you gave and nothing else.

    protect.pause / protect.resume   one source (gmail, deadlines, folders, devices, security) or all
    protect.watch_pc                 High: watch Downloads (or another folder), devices and Windows Security
    protect.add_folder               High: watch one more folder (5 at most; system and private folders refused)
    protect.remove_folder            stop watching a folder
    alerts.dismiss                   mark an alert done, or a false alarm (kept as your report, never a rule change)
    deadline.add / deadline.remove   your own deadlines

They only change Kairu's own notes in data/protection.db. Each ends with exit code 1, and a reason
on Guardian's log, when there is nothing to change.
"""

import sys
from datetime import datetime

from kairu.protect.store import ProtectStore

SOURCES = ("all", "gmail", "deadlines", "folders", "devices", "security")
LONGEST_TITLE = 200


def pause(data_dir: str, source: str) -> None:
    store = _store(data_dir)
    _check_source(source)
    store.set_setting(f"paused:{source}", "1")


def resume(data_dir: str, source: str) -> None:
    store = _store(data_dir)
    _check_source(source)
    if source == "all":
        for name in SOURCES:
            store.set_setting(f"paused:{name}", None)
    else:
        store.set_setting(f"paused:{source}", None)


def dismiss(data_dir: str, alert: float, false_alarm: bool = False) -> None:
    if alert != int(alert) or alert < 1:
        _fail(f"alert must be a whole number, not {alert}")
    if not _store(data_dir).close_alert(int(alert), false_alarm):
        _fail(f"there is no open alert {int(alert)}")


def add_deadline(data_dir: str, title: str, due: str, note: str = "") -> None:
    title = " ".join(title.split())
    if not title or len(title) > LONGEST_TITLE:
        _fail(f"a deadline needs a title of 1 to {LONGEST_TITLE} characters")
    try:
        when = datetime.fromisoformat(due)
    except ValueError:
        _fail(f"due must be a date and time like 2026-11-05T18:00+05:30, not {due!r}")
    if when.tzinfo is None:
        _fail("due must say its time zone, like 2026-11-05T18:00+05:30")
    _store(data_dir).add_deadline(title, when, "you", None, " ".join(note.split())[:LONGEST_TITLE])


def remove_deadline(data_dir: str, deadline: float) -> None:
    if deadline != int(deadline) or deadline < 1:
        _fail(f"deadline must be a whole number, not {deadline}")
    if not _store(data_dir).remove_deadline(int(deadline)):
        _fail(f"there is no open deadline {int(deadline)}")


def watch_pc(data_dir: str, folder: str = "", devices: bool = False, security: bool = False) -> None:
    if not (folder or devices or security):
        _fail("nothing to watch was chosen")
    if folder:
        add_folder(data_dir, folder)
    store = _store(data_dir)
    if devices:
        store.set_setting("devices:on", "1")
    if security:
        store.set_setting("security:on", "1")


def add_folder(data_dir: str, folder: str) -> None:
    from kairu.protect.folders import FOLDERS, MOST_FOLDERS, FolderProblem, approved, fence
    store = _store(data_dir)
    try:
        path = fence(folder, data_dir)
    except FolderProblem as problem:
        _fail(str(problem))
    now = approved(store)
    if path in now:
        return
    if len(now) >= MOST_FOLDERS:
        _fail(f"Kairu watches at most {MOST_FOLDERS} folders; remove one first")
    store.set_setting(FOLDERS, "\n".join(now + [path]))


def remove_folder(data_dir: str, folder: str) -> None:
    from kairu.protect.folders import FOLDERS, approved
    store = _store(data_dir)
    now = approved(store)
    keep = [path for path in now if path != folder]
    if keep == now:
        _fail(f"Kairu does not watch {folder}")
    store.set_setting(FOLDERS, "\n".join(keep) or None)
    with store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS files (folder TEXT NOT NULL, path TEXT PRIMARY KEY, size INTEGER, mtime REAL)")
        db.execute("DELETE FROM files WHERE folder = ?", (folder,))
    store.set_setting(f"folder:baseline:{folder}", None)


def _store(data_dir: str) -> ProtectStore:
    return ProtectStore(data_dir)


def _check_source(source: str) -> None:
    if source not in SOURCES:
        _fail(f"source must be one of {', '.join(SOURCES)}")


def _fail(why: str):
    print(f"kairu: {why}", file=sys.stderr)
    raise SystemExit(1)
