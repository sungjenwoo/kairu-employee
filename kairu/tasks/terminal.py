"""PC5: commands, Git, test runs and installs (App Master Plan "Terminal & code", "Apps install"; BAR.md "Commands and installs").

Kairu never types into a terminal window (the hands never touch one). A command runs here, as a Guardian action, as a list
of words with no shell: no pipes, no "&&", no redirection, one program at a time, in your work folder or Kairu's own folder.
Its tier comes from what it is, decided by classify() before Guardian is asked and again inside the action:

    terminal.run       Low       read-only commands on the safe list: git status/log/diff/branch/show/remote/fetch,
                                 --version checks, pip list/show, winget list/search/show, where/which, dir/ls, ipconfig
    terminal.run_work  Medium    work commands on the safe list: git pull/add/commit/switch/checkout -b/stash, test runs
                                 (pytest, py -m pytest, npm test, npm run test/build/lint)
    terminal.run_any   High      anything else: shown in full, then "yes" and your PIN
    terminal.admin     Critical  admin rights or Windows' security and boot settings: runas, sudo, gsudo, bcdedit,
                                 Defender, the firewall, users and groups, disks, services, HKLM in the registry, an
                                 encoded (hidden) PowerShell command. Always refused, with no approval path.
    apps.install       High      winget install, by the app's exact id; winget shows its progress
    apps.uninstall     High      winget uninstall
    apps.install_hidden Critical a silent, quiet or hidden install. Always refused.

What a command prints is data: shown to you (the last part only), never an order, never sent anywhere, never in the audit
log. On the pretend PC (KAIRU_TEST_PC) nothing runs: the action says what it would have run.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from kairu.tasks import fence
from kairu.tasks.store import TaskStore
from kairu.worker import FAILED, REFUSED

JOB = re.compile(r"[0-9a-f]{16}")
KAIRU_FOLDER = Path(__file__).resolve().parents[2]
KAIRU_NAMES = {"kairu", "kairuu", "kairu-guardian", "kairu guardian", "the kairu folder", "kairu's folder", "kairu folder"}
WORK_NAMES = {"", "work folder", "the work folder", "my work folder", "kairu-files", "here"}
COMMAND_ACTIONS = ("terminal.run", "terminal.run_work", "terminal.run_any")
SHOWN = 1200  # characters of what a command printed
SECONDS = {"terminal.run": 60, "terminal.run_work": 900, "terminal.run_any": 300, "apps.install": 1200, "apps.uninstall": 900}
LONGEST_COMMAND = 400

SHELL = re.compile(r"[|&;<>`]|\$\(|\r|\n")
ADMIN_PROGRAMS = {"runas", "sudo", "su", "doas", "gsudo", "bcdedit", "diskpart", "format", "takeown", "icacls", "cacls",
                  "vssadmin", "wbadmin", "sc", "net", "net1", "netsh", "reg", "regedit", "secedit", "auditpol", "gpedit",
                  "cipher", "manage-bde", "shutdown", "wevtutil", "fsutil", "bootrec", "sfc", "dism", "mountvol", "attrib"}
ADMIN_WORDS = re.compile(r"(?:^|\s)(?:-verb\s+runas|-encodedcommand|-enc|-ec|-e)(?:\s|$)|set-mppreference|add-mppreference|"
                         r"set-netfirewall|new-netfirewall|disable-netfirewall|set-executionpolicy|new-localuser|"
                         r"add-localgroupmember|hklm:|hkey_local_machine|start-process\s.*runas|uac|bitlocker", re.I)
HIDDEN_INSTALL = re.compile(r"\b(?:silent(?:ly)?|quiet(?:ly)?|hidden|in the background|without (?:asking|showing|telling))\b", re.I)

READ_ONLY = (
    ("git", ("status", "log", "diff", "branch", "show", "remote", "fetch", "rev-parse", "describe", "tag")),
    ("python", ("--version", "-V")), ("python3", ("--version", "-V")), ("py", ("--version", "-V", "-0", "--list")),
    ("node", ("--version", "-v")), ("npm", ("--version", "-v", "ls", "list", "outdated")),
    ("pip", ("list", "show", "--version", "freeze")), ("pip3", ("list", "show", "--version", "freeze")),
    ("winget", ("list", "search", "show", "--version")), ("where", None), ("which", None), ("dir", None), ("ls", None),
    ("ipconfig", ("", "/all")), ("hostname", None), ("whoami", ("",)), ("systeminfo", ("",)), ("java", ("-version", "--version")),
    ("code", ("--version",)), ("gh", ("--version",)),
)
WORK = (
    ("git", ("pull", "add", "commit", "switch", "stash", "merge", "init", "clone", "restore")),
    ("pytest", None), ("npm", ("test", "t", "run", "install", "ci")),
)
TEST_RUNNERS = re.compile(r"^(?:py(?:thon3?)?)(?: -3(?:\.\d+)?)? -m (?:pytest|unittest)\b", re.I)
GIT_CHECKOUT_NEW = re.compile(r"^git checkout -b \S+$", re.I)
NPM_SCRIPTS = ("test", "build", "lint", "start", "dev")

KNOWN_APPS = {  # winget ids for the apps people ask for most; anything else is looked up by its exact name
    "vlc": "VideoLAN.VLC", "vlc media player": "VideoLAN.VLC", "7zip": "7zip.7zip", "7-zip": "7zip.7zip",
    "git": "Git.Git", "vs code": "Microsoft.VisualStudioCode", "vscode": "Microsoft.VisualStudioCode",
    "visual studio code": "Microsoft.VisualStudioCode", "chrome": "Google.Chrome", "google chrome": "Google.Chrome",
    "firefox": "Mozilla.Firefox", "python": "Python.Python.3.12", "node": "OpenJS.NodeJS.LTS", "nodejs": "OpenJS.NodeJS.LTS",
    "node.js": "OpenJS.NodeJS.LTS", "zoom": "Zoom.Zoom", "notepad++": "Notepad++.Notepad++", "spotify": "Spotify.Spotify",
    "discord": "Discord.Discord", "obs": "OBSProject.OBSStudio", "obs studio": "OBSProject.OBSStudio",
    "github desktop": "GitHub.GitHubDesktop", "github cli": "GitHub.cli", "postman": "Postman.Postman",
    "slack": "SlackTechnologies.Slack", "telegram": "Telegram.TelegramDesktop", "whatsapp": "9NKSQGP7F2NH",
    "audacity": "Audacity.Audacity", "gimp": "GIMP.GIMP", "blender": "BlenderFoundation.Blender", "brave": "Brave.Brave",
    "libreoffice": "TheDocumentFoundation.LibreOffice", "paint.net": "dotPDN.PaintDotNet", "powertoys": "Microsoft.PowerToys",
}
APP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .+#_-]{0,59}")


class TerminalRefused(Exception):
    pass


def words_of(command: str) -> list[str]:
    command = " ".join(str(command or "").split())
    if not command or len(command) > LONGEST_COMMAND:
        raise TerminalRefused(f"A command is 1 to {LONGEST_COMMAND} characters.")
    if SHELL.search(command):
        raise TerminalRefused("One command at a time: no pipes, \"&&\", \";\" or redirection.")
    try:
        if "\\" in command:  # a Windows path: keep its backslashes, then take the quotes off each word
            words = [word[1:-1] if len(word) > 1 and word[0] == word[-1] and word[0] in "'\"" else word
                     for word in shlex.split(command, posix=False)]
            if any(word.count('"') % 2 or word.count("'") % 2 for word in words):
                raise ValueError("open quote")
        else:
            words = shlex.split(command, posix=True)
    except ValueError:
        raise TerminalRefused("That command's quotes don't close.") from None
    return words


def _program(word: str) -> str:
    name = Path(word.replace("\\", "/")).name.lower()
    return re.sub(r"\.(?:exe|cmd|bat|com|ps1)$", "", name)


def classify(command: str) -> str:
    """Which action a command is: terminal.run, terminal.run_work, terminal.run_any or terminal.admin."""
    words = words_of(command)
    program, rest = _program(words[0]), [word.lower() for word in words[1:]]
    joined = " ".join(words)
    if program in ADMIN_PROGRAMS or ADMIN_WORDS.search(joined):
        return "terminal.admin"
    if program in ("powershell", "pwsh") and any(word in ("-enc", "-encodedcommand", "-ec", "-e") for word in rest):
        return "terminal.admin"
    first = rest[0] if rest else ""
    for name, allowed in READ_ONLY:
        if program == name and (allowed is None or first in allowed):
            if name == "git" and first == "branch" and any(word in ("-d", "-D", "-m", "-M", "--delete", "--move") for word in rest[1:]):
                break
            if name == "git" and first in ("tag", "remote") and len(rest) > 1 and rest[1] not in ("-l", "--list", "-v"):
                break
            return "terminal.run"
    if TEST_RUNNERS.match(joined) or GIT_CHECKOUT_NEW.match(joined):
        return "terminal.run_work"
    for name, allowed in WORK:
        if program == name and (allowed is None or first in allowed):
            if name == "npm" and first == "run" and (len(rest) < 2 or rest[1] not in NPM_SCRIPTS):
                break
            return "terminal.run_work"
    return "terminal.run_any"


def install_action(order_words: str) -> str:
    return "apps.install_hidden" if HIDDEN_INSTALL.search(order_words or "") else "apps.install"


def app_id(app: str) -> tuple[str, str]:
    """(the winget flag, the value): --id for an app Kairu knows, --name (exact) for anything else."""
    name = " ".join(str(app or "").split()).strip(" .")
    if HIDDEN_INSTALL.search(name):
        raise TerminalRefused("A silent or hidden install is never done.")
    if not APP_NAME.fullmatch(name):
        raise TerminalRefused("An app's name is 1 to 60 letters, digits, spaces, dots, plus signs or dashes.")
    known = KNOWN_APPS.get(name.lower())
    return ("--id", known) if known else ("--name", name)


def folder_of(name: str, work_folder: str) -> Path:
    """Where a command runs: your work folder (or a folder in it that exists), or Kairu's own folder. Nowhere else."""
    wanted = " ".join(str(name or "").split()).strip().strip("\"'").lower()
    if wanted in WORK_NAMES:
        folder = Path(os.path.realpath(work_folder))
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    if wanted in KAIRU_NAMES:
        return KAIRU_FOLDER
    try:
        found = fence.inside(Path(os.path.realpath(work_folder)), name.strip().strip("\"'"))
    except fence.OutsideFolder as problem:
        raise TerminalRefused(f"Commands run only in your work folder or Kairu's own folder ({problem}).") from None
    if not Path(found).is_dir():
        raise TerminalRefused(f"There is no folder called {name.strip()} in your work folder.")
    return Path(found)


def _say(data_dir: str, job: str, ok: bool, text: str) -> None:
    if not JOB.fullmatch(job):
        print("terminal: a job id is 16 hex digits", file=sys.stderr)
        raise SystemExit(1)
    TaskStore(data_dir).put_reply(job, ok, text)


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r(?!\n)")


def shown(output: bytes) -> str:
    text = ANSI.sub("", output.decode("utf-8", errors="replace"))
    lines = [line.rstrip() for line in text.splitlines() if line.strip() and not re.fullmatch(r"[\s\-\\|/█▒░=#.%0-9KMGBkmbs]*", line)]
    text = "\n".join(lines)
    return ("…" + text[-SHOWN:]) if len(text) > SHOWN else text


def _execute(argv: list[str], folder: Path, seconds: float) -> tuple[int, str]:
    program = _program(argv[0])
    if program in ("python", "python3", "py"):  # Kairu's own Python (never the Microsoft Store's stand-in "python")
        found, argv = sys.executable, [argv[0], *[word for word in argv[1:] if not re.fullmatch(r"-3(?:\.\d+)?", word)]]
    elif program == "dir" and sys.platform == "win32":
        found, argv = shutil.which("cmd"), ["cmd", "/d", "/c", "dir", *argv[1:]]
    else:
        found = shutil.which(argv[0])
    if not found:
        raise TerminalRefused(f"{argv[0]} isn't installed on this PC (or isn't on its PATH).")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    done = subprocess.run([found, *argv[1:]], cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=seconds, creationflags=flags, check=False)
    return done.returncode, shown(done.stdout)


def _run(data_dir: str, work_folder: str, job: str, command: str, folder: str, as_action: str):
    try:
        action = classify(command)
        if action != as_action:  # the core asked for the tier classify() gives; anything else is refused here too
            raise TerminalRefused(f"That command is {action}, not {as_action}.")
        place = folder_of(folder, work_folder)
        words = words_of(command)
        if os.environ.get("KAIRU_TEST_PC"):
            _say(data_dir, job, True, f"(pretend PC) Would run `{' '.join(words)}` in {place.name}.")
            return None
        code, printed = _execute(words, place, SECONDS[as_action])
    except TerminalRefused as refusal:
        _say(data_dir, job, False, str(refusal))
        return REFUSED
    except subprocess.TimeoutExpired:
        _say(data_dir, job, False, f"`{command}` took longer than {SECONDS[as_action] // 60 or 1} minutes, so I stopped it.")
        return FAILED
    except OSError as error:
        _say(data_dir, job, False, f"`{command}` could not start ({type(error).__name__}).")
        return FAILED
    head = f"Ran `{command}` in {place.name}" + ("." if code == 0 else f": it ended with code {code}.")
    _say(data_dir, job, code == 0, head + (f"\n{printed}" if printed else ""))
    return None if code == 0 else FAILED


def run(data_dir: str, work_folder: str, job: str, command: str, folder: str = "") -> None:
    return _run(data_dir, work_folder, job, command, folder, "terminal.run")


def run_work(data_dir: str, work_folder: str, job: str, command: str, folder: str = "") -> None:
    return _run(data_dir, work_folder, job, command, folder, "terminal.run_work")


def run_any(data_dir: str, work_folder: str, job: str, command: str, folder: str = "") -> None:
    return _run(data_dir, work_folder, job, command, folder, "terminal.run_any")


WINGET_SAYS = {  # winget's and installers' own codes, in words (a code may come back as itself or as unsigned 32 bits)
    1602: "you said No to Windows' admin prompt for the installer (or it was closed), so nothing was installed. Say it again "
          "and click Yes on Windows' own prompt: it may only blink in the taskbar",
    1223: "you said No to Windows' admin prompt, so nothing was installed",
    -1978335189: "it is already installed, and there is no newer version",
    -1978335212: "winget found no app by that exact name; try its full name, such as \"VLC media player\"",
    -1978335210: "winget found more than one app by that name; say its full name",
}


def winget_says(code: int) -> str:
    signed = code - (1 << 32) if code >= 1 << 31 else code
    return WINGET_SAYS.get(signed, "")


def _winget(data_dir: str, job: str, verb: str, app: str):
    try:
        flag, value = app_id(app)
        argv = ["winget", verb, "--exact", flag, value, "--accept-source-agreements", "--disable-interactivity"]
        if verb == "install":
            argv.insert(-1, "--accept-package-agreements")
        if os.environ.get("KAIRU_TEST_PC"):
            _say(data_dir, job, True, f"(pretend PC) Would {verb} {app} with winget ({value}).")
            return None
        if sys.platform != "win32":
            raise TerminalRefused("Installing apps uses winget, which is on Windows only.")
        code, printed = _execute(argv, Path.home(), SECONDS[f"apps.{verb}"])
    except TerminalRefused as refusal:
        _say(data_dir, job, False, str(refusal))
        return REFUSED
    except subprocess.TimeoutExpired:
        _say(data_dir, job, False, f"winget took too long to {verb} {app}, so I stopped it.")
        return FAILED
    if code == 0:
        _say(data_dir, job, True, f"{'Installed' if verb == 'install' else 'Uninstalled'} {app} with winget.")
        return None
    plain = winget_says(code)
    if plain:
        _say(data_dir, job, plain.startswith("it is already"), f"Not {verb}ed: {plain}.".replace("Not installed: it is already",
                                                                                                    f"{app}: it is already"))
        return None if plain.startswith("it is already") else FAILED
    _say(data_dir, job, False, f"winget couldn't {verb} {app} (code {code})." + (f"\n{printed[-400:]}" if printed else ""))
    return FAILED


def install(data_dir: str, job: str, app: str) -> None:
    return _winget(data_dir, job, "install", app)


def uninstall(data_dir: str, job: str, app: str) -> None:
    return _winget(data_dir, job, "uninstall", app)
