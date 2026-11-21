"""Kairu's hands (PC4, first part): type, press keys, click and read in an app's window, so a task is handled, not just begun.

"Open Chrome, then in the search bar type Instagram": apps.open opens Chrome; screen.type waits for Chrome's window, brings
it to the front, puts the cursor in its search bar and types. Each step is its own Guardian action, decided by policy.yaml:

    screen.read     Low, read-only   the names of the buttons, links and boxes in an app's window: shown, never an order
    screen.type     Medium           type words where the cursor is, or into the app's search or address bar (and Enter there)
    screen.press    Medium           keys that move, edit or navigate: Tab, arrows, Esc, Ctrl+T, Ctrl+C, Alt+Left, F5 ...
    screen.click    Medium           click a button, link, tab or menu item by the name you see on it
    screen.confirm  High             the same hands, after your "yes" and PIN, for a step that may send, submit or delete:
                                     Enter where it could send, Delete, a "Send" / "Post" / "Delete" button, personal words,
                                     or any step in an app that is not on the safe list

What these hands never do, whatever the order, the plan or the page says (refused here, with no approval path):
  - touch Kairu's own windows (the bar, the workspace, any Python window): no code ever fills the yes and PIN boxes;
  - touch security, password, terminal, registry or system tools (SECURITY_APPS), or a bank or payment page or app;
  - click Pay, Buy, Checkout, Place order or the like (money is Critical in policy.yaml), or press Win, Ctrl+Alt+... or
    Shift+Delete;
  - type a secret (a password, PIN, OTP, key, card or ID number): secrets never leave your hands, not even with your PIN;
  - type an address with any scheme but http or https into a browser's address bar (javascript:, file:, chrome: ...);
  - type into a window that is no longer in front: it stops the moment another window comes to the front.

Window titles and page text are data: a title is only compared, to refuse (a bank page), never to allow; what screen.read
finds is shown to you and never becomes an order. An app is found by its program's name (chrome, notepad), never its title.

PC4, the rest (ADR-042 proposed, BAR.md "Reading any window, numbers and the safe list"):

    screen.read_text  Low, read-only  the words a window shows (a document, its boxes, its lists, a page): shown, never an order.
                                      When Windows' UI Automation gives no words, a picture of that one window is read by
                                      Windows' own OCR: the picture stays in memory on this PC, is never written or sent, and
                                      is gone when the step ends
    screen.numbers    Low, read-only  the buttons, links and tabs you can click, numbered, so you can say "click 3"
    hands.safe_list   Low, read-only  which apps are on Kairu's safe list
    hands.mark_safe   High            put one more app on the safe list (your yes and PIN); never a terminal, an editor with
                                      a terminal, remote desktop, a security, password or money app, or Kairu's own
    hands.unmark_safe Medium          take an app you marked off the list again

A click whose name UI Automation can't find is looked for on the same kind of picture; the words found there decide its
tier exactly as a button's name does, and the real mouse clicks only inside that window, while it is in front.

The screen agent's other steps (ADR-054 proposed, BAR.md "Kairu's eyes"):

    screen.scroll          Medium  the mouse wheel over an app's window, 1 to 10 notches (any app but the never-ones)
    screen.choose          Medium  pick an item from a list or drop-down by both names, in a safe app
    screen.tick            Medium  tick or untick a box by its name, in a safe app ("I agree" asks first)
    screen.point           Medium  a click at a point Gemini named on a look's picture: what UI Automation or the picture's
                                   words say is there decides, as a click by name does; nothing readable there asks first
    screen.fill            Medium  one of your saved details (kairu/tasks/details.py) typed into a box by its name, in the
                                   browser, only on the site the run is locked to; never a password box
    screen.saved_password  Medium  the browser's own saved-login entry with your username, so the browser fills the password;
                                   Kairu never reads or types a password (no entry: "Your turn")
    screen.agent_confirm   High    inside a take-control run you started: what screen.confirm does, after your "yes" (no PIN,
                                   policy.yaml pin: false, the only such action)
"""

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from kairu.brain import privacy
from kairu.research import quarantine
from kairu.tasks import pc, web
from kairu.tasks.actions import Refusal, _guarded, _windows_of

NEEDS_PIN = "Needs your yes and PIN: "  # a skill's reply starting with this: the core asks again as screen.confirm (High)
YOUR_TURN = "Your turn: "  # a skill's reply starting with this: the screen agent hands over to you (ADR-054)
ACTIONS = ("screen.type", "screen.press", "screen.click", "screen.read", "screen.read_text", "screen.numbers",
           "screen.scroll")
SAFE_LIST_ACTIONS = ("hands.mark_safe", "hands.unmark_safe", "hands.safe_list")
VERBS = {"screen.type": "type", "screen.press": "press", "screen.click": "click", "screen.choose": "choose",
         "screen.tick": "tick", "screen.point": "point"}
WHAT_DETAIL = {"type": "text", "press": "keys", "click": "target", "choose": "item", "tick": "target", "point": "point"}
MOST_NOTCHES = 10
AGREE_WORDS = re.compile(r"\b(?:i agree|agree|accept|i accept|consent|terms|privacy policy|subscribe|newsletter)\b",
                         re.IGNORECASE)
APP_WAIT = 10.0  # seconds to wait for a just-opened app's window
SETTLE = 1.5  # seconds a just-opened app gets to come to the front by itself
LONGEST_TEXT = 500
MOST_SHOWN = 30

# --- which apps ---------------------------------------------------------------------------------------

BROWSERS = frozenset({"chrome", "msedge", "firefox", "brave", "opera", "vivaldi"})
# The apps whose typing, keys and plain clicks are Medium. Any other app: every step there needs your yes and PIN
# (App Master Plan: "unknown app actions start at High until the owner marks them safe"). The owner adds an app here, in a
# pull request, to mark it safe.
SAFE_APPS = BROWSERS | frozenset({"notepad", "wordpad", "explorer", "winword", "excel", "powerpnt", "onenote", "spotify",
                                  "mspaint", "stickynotes"})
# Enter only makes a new line (or the answer) here, so "press enter" is Medium; in any other app it may send or submit.
NEW_LINE_APPS = frozenset({"notepad", "wordpad", "winword", "onenote", "stickynotes"})
KAIRU_PROGRAMS = frozenset({"python", "pythonw", "py", "pyw", "kairu"})
KAIRU_TITLES = re.compile(r"kairu|kairu bar(?: .*)?", re.IGNORECASE)  # the workspace's page title and the bar's own title
KAIRU_PROFILE = "workspace-profile"  # the workspace's own browser profile folder (kairu/workspace/app.py)
SECURITY_APPS = frozenset({
    "securityhealthui", "sechealthui", "securityhealthsystray", "msmpeng", "mpcmdrun", "windowsdefender", "consent",
    "credentialuibroker", "logonui", "lockapp", "keepass", "keepassxc", "1password", "bitwarden", "lastpass", "dashlane",
    "nordpass", "enpass", "cmd", "powershell", "pwsh", "windowsterminal", "wt", "conhost", "openconsole", "wsl", "bash",
    "regedit", "mmc", "gpedit", "taskmgr", "msconfig", "control", "systemsettings", "msiexec", "services", "secpol",
    "certmgr", "wf", "netplwiz", "useraccountcontrolsettings", "rstrui", "diskmgmt", "diskpart", "format",
    "phonepe", "paytm", "gpay", "googlepay", "paypal",
})
MONEY_TITLE = re.compile(
    r"\b(?:net ?banking|internet banking|online banking|bank|banking|paypal|paytm|phonepe|google pay|gpay|razorpay|billdesk|"
    r"stripe checkout|upi|payment|payments|checkout|check out|pay now|credit card|debit card|wallet|demat|zerodha|groww|"
    r"upstox|angel one|sbi|hdfc|icici|axis bank|kotak|yes bank|canara|pnb|bank of baroda)\b", re.IGNORECASE)
PROGRAM_NAMES = {  # what you call an app -> its program's name
    "google chrome": "chrome", "chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge", "firefox": "firefox",
    "brave": "brave", "opera": "opera", "vivaldi": "vivaldi", "notepad": "notepad", "wordpad": "wordpad",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer", "word": "winword", "microsoft word": "winword",
    "excel": "excel", "microsoft excel": "excel", "powerpoint": "powerpnt", "onenote": "onenote", "spotify": "spotify",
    "paint": "mspaint", "sticky notes": "stickynotes",
}
BROWSER = "browser"  # the app of a step after web.open: Kairu's browser, Chrome or Edge, whichever is in front
# Apps that can never go on the safe list, not even with your PIN (each step there still asks for it, or is refused): where
# typed words can run commands (terminals, editors and IDEs with a terminal inside, remote desktops that reach another PC's
# terminal), Windows' own frame and shell hosts (one name for many apps), and everything SECURITY_APPS already refuses.
NEVER_SAFE = SECURITY_APPS | KAIRU_PROGRAMS | frozenset({
    "applicationframehost", "explorer_frame", "shellexperiencehost", "startmenuexperiencehost", "searchhost", "searchapp",
    "textinputhost", "rundll32", "dllhost", "svchost", "sihost", "ctfmon", "runtimebroker", "werfault",
    "code", "code - insiders", "code-insiders", "cursor", "windsurf", "trae", "kiro", "antigravity", "devenv", "idea64", "idea",
    "pycharm64", "pycharm", "webstorm64", "clion64", "rider64", "goland64", "phpstorm64", "rubymine64", "datagrip64", "studio64",
    "eclipse", "netbeans64", "zed", "fleet", "spyder", "jupyter-lab", "notepad++", "sublime_text", "atom", "vim", "gvim", "nvim-qt",
    "mintty", "putty", "kitty", "alacritty", "wezterm-gui", "hyper", "tabby", "mobaxterm", "termius", "git-bash", "cygwin",
    "mstsc", "msrdc", "anydesk", "teamviewer", "rustdesk", "vncviewer", "tvnviewer", "parsecd", "chrome_remote_desktop",
    "quickassist", "virtualbox", "virtualboxvm", "vmware", "vmplayer", "vmconnect", "docker desktop",
})
SAFE_LIST = "hands-safe.json"  # in Guardian's data folder: the apps you marked safe, written only by hands.mark_safe/unmark_safe
NUMBERS = "screen-numbers.json"  # in Guardian's data folder: the names screen.numbers last showed, for "click 3"
NUMBERS_SECONDS = 300  # "click 3" means the numbers shown within this long
MOST_NUMBERED = 30
LONGEST_READ = 1500  # characters of a window's words shown at once
FEW_LETTERS = 3  # fewer letters than this from UI Automation: the picture is read instead
CLICKABLE = pc.CLICKABLE

# --- keys ----------------------------------------------------------------------------------------------

KEY_NAMES = {
    "enter": "enter", "return": "enter", "tab": "tab", "esc": "escape", "escape": "escape", "space": "space",
    "spacebar": "space", "backspace": "backspace", "back space": "backspace", "delete": "delete", "del": "delete",
    "up": "up", "down": "down", "left": "left", "right": "right", "up arrow": "up", "down arrow": "down",
    "left arrow": "left", "right arrow": "right", "arrow up": "up", "arrow down": "down", "arrow left": "left",
    "arrow right": "right", "home": "home", "end": "end", "page up": "pageup", "pageup": "pageup", "page down": "pagedown",
    "pagedown": "pagedown", "plus": "plus", "minus": "minus", "insert": "insert", "windows": "win", "win": "win",
    **{f"f{number}": f"f{number}" for number in range(1, 13)},
    **{letter: letter for letter in "abcdefghijklmnopqrstuvwxyz0123456789"},
}
MODIFIERS = {"ctrl": "ctrl", "control": "ctrl", "shift": "shift", "alt": "alt", "win": "win", "windows": "win"}
# Medium: keys that move, edit or navigate, and never send, submit or delete anything
SAFE_KEYS = frozenset({
    "tab", "shift+tab", "escape", "space", "backspace", "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "shift+up", "shift+down", "shift+left", "shift+right", "shift+home", "shift+end", "ctrl+left", "ctrl+right",
    "ctrl+home", "ctrl+end", "ctrl+a", "ctrl+c", "ctrl+x", "ctrl+v", "ctrl+z", "ctrl+y", "ctrl+f", "ctrl+s", "ctrl+t",
    "ctrl+w", "ctrl+n", "ctrl+l", "ctrl+tab", "ctrl+shift+tab", "ctrl+shift+t", "ctrl+plus", "ctrl+minus", "ctrl+0",
    "alt+left", "alt+right", "f5", "ctrl+r", "f11", "f3", "ctrl+b", "ctrl+i", "ctrl+u",
    *{f"ctrl+{digit}" for digit in "123456789"},
})
# High: keys that may send, submit or delete. ("enter" is Medium only in NEW_LINE_APPS, or when the cursor is in a search or
# address bar: then it is a search, which the skill checks when it runs)
CAREFUL_KEYS = frozenset({"enter", "ctrl+enter", "shift+enter", "alt+enter", "delete", "alt+f4", "ctrl+d", "ctrl+p",
                          "ctrl+shift+delete", "ctrl+shift+n", "ctrl+shift+esc", "ctrl+o", "f2"})
NEVER_KEYS = re.compile(r"(?:^|\+)win(?:\+|$)|ctrl\+alt\+|alt\+ctrl\+|shift\+delete", re.IGNORECASE)
MOST_KEYS = 3

# --- clicks --------------------------------------------------------------------------------------------

MONEY_WORDS = re.compile(
    r"\b(?:pay|pay now|payment|payments|buy|buy now|purchase|checkout|check out|place (?:your )?order|order now|confirm order|"
    r"donate|send money|transfer|add (?:a )?card|add money|recharge|top up|subscribe now|upgrade now|proceed to pay)\b",
    re.IGNORECASE)
CAREFUL_WORDS = re.compile(
    r"\b(?:send|submit|post|publish|share|upload|delete|remove|discard|erase|clear|reset|confirm|accept|agree|allow|grant|"
    r"install|uninstall|update|apply|reply|comment|tweet|retweet|repost|follow|unfollow|subscribe|unsubscribe|join|invite|"
    r"block|report|sign in|sign out|log in|log out|login|logout|sign up|register|save changes|turn off|disable|forward|"
    r"call|video call|add to cart|book|reserve)\b", re.IGNORECASE)

# --- fields --------------------------------------------------------------------------------------------

FIELDS = {"": "", "search": "search", "address": "address"}
ADDRESS_WORDS = re.compile(r"address|url|location|omnibox", re.IGNORECASE)


def field_of(words: str) -> str:
    """"search bar", "address bar", "url bar" ... as search or address; "" for where the cursor is."""
    words = (words or "").strip().lower()
    if not words:
        return ""
    return "address" if ADDRESS_WORDS.search(words) else "search"


def program_of(name: str) -> str:
    """The program's name for what you call an app ("Google Chrome" -> chrome); "" for the app in front."""
    words = " ".join((name or "").lower().split())
    if words in ("", "it", "this", "that", "there", "here", "the app", "this app", "that app", "the window", "this window",
                 "that window", "the screen", "screen", "this screen", "the one in front", "the app in front"):
        return ""
    if words in (BROWSER, "the browser", "my browser", "kairu's browser", "web browser"):
        return BROWSER
    return PROGRAM_NAMES.get(words, words)


def keys_of(words: str) -> str:
    """"Ctrl T", "control + shift + tab", "enter" -> ctrl+t, ctrl+shift+tab, enter. Refusal if it isn't keys Kairu knows."""
    text = re.sub(r"\b(?:the|keys?|button)\b", " ", (words or "").lower())
    tokens = text.replace("+", " ").split()
    held = []
    while tokens and tokens[0] in MODIFIERS:
        held.append(MODIFIERS[tokens.pop(0)])
    name = " ".join(tokens)
    if not name and held:  # "press windows", "press ctrl": a modifier alone is the key
        name = held.pop()
    if name not in KEY_NAMES:
        raise Refusal(f"I don't know the key '{name[:20]}'." if name else "Which key?")
    if len(held) + 1 > MOST_KEYS or len(set(held)) != len(held):
        raise Refusal("I press one key, with at most two of Ctrl, Shift and Alt.")
    order = [mod for mod in ("ctrl", "shift", "alt", "win") if mod in held]
    return "+".join([*order, KEY_NAMES[name]])


def key_tier(keys: str, app: str, field: str = "") -> str:
    """"medium", "high" or "never" for these keys in this app's program."""
    if NEVER_KEYS.search(keys) or keys == "win":
        return "never"
    if keys == "enter" and (app in NEW_LINE_APPS or field):
        return "medium"
    if keys in SAFE_KEYS:
        return "medium"
    return "high"


def click_tier(target: str) -> str:
    if MONEY_WORDS.search(target or ""):
        return "never"
    return "high" if CAREFUL_WORDS.search(target or "") else "medium"


def text_problem(text: str) -> str:
    """Why these words can't be typed at all ("" if they can)."""
    if not text or len(text) > LONGEST_TEXT:
        return f"I type 1 to {LONGEST_TEXT} characters."
    if re.search(r"[\x00-\x1f\x7f]", text):
        return "I type one line of plain text."
    verdict = privacy.classify(text)
    if verdict.secret:
        return f"Not typed: it has {verdict.why()}. Kairu never types a secret, not even with your PIN."
    return ""


def text_is_personal(text: str) -> bool:
    return privacy.classify(text).personal


def address_problem(text: str) -> str:
    """For a browser's address bar: any scheme but http or https is refused (javascript:, file:, chrome:, edge:, about: ...)."""
    words = text.strip()
    scheme = web.SCHEME.match(words)
    if scheme and scheme.group(1).lower() not in ("http", "https"):
        return f"Refused: Kairu types only http and https addresses into a browser, not {scheme.group(1).lower()}:."
    if re.match(r"(?:about|chrome|edge|brave|opera|vivaldi|view-source|javascript|file|data|vbscript)\s*:", words, re.IGNORECASE):
        return "Refused: Kairu types only http and https addresses into a browser."
    if re.match(r"\\\\|[a-z]:[\\/]", words, re.IGNORECASE):
        return "Refused: Kairu doesn't type a path into a browser."
    return ""


@dataclass(frozen=True)
class Target:
    window: pc.Window
    app: str  # the program's name, as Windows says it


# --- finding the window --------------------------------------------------------------------------------

def _kairu_window(system, window) -> bool:
    if window.app in KAIRU_PROGRAMS or KAIRU_TITLES.fullmatch(window.title.strip()):
        return True
    try:
        return KAIRU_PROFILE in system.command_line(window).lower()
    except (pc.PcProblem, OSError):
        return False


def _usable(system, window) -> bool:
    return bool(window.app) and not _kairu_window(system, window) and not (window.app == "explorer" and window.title == "Program Manager")


def _check_window(system, window) -> None:
    """Refuse a window these hands must never touch. A title is only ever used to refuse."""
    if _kairu_window(system, window):
        raise Refusal("Refused: Kairu never types or clicks in its own windows.")
    if window.app in SECURITY_APPS:
        raise Refusal(f"Refused: Kairu doesn't type or click in {window.app}: security, passwords, terminals and money stay yours.")
    if MONEY_TITLE.search(window.title or ""):
        raise Refusal("Refused: that window looks like a bank or payment page, and money stays yours.")


def find(system, app: str, wait: float | None = None) -> Target:
    """The front window of this app (by its program's name), waiting a little for a just-opened one; for "" the app in front.

    A just-opened app comes to the front by itself, so when the app has a window but another app is in front, it gets SETTLE
    seconds to do so: then a new Chrome window is used, not an older one behind it.
    """
    deadline = time.monotonic() + (APP_WAIT if wait is None else wait)
    settle = None
    while True:
        windows = [window for window in system.windows() if _usable(system, window)]
        if app == "" and windows:
            return Target(windows[0], windows[0].app)
        if app:
            wanted = [window for window in windows if window.app in BROWSERS] if app == BROWSER else _of(system, app, windows)
            if wanted:
                front = system.foreground()
                if front is not None and front.app == wanted[0].app:
                    return Target(next((window for window in wanted if window.handle == front.handle), wanted[0]), wanted[0].app)
                if front is None or _kairu_window(system, front):  # you just gave the order in the bar: nothing is opening
                    return Target(wanted[0], wanted[0].app)
                settle = settle or time.monotonic() + SETTLE
                if time.monotonic() >= settle:
                    return Target(wanted[0], wanted[0].app)
        if time.monotonic() >= deadline:
            raise Refusal("No app window is open." if not app else f"{'A browser' if app == BROWSER else app} isn't open.")
        time.sleep(0.1)


def _of(system, app: str, usable: list) -> list:
    """This app's usable windows, front first, by its program's name only (as apps.close and apps.arrange find them)."""
    handles = {window.handle for window in usable}
    try:
        return [window for window in _windows_of(system, app) if window.handle in handles]
    except Refusal:
        return []


def _seen(system, app: str) -> Target:
    """The window a read looks at: never Kairu's own (refused by name, before any window is looked for), security or money."""
    if program_of(app) in KAIRU_PROGRAMS or "kairu" in (app or "").lower():
        raise Refusal("Refused: Kairu never reads, types or clicks in its own windows.")
    target = find(system, program_of(app) if app not in ("", BROWSER) else app)
    _check_window(system, target.window)
    return target


def _ready(system, app: str) -> Target:
    if program_of(app) in KAIRU_PROGRAMS or "kairu" in (app or "").lower():
        raise Refusal("Refused: Kairu never types or clicks in its own windows.")
    target = find(system, program_of(app) if app not in ("", BROWSER) else app)
    _check_window(system, target.window)
    system.bring_to_front(target.window)
    return target


def _name(target: Target) -> str:
    return {"msedge": "Edge", "chrome": "Chrome", "explorer": "File Explorer", "winword": "Word", "powerpnt": "PowerPoint"}.get(
        target.app, target.app[:1].upper() + target.app[1:])


def _needs_pin(why: str):
    return Refusal(f"{NEEDS_PIN}{why}")


# --- the safe list: the built-in apps, and the ones you marked safe with your PIN ----------------------------

def never_safe_why(program: str) -> str:
    """Why this program can never go on the safe list ("" if it can)."""
    program = (program or "").strip().lower()
    if not program or program in KAIRU_PROGRAMS or "kairu" in program:
        return "Kairu's own windows are never typed or clicked in."
    if program in NEVER_SAFE:
        return f"{program} can run commands or holds security, passwords or money, so every step there stays yours."
    if MONEY_TITLE.search(program):
        return "money stays yours."
    if not re.fullmatch(r"[a-z0-9][a-z0-9 ._+-]{0,40}", program):
        return "that isn't a program's name."
    return ""


def owner_safe(data_dir: str) -> tuple[str, ...]:
    """The apps you marked safe (hands.mark_safe), each checked again on every read: a name that may never be safe is
    dropped even if the file has it."""
    try:
        kept = json.loads((Path(data_dir) / SAFE_LIST).read_text(encoding="utf-8")).get("apps", [])
    except (OSError, ValueError, AttributeError):
        return ()
    names = []
    for item in kept if isinstance(kept, list) else []:
        name = str(item.get("app", "") if isinstance(item, dict) else "").strip().lower()
        if name and not never_safe_why(name) and name not in names:
            names.append(name)
    return tuple(names)


def safe_apps(data_dir: str) -> frozenset:
    return SAFE_APPS | frozenset(owner_safe(data_dir))


def _save_safe(data_dir: str, names: list[str]) -> None:
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    spare = folder / (SAFE_LIST + ".new")
    spare.write_text(json.dumps({"apps": [{"app": name, "marked": int(time.time())} for name in names]}), encoding="utf-8")
    os.replace(spare, folder / SAFE_LIST)


# --- File Explorer: folders by name, never a program ------------------------------------------------------

KNOWN_FOLDERS = {"downloads": "downloads", "download": "downloads", "documents": "documents", "docs": "documents",
                 "desktop": "desktop", "pictures": "pictures", "photos": "pictures", "music": "music", "videos": "videos"}
FOLDER_PATH = re.compile(r"[A-Za-z]:\\(?:[^<>\"|?*%\x00-\x1f\\]+\\?)*")  # a whole path on a drive: no \\server, no %VARIABLE%


def explorer_folder(system, text: str) -> str:
    """The folder these words mean in File Explorer's address bar, as a full path ("" if they aren't a folder): Downloads,
    Documents, Desktop, Pictures, Music, Videos, or a whole path of a folder that exists. Typed there, a folder can only be
    opened, never started; anything else in that bar still needs your yes and PIN."""
    words = " ".join((text or "").lower().split())
    words = re.sub(r"^(?:my |the )", "", words)
    words = re.sub(r" folder$", "", words)
    if words in KNOWN_FOLDERS:
        try:
            return system.known_folder(KNOWN_FOLDERS[words]) or ""
        except (pc.PcProblem, OSError):
            return ""
    path = (text or "").strip()
    if FOLDER_PATH.fullmatch(path) and os.path.isdir(path):
        return os.path.normpath(path)
    return ""


# --- the skills ------------------------------------------------------------------------------------------

def _type(system, app: str, text: str, field: str, enter: str, confirmed: bool, safe: frozenset = SAFE_APPS) -> str:
    field = FIELDS.get((field or "").strip().lower(), None)
    if field is None:
        raise Refusal("I type where the cursor is, or into a search or address bar.")
    pressing = (enter or "no").strip().lower() in ("yes", "true", "1", "enter")
    problem = text_problem(text)
    if problem:
        raise Refusal(problem)
    if not confirmed and text_is_personal(text):
        raise _needs_pin("those words look personal.")
    if pressing and not field and not confirmed:
        raise _needs_pin("pressing Enter there may send or submit something.")
    target = _ready(system, app)
    if not confirmed and target.app not in safe:
        raise _needs_pin(f"{_name(target)} isn't on Kairu's safe list yet.")
    if target.app in BROWSERS and field:
        problem = address_problem(text)
        if problem:
            raise Refusal(problem)
    folder = ""
    if field == "address" and target.app == "explorer":
        folder = explorer_folder(system, text)
        if folder:
            text = folder  # the folder's whole path: Explorer opens it, and starts nothing
    if field == "address" and target.app not in BROWSERS and not folder:
        if not confirmed:
            raise _needs_pin(f"typing into {_name(target)}'s address bar can start programs.")
    where = ""
    if field:
        where = system.focus_field(target.window, field, target.app in BROWSERS)
    system.type_text(target.window, text)
    if pressing:
        system.press(target.window, "enter")
    if folder and pressing:
        return f"Opened {Path(folder).name or folder} in {_name(target)}."
    said = f'Typed "{text}"' if len(text) <= 60 else f"Typed {len(text)} characters"
    return f"{said} in {_name(target)}{' ' + where if where else ''}{' and pressed Enter' if pressing else ''}."


def _press(system, app: str, keys: str, confirmed: bool, safe: frozenset = SAFE_APPS) -> str:
    keys = keys_of(keys)
    tier = key_tier(keys, program_of(app) if app else "")
    if tier == "never":
        raise Refusal(f"Refused: Kairu never presses {keys.title()}.")
    target = _ready(system, app)
    tier = key_tier(keys, target.app)
    if tier == "never":
        raise Refusal(f"Refused: Kairu never presses {keys.title()}.")
    if not confirmed and target.app not in safe:
        raise _needs_pin(f"{_name(target)} isn't on Kairu's safe list yet.")
    searching = keys == "enter" and target.app not in NEW_LINE_APPS and system.focus_is_search(target.window)
    if not confirmed and tier == "high" and not searching:
        raise _needs_pin(f"{keys.title()} may send, submit or delete something in {_name(target)}.")
    system.press(target.window, keys)
    return f"Searched in {_name(target)}." if searching else f"Pressed {keys.title()} in {_name(target)}."


def spot(lines, wanted: str):
    """Where these words are on a picture of the window: (the words found, the whole line they are in, x, y), or None.
    The same words, any capitals, first; else the shortest line that has them. Lines are {"text", "words": [[w, x, y, wd, ht]]}."""
    want = " ".join(wanted.lower().split())
    size = len(want.split())
    best = None
    for line in lines:
        words = [item for item in line.get("words", []) if isinstance(item, (list, tuple)) and len(item) == 5]
        said = [str(item[0]) for item in words]
        for start in range(0, max(0, len(said) - size + 1)):
            if " ".join(said[start:start + size]).lower().strip(".,:;!?") == want:
                span = words[start:start + size]
                left, top = min(item[1] for item in span), min(item[2] for item in span)
                right = max(item[1] + item[3] for item in span)
                bottom = max(item[2] + item[4] for item in span)
                return " ".join(said[start:start + size]), str(line.get("text", "")), int((left + right) / 2), int((top + bottom) / 2)
        text = str(line.get("text", ""))
        if want and want in text.lower() and words and len(text) <= 60 and (best is None or len(text) < len(best[0])):
            left, top = min(item[1] for item in words), min(item[2] for item in words)
            right, bottom = max(item[1] + item[3] for item in words), max(item[2] + item[4] for item in words)
            best = (text, text, int((left + right) / 2), int((top + bottom) / 2))
    return best


def _click(system, app: str, target_name: str, confirmed: bool, safe: frozenset = SAFE_APPS) -> str:
    wanted = " ".join((target_name or "").split()).strip(" \"'“”")
    if not wanted or len(wanted) > 80:
        raise Refusal("Which button or link? Say the name you see on it.")
    if click_tier(wanted) == "never":
        raise Refusal("Refused: Kairu never clicks pay, buy or checkout. Money stays yours.")
    if not confirmed and click_tier(wanted) == "high":
        raise _needs_pin(f'"{wanted}" may send, submit or delete something.')
    target = _ready(system, app)
    if not confirmed and target.app not in safe:
        raise _needs_pin(f"{_name(target)} isn't on Kairu's safe list yet.")
    found = system.find_control(target.window, wanted)
    if not found:
        return _click_on_picture(system, target, wanted, confirmed)
    if click_tier(found) == "never":  # what it is really called decides, not only what you said
        raise Refusal("Refused: Kairu never clicks pay, buy or checkout. Money stays yours.")
    if not confirmed and click_tier(found) == "high":
        raise _needs_pin(f'"{found}" may send, submit or delete something.')
    system.click_control(target.window, found)
    return f'Clicked "{found}" in {_name(target)}.'


def _click_on_picture(system, target: Target, wanted: str, confirmed: bool) -> str:
    """The backup way (PC4): the words on a picture of that one window, read by Windows' own OCR. The picture stays in memory
    on this PC. The whole line the words are in decides the tier, as a button's real name does ("order" on "Place order")."""
    try:
        lines = system.read_picture(target.window)
    except pc.PcProblem:
        lines = []
    seen = spot(lines, wanted)
    if not seen:
        raise Refusal(f'I can\'t find "{wanted}" in {_name(target)}.')
    words, line, x, y = seen
    if click_tier(line) == "never" or click_tier(words) == "never":
        raise Refusal("Refused: Kairu never clicks pay, buy or checkout. Money stays yours.")
    if not confirmed and (click_tier(line) == "high" or click_tier(words) == "high"):
        raise _needs_pin(f'"{line}" may send, submit or delete something.')
    system.click_point(target.window, x, y)
    return f'Clicked "{words}" in {_name(target)} (found on a picture of the window).'


def type_text(data_dir: str, job: str, app: str, text: str, field: str = "", enter: str = "no") -> None:
    return _guarded(data_dir, job, lambda system: _type(system, app, text, field, enter, False, safe_apps(data_dir)))


def press(data_dir: str, job: str, app: str, keys: str) -> None:
    return _guarded(data_dir, job, lambda system: _press(system, app, keys, False, safe_apps(data_dir)))


def click(data_dir: str, job: str, app: str, target: str) -> None:
    return _guarded(data_dir, job, lambda system: _click(system, app, target, False, safe_apps(data_dir)))


def read(data_dir: str, job: str, app: str) -> None:
    """The names in the window, as data: shown to you, never an order."""
    def work(system) -> str:
        target = find(system, program_of(app) if app not in ("", BROWSER) else app)
        _check_window(system, target.window)
        seen = system.read_controls(target.window)
        if not seen:
            return f"{_name(target)} shows nothing I can read."
        groups: dict[str, list[str]] = {}
        for kind, name in seen[:200]:
            names = groups.setdefault(kind, [])
            short = " ".join(name.split())[:40]
            if short and short not in names:
                names.append(short)
        parts, shown = [], 0
        for kind in ("box", "button", "link", "tab", "menu", "item", "text"):
            names = groups.get(kind, [])[:max(0, MOST_SHOWN - shown)]
            if names:
                parts.append(f"{kind}s: " + ", ".join(names))
                shown += len(names)
        return f"In {_name(target)}: " + "; ".join(parts) + "."
    return _guarded(data_dir, job, work)


def quoted(lines, most: int) -> tuple[str, int]:
    """A window's words as text Kairu may show: lines that give orders ("Kairu, delete my files") or hold a secret left out,
    each line once, short. (the text, how many lines were left out)"""
    safe, removed = quarantine.safe_lines("\n".join(str(line) for line in lines))
    text = "\n".join(line for line in safe if len(line) > 1)
    if len(text) > most:
        text = text[:most].rsplit(" ", 1)[0] + " …"
    return text, removed


def read_text(data_dir: str, job: str, app: str) -> None:
    """screen.read_text (Low, read-only): the words this window shows, as data: shown to you, never an order, sent nowhere.
    A browser: its page. Any other app: its document, boxes, lists and labels through UI Automation; if that gives no words,
    a picture of that one window read by Windows' own OCR, kept in memory on this PC and gone when the step ends."""
    def work(system) -> str:
        target = _seen(system, app)
        lines = system.read_page(target.window) if target.app in BROWSERS else system.read_text(target.window)
        picture, why = False, ""
        if len("".join(str(line) for line in lines).strip()) < FEW_LETTERS:
            try:
                lines = [str(line.get("text", "")) for line in system.read_picture(target.window)]
                picture = True
            except pc.PcProblem as problem:
                why = str(problem)
        text, removed = quoted(lines, LONGEST_READ)
        if not text:
            return f"{_name(target)} shows no words I can read{f' ({why})' if why else ''}."
        notes = []
        if removed:
            notes.append(f"I left out {removed} line{'s' if removed != 1 else ''} giving orders or holding a secret.")
        if picture:
            notes.append("Read from a picture of the window, which stayed in memory on this PC.")
        return f"{_name(target)} shows: {text}" + "".join(f"\n({note})" for note in notes)
    return _guarded(data_dir, job, work)


def numbers(data_dir: str, job: str, app: str) -> None:
    """screen.numbers (Low, read-only): what you can click in this window, numbered, so "click 3" can name it. The names are
    kept in Guardian's data folder for NUMBERS_SECONDS, only to turn your number back into the name; they are data."""
    def work(system) -> str:
        target = _seen(system, app)
        names: list[str] = []
        for kind, name in system.read_controls(target.window):
            short = " ".join(str(name).split())[:60]
            if kind in CLICKABLE and short and short not in names:
                names.append(short)
            if len(names) >= MOST_NUMBERED:
                break
        folder = Path(data_dir)
        folder.mkdir(parents=True, exist_ok=True)
        spare = folder / (NUMBERS + ".new")
        spare.write_text(json.dumps({"app": target.app, "made": time.time(), "names": names}), encoding="utf-8")
        os.replace(spare, folder / NUMBERS)
        if not names:
            return f"{_name(target)} shows nothing I can click by name."
        listed = ", ".join(f"{number} {name}" for number, name in enumerate(names, 1))
        return f'In {_name(target)}: {listed}. Say "click" and a number.'
    return _guarded(data_dir, job, work)


def confirm(data_dir: str, job: str, verb: str, app: str, what: str, field: str = "", enter: str = "no") -> None:
    """screen.confirm (High): you said yes and typed your PIN for exactly this step. Everything refused above still is."""
    def work(system) -> str:
        if verb not in ("type", "press", "click", "choose", "tick", "point"):
            raise Refusal("Refused: that isn't a step Kairu's hands take.")
        return _confirmed(system, verb, app, what, field, enter)
    return _guarded(data_dir, job, work)


# --- the screen agent's other steps (ADR-054 proposed) ------------------------------------------------------------

def _scroll(system, app: str, direction: str, times: str) -> str:
    direction = (direction or "").strip().lower()
    if direction not in ("up", "down"):
        raise Refusal("I scroll up or down.")
    try:
        notches = int(str(times).strip() or "3")
    except ValueError:
        raise Refusal(f"I scroll 1 to {MOST_NOTCHES} notches.") from None
    if not 1 <= notches <= MOST_NOTCHES:
        raise Refusal(f"I scroll 1 to {MOST_NOTCHES} notches.")
    target = _ready(system, app)  # never Kairu's own, security, password, terminal or money windows
    system.scroll(target.window, notches if direction == "up" else -notches)
    return f"Scrolled {direction} in {_name(target)}."


def _choose(system, app: str, box: str, item: str, confirmed: bool, safe: frozenset = SAFE_APPS) -> str:
    box, item = " ".join((box or "").split()), " ".join((item or "").split())
    if not box or not item or len(box) > 80 or len(item) > 80:
        raise Refusal("Say the list's name and the item, as you see them.")
    for words in (box, item):
        if click_tier(words) == "never":
            raise Refusal("Refused: Kairu never picks pay, buy or checkout. Money stays yours.")
        if not confirmed and click_tier(words) == "high":
            raise _needs_pin(f'"{words}" may send, submit or delete something.')
    target = _ready(system, app)
    if not confirmed and target.app not in safe:
        raise _needs_pin(f"{_name(target)} isn't on Kairu's safe list yet.")
    chosen = system.choose(target.window, box, item)
    if click_tier(chosen) == "never":  # what it is really called decides, not only what was asked
        raise Refusal("Refused: Kairu never picks pay, buy or checkout. Money stays yours.")
    return f'Chose "{chosen}" in "{box}" in {_name(target)}.'


def _tick(system, app: str, box: str, on: str, confirmed: bool, safe: frozenset = SAFE_APPS) -> str:
    box = " ".join((box or "").split())
    turning_on = (on or "yes").strip().lower() in ("yes", "on", "true", "1")
    if not box or len(box) > 120:
        raise Refusal("Which box? Say the words next to it.")
    if click_tier(box) == "never":
        raise Refusal("Refused: Kairu never ticks a box that pays or buys. Money stays yours.")
    if not confirmed and turning_on and (AGREE_WORDS.search(box) or click_tier(box) == "high"):
        raise _needs_pin(f'ticking "{box}" agrees to something for you.')
    target = _ready(system, app)
    if not confirmed and target.app not in safe:
        raise _needs_pin(f"{_name(target)} isn't on Kairu's safe list yet.")
    found = system.tick(target.window, box, turning_on)
    return f'{"Ticked" if turning_on else "Unticked"} "{found}" in {_name(target)}.'


def _point(system, app: str, point: str, confirmed: bool, safe: frozenset = SAFE_APPS) -> str:
    match = re.fullmatch(r"\s*(\d{1,5})\s*,\s*(\d{1,5})\s*", point or "")
    if not match:
        raise Refusal("A point is two numbers: x,y on the picture.")
    x, y = int(match.group(1)), int(match.group(2))
    target = _ready(system, app)
    if not confirmed and target.app not in safe:
        raise _needs_pin(f"{_name(target)} isn't on Kairu's safe list yet.")
    seen = system.point_info(target.window, x, y)
    if seen.get("password"):
        raise Refusal("Refused: that point is a password box, and Kairu never clicks into one for you.")
    words = " ".join(str(seen.get("name") or "").split())[:80]
    if words and click_tier(words) == "never":
        raise Refusal("Refused: Kairu never clicks pay, buy or checkout. Money stays yours.")
    if not confirmed and words and click_tier(words) == "high":
        raise _needs_pin(f'"{words}" may send, submit or delete something.')
    if not confirmed and not words:
        raise _needs_pin("nothing at that point says what it is, so you decide.")
    system.click_picture_point(target.window, x, y)
    return f'Clicked "{words}" in {_name(target)} (at the point Gemini named).' if words else \
        f"Clicked the point you approved in {_name(target)}."


def _site_now(system, target: Target) -> str:
    from kairu.tasks import details
    try:
        return details.site_of(system.address(target.window))
    except pc.PcProblem:
        return ""


def _on_the_site(system, target: Target, site: str) -> str:
    """The site the browser is on now; refused if it isn't the site the run is locked to (a look-alike, another site)."""
    now = _site_now(system, target)
    if not now:
        raise Refusal("I stopped: I can't tell which site the browser is on, so I typed nothing.")
    if site and now != site:
        raise Refusal(f"I stopped: the page is on {now} now, not {site}, so I typed nothing there.")
    return now


def _fill(system, data_dir: str, app: str, box: str, detail: str, site: str) -> str:
    from kairu.tasks import details
    key = details.key_of(detail)
    if key is None:
        raise Refusal(f"Kairu fills only your saved details: {', '.join(details.KEYS)}, or your username.")
    box = " ".join((box or "").split())
    if not box or len(box) > 80:
        raise Refusal("Which box? Say the name next to it.")
    if re.search(r"password|passcode|\bpin\b|otp|verification|one.time|cvv|card number|aadhaar", box, re.IGNORECASE):
        raise Refusal(f'{YOUR_TURN}"{box}" is yours to fill. Kairu never types a password, PIN or code.')
    target = _ready(system, app)
    if target.app not in BROWSERS:
        raise Refusal("Refused: Kairu fills your details only in the browser.")
    now = _on_the_site(system, target, details.site_of(site) if site else "")
    value = details.value(data_dir, key, now)
    if not value:
        raise Refusal(f'{YOUR_TURN}you haven\'t saved {details.LABELS[key]}. Type it yourself, or save it first '
                      f'("save my {key} as ..."), then say go on.')
    problem = text_problem(value)  # never a secret, even if one got into the file
    if problem:
        raise Refusal(problem)
    found = system.focus_box(target.window, box)
    if found == pc.PASSWORD_BOX:
        raise Refusal(f'{YOUR_TURN}"{box}" is a password box. Kairu never types into one.')
    if system.focus_is_password(target.window):
        raise Refusal(f"{YOUR_TURN}the cursor is in a password box. Kairu never types into one.")
    system.press(target.window, "ctrl+a")
    system.type_text(target.window, value)
    return f'Filled {details.LABELS[key]} in "{found}" on {now}.'  # never the value


def _saved_password(system, data_dir: str, app: str, site: str) -> str:
    from kairu.tasks import details
    target = _ready(system, app)
    if target.app not in BROWSERS:
        raise Refusal("Refused: Kairu picks a saved login only in the browser.")
    now = _on_the_site(system, target, details.site_of(site) if site else "")
    user = details.value(data_dir, details.USERNAME, now)
    if not user:
        raise Refusal(f"{YOUR_TURN}type your password yourself (you have no username saved for {now}), then say go on.")
    if not system.pick_saved_login(target.window, user):
        raise Refusal(f"{YOUR_TURN}the browser has no saved password for your username on {now}. Type your password "
                      "yourself, then say go on.")
    return f"Picked the browser's saved login for your username on {now}; the browser filled the password."


def scroll(data_dir: str, job: str, app: str, direction: str, times: str = "3") -> None:
    return _guarded(data_dir, job, lambda system: _scroll(system, app, direction, times))


def choose(data_dir: str, job: str, app: str, box: str, item: str) -> None:
    return _guarded(data_dir, job, lambda system: _choose(system, app, box, item, False, safe_apps(data_dir)))


def tick(data_dir: str, job: str, app: str, target: str, on: str = "yes") -> None:
    return _guarded(data_dir, job, lambda system: _tick(system, app, target, on, False, safe_apps(data_dir)))


def point(data_dir: str, job: str, app: str, point: str) -> None:
    return _guarded(data_dir, job, lambda system: _point(system, app, point, False, safe_apps(data_dir)))


def fill(data_dir: str, job: str, app: str, box: str, detail: str, site: str = "") -> None:
    return _guarded(data_dir, job, lambda system: _fill(system, data_dir, app, box, detail, site))


def saved_password(data_dir: str, job: str, app: str, site: str = "") -> None:
    return _guarded(data_dir, job, lambda system: _saved_password(system, data_dir, app, site))


def _confirmed(system, verb: str, app: str, what: str, field: str, enter: str) -> str:
    """The same hands, after your approval. Everything refused above still is."""
    if verb == "type":
        return _type(system, app, what, field, enter, confirmed=True)
    if verb == "press":
        return _press(system, app, what, confirmed=True)
    if verb == "click":
        return _click(system, app, what, confirmed=True)
    if verb == "choose":
        return _choose(system, app, field, what, confirmed=True)
    if verb == "tick":
        return _tick(system, app, what, enter, confirmed=True)
    if verb == "point":
        return _point(system, app, what, confirmed=True)
    raise Refusal("Refused: that isn't a step Kairu's hands take.")


def agent_confirm(data_dir: str, job: str, verb: str, app: str, what: str, field: str = "", enter: str = "no", site: str = "",
                  filled: str = "") -> None:
    """screen.agent_confirm (High, no PIN: ADR-054): inside a take-control run, you said "yes" to exactly this step. On a site
    the run is locked to, the browser must still be on it. filled: only the names of the boxes filled, for the card."""
    def work(system) -> str:
        if site:
            from kairu.tasks import details
            target = _ready(system, app)
            _on_the_site(system, target, details.site_of(site))
        return _confirmed(system, verb, app, what, field, enter)
    return _guarded(data_dir, job, work)


# --- the safe list, from the bar (hands.*) ---------------------------------------------------------------

def _open_program(system, app: str) -> Target:
    """The program of an app that is open now, by the name you call it: the safe list keeps a program's name, never a title."""
    wanted = program_of(app)
    if not wanted or wanted == BROWSER:
        raise Refusal("Say the app's name, such as \"mark Slack safe\".")
    if wanted in KAIRU_PROGRAMS or "kairu" in wanted:
        raise Refusal("Refused: Kairu's own windows are never typed or clicked in.")
    usable = [window for window in system.windows() if _usable(system, window)]
    found = _of(system, wanted, usable)
    if not found:
        raise Refusal(f"Open {app.strip()} first, so I can see which program it is, then ask again.")
    return Target(found[0], found[0].app)


def mark_safe(data_dir: str, job: str, app: str) -> None:
    """hands.mark_safe (High: your yes and PIN): typing, keys and plain clicks in this app become Medium, as in the built-in
    safe apps. Careful steps there still ask for your PIN, and everything refused stays refused."""
    def work(system) -> str:
        target = _open_program(system, app)
        _check_window(system, target.window)
        why = never_safe_why(target.app)
        if why:
            raise Refusal(f"Refused: {why}")
        if target.app in SAFE_APPS:
            return f"{_name(target)} is already on Kairu's safe list."
        names = list(owner_safe(data_dir))
        if target.app in names:
            return f"{_name(target)} is already on Kairu's safe list (you marked it)."
        _save_safe(data_dir, [*names, target.app])
        return (f"{_name(target)} is on Kairu's safe list now: typing, keys and plain clicks there no longer ask for your PIN. "
                f"Steps that may send, submit or delete still do. Say \"unmark {app.strip()}\" to take it off.")
    return _guarded(data_dir, job, work)


def unmark_safe(data_dir: str, job: str, app: str) -> None:
    """hands.unmark_safe (Medium): take an app you marked off the safe list. It makes Kairu stricter, never looser."""
    def work(system) -> str:
        wanted = program_of(app)
        names = list(owner_safe(data_dir))
        hit = [name for name in names if name == wanted or name in re.sub(r"[^a-z0-9]+", " ", wanted).split()
               or (len(wanted) >= 3 and wanted.replace(" ", "") in name)]
        if not hit:
            if wanted in SAFE_APPS:
                return f"{app.strip()} is on the built-in safe list; it comes off only in a pull request."
            return f"{app.strip()} isn't on the list of apps you marked safe."
        _save_safe(data_dir, [name for name in names if name not in hit])
        return f"Took {', '.join(hit)} off Kairu's safe list: every step there asks for your yes and PIN again."
    return _guarded(data_dir, job, work)


def safe_list(data_dir: str, job: str) -> None:
    """hands.safe_list (Low, read-only)."""
    def work(system) -> str:
        built_in = ", ".join(sorted(SAFE_APPS))
        mine = owner_safe(data_dir)
        return (f"Built in: {built_in}. " + (f"You marked: {', '.join(mine)}." if mine else "You haven't marked any app safe."))
    return _guarded(data_dir, job, work)


# --- for the task core: "click 3" after "show numbers" ----------------------------------------------------

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
            "tenth": 10, "last": -1}
POINTED = re.compile(r"(?:number|no\.?|option|item|#) ?(?P<number>\d{1,2})", re.IGNORECASE)  # always means the numbers shown
BARE = re.compile(r"#?(?P<number>\d{1,2})(?:st|nd|rd|th)?|(?P<word>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
                  r"tenth|last)(?: one| item| option| button| link)?", re.IGNORECASE)
IT_WORDS = frozenset({"it", "this", "that", "this one", "that one", "the one", "it please"})


def number_of(said: str) -> tuple[int, bool] | None:
    """What a click's words point at among the numbers shown: (number, always). number 0 is "it" (the one thing shown), -1 the
    last; always: it can only mean the numbers ("number 3", "it"), not a button's own name ("3", "last"). None: a name."""
    words = " ".join((said or "").lower().split()).strip(" .")
    words = re.sub(r"^the ", "", words)
    if words in IT_WORDS:
        return 0, True
    found = POINTED.fullmatch(words)
    if found:
        return int(found["number"]), True
    found = BARE.fullmatch(words)
    if found:
        return (int(found["number"]) if found["number"] else ORDINALS[found["word"].lower()]), False
    return None


def shown_numbers(data_dir: str) -> tuple[str, list[str]] | None:
    """(the app's program, the names) that screen.numbers showed within NUMBERS_SECONDS; None if none. The names are data."""
    try:
        kept = json.loads((Path(data_dir) / NUMBERS).read_text(encoding="utf-8"))
        made, app, names = float(kept["made"]), str(kept["app"]), [str(name) for name in kept["names"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not 0 <= time.time() - made < NUMBERS_SECONDS or not app or not names:
        return None
    return app, names


# --- for the task core: which action a step needs, before Guardian is asked ------------------------------

def confirm_details(action: str, details: dict) -> dict:
    """The same step as screen.confirm's (or screen.agent_confirm's) details."""
    verb = VERBS[action]
    field, enter = details.get("field", ""), details.get("enter", "no")
    if verb == "choose":
        field = details.get("box", "")  # the list's name rides in "field", the item in "what"
    if verb == "tick":
        enter = details.get("on", "yes")  # ticking on or off rides in "enter"
    return {"verb": verb, "app": details.get("app", ""), "what": details.get(WHAT_DETAIL[verb], ""),
            "field": field, "enter": enter}


def needs_pin_now(action: str, details: dict) -> bool:
    """True when the words alone already show the step is High (personal words, a careful key or button). Whatever the app
    turns out to be, the skill checks everything again and asks for screen.confirm itself when the app decides it."""
    if action == "screen.type":
        text = details.get("text", "")
        return not text_problem(text) and text_is_personal(text)
    if action == "screen.press":
        try:
            keys = keys_of(details.get("keys", ""))
        except Refusal:
            return False
        return keys != "enter" and key_tier(keys, program_of(details.get("app", "")), "") == "high"  # Enter: the skill decides
    if action == "screen.click":
        return click_tier(details.get("target", "")) == "high"
    if action == "screen.choose":
        return "high" in (click_tier(details.get("box", "")), click_tier(details.get("item", "")))
    if action == "screen.tick":
        box = details.get("target", "")
        return details.get("on", "yes") == "yes" and (bool(AGREE_WORDS.search(box)) or click_tier(box) == "high")
    return False
