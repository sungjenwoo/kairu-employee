"""Builder powers (BUILDER.md "Sites, apps, slides and tests"): Kairu builds a small thing from a public brief.

    build.draft  (Low)     the free cloud AI (brain.build_providers, Gemini first) writes the files; they are read strictly
                           here and kept in data/builder.db as a draft. Nothing is written to your work folder yet.
    build.write  (Medium)  you saw the draft's files and said "yes": exactly those files (the same sha256) go into a NEW folder
                           in your work folder. Nothing is ever overwritten; nothing is written anywhere else.
    build.test   (High)    run the tests of a Python program the Builder made, with "yes" and your PIN: it is code an AI wrote.
                           Only a folder build.write made, only while its files are unchanged, with Python's own unittest.

The kinds:
    site    a website: index.html with its CSS and JavaScript, in one folder
    app     a web app (a calculator, a to-do list, a small game): index.html and its script, running in the browser
    slides  a slide deck: index.html, arrow keys to move, for a talk
    tests   a small Python program with unittest tests, for "build a python app that ..."

What a build can never be, whatever the AI writes (checked here, at build.write and at build.test):
    - a file outside its one new folder, or a kind of file not in its list (no .exe, .bat, .ps1, .lnk, ...);
    - a page that reaches the network: no remote script, style, picture or frame, no fetch, XMLHttpRequest, WebSocket,
      beacon or eval. A link you click (<a href="https://...">) is fine: your browser opens it when you click;
    - Python that reaches past its folder: only the standard modules in IMPORTS (and its own files), no open(), eval, exec,
      os, subprocess or socket;
    - a secret (the privacy filter's backstop reads every file).
"""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass

from kairu.brain import privacy
from kairu.build.store import BuilderStore, digest
from kairu.tasks import fence
from kairu.tasks.actions import Refusal, _guarded, _say
from kairu.tasks.terminal import shown
from kairu.worker import FAILED

MOST_FILES = 6
LONGEST_FILE = 30_000
LONGEST_BUILD = 60_000
TEST_SECONDS = 120
FOLDER = re.compile(r"[a-z0-9][a-z0-9-]{1,40}")
WEB = (".html", ".css", ".js", ".svg", ".json", ".md", ".txt")


@dataclass(frozen=True)
class Kind:
    name: str
    said: str  # how Kairu says it
    suffixes: tuple[str, ...]
    lead: str  # the line the brief follows, for the AI
    asks: str  # what the AI is told to make


KINDS = {
    "site": Kind("site", "a website", WEB, "Website brief", (
        "a beautiful, modern, responsive one-page website. index.html is the page; put the styles in style.css and any script "
        "in script.js. Use real, warm, specific words for the business or topic (headings, a hero line, sections, a call to "
        "action, a footer), a pleasing colour scheme, good spacing and system fonts. Shapes, gradients and emoji may stand in "
        "for pictures")),
    "app": Kind("app", "a web app", WEB, "Web app brief", (
        "a small, working web app that runs in the browser from index.html, with its script in app.js and styles in "
        "style.css. Make every button work. Keep data in memory (or localStorage if it must last). Clean, modern look")),
    "slides": Kind("slides", "a slide deck", WEB, "Slides brief", (
        "a slide deck in one index.html (styles and script inside it): 6 to 10 slides, one idea each, a big clear title and 2 to 4 "
        "short points per slide (a simple diagram drawn with boxes and arrows in HTML where it helps), a title slide first and "
        "a closing slide last; the arrow keys and a click move between slides, and a small "
        "counter shows the slide number. Good contrast, modern look")),
    "tests": Kind("tests", "a Python program with tests", (".py", ".md", ".txt", ".json", ".csv"), "Python program brief", (
        "a small Python program and its tests: the program in one or two .py files, and test_<name>.py files using only "
        "unittest (import unittest; class ...(unittest.TestCase)). Pure functions are best. Use only these standard modules: "
        "{imports}. No files, no network, no input(), no os, sys or subprocess. Add a short README.md")),
}
IMPORTS = ("__future__", "argparse", "contextlib", "numbers", "cmath", "pprint", "unittest", "math", "statistics", "random", "string", "re", "json", "datetime", "time", "collections", "itertools",
           "functools", "dataclasses", "typing", "decimal", "fractions", "enum", "textwrap", "operator", "heapq", "bisect",
           "copy", "calendar", "unicodedata", "abc")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,40}")

# A page that reaches the network is no build (WEB files): where a browser would fetch or send something by itself
NETWORK = re.compile(
    r"""\bsrc\s*=\s*["']?\s*(?:https?:)?//|<link\b[^>]*\bhref\s*=\s*["']?\s*(?:https?:)?//|@import\b|url\(\s*["']?\s*(?:https?:)?//|"""
    r"""\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|serviceWorker|importScripts|\beval\s*\(|new\s+Function\s*\(|"""
    r"""<\s*(?:iframe|object|embed|base|frame)\b|<form\b[^>]*\baction\s*=\s*["']?\s*(?:https?:)?//|http-equiv\s*=\s*["']?refresh|"""
    r"""document\s*\.\s*cookie|\blocation\s*(?:\.\s*(?:href|assign|replace)\s*)?=|\bimport\s*\(|\bimport\s+[^;]*\bfrom\s*["'](?:https?:)?//""",
    re.IGNORECASE)
CALLS_NEVER = {"open", "eval", "exec", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr",
               "breakpoint", "input", "exit", "quit", "memoryview"}
DUNDERS_FINE = {"__name__", "__doc__", "__init__"}
ATTRIBUTES_NEVER = {"system", "popen", "remove", "unlink", "rmdir", "removedirs", "rename", "replace", "rmtree", "kill",
                    "startfile", "write_text", "write_bytes", "open", "spawn", "fork", "chmod", "chown", "environ"}


# What the Builder is told when a brief names Kairu, so slides and pages about Kairu are true (from the team's own documents,
# "The problem and how Kairu solves it" and the 17 Nov recap). Only Kairu's own public pitch: nothing personal.
KAIRU = re.compile(r"\bkairu\b", re.I)
KAIRU_FACTS = (
    "Kairu is a voice-first AI teammate on every employee's Windows laptop, built by team Sung for Google's Startup "
    "Buildathon. The problem: employees start projects on time, yet deadlines still slip, because work gets lost between "
    "people, nobody sees a slip early, and the pressure lands on the employee at the end; companies pay in overtime, "
    "burnout and client trust. Today's AI tools help one person inside one app; none splits a whole project across a team "
    "and does the work. How Kairu works: the manager gives Main Kairu the project brief once; Main Kairu splits it into "
    "tasks, each with a 'Done when' check, by skill and workload, and tracks the deadline; a Kairu Clone on each employee's "
    "laptop does the clicking and typing while the employee guides it by voice. Guardian (plain rules, not AI) checks every "
    "step: Low runs, Medium asks you to type yes, High needs a typed yes plus a PIN on that laptop (a spoken yes or PIN "
    "never counts), and Critical (moving money, security "
    "changes, silent installs) is always refused; every action is logged and can be undone; personal memory stays on the "
    "laptop. A live deadline board flags slips early and Kairu answers 'how's the project going?' aloud; hand-offs start "
    "the next task on their own. A growth record notes facts about tasks (delivered early, on time), never a score or a "
    "ranking, and a person always decides. The Builder makes websites, web apps, slides and tested programs; Forge writes "
    "a new skill, tests it five times on a stand-in laptop and keeps it only with a PIN; Five Paths tries a big task five "
    "ways and a judge ranks them. Built on Google: Gemini for planning and building, Gemma for simple steps, and a Cloud "
    "Run, Pub/Sub and Firestore team layer on the roadmap. Who gains: employees (no handwork, less last-minute stress, good "
    "work gets seen), managers (projects split for them, early slip alerts) and the company (deadlines met, low cost, every "
    "action audited). First buyers: small and mid-size IT services firms, startups and agencies in Hyderabad, Bengaluru, "
    "Pune and Chennai, priced per laptop (free up to 5 laptops, then Team and Enterprise). Pitch line: Kairu doesn't just "
    "finish projects. It makes sure good work gets seen, and a person always decides.")


HARD_CODED = re.compile(r"\b(?:password|passwd|pwd|passcode|pin|otp|api_?key|secret|token)\s*[:=]\s*[\"'`][^\"'`\s]{4,}[\"'`]", re.I)


def secret_in_file(body: str) -> str:
    """A secret in a built file: a real key or token, a card or ID number, or a password written into the code. Not the
    privacy filter's sentence rules (a quoted colour code near the word "PIN" is code, not your PIN)."""
    for label, pattern in privacy.SECRET_PATTERNS:
        if pattern.search(body):
            return label
    for label, pattern, needs in privacy.CONTEXT_IDS:
        if pattern.search(body) and needs.search(body):
            return label
    found = privacy._secret_numbers(body)
    if found:
        return found[0]
    return "a password written into the code" if HARD_CODED.search(body) else ""


class NoBuild(Exception):
    """The AI's answer is not a build Kairu makes. Its text says why, shortly."""


def instructions(kind: str, brief: str = "") -> str:
    known = KINDS[kind]
    asks = known.asks.format(imports=", ".join(IMPORTS))
    about = f"What is true about Kairu (use these facts, never others about it): {KAIRU_FACTS}\n" if KAIRU.search(brief) else ""
    return (
        f"You are Kairu's Builder. Make {asks}.\n" + about +
        "- Use only facts the brief (and the facts above) give. Never invent names of people, dates, years, prices, awards, "
        "reviews, numbers or claims; where a detail is not given, write general, honest words instead.\n"
        "Reply in exactly this form and nothing else (no JSON, no markdown fences):\n"
        "FOLDER: <a short folder name: lower case letters, digits and dashes>\n"
        "=== FILE: <file name> ===\n<the whole file, as it is>\n=== END FILE ===\n"
        "(then the next file the same way)\n"
        f"- At most {MOST_FILES} files, all in that one folder (no sub-folders), each at most {LONGEST_FILE} characters. "
        f"File kinds allowed: {', '.join(known.suffixes)}.\n"
        + ("- The page must work offline from the file itself: never load anything from the internet (no CDN, no web fonts, "
           "no remote pictures, no fetch, no eval, no iframes). Links people click are fine.\n" if known.suffixes == WEB else "")
        + "- Never put a secret (a sign-in, key or token) in any file.\n"
        "- Write complete, working files with no placeholders.")


FOLDER_LINE = re.compile(r"^\W{0,3}folder\W{0,3}:\s*(?P<folder>.+?)\s*$", re.I)
FILE_LINE = re.compile(r"^\s*={2,}\s*file\s*:\s*(?P<name>.+?)\s*={2,}\s*$", re.I)
END_LINE = re.compile(r"^\s*={2,}\s*end(?: of)? file\s*={2,}\s*$", re.I)
FENCE = re.compile(r"^\s*```[\w+-]*\s*$")


def _finished(name: str, lines: list[str]) -> dict:
    while lines and FENCE.match(lines[0]):  # a fence the AI put around the file anyway
        lines.pop(0)
    while lines and (FENCE.match(lines[-1]) or not lines[-1].strip()):
        lines.pop()
    return {"name": name, "text": "\n".join(lines) + "\n"}


def _blocks(text: str, whole: bool = False) -> dict | None:
    """The answer in the file-by-file form ("FOLDER: ...", "=== FILE: name ===" ... "=== END FILE ==="), or None if it
    has none. whole: the provider said it finished writing (not cut off), so a LAST file with no end line is complete (AIs
    often leave that line out); a page still needs its </html>. Otherwise a file with no end line is unfinished: no build."""
    folder, files, name, lines = None, [], None, []
    for line in text.replace("\r\n", "\n").split("\n"):
        if name is None:
            start = FILE_LINE.match(line)
            if start:
                name, lines = start.group("name").strip("`*\"' "), []
            elif folder is None and FOLDER_LINE.match(line):
                folder = FOLDER_LINE.match(line).group("folder").strip("`*\"' ")
            continue
        if END_LINE.match(line):
            files.append(_finished(name, lines))
            name = None
        elif FILE_LINE.match(line):
            raise NoBuild(f"{name} wasn't finished before the next file began")
        else:
            lines.append(line)
    if name is not None:
        last = _finished(name, lines)
        if not whole or (name.lower().endswith((".html", ".htm")) and "</html>" not in last["text"].lower()):
            raise NoBuild(f"{name} wasn't finished (the answer was cut off)")
        files.append(last)
    return {"folder": folder or "", "files": files} if files else None


def _json(text: str, whole: bool = False) -> dict:
    """The build from the AI's answer: the file-by-file form first, else JSON (line breaks inside a file's text allowed)."""
    blocks = _blocks(text, whole)
    if blocks is not None:
        return blocks
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", body, re.DOTALL)
    if fenced:
        body = fenced.group(1)
    for attempt in (body, body[body.find("{"):body.rfind("}") + 1] if "{" in body else ""):
        try:
            data = json.loads(attempt, strict=False)  # an AI often leaves real line breaks inside a file's text
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise NoBuild("the AI's answer wasn't a build: no FILE blocks and no JSON")


def folder_name(said, brief: str = "") -> str:
    """The new folder's name: the AI's, if it is short plain words, else from the brief."""
    for text in (said if isinstance(said, str) else "", brief):
        name = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
        if FOLDER.fullmatch(name or ""):
            return name
    return "kairu-build"


def parse(text: str, kind: str, brief: str = "", whole: bool = False) -> tuple[str, list[dict]]:
    """(folder, [{"name", "text"}]) from the AI's answer, or NoBuild. whole: the provider finished writing (not cut off)."""
    data = _json(text, whole)
    if set(data) - {"folder", "files"} or not isinstance(data.get("files"), list):
        raise NoBuild("the AI's answer wasn't a build")
    files = [{"name": item.get("name"), "text": item.get("text")} if isinstance(item, dict) and set(item) <= {"name", "text"}
             else None for item in data["files"]]
    if None in files:
        raise NoBuild("a file in the build wasn't a name and its text")
    folder = folder_name(data.get("folder"), brief)
    check(kind, folder, files)
    return folder, files


def check(kind: str, folder: str, files: list[dict]) -> None:
    """Every rule a build must keep. Run when it is read, again at build.write, and (Python) again at build.test."""
    known = KINDS.get(kind)
    if known is None:
        raise NoBuild("that is not a kind of build Kairu makes")
    if not FOLDER.fullmatch(folder):
        raise NoBuild("the folder's name isn't short plain words")
    if not 1 <= len(files) <= MOST_FILES:
        raise NoBuild(f"a build has 1 to {MOST_FILES} files")
    names = [item["name"] for item in files]
    if len({name.lower() for name in names if isinstance(name, str)}) != len(names):
        raise NoBuild("two files had the same name")
    total = 0
    for item in files:
        name, body = item["name"], item["text"]
        if not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name or fence.RESERVED.fullmatch(name):
            raise NoBuild("a file's name isn't a plain name in the build's folder")
        if not name.lower().endswith(known.suffixes):
            raise NoBuild(f"{name} isn't a kind of file {known.said} may have ({', '.join(known.suffixes)})")
        if not isinstance(body, str) or not body.strip() or len(body) > LONGEST_FILE or "\x00" in body:
            raise NoBuild(f"{name} is empty or too long")
        total += len(body)
        secret = secret_in_file(body)
        if secret:
            raise NoBuild(f"{name} had {secret}, so it isn't made")
        if name.lower().endswith((".html", ".css", ".js", ".svg")):
            found = NETWORK.search(body)
            if found:
                raise NoBuild(f"{name} would reach the network ({found.group(0).strip()[:30]}), and a built page never does")
        if name.lower().endswith(".py"):
            python_problem(name, body, {other[:-3] for other in names if other.lower().endswith(".py")})
    if total > LONGEST_BUILD:
        raise NoBuild(f"a build is at most {LONGEST_BUILD} characters")
    lowered = [name.lower() for name in names]
    if known.suffixes == WEB and "index.html" not in lowered:
        raise NoBuild("a page needs its index.html")
    if kind == "tests" and not (any(re.fullmatch(r"test_\w+\.py", name) for name in lowered)
                                and any(name.endswith(".py") and not name.startswith("test_") for name in lowered)):
        raise NoBuild("a Python build needs its program and a test_*.py")


def python_problem(name: str, body: str, own: set[str]) -> None:
    try:
        tree = ast.parse(body, name)
    except SyntaxError as error:
        raise NoBuild(f"{name} isn't valid Python (line {error.lineno})") from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""] if not node.level else []  # "from . import x": its own files
        else:
            modules = []
        for module in modules:
            top = module.split(".")[0]
            if top not in IMPORTS and top not in own:
                raise NoBuild(f"{name} imports {module}, and a build uses only safe standard modules and its own files")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CALLS_NEVER:
            raise NoBuild(f"{name} calls {node.func.id}(), which a build never does")
        if isinstance(node, ast.Name) and node.id in ("__builtins__", "__loader__", "__spec__"):
            raise NoBuild(f"{name} reaches {node.id}, which a build never does")
        if isinstance(node, ast.Attribute):
            if node.attr in ATTRIBUTES_NEVER or (node.attr.startswith("__") and node.attr.endswith("__")
                                                 and node.attr not in DUNDERS_FINE):
                raise NoBuild(f"{name} uses .{node.attr}, which a build never does")


def summary(kind: str, folder: str, files: list[dict]) -> str:
    sizes = ", ".join(f"{item['name']} ({len(item['text']):,} characters)" for item in files)
    return f"{KINDS[kind].said.capitalize()} in a new folder {folder}: {sizes}"


# --- build.draft ---------------------------------------------------------------------------------------------

def free_name(folder: str, work_folder: str) -> str:
    """The build's folder name, or name-2, name-3 ... if that is already in your work folder (only names are looked at)."""
    try:
        place = fence.work_folder(work_folder)
    except OSError:
        return folder
    for number in range(1, 100):
        name = folder if number == 1 else f"{folder[:37]}-{number}"
        if not os.path.lexists(place / name):
            return name
    return folder  # build.write says it is there, and makes nothing


def draft(data_dir: str, brief: str, kind: str, ask: str, source: str, brain: dict | None = None,
          work_folder: str = "") -> None:
    """The AI writes the build; it is read strictly and kept as a draft. Only a short summary is the answer."""
    from kairu.brain.ask import _check, _keep
    from kairu.brain.gateway import ANSWERED, CUT_OFF, NOT_SENT, REFUSED, Gateway, Result
    _check(ask, source)
    if kind not in KINDS:
        return _keep(data_dir, ask, source, Result(REFUSED, "L3", "That is not a kind of build Kairu makes."))
    result = Gateway(data_dir, brain).build(brief, source, instructions(kind, brief), lead=KINDS[kind].lead)
    if result.status != ANSWERED:
        return _keep(data_dir, ask, source, result)
    if CUT_OFF in result.note:
        return _keep(data_dir, ask, source, Result(NOT_SENT, "L3", "The build was too long for the AI's answer and got cut "
                                                                     "off. Ask for something a little smaller.", result.provider))
    try:
        folder, files = parse(result.text, kind, brief, whole=True)
    except NoBuild as why:
        return _keep(data_dir, ask, source, Result(NOT_SENT, "L3", f"The build didn't come out right ({why}). Try again, or say "
                                                                     "it more simply.", result.provider))
    if work_folder:
        folder = free_name(folder, work_folder)  # so the folder you are shown is the one build.write makes
    BuilderStore(data_dir).add_draft(ask, kind, folder, files)
    _keep(data_dir, ask, source, Result(ANSWERED, "L3", summary(kind, folder, files), result.provider, seconds=result.seconds))


# --- build.write ---------------------------------------------------------------------------------------------

def write(data_dir: str, job: str, draft: float, sha: str, work_folder: str) -> None:
    """Exactly the draft you were shown (its sha256), into a NEW folder in your work folder. Nothing is overwritten."""
    def work(_) -> str:
        store = BuilderStore(data_dir)
        found = store.draft(int(draft))
        if found is None or found["state"] != "drafted":
            raise Refusal("Not made: that build is gone or already made. Ask for it again.")
        if sha != found["sha256"] or digest({"kind": found["kind"], "folder": found["folder"], "files": found["files"]}) != sha:
            raise Refusal("Not made: that build isn't the one you were shown.")
        try:
            check(found["kind"], found["folder"], found["files"])
        except NoBuild as why:
            raise Refusal(f"Not made: {why}.") from None
        try:
            place = fence.inside(fence.work_folder(work_folder), found["folder"])
        except fence.OutsideFolder as problem:
            raise Refusal(f"Not made: {problem}.") from None
        if os.path.lexists(place):
            raise Refusal(f"Not made: {found['folder']} is already in your work folder, and Kairu overwrites nothing.")
        made, hashes = [], {}
        try:
            place.mkdir()
            for item in found["files"]:
                data = item["text"].encode("utf-8")
                target = place / item["name"]
                with open(target, "xb") as file:
                    file.write(data)
                made.append(target)
                hashes[item["name"]] = hashlib.sha256(data).hexdigest()
        except OSError as error:
            for target in made:  # only the files this build just made, in the folder it just made
                target.unlink(missing_ok=True)
            if place.is_dir() and not any(place.iterdir()):
                place.rmdir()
            raise Refusal(f"Not made: Windows refused it ({type(error).__name__}).") from None
        store.made(found["id"], found["folder"], found["kind"], hashes)
        return f"Made {found['folder']} in your work folder: {', '.join(hashes)}."
    return _guarded(data_dir, job, work)


# --- build.test ----------------------------------------------------------------------------------------------

class TestsFailed(Exception):
    pass


def test(data_dir: str, job: str, folder: str, work_folder: str) -> None:
    """The tests of a Python program the Builder made, unchanged since build.write made it, with unittest and no shell."""
    def work(_) -> str:
        build = BuilderStore(data_dir).build(folder.strip())
        if build is None or build["kind"] != "tests":
            raise Refusal(f"Not run: {folder[:60]} isn't a Python program the Builder made.")
        try:
            place = fence.inside(fence.work_folder(work_folder), build["folder"])
        except fence.OutsideFolder as problem:
            raise Refusal(f"Not run: {problem}.") from None
        if not place.is_dir():
            raise Refusal(f"Not run: {build['folder']} isn't in your work folder any more.")
        files = []
        for name, made in build["files"].items():
            target = place / name
            try:
                data = target.read_bytes()
            except OSError:
                raise Refusal(f"Not run: {name} is gone from {build['folder']}.") from None
            if hashlib.sha256(data).hexdigest() != made:
                raise Refusal(f"Not run: {name} changed since the Builder made it, so these aren't the tests you saw.")
            files.append({"name": name, "text": data.decode("utf-8")})
        extra = sorted(item.name for item in place.iterdir() if item.suffix.lower() == ".py" and item.name not in build["files"])
        if extra:
            raise Refusal(f"Not run: {', '.join(extra[:3])} wasn't made by the Builder.")
        try:
            check("tests", build["folder"], files)
        except NoBuild as why:
            raise Refusal(f"Not run: {why}.") from None
        if os.environ.get("KAIRU_TEST_PC"):
            return f"(pretend PC) Would run the tests in {build['folder']} with unittest."
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            done = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", ".", "-t", ".", "-p", "test_*.py"],
                                  cwd=place, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=TEST_SECONDS, creationflags=flags, check=False)
        except subprocess.TimeoutExpired:
            raise Refusal(f"The tests took longer than {TEST_SECONDS // 60} minutes, so I stopped them.") from None
        printed = shown(done.stdout)
        ran = re.search(r"Ran (\d+) tests?", printed)
        head = (f"The tests in {build['folder']} passed ({ran.group(1) if ran else 'all'} ran)." if done.returncode == 0 else
                f"The tests in {build['folder']} failed.")
        if done.returncode != 0:
            raise TestsFailed(head + (f"\n{printed}" if printed else ""))
        return head
    try:
        return _guarded(data_dir, job, work)
    except TestsFailed as failed:  # they ran, and failed: shown to you, never an order
        _say(data_dir, job, False, str(failed))
        return FAILED
