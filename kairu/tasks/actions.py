"""The PC skills, as Guardian actions: Guardian decided before any of this runs, and each runs in its own process.

Each takes a random job id and leaves one short line for whoever asked (data/tasks.db). Exit code 0 whenever there is
something to say, even "I can't find that". Window titles, file names and app names are data: they are only shown, or
compared with the name you typed. Guardian's audit log keeps only a hash of the details (policy.yaml: private).
"""

import datetime
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from kairu.brain import privacy
from kairu.tasks import fence, pc, recycle, web
from kairu.tasks.store import TaskStore
from kairu.worker import FAILED, REFUSED

JOB = re.compile(r"[0-9a-f]{16}")
MOST_SHOWN = 8
NOT_CONTROLLED = re.compile(r"\b(?:windows security|defender|firewall|antivirus|anti-virus|credential|password)\b", re.IGNORECASE)
NOT_AN_APP = re.compile(r"\b(?:uninstall|read ?me|help|website|documentation|license|licence|release notes|manual|support)\b", re.IGNORECASE)
STEP = 10


def _say(data_dir: str, job: str, ok: bool, text: str) -> None:
    if not JOB.fullmatch(job):
        print("tasks: a job id is 16 hex digits", file=sys.stderr)
        raise SystemExit(1)
    TaskStore(data_dir).put_reply(job, ok, text)


def _guarded(data_dir: str, job: str, work):
    """Run the skill and say what came of it. Only a short label ever comes from a failure.

    A refusal ends as REFUSED and a failure as FAILED (kairu/worker.py), so Guardian's audit log tells them from a finish.
    """
    try:
        _say(data_dir, job, True, work(pc.backend()))
    except pc.PcProblem as problem:
        _say(data_dir, job, False, f"{str(problem)[:1].upper()}{str(problem)[1:]}.")
        return FAILED
    except pc.NotOnThisSystem as problem:
        _say(data_dir, job, False, f"{str(problem)[:1].upper()}{str(problem)[1:]}.")
        return REFUSED
    except Refusal as refusal:
        _say(data_dir, job, False, str(refusal))
        return REFUSED
    return None


class Refusal(Exception):
    """The skill will not do this. Its text is what to tell you."""


class NoSuchApp(Refusal):
    """No app with that name among the ones looked at."""


# --- what's open -------------------------------------------------------------------------------------

def list_open(data_dir: str, job: str) -> None:
    def work(system) -> str:
        shown: dict[str, str] = {}
        for window in system.windows():
            shown.setdefault(window.app or "an app", window.title)
        if not shown:
            return "No app windows are open."
        names = [f"{app} ({_short(title)})" for app, title in list(shown.items())[:MOST_SHOWN]]
        more = len(shown) - MOST_SHOWN
        return "Open: " + ", ".join(names) + (f", and {more} more." if more > 0 else ".")
    return _guarded(data_dir, job, work)


def _short(title: str, most: int = 28) -> str:
    title = " ".join(title.split())
    return title if len(title) <= most else title[:most - 1].rstrip() + "…"


# --- files, inside your work folder ------------------------------------------------------------------

def rename(data_dir: str, job: str, old: str, new: str, work_folder: str) -> None:
    def work(_) -> str:
        folder = fence.work_folder(work_folder)
        try:
            was, now = fence.rename(folder, old, new)
        except (fence.OutsideFolder, FileExistsError) as problem:  # the fence, or a name that is taken: Kairu refuses
            raise Refusal(f"Refused: {problem}.") from None
        except FileNotFoundError as problem:
            raise Refusal(f"Not renamed: {problem}.") from None
        except OSError as error:
            raise Refusal(f"Not renamed: Windows refused it ({type(error).__name__}).") from None
        TaskStore(data_dir).remember("rename", {"old": was, "new": now})
        return f"Renamed {was} to {now}."
    return _guarded(data_dir, job, work)


def undo(data_dir: str, job: str, work_folder: str) -> None:
    def work(_) -> str:
        store = TaskStore(data_dir)
        entry = store.newest_undo()
        if entry is None:
            return "Nothing to undo."
        store.forget_undo(entry.id)  # also when it cannot be undone any more: the next undo goes on to the one before
        folder = fence.work_folder(work_folder)
        if entry.kind == "rename":
            return _undo_rename(folder, entry.detail)
        if entry.kind == "move":
            return _undo_move(folder, entry.detail)
        if entry.kind == "delete":
            return _undo_delete(folder, entry.detail)
        if entry.kind == "write":
            return _undo_write(folder, entry.detail)
        raise Refusal("That change can't be undone.")
    return _guarded(data_dir, job, work)


def _undo_rename(folder, detail: dict) -> str:
    try:
        fence.rename(folder, detail["new"], detail["old"])
    except (fence.OutsideFolder, FileExistsError) as problem:
        raise Refusal(f"Refused to undo the rename of {detail['old']}: {problem}.") from None
    except FileNotFoundError as problem:
        raise Refusal(f"I couldn't undo the rename of {detail['old']}: {problem}.") from None
    except OSError as error:
        raise Refusal(f"I couldn't undo the rename of {detail['old']} ({type(error).__name__}).") from None
    return f"Undone: {detail['new']} is {detail['old']} again."


def _undo_move(folder, detail: dict) -> str:
    """Each name back where it was, through the same fence, overwriting nothing; the folder the move made goes if it is empty."""
    back, kept = 0, []
    for old, new in reversed(detail["moves"]):
        try:
            fence.rename(folder, new, old)
            back += 1
        except (OSError, fence.OutsideFolder):
            kept.append(new)
    made = detail.get("made")
    if made:
        try:
            place = fence.inside(folder, made)
            if place.is_dir() and not any(place.iterdir()):
                place.rmdir()
        except (OSError, fence.OutsideFolder):
            pass
    if kept and not back:
        raise Refusal(f"I couldn't undo the move: {_names(kept)} can't go back (a name there is taken, or it has gone).")
    said = f"Undone: {_count(back, 'file')} back where {'it was' if back == 1 else 'they were'}."
    return said + (f" {_names(kept)} couldn't go back." if kept else "")


def _undo_delete(folder, detail: dict) -> str:
    name = detail["name"]
    if not detail.get("bin"):
        raise Refusal(f"I can't bring {name} back: Windows didn't say where in the Recycle Bin it went. "
                      "Explorer's Recycle Bin may still have it.")
    try:
        original = fence.inside(folder, name)
    except fence.OutsideFolder as problem:
        raise Refusal(f"Refused to undo the delete of {name}: {problem}.") from None
    if os.path.lexists(original):
        raise Refusal(f"I can't bring {name} back: something else has that name now, and Kairu overwrites nothing.")
    if not original.parent.is_dir():
        raise Refusal(f"I can't bring {name} back: the folder it was in has gone.")
    try:
        recycle.backend().restore(detail["bin"], original)
    except recycle.CannotRestore as problem:
        raise Refusal(f"Windows can't restore {name}: {problem}.") from None
    return f"Undone: {name} is back from the Recycle Bin."


def _undo_write(folder, detail: dict) -> str:
    """A file files.write made goes to the Recycle Bin, if it is still exactly what Kairu wrote; never deleted for good."""
    name = detail["name"]
    try:
        made = fence.inside(folder, name)
    except fence.OutsideFolder as problem:
        raise Refusal(f"Refused to undo making {name}: {problem}.") from None
    if not made.is_file() or made.is_symlink():
        raise Refusal(f"I can't undo making {name}: it has gone.")
    if hashlib.sha256(made.read_bytes()).hexdigest() != detail["sha256"]:
        raise Refusal(f"I didn't undo making {name}: it has changed since, so it stays.")
    try:
        recycle.backend().recycle(made)
    except recycle.CannotRecycle as problem:
        raise Refusal(f"I didn't undo making {name}: {problem}.") from None
    return f"Undone: {name} is in the Recycle Bin."


def _count(number: int, what: str) -> str:
    return f"{number} {what}{'' if number == 1 else 's'}"


def _names(names, most: int = 5) -> str:
    shown = ", ".join(names[:most])
    return shown + (f" and {len(names) - most} more" if len(names) > most else "")


# --- find, move and delete, inside your work folder (Sprint Day 4) ------------------------------------------

KINDS = {
    "pdf": ("*.pdf",), "image": ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.webp", "*.heic"),
    "photo": ("*.jpg", "*.jpeg", "*.png", "*.heic"), "picture": ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.webp"),
    "screenshot": ("*.png", "*.jpg"), "document": ("*.pdf", "*.doc", "*.docx", "*.txt", "*.odt", "*.rtf", "*.md"),
    "doc": ("*.doc", "*.docx"), "word": ("*.doc", "*.docx"), "text": ("*.txt", "*.md"), "txt": ("*.txt",),
    "spreadsheet": ("*.xls", "*.xlsx", "*.csv", "*.ods"), "excel": ("*.xls", "*.xlsx"), "csv": ("*.csv",),
    "slide": ("*.ppt", "*.pptx"), "presentation": ("*.ppt", "*.pptx"), "powerpoint": ("*.ppt", "*.pptx"),
    "video": ("*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"), "music": ("*.mp3", "*.wav", "*.m4a", "*.flac", "*.ogg"),
    "song": ("*.mp3", "*.m4a"), "audio": ("*.mp3", "*.wav", "*.m4a", "*.flac", "*.ogg"), "zip": ("*.zip", "*.rar", "*.7z"),
}
FILLER = {"the", "my", "all", "a", "an", "some", "any", "of", "file", "files", "called", "named", "with", "in", "kairu-files",
          "and", "that", "are", "is", "were", "me", "everything", "anything", "something", "folder", "folders"}
WHEN = {"today": 0, "yesterday": 1, "this week": 7, "last week": 14, "recently": 7, "recent": 7}
MOST_SAID = 8


def what_to_find(what: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(patterns, words) for a name: "*.pdf", "pdfs", "tax report", "report pdfs"."""
    text = what.strip().strip("\"'“”").lower()
    if fence.is_pattern(text):
        if re.search(r"[\\/:]", text):
            raise Refusal("Refused: a find looks only at names, with no folder or drive in them.")
        return (text,), ()
    kinds: list[str] = []
    words: list[str] = []
    for word in re.findall(r"[\w.+-]+", text):
        bare = word.lstrip(".")
        single = bare[:-1] if bare.endswith("s") and bare[:-1] in KINDS else bare
        if single in KINDS:
            kinds.extend(KINDS[single])
        elif word not in FILLER:
            words.append(word)
    return tuple(dict.fromkeys(kinds)), tuple(words)


def find_files(data_dir: str, job: str, what: str, when: str, work_folder: str) -> None:
    def work(_) -> str:
        folder = fence.work_folder(work_folder)
        kinds, words = what_to_find(what)
        said_when = " ".join(when.lower().split())
        days = WHEN.get(said_when) if said_when else None
        if said_when and days is None:
            raise Refusal("I can find by today, yesterday, this week or last week.")
        since = None
        if days is not None:
            midnight = datetime.datetime.combine(datetime.date.today(), datetime.time())
            since = (midnight - datetime.timedelta(days=days)).timestamp()
        found = fence.find(folder, kinds, words, since)
        asked = what.strip() or "files"
        if not found:
            return f"No {asked} in your work folder{' from ' + said_when if said_when else ''}."
        more = len(found) - MOST_SAID
        return f"Found {len(found)}: " + ", ".join(found[:MOST_SAID]) + (f", and {more} more." if more > 0 else ".")
    return _guarded(data_dir, job, work)


def move_files(data_dir: str, job: str, name: str, to: str, work_folder: str) -> None:
    def work(_) -> str:
        folder = fence.work_folder(work_folder)
        try:
            moves, made = fence.move(folder, name, to)
        except fence.PartlyMoved as partly:
            if partly.done:
                TaskStore(data_dir).remember("move", {"moves": partly.done, "made": partly.made})
            raise Refusal(f"Not all moved: {partly}. \"undo\" puts back what moved.") from None
        except (fence.OutsideFolder, FileExistsError) as problem:
            raise Refusal(f"Refused: {problem}.") from None
        except FileNotFoundError as problem:
            raise Refusal(f"Not moved: {problem}.") from None
        except OSError as error:
            raise Refusal(f"Not moved: {error}.") from None
        TaskStore(data_dir).remember("move", {"moves": moves, "made": made})
        place = to.strip().strip("/\\") or "your work folder"
        what = moves[0][0] if len(moves) == 1 else _count(len(moves), "file")
        return f"Moved {what} into {place}" + (" (a new folder)." if made else ".")
    return _guarded(data_dir, job, work)


def delete(data_dir: str, job: str, name: str, work_folder: str) -> None:
    """One file or folder to the Recycle Bin (High: you said "yes" and typed your PIN). Never deleted for good."""
    def work(_) -> str:
        folder = fence.work_folder(work_folder)
        if fence.is_pattern(name):
            raise Refusal("Refused: Kairu deletes one file or folder at a time, never a pattern.")
        try:
            item = fence.inside(folder, name)
        except fence.OutsideFolder as problem:
            raise Refusal(f"Refused: {problem}.") from None
        if not os.path.lexists(item):
            raise Refusal(f"Not deleted: there is no '{name}' in your work folder.")
        what = "folder" if item.is_dir() and not item.is_symlink() else "file"
        relative = str(item.relative_to(folder)).replace("\\", "/")
        try:
            token = recycle.backend().recycle(item)
        except recycle.CannotRecycle as problem:
            raise Refusal(f"Not deleted: {problem}. Kairu never deletes for good.") from None
        TaskStore(data_dir).remember("delete", {"name": relative, "bin": token, "what": what})
        if not token:
            return (f"The {what} {relative} is in the Recycle Bin, but Windows didn't say where, so \"undo\" can't bring it back; "
                    "Explorer's Recycle Bin can.")
        return f"The {what} {relative} is in the Recycle Bin. \"undo\" brings it back."
    return _guarded(data_dir, job, work)


# --- make, open and show a file in your work folder (W2, ADR-036) ------------------------------------------------

WRITABLE = frozenset(".txt .md .csv .json .html .htm .css .xml .log .yaml .yml".split())
# files.open opens only these kinds, by the name's ending: documents, pictures, sound, video, text and archives. Anything else,
# above all a program, script or shortcut (.exe .bat .cmd .ps1 .vbs .js .msi .lnk .url .hta …), is refused, so opening a file
# never runs code. A folder opens in Explorer.
OPENABLE = WRITABLE | frozenset((
    ".pdf .doc .docx .xls .xlsx .ppt .pptx .odt .ods .odp .rtf .epub "
    ".png .jpg .jpeg .gif .bmp .webp .heic .tif .tiff .ico .svg "
    ".mp3 .wav .m4a .flac .ogg .aac .mp4 .mkv .avi .mov .webm .wmv "
    ".zip").split())
LONGEST_WRITE = 20_000


def _named(folder, name: str, verb: str) -> Path:
    if fence.is_pattern(name):
        raise Refusal(f"Refused: Kairu {verb} one file at a time, never a pattern.")
    try:
        return fence.inside(folder, name)
    except fence.OutsideFolder as problem:
        raise Refusal(f"Refused: {problem}.") from None


def _relative_name(folder, path: Path) -> str:
    return str(path.relative_to(folder)).replace("\\", "/")


def write_file(data_dir: str, job: str, name: str, text: str, work_folder: str) -> None:
    """A NEW text file in your work folder, with these words. It never overwrites; "undo" puts it in the Recycle Bin."""
    def work(_) -> str:
        folder = fence.work_folder(work_folder)
        place = _named(folder, name, "makes")
        if place.suffix.lower() not in WRITABLE:
            raise Refusal(f"Refused: Kairu makes text files only ({', '.join(sorted(WRITABLE))}).")
        if len(text) > LONGEST_WRITE:
            raise Refusal(f"Refused: at most {LONGEST_WRITE} characters in one file.")
        if not place.parent.is_dir():
            raise Refusal(f"Not made: there is no folder {_relative_name(folder, place.parent)} in your work folder.")
        words = text.replace("\\n", "\n")
        data = (words + ("\n" if words and not words.endswith("\n") else "")).encode("utf-8")
        try:
            with open(place, "xb") as file:  # x: never over a file that is there
                file.write(data)
        except FileExistsError:
            raise Refusal(f"Not made: {_relative_name(folder, place)} is already there, and Kairu overwrites nothing.") from None
        except OSError as error:
            raise Refusal(f"Not made: Windows refused it ({type(error).__name__}).") from None
        made = _relative_name(folder, place)
        TaskStore(data_dir).remember("write", {"name": made, "sha256": hashlib.sha256(data).hexdigest()})
        return f"Made {made}" + (f" ({len(words)} characters)." if words else " (empty).")
    return _guarded(data_dir, job, work)


def open_file(data_dir: str, job: str, name: str, work_folder: str) -> None:
    """A file of your work folder with its own app, or a folder in Explorer. Never a program, script or shortcut."""
    def work(system) -> str:
        folder = fence.work_folder(work_folder)
        place = _named(folder, name, "opens")
        if not place.is_dir() and place.suffix.lower() not in OPENABLE:  # by its kind first, whether it is there or not
            raise Refusal(f"Refused: Kairu never opens programs, scripts or shortcuts, and opens only documents, pictures, "
                          f"sound, video and text ({name}).")
        if not os.path.lexists(place):
            raise Refusal(f"Not opened: there is no '{name}' in your work folder.")
        shown = _relative_name(folder, place)
        system.open_file(str(place))
        return f"Opened {shown}."
    return _guarded(data_dir, job, work)


def show_file(data_dir: str, job: str, name: str, work_folder: str) -> None:
    """Explorer, with this file or folder of your work folder selected. It reads and changes nothing."""
    def work(system) -> str:
        folder = fence.work_folder(work_folder)
        place = _named(folder, name, "shows")
        if not os.path.lexists(place):
            raise Refusal(f"Not shown: there is no '{name}' in your work folder.")
        system.show_file(str(place))
        return f"{_relative_name(folder, place)} is shown in its folder."
    return _guarded(data_dir, job, work)


# --- Kairu's own browser (kairu/tasks/web.py) ---------------------------------------------------------

PERSONAL_SEARCH = "Not searched yet: "  # the core asks for your approval (web.search_private) when a reply starts with this


def _browser(system) -> str:
    found = system.browsers()
    browser = found.get("chrome") or found.get("edge")
    if not browser:
        raise Refusal("I can't find Chrome or Edge on this PC.")
    return browser


def _open_page(system, data_dir: str, url: str) -> None:
    system.browse(_browser(system), web.arguments(web.profile(data_dir), url), Path(data_dir).resolve() / "browser-links")


def web_open(data_dir: str, job: str, url: str) -> None:
    def work(system) -> str:
        try:
            address = web.address(url)
        except web.NotAnAddress as problem:
            raise Refusal(f"Refused: {problem}.") from None
        _open_page(system, data_dir, address)
        return f"Opened {urlsplit(address).hostname} in Kairu's browser."
    return _guarded(data_dir, job, work)


def web_search(data_dir: str, job: str, query: str) -> None:
    """A Google search in Kairu's browser. The privacy filter reads the words first: a secret is never searched, and personal
    words are not searched here: they need web.search_private, which is High ("yes" and your PIN)."""
    def work(system) -> str:
        words = _search_words(query)
        verdict = privacy.classify(words)
        if verdict.personal:
            raise Refusal(f"{PERSONAL_SEARCH}it looks personal ({verdict.why()}), so it needs your yes and PIN first.")
        _open_page(system, data_dir, web.search_address(words))
        return f"Searched Google for {words} in Kairu's browser."
    return _guarded(data_dir, job, work)


def web_search_private(data_dir: str, job: str, query: str) -> None:
    """You approved these words ("yes" and your PIN): searched, as long as they hold no secret."""
    def work(system) -> str:
        words = _search_words(query)
        _open_page(system, data_dir, web.search_address(words))
        return "Searched Google for your approved words in Kairu's browser."
    return _guarded(data_dir, job, work)


def _search_words(query: str) -> str:
    words = " ".join(query.split())
    if not words or len(words) > 300:
        raise Refusal("A search is 1 to 300 characters.")
    verdict = privacy.classify(words)
    if verdict.secret:
        raise Refusal(f"Not searched: it has {verdict.why()}. Secrets never leave this PC, not even with your approval.")
    return words


# --- a free-form plan's own record (Sprint Day 4) ---------------------------------------------------

APPROVED = ("yes", "yes+PIN")
REQUEST = re.compile(r"[0-9a-f]{8,64}|")
SOURCE = re.compile(r"pc|dev-[0-9a-f]{16}")


def record_plan(data_dir: str, job: str, plan: str, approved: str, request: str, source: str) -> None:
    """task.plan: a plan you approved, kept before its first step runs. Guardian's audit log keeps the hash of these details
    (policy.yaml: private); data/tasks.db keeps when, from where, how you approved it and its skills' names, with that hash."""
    def work(_) -> str:
        try:
            steps = json.loads(plan)
            names = [step["action"] for step in steps["steps"]]
        except (ValueError, KeyError, TypeError):
            raise Refusal("Refused: that isn't a plan Kairu wrote.") from None
        if approved not in APPROVED or not REQUEST.fullmatch(request) or not SOURCE.fullmatch(source) \
                or (approved == "yes+PIN") != bool(request) or not all(isinstance(name, str) for name in names):
            raise Refusal("Refused: a plan is kept only with how you approved it.")
        details = {"job": job, "plan": plan, "approved": approved, "request": request, "source": source}
        digest = hashlib.sha256(json.dumps(details, sort_keys=True, default=str).encode()).hexdigest()  # as the audit log has it
        TaskStore(data_dir).keep_plan(source, approved, request, names, digest)
        return f"Plan kept: {len(names)} step{'s' if len(names) != 1 else ''}, approved with {approved}."
    return _guarded(data_dir, job, work)


# --- waiting, between the steps of a task -----------------------------------------------------------

MOST_WAIT = 60


def wait(data_dir: str, job: str, seconds: str) -> None:
    def work(_) -> str:
        if not seconds.strip().isdigit() or not 1 <= int(seconds) <= MOST_WAIT:
            raise Refusal(f"I wait 1 to {MOST_WAIT} seconds.")
        time.sleep(int(seconds))
        return f"Waited {int(seconds)} seconds."
    return _guarded(data_dir, job, work)


# --- apps and windows --------------------------------------------------------------------------------

def choose_app(name: str, apps: dict[str, str]) -> str:
    """Where the app with this name is. Only names from the Start Menu and App Paths: a name never becomes a path."""
    wanted = " ".join(name.lower().split())
    usable = {key: path for key, path in apps.items() if not NOT_AN_APP.search(key)}
    for key, path in usable.items():
        if key.lower() == wanted:
            return path
    fits = {key: path for key, path in usable.items() if re.search(rf"\b{re.escape(wanted)}\b", key.lower())}
    if len(set(fits.values())) == 1:
        return next(iter(fits.values()))
    if fits:
        raise Refusal(f"Which one: {', '.join(sorted(fits)[:4])}?")
    raise NoSuchApp(f"I can't find an app called {name} on this PC.")


def open_app(data_dir: str, job: str, name: str) -> None:
    def work(system) -> str:
        if NOT_CONTROLLED.search(name):
            raise Refusal(f"Kairu doesn't open {name}: security settings stay yours.")
        try:
            path = choose_app(name, system.apps())
        except NoSuchApp:  # not a shortcut or App Path: a Microsoft Store app, such as WhatsApp, by the ID Windows lists
            store = {key: value for key, value in system.store_apps().items() if not NOT_CONTROLLED.search(key)}
            path = choose_app(name, store)
        system.launch(path)
        return f"Opened {name}."
    return _guarded(data_dir, job, work)


def _windows_of(system, name: str) -> list:
    """The windows of this app, by its program's name only. A title is a page's or a file's words, so it never decides."""
    wanted = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    squeezed = wanted.replace(" ", "")
    windows = [window for window in system.windows() if window.app]
    for test in (lambda app: app == squeezed,
                 lambda app: app in wanted.split(),
                 lambda app: len(squeezed) >= 3 and squeezed in app):
        found = [window for window in windows if test(window.app)]
        if found:
            return found
    raise Refusal(f"{name} isn't open.")


def close_app(data_dir: str, job: str, name: str) -> None:
    def work(system) -> str:
        results = [system.close(window) for window in _windows_of(system, name)]
        if all(results):
            return f"Closed {name}."
        return f"I asked {name} to close; it may be asking you to save something."
    return _guarded(data_dir, job, work)


ARRANGE_WORDS = {"left": "left", "right": "right", "maximize": "maximize", "maximise": "maximize", "minimize": "minimize",
                 "minimise": "minimize", "front": "front"}
ARRANGED = {"left": "on the left half", "right": "on the right half", "maximize": "maximized", "minimize": "minimized",
            "front": "in front"}


def arrange_app(data_dir: str, job: str, name: str, how: str) -> None:
    def work(system) -> str:
        wanted = ARRANGE_WORDS.get(how.lower())
        if wanted is None:
            raise Refusal("I can only put a window on the left or right half, maximize, minimize or bring it to the front.")
        system.arrange(_windows_of(system, name)[0], wanted)
        return f"{name} is {ARRANGED[wanted]}."
    return _guarded(data_dir, job, work)


# --- sound and the screen ----------------------------------------------------------------------------

def _level(setting: str, current: int) -> int:
    word = setting.strip().lower()
    if word == "up":
        return min(100, current + STEP)
    if word == "down":
        return max(0, current - STEP)
    if word.isdigit() and int(word) <= 100:
        return int(word)
    raise Refusal("A level is 0 to 100, up or down.")


def volume(data_dir: str, job: str, setting: str) -> None:
    def work(system) -> str:
        word = setting.strip().lower()
        if word in ("mute", "unmute"):
            system.set_volume(muted=word == "mute")
            return "Muted." if word == "mute" else "Sound is back on."
        current = system.volume()[0] if word in ("up", "down") else 0
        level = _level(word, current)
        system.set_volume(level=level)
        return f"Volume {level}."
    return _guarded(data_dir, job, work)


def brightness(data_dir: str, job: str, setting: str) -> None:
    def work(system) -> str:
        word = setting.strip().lower()
        current = system.brightness() if word in ("up", "down") else 0
        level = _level(word, current)
        system.set_brightness(level)
        return f"Brightness {level}."
    return _guarded(data_dir, job, work)


def wifi(data_dir: str, job: str, setting: str) -> None:
    def work(system) -> str:
        word = setting.strip().lower()
        if word not in ("on", "off"):
            raise Refusal("Wi-Fi is on or off.")
        system.set_wifi(word == "on")
        return "Wi-Fi is on." if word == "on" else "Wi-Fi is off. Your phone can't reach this PC until it's on again."
    return _guarded(data_dir, job, work)


# --- status and power --------------------------------------------------------------------------------

def status(data_dir: str, job: str) -> None:
    def work(system) -> str:
        state = system.status()
        battery = "" if state.battery_percent is None else (
            f" Battery {state.battery_percent}%{', charging' if state.charging else ''}.")
        top = ", ".join(f"{name} {size} MB" for name, size in state.top)
        return (f"Free RAM {state.free_gb:.1f} of {state.total_gb:.1f} GB.{battery} CPU {state.cpu_percent}%."
                + (f" Most memory: {top}." if top else ""))
    return _guarded(data_dir, job, work)


def lock(data_dir: str, job: str) -> None:
    def work(system) -> str:
        system.lock()
        return "Locked."
    return _guarded(data_dir, job, work)


def sleep(data_dir: str, job: str) -> None:
    def work(system) -> str:
        system.sleep()
        return "Going to sleep."
    return _guarded(data_dir, job, work)


def restart(data_dir: str, job: str) -> None:
    def work(system) -> str:
        system.restart()
        return "Restarting in 5 seconds."
    return _guarded(data_dir, job, work)


def shutdown(data_dir: str, job: str) -> None:
    def work(system) -> str:
        system.shutdown()
        return "Shutting down in 5 seconds."
    return _guarded(data_dir, job, work)
