"""The fence around your work folder (tasks.work_folder in config.yaml; BAR.md, "The work folder").

Guardian hands the folder to a file skill as a supplied argument, like data_dir, so a request can never set or change
it. A path is taken apart only after resolving its real location: anything outside the folder is refused, including
"..", symlinks and junctions that lead out, and other drives. A name with ":" is refused on every system: on Windows it
is a drive or a hidden stream, and Linux would take it as a plain name. So names are relative to the folder: a whole
Windows path is refused, even one inside it. files.read and files.summarize use this same fence when their code is added.
The word for a refusal is OutsideFolder; its text names the path you gave, never anything else.
"""

import fnmatch
import os
import re
from pathlib import Path

RESERVED = re.compile(r"(?:con|prn|aux|nul|com\d|lpt\d)(?:\..*)?", re.IGNORECASE)


class OutsideFolder(Exception):
    pass


def work_folder(folder) -> Path:
    """The folder itself, made on first use, with its real location."""
    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    return Path(os.path.realpath(path))


def inside(folder: Path, name: str) -> Path:
    """Where this name really is, if that is inside the folder. Relative names start at the folder.

    The real path is resolved all the way through existing symlinks and junctions. Raises OutsideFolder otherwise.
    """
    if not name or not name.strip():
        raise OutsideFolder("no file was named")
    for part in re.split(r"[\\/]", name):
        if part.rstrip(" .") != part and part not in ("", ".", ".."):
            raise OutsideFolder(f"'{name}' has a name Windows would change")
        if RESERVED.fullmatch(part):
            raise OutsideFolder(f"'{name}' has a name Windows keeps for itself")
    if ":" in name:  # a drive, a hidden stream, or a name Windows reads as either: never, on any system
        raise OutsideFolder(f"'{name}' is outside your work folder: a name with ':' is never taken")
    real = Path(os.path.realpath(folder / name))
    if "\\" in name and os.sep == "/":  # Linux takes "..\x" as a plain name; Windows would go up: the same answer on every system
        _check_inside(folder, Path(os.path.realpath(folder / name.replace("\\", "/"))), name)
    _check_inside(folder, real, name)
    return real


def _check_inside(folder: Path, real: Path, name: str) -> None:
    try:
        common = os.path.commonpath([str(folder), str(real)])
    except ValueError:  # another drive
        raise OutsideFolder(f"'{name}' is outside your work folder") from None
    if os.path.normcase(common) != os.path.normcase(str(folder)) or os.path.normcase(str(real)) == os.path.normcase(str(folder)):
        raise OutsideFolder(f"'{name}' is outside your work folder")


def rename(folder: Path, source: str, target: str) -> tuple[str, str]:
    """Rename inside the folder and overwrite nothing: (old name, new name), both relative to the folder.

    Raises OutsideFolder, or FileNotFoundError / FileExistsError / OSError for what is wrong with the files.
    """
    old, new = inside(folder, source), inside(folder, target)
    if not os.path.lexists(old):
        raise FileNotFoundError(f"there is no '{source}' in your work folder")
    if os.path.lexists(new) and not _same_file_new_case(old, new):
        raise FileExistsError(f"'{target}' already exists, and Kairu overwrites nothing")
    if not new.parent.is_dir():
        raise FileNotFoundError(f"the folder for '{target}' does not exist")
    os.rename(old, new)
    return str(old.relative_to(folder)), str(new.relative_to(folder))


def _same_file_new_case(old: Path, new: Path) -> bool:
    """Only the capitals change, on a system that does not tell them apart: the same file, not an overwrite."""
    return old != new and str(old).lower() == str(new).lower() and os.path.samefile(old, new)


# --- many names at once, finding by name, moving (Sprint Day 4) --------------------------------------------

MOST_FILES = 500  # one move takes at most this many
MOST_LOOKED_AT = 5000  # a find looks at no more names than this


def is_pattern(name: str) -> bool:
    return "*" in name or "?" in name


def matching(folder: Path, pattern: str) -> list[Path]:
    """Every name in one folder that fits a pattern such as *.pdf or notes/*.txt; case does not matter.

    Only the last part may hold * or ?, and "**" is refused. Each name found is checked with the fence again, so a link that
    leads out is left out. Links are never followed into.
    """
    parts = re.split(r"[\/]", pattern)
    if any(is_pattern(part) for part in parts[:-1]) or "**" in pattern:
        raise OutsideFolder(f"'{pattern}': only the last part of a name may hold * or ?")
    place = inside(folder, "/".join(parts[:-1])) if len(parts) > 1 else folder
    if not place.is_dir():
        raise FileNotFoundError(f"there is no folder '{'/'.join(parts[:-1])}' in your work folder")
    found = []
    for entry in sorted(os.scandir(place), key=lambda item: item.name.lower()):
        if fnmatch.fnmatch(entry.name.lower(), parts[-1].lower()):
            try:
                found.append(inside(folder, str(Path(entry.path).relative_to(folder))))
            except (OutsideFolder, ValueError):
                continue
    return found


def find(folder: Path, kinds: tuple[str, ...], words: tuple[str, ...], since: float | None) -> list[str]:
    """Names in the work folder and the folders in it, by name only: never opening a file. The newest first.

    kinds: patterns such as *.pdf (any one fits); words: each must be in the name; since: changed at or after this time.
    """
    found: list[tuple[float, str]] = []
    looked = 0
    for root, folders, files in os.walk(folder, followlinks=False):
        folders[:] = [name for name in folders if not _leads_away(Path(root) / name)]
        for name in files + folders:
            looked += 1
            if looked > MOST_LOOKED_AT:
                break
            low = name.lower()
            if kinds and not any(fnmatch.fnmatch(low, kind) for kind in kinds):
                continue
            if any(word not in low for word in words):
                continue
            path = Path(root) / name
            try:
                changed = path.lstat().st_mtime
            except OSError:
                continue
            if since is not None and changed < since:
                continue
            found.append((changed, str(path.relative_to(folder)).replace("\\", "/")))
    return [name for _, name in sorted(found, reverse=True)]


def _leads_away(path: Path) -> bool:
    """A link or junction: never walked into, wherever it leads."""
    return path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def move(folder: Path, source: str, into: str) -> tuple[list[tuple[str, str]], str]:
    """Move one name, or every name a pattern fits, into a folder inside the work folder, overwriting nothing.

    The folder is made if it isn't there (inside the work folder only). ([(old, new), ...] relative names, the folder made or
    ""). Everything is checked before anything moves: if one name would overwrite, nothing moves.
    Raises OutsideFolder, FileNotFoundError, FileExistsError, or OSError.
    """
    into = into.strip()
    if into not in ("", ".", "./", ".\\"):
        into = into.rstrip("/\\") or into  # "notes/" is notes; "/" alone, or "/tmp/x", is a whole path, refused below
    else:
        into = "."
    place = folder if into == "." else inside(folder, into)
    if os.path.lexists(place) and not place.is_dir():
        raise FileExistsError(f"'{into}' is a file, not a folder")
    if is_pattern(source):
        sources = matching(folder, source)
        if not sources:
            raise FileNotFoundError(f"nothing in your work folder fits '{source}'")
    else:
        one = inside(folder, source)
        if not os.path.lexists(one):
            raise FileNotFoundError(f"there is no '{source}' in your work folder")
        sources = [one]
    if len(sources) > MOST_FILES:
        raise OSError(f"that is {len(sources)} files; Kairu moves at most {MOST_FILES} at once")
    moves = []
    for item in sources:
        if item == place:
            continue  # the folder it goes into, which a pattern can fit too
        if item.parent == place:
            continue  # already there
        if os.path.commonpath([str(item), str(place)]) == str(item):
            raise OSError(f"'{item.relative_to(folder)}' can't go into a folder inside itself")
        target = place / item.name
        if os.path.lexists(target):
            raise FileExistsError(f"'{target.relative_to(folder)}' already exists, and Kairu overwrites nothing")
        moves.append((item, target))
    if not moves:
        raise FileExistsError(f"{'they are' if len(sources) > 1 else 'it is'} already in '{into}'")
    made = ""
    if not place.exists():
        if not place.parent.is_dir():
            raise FileNotFoundError(f"the folder for '{into}' does not exist")
        place.mkdir()
        made = str(place.relative_to(folder)).replace("\\", "/")
    done = []
    try:
        for item, target in moves:
            os.rename(item, target)
            done.append((_relative(folder, item), _relative(folder, target)))
    except OSError as error:
        raise PartlyMoved(done, made, error) from None
    return done, made


class PartlyMoved(OSError):
    """Some names moved before Windows refused one: what moved, so it can still be undone."""

    def __init__(self, done, made, error):
        super().__init__(f"moved {len(done)}, then Windows refused one ({type(error).__name__})")
        self.done, self.made = done, made


def _relative(folder: Path, path: Path) -> str:
    return str(path.relative_to(folder)).replace("\\", "/")
