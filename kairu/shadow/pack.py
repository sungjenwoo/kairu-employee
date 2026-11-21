"""A skill pack: one use case for Kairu, as a small folder a friend builds in a Shadow's workspace (SHADOW.md).

    packs/NAME/
        pack.json       {"pack": 1, "name": NAME, "title", "description", "version", "entry": "skill.py", "made_by"}
        skill.py        def run(text: str) -> str      what Kairu calls: your words in, its answer out
        README.md       what it does, how to use it, what it needs
        tests/test_*.py unittest tests that `import skill`; they must all pass (`python -m kairu.shadow check` runs them)

check() says what is still wrong with a folder ([] when it is a pack). It is the same check on the friend's laptop
(before the Shadow may come home) and on the owner's PC (before an install), and it only reads:

  - text files only, of the kinds in SUFFIXES; no links, no hidden files, nothing above the limits below;
  - its Python imports the standard library and the pack's own files only, so installing it installs nothing else;
  - skill.py has run(text).

uses() names what a pack's code reaches for (the network, other programs, files, Windows itself), from its imports.
It is shown to the owner before "yes" and the PIN. It is a reading aid, not a fence: a pack is code, and the owner
decides about it by reading the pull request and by the PIN.

digest() is one SHA-256 over the pack's file names and contents (line ends made the same, so Windows and Linux agree).
The Shadow signs it in its return report; an install takes only a folder with exactly that digest.

Standard library only: this module also runs on the friend's laptop.
"""

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from kairu.shadow.kinds import MAX_PACK_NAME, PACK_NAME

MANIFEST, ENTRY, README, TESTS = "pack.json", "skill.py", "README.md", "tests"
SUFFIXES = (".py", ".md", ".json", ".txt", ".yaml", ".yml", ".csv")
MOST_FILES, MOST_BYTES, MOST_FILE_BYTES = 60, 512 * 1024, 128 * 1024
SKIPPED = ("__pycache__",)  # Python's own leftovers: never part of a pack
README_LINES = 5  # a README says at least this much
UNFINISHED = "KAIRU-SHADOW-TODO"  # the scaffold's marker: a file that still has it is not written yet
MANIFEST_KEYS = {"pack", "name", "title", "description", "version", "entry", "made_by"}
TEST_SECONDS, RUN_SECONDS, MOST_OUTPUT = 180, 60, 20000

USES = {  # a module a pack imports -> what that lets its code reach
    "network": ("socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "xmlrpc", "socketserver",
                "asyncio", "webbrowser"),
    "other programs": ("subprocess", "multiprocessing", "pty", "runpy", "code", "importlib"),
    "files": ("os", "shutil", "pathlib", "io", "glob", "tempfile", "sqlite3", "zipfile", "tarfile", "fileinput"),
    "Windows itself": ("ctypes", "winreg", "msvcrt", "_winapi", "signal"),
}

# Guardian and the Shadow's background part run with no console: on Windows, a console program they start (git, python)
# would open a black window of its own for a moment. This keeps it hidden. Every subprocess in kairu/shadow uses it.
HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

RUNNER = """
import importlib.util, sys
folder, entry = sys.argv[1], sys.argv[2]
sys.path.insert(0, folder)
spec = importlib.util.spec_from_file_location("kairu_pack_skill", folder + "/" + entry)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
answer = module.run(sys.stdin.read())
sys.stdout.write(answer if isinstance(answer, str) else repr(answer))
"""


class PackProblem(Exception):
    pass


def files(folder) -> list[Path]:
    """Every file of the pack, sorted, as paths relative to the folder. Raises PackProblem for a link or a strange entry."""
    folder, found = Path(folder), []
    for here, names, leaves in os.walk(folder, followlinks=False):
        names[:] = sorted(name for name in names if name not in SKIPPED)
        for name in names + sorted(leaves):
            path = Path(here) / name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise PackProblem(f"{path.relative_to(folder).as_posix()} is a link or not a plain file: a pack holds files only")
        found += [(Path(here) / leaf).relative_to(folder) for leaf in sorted(leaves)]
    return sorted(found, key=lambda path: path.as_posix())


def _text(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def digest(folder) -> str:
    """One SHA-256 for the whole pack: every file's name and content, in order."""
    total = hashlib.sha256(b"kairu-pack-v1\n")
    for relative in files(folder):
        total.update(f"{relative.as_posix()}\n{hashlib.sha256(_text(Path(folder) / relative)).hexdigest()}\n".encode())
    return total.hexdigest()


def manifest(folder) -> dict:
    """pack.json, checked. Raises PackProblem."""
    try:
        data = json.loads((Path(folder) / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackProblem(f"there is no {MANIFEST}") from None
    except (OSError, ValueError) as error:
        raise PackProblem(f"{MANIFEST} cannot be read ({type(error).__name__})") from None
    if not isinstance(data, dict) or set(data) != MANIFEST_KEYS:
        raise PackProblem(f"{MANIFEST} must have exactly: {', '.join(sorted(MANIFEST_KEYS))}")
    if data["pack"] != 1 or not all(isinstance(data[key], str) for key in MANIFEST_KEYS - {"pack"}):
        raise PackProblem(f'{MANIFEST}: "pack" is 1 and everything else is text')
    if not good_name(data["name"]):
        raise PackProblem(f"{MANIFEST}: the name is small letters, digits and dashes, at most {MAX_PACK_NAME} long")
    if data["entry"] != ENTRY:
        raise PackProblem(f'{MANIFEST}: "entry" is {ENTRY}')
    for key, most in (("title", 60), ("description", 300), ("version", 20), ("made_by", 40)):
        if not data[key].strip() or len(data[key]) > most or not data[key].isprintable():
            raise PackProblem(f'{MANIFEST}: "{key}" is 1 to {most} printable characters')
    return data


def good_name(name) -> bool:
    return isinstance(name, str) and len(name) <= MAX_PACK_NAME and bool(PACK_NAME.fullmatch(name))


def check(folder, name: str | None = None) -> list[str]:
    """What is still wrong with this folder as a pack, in plain words; [] when nothing is. It only reads."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        return ["there is no pack folder"]
    try:
        found, about = files(folder), manifest(folder)
    except PackProblem as problem:
        return [str(problem)]
    problems = []
    if name is not None and about["name"] != name:
        problems.append(f'{MANIFEST} names the pack "{about["name"]}", but this Shadow\'s pack is "{name}"')
    total = 0
    for relative in found:
        size = (folder / relative).stat().st_size
        total += size
        shown = relative.as_posix()
        if any(part.startswith(".") for part in relative.parts):
            problems.append(f"{shown}: no hidden files in a pack")
        elif relative.suffix.lower() not in SUFFIXES:
            problems.append(f"{shown}: a pack holds text files only ({' '.join(SUFFIXES)})")
        elif size > MOST_FILE_BYTES:
            problems.append(f"{shown} is larger than {MOST_FILE_BYTES // 1024} KB")
    if len(found) > MOST_FILES or total > MOST_BYTES:
        problems.append(f"a pack is at most {MOST_FILES} files and {MOST_BYTES // 1024} KB together")
    if problems:
        return problems
    names = {relative.as_posix() for relative in found}
    sources = {}
    for relative in found:
        if relative.suffix.lower() != ".py":
            continue
        try:
            sources[relative] = ast.parse((folder / relative).read_text(encoding="utf-8"))
        except (SyntaxError, ValueError, UnicodeDecodeError) as error:
            problems.append(f"{relative.as_posix()} is not Python that runs ({type(error).__name__})")
    if ENTRY not in names:
        problems.append(f"there is no {ENTRY}")
    elif Path(ENTRY) in sources and not _has_run(sources[Path(ENTRY)]):
        problems.append(f"{ENTRY} needs `def run(text)`: your words in, the answer out as text")
    if README not in names:
        problems.append(f"there is no {README}")
    else:
        lines = [line for line in (folder / README).read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if len(lines) < README_LINES:
            problems.append(f"{README} is not written yet (it needs at least {README_LINES} lines: what it does, how to use it)")
    if not any(relative.parts[0] == TESTS and relative.name.startswith("test_") and relative.suffix == ".py"
               for relative in found if len(relative.parts) > 1):
        problems.append(f"there are no tests ({TESTS}/test_*.py)")
    own = {relative.parts[0].removesuffix(".py") for relative in sources}
    foreign = sorted({module for tree in sources.values() for module in _imports(tree)
                      if module not in sys.stdlib_module_names and module not in own})
    if foreign:
        problems.append(f"it imports {', '.join(foreign)}: a pack uses Python's standard library and its own files only")
    for relative in found:
        if UNFINISHED in (folder / relative).read_text(encoding="utf-8", errors="replace"):
            problems.append(f"{relative.as_posix()} still has the {UNFINISHED} marker: finish it and take the marker out")
    return problems


def _has_run(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            wanted = node.args
            return len(wanted.posonlyargs) + len(wanted.args) >= 1 and \
                len(wanted.posonlyargs) + len(wanted.args) - len(wanted.defaults) <= 1 and \
                not [arg for arg, default in zip(wanted.kwonlyargs, wanted.kw_defaults) if default is None]
    return False


def _imports(tree: ast.Module) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def uses(folder) -> list[str]:
    """What the pack's code reaches for, from its imports: some of "network", "other programs", "files", "Windows itself"."""
    folder, modules = Path(folder), set()
    for relative in files(folder):
        if relative.suffix.lower() == ".py" and relative.parts[0] != TESTS:
            try:
                modules |= _imports(ast.parse((folder / relative).read_text(encoding="utf-8")))
            except (SyntaxError, ValueError, UnicodeDecodeError):
                pass
    return [what for what, names in USES.items() if modules & set(names)]


def _quiet_environment() -> dict:
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}


def run_tests(folder, seconds: float = TEST_SECONDS) -> tuple[bool, int, str]:
    """Run the pack's tests in the pack's folder. (all passed, how many ran, the last lines of what they printed)."""
    try:
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", TESTS], cwd=str(folder),
                              capture_output=True, text=True, timeout=seconds, stdin=subprocess.DEVNULL,
                              env={**_quiet_environment(), "PYTHONPATH": str(folder)}, errors="replace", **HIDDEN)
    except subprocess.TimeoutExpired:
        return False, 0, f"the tests were still running after {seconds:g} seconds"
    except OSError as error:
        return False, 0, f"the tests could not be started ({error})"
    said = (done.stderr or "") + (done.stdout or "")
    ran = 0
    for line in said.splitlines():
        words = line.split()
        if len(words) >= 3 and words[0] == "Ran" and words[1].isdigit() and words[2].startswith("test"):
            ran = int(words[1])
    tail = "\n".join(said.strip().splitlines()[-12:])
    return done.returncode == 0 and ran > 0, ran, tail or "(the tests printed nothing)"


def run(folder, text: str, seconds: float = RUN_SECONDS) -> tuple[bool, str]:
    """Call the pack's run(text) in a program of its own. (it worked, its answer or why not)."""
    try:
        done = subprocess.run([sys.executable, "-c", RUNNER, str(folder), ENTRY], input=text, capture_output=True,
                              text=True, timeout=seconds, cwd=str(folder), env=_quiet_environment(), errors="replace",
                              **HIDDEN)
    except subprocess.TimeoutExpired:
        return False, f"it was still running after {seconds:g} seconds, so it was ended"
    except OSError as error:
        return False, f"it could not be started ({error})"
    if done.returncode != 0:
        return False, ("it failed: " + (done.stderr or "").strip().splitlines()[-1][:300]) if done.stderr.strip() else "it failed"
    return True, done.stdout[:MOST_OUTPUT]
