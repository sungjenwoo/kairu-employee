"""The PC itself: windows, apps, sound, the screen, Wi-Fi, status and power, through ctypes and Windows' own programs.

Only the skills in kairu/tasks/actions.py call this, inside Guardian's actions. backend() picks one of:

    Windows    this PC: ctypes first (no new package), PowerShell only for brightness, Wi-Fi and the Store apps' list, whose scripts are fixed
    StandIn    KAIRU_TEST_PC names a folder: a pretend PC in a file, so tests never close an app or restart this PC
    NotHere    any other system: every call says "not on this system"

An app is started through Explorer, not as a child of the action: Guardian ends everything an action started when the
action ends, and an app you asked for must stay open. Nothing here ever kills a process: closing is a polite WM_CLOSE.
"""

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

TEST_PC = "KAIRU_TEST_PC"
SIGN_IN = "\x00sign-in"  # ask_box: the page wants you to sign in
PASSWORD_BOX = "\x00password"  # focus_box: that box is a password box, which Kairu never types into (ADR-054)
SCRIPT_SECONDS = 20

# Microsoft Store apps (WhatsApp, Spotify from the Store, ...) have no Start Menu shortcut and no App Path: Windows starts them
# by their app ID, through Explorer, as shell:AppsFolder\<ID>. Only IDs Windows itself lists (Get-StartApps) are ever used,
# and each is checked against this shape again just before it starts, so a name typed or said never becomes one.
STORE_PREFIX = "shell:AppsFolder\\"
STORE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,99}_[a-z0-9]{13}![A-Za-z0-9][A-Za-z0-9._-]{0,99}")
# Never started as a Store app: Windows Security, Settings, the terminal, the sign-in and lock screens
NEVER_STORE = re.compile(r"(?:Microsoft\.(?:Windows\.)?SecHealthUI|windows\.immersivecontrolpanel|Microsoft\.WindowsTerminal\w*|"
                         r"Microsoft\.LockApp|Microsoft\.CredDialogHost|Microsoft\.Windows\.CloudExperienceHost)_",
                         re.IGNORECASE)
STORE_SCRIPT = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                "Get-StartApps | ForEach-Object { $_.Name + [char]9 + $_.AppID }")

# "What's on my wallpaper" (kairu/tasks/eyes.py, the owner's ask of 19 Nov 2026): the wallpaper is no window, so Windows' own
# System.Drawing makes a small PNG of the picture file Windows names for it, in memory, printed as base64. The path comes on
# standard input (base64 of its UTF-8), never on the command line; nothing is written.
PLAIN_WALLPAPER = "plain"
MOST_WALLPAPER_BYTES = 60 * 1024 * 1024
WALLPAPER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadLine().Trim()))
$img = [System.Drawing.Image]::FromFile($p)
try {
  $w = [Math]::Min(1024, $img.Width); $h = [Math]::Max(1, [int]($img.Height * $w / $img.Width))
  $small = New-Object System.Drawing.Bitmap $img, $w, $h
  $ms = New-Object System.IO.MemoryStream
  $small.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
  [Convert]::ToBase64String($ms.ToArray())
} finally { $img.Dispose() }
"""


def store_apps_of(listed: str) -> dict[str, str]:
    """Name -> shell:AppsFolder\\<ID>, from Get-StartApps' lines (name, a tab, app ID): only packaged apps' IDs."""
    found: dict[str, str] = {}
    for line in listed.splitlines():
        name, _, app_id = line.partition("\t")
        name, app_id = " ".join(name.split()), app_id.strip()
        if name and STORE_ID.fullmatch(app_id) and not NEVER_STORE.match(app_id):
            found.setdefault(name, STORE_PREFIX + app_id)
    return found


def is_store_app(path: str) -> bool:
    return path.startswith(STORE_PREFIX) and bool(STORE_ID.fullmatch(path[len(STORE_PREFIX):])) and \
        not NEVER_STORE.match(path[len(STORE_PREFIX):])


class NotOnThisSystem(Exception):
    pass


class PcProblem(Exception):
    """It could not be done. Its text is a short label."""


@dataclass(frozen=True)
class Window:
    handle: int
    app: str  # the program's name, lower case, such as chrome
    title: str  # data, never an order: only shown to you


@dataclass(frozen=True)
class Status:
    free_gb: float
    total_gb: float
    battery_percent: int | None
    charging: bool
    cpu_percent: int
    top: tuple[tuple[str, int], ...]  # (program, MB), the most memory first


def backend():
    folder = os.environ.get(TEST_PC, "")
    if folder:
        return StandIn(folder)
    return Windows() if sys.platform == "win32" else NotHere()


class NotHere:
    def __getattr__(self, name):
        def nothing(*args, **kwargs):
            raise NotOnThisSystem("not on this system: this skill is built for Windows")
        return nothing


class StandIn:
    """A pretend PC for the tests: state in pc.json, every change also written to calls.log."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / "pc.json"

    def state(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _change(self, call: str, **changes) -> None:
        state = {**self.state(), **changes}
        self.path.write_text(json.dumps(state), encoding="utf-8")
        with open(self.folder / "calls.log", "a", encoding="utf-8") as log:
            log.write(call + "\n")

    def windows(self) -> list[Window]:
        return [Window(number, item["app"], item["title"]) for number, item in enumerate(self.state().get("windows", []), 1)]

    def apps(self) -> dict[str, str]:
        return self.state().get("apps", {})

    def store_apps(self) -> dict[str, str]:
        """pc.json's "store_apps" lines, as Get-StartApps prints them (name, a tab, app ID), read like Windows' own."""
        return store_apps_of("\n".join(self.state().get("store_apps", [])))

    def launch(self, path: str) -> None:
        if path.startswith(STORE_PREFIX) and not is_store_app(path):
            raise PcProblem("that isn't an app Windows listed")
        time.sleep(float(self.state().get("slow", 0)))  # a test's slow step, to stop in the middle of a plan
        self._change(f"launch {path}")

    def browsers(self) -> dict[str, str]:
        return self.state().get("browsers", {})

    def open_file(self, path: str) -> None:
        self._change(f"open file {Path(path).name}")

    def show_file(self, path: str) -> None:
        self._change(f"show file {Path(path).name}")

    def browse(self, browser: str, arguments: list[str], shortcuts) -> None:
        self._change("browse " + " ".join([browser, *arguments]))

    def close(self, window: Window) -> bool:
        kept = [item for item in self.state()["windows"] if (item["app"], item["title"]) != (window.app, window.title)]
        self._change(f"close {window.app}", windows=kept)
        return True

    def arrange(self, window: Window, how: str) -> None:
        self._change(f"arrange {window.app} {how}")

    def volume(self) -> tuple[int, bool]:
        return self.state().get("volume", 50), self.state().get("muted", False)

    def set_volume(self, level: int | None = None, muted: bool | None = None) -> None:
        was, was_muted = self.volume()
        self._change(f"volume {level} {muted}", volume=was if level is None else level, muted=was_muted if muted is None else muted)

    def brightness(self) -> int:
        return self.state().get("brightness", 70)

    def set_brightness(self, level: int) -> None:
        self._change(f"brightness {level}", brightness=level)

    def set_wifi(self, on: bool) -> None:
        self._change(f"wifi {on}", wifi=on)

    def status(self) -> Status:
        return Status(2.5, 7.7, 84, True, 12, (("chrome", 900), ("code", 400)))

    def lock(self) -> None:
        self._change("lock")

    def sleep(self) -> None:
        self._change("sleep")

    def restart(self) -> None:
        self._change("restart")

    def shutdown(self) -> None:
        self._change("shutdown")

    # --- Kairu's hands (kairu/tasks/screen.py): pc.json's "controls" {app: [[kind, name], ...]}, "command_lines" {app: text} ---

    def foreground(self) -> Window | None:
        windows = self.windows()
        return windows[0] if windows else None

    def bring_to_front(self, window: Window) -> None:
        items = self.state().get("windows", [])
        moved = [item for item in items if (item["app"], item["title"]) == (window.app, window.title)][:1]
        self._change(f"front {window.app}", windows=moved + [item for item in items if item not in moved])

    def command_line(self, window: Window) -> str:
        return self.state().get("command_lines", {}).get(window.app, "")

    def focus_field(self, window: Window, field: str, browser: bool) -> str:
        boxes = self._controls(window, "box")
        if browser:
            where = "in the search bar"
        elif window.app == "explorer":
            where = "in the address bar" if field == "address" else "in the search box"
        elif not boxes:
            raise PcProblem(f"I can't find a search box in {window.app}")
        else:
            where = "in the search box"
        self._change(f"field {window.app} {field}", search_focused=[*self.state().get("search_focused", []), window.app])
        return where

    def type_text(self, window: Window, text: str) -> None:
        time.sleep(float(self.state().get("slow", 0)))
        typed = {**self.state().get("typed", {}), window.app: self.state().get("typed", {}).get(window.app, "") + text}
        self._change(f"type {window.app} {text}", typed=typed)

    def press(self, window: Window, keys: str) -> None:
        state = self.state()
        if keys == "enter" and window.app in state.get("asking", []) and window.app in state.get("answers", {}):
            pages = dict(state.get("pages", {}))  # the pretend page shows the question, then its answer
            pages[window.app] = [*pages.get(window.app, []), state.get("typed", {}).get(window.app, ""), *state["answers"][window.app]]
            return self._change(f"press {window.app} {keys}", pages=pages)
        self._change(f"press {window.app} {keys}")

    def focus_is_search(self, window: Window) -> bool:
        return window.app in self.state().get("search_focused", [])

    def _controls(self, window: Window, kind: str = "") -> list[tuple[str, str]]:
        found = [(item[0], item[1]) for item in self.state().get("controls", {}).get(window.app, [])]
        return [item for item in found if not kind or item[0] == kind]

    def find_control(self, window: Window, name: str) -> str | None:
        return _best_control(name, [found for kind, found in self._controls(window) if kind in CLICKABLE])

    def click_control(self, window: Window, name: str) -> None:
        self._change(f"click {window.app} {name}")

    def read_controls(self, window: Window) -> list[tuple[str, str]]:
        return self._controls(window)

    # --- PC4, the rest: a window's words ("texts" {app: [line, ...]}), a picture of it read by OCR ("pictures" {app: [[line,
    #     x, y], ...]}, each word 10 pixels wide from x), a click at a point, and the known folders ("folders" {name: path}) ---

    def read_text(self, window: Window) -> list[str]:
        typed = self.state().get("typed", {}).get(window.app, "")  # what Kairu typed there shows too, as in a real Notepad
        return [str(line) for line in self.state().get("texts", {}).get(window.app, [])] + ([typed] if typed else [])

    def read_picture(self, window: Window) -> list[dict]:
        if window.app in self.state().get("no_picture", []):
            raise PcProblem(f"Windows didn't let Kairu see {window.app}'s window")
        lines = []
        for text, x, y in self.state().get("pictures", {}).get(window.app, []):
            words, left = [], int(x)
            for word in str(text).split():
                words.append([word, left, int(y), 10 * len(word), 12])
                left += 10 * len(word) + 5
            lines.append({"text": str(text), "words": words})
        return lines

    def click_point(self, window: Window, x: int, y: int) -> None:
        self._change(f"point {window.app} {x} {y}")

    def picture_png(self, window: Window, hide: tuple = ()) -> bytes:
        """Kairu's eyes (kairu/tasks/eyes.py): a small grey picture standing in for the window (pc.json's "no_picture" refuses).
        hide: rectangles painted black first (the boxes Kairu filled, ADR-054); calls.log says how many."""
        if window.app in self.state().get("no_picture", []):
            raise PcProblem(f"Windows didn't let Kairu see {window.app}'s window")
        from kairu import hands
        with open(self.folder / "calls.log", "a", encoding="utf-8") as log:
            log.write(f"picture {window.app}" + (f" hide:{len(hide)}" if hide else "") + "\n")
        return hands.png_of(b"\x80\x80\x80\xff" * 64, 8, 8)[0]

    # --- the screen agent's other steps (ADR-054): pc.json's "lists" {app: {list: [item, ...]}}, "ticks" {app: {box: on}},
    #     "points" {app: {"x,y": {"name", "password"}}}, "rects" {app: {box: [l, t, r, b]}}, "address" {app: url},
    #     "password_focus" [app, ...], "saved_logins" {app: [username, ...]}, "password_boxes" {app: [box, ...]} ---

    def scroll(self, window: Window, notches: int) -> None:
        self._change(f"scroll {window.app} {notches}")

    def choose(self, window: Window, box: str, item: str) -> str:
        lists = self.state().get("lists", {}).get(window.app, {})
        found = _best_control(box, list(lists))
        if not found:
            raise PcProblem(f'I can\'t find the list "{box}"')
        chosen = _best_control(item, lists[found])
        if not chosen:
            raise PcProblem(f'"{found}" has no "{item}"')
        self._change(f"choose {window.app} {found} {chosen}")
        return chosen

    def tick(self, window: Window, box: str, on: bool) -> str:
        ticks = self.state().get("ticks", {}).get(window.app, {})
        found = _best_control(box, list(ticks))
        if not found:
            raise PcProblem(f'I can\'t find the box "{box}"')
        self._change(f"tick {window.app} {found} {'on' if on else 'off'}")
        return found

    def point_info(self, window: Window, x: int, y: int) -> dict:
        return dict(self.state().get("points", {}).get(window.app, {}).get(f"{x},{y}", {"name": "", "password": False}))

    def click_picture_point(self, window: Window, x: int, y: int) -> None:
        self._change(f"point {window.app} {x} {y}")

    def box_rects(self, window: Window, names: list[str]) -> list | None:
        rects = self.state().get("rects", {}).get(window.app, {})
        found = [rects.get(_best_control(name, list(rects)) or "") for name in names]
        return None if any(rect is None for rect in found) else [tuple(rect) for rect in found]

    def focus_is_password(self, window: Window) -> bool:
        return window.app in self.state().get("password_focus", [])

    def address(self, window: Window) -> str:
        return str(self.state().get("address", {}).get(window.app, ""))

    def focus_box(self, window: Window, name: str) -> str:
        if _best_control(name, self.state().get("password_boxes", {}).get(window.app, [])):
            return PASSWORD_BOX
        found = _best_control(name, [found for kind, found in self._controls(window) if kind == "box"])
        if not found:
            raise PcProblem(f'I can\'t find the box "{name}"')
        self._change(f"focus {window.app} {found}")
        return found

    def pick_saved_login(self, window: Window, username: str) -> bool:
        if username not in self.state().get("saved_logins", {}).get(window.app, []):
            return False
        self._change(f"saved login {window.app} {username}")
        return True

    def screen_windows(self) -> list[tuple[Window, tuple[int, int, int, int], tuple[int, int, int, int], bool]]:
        """pc.json's "windows", front first, each with its "rect" (default the whole screen) and "opaque" (default true)."""
        found = []
        for number, item in enumerate(self.state().get("windows", []), 1):
            rect = tuple(item.get("rect", (0, 0, 1920, 1080)))
            found.append((Window(number, item["app"], item["title"]), rect, rect, bool(item.get("opaque", True))))
        return found

    def screen_png(self, regions: list[tuple[str, tuple[int, int, int, int], str]]) -> bytes:
        """A small grey PNG; calls.log says what was hidden and shown, back to front."""
        from kairu import hands
        with open(self.folder / "calls.log", "a", encoding="utf-8") as log:
            log.write("picture screen " + " ".join(f"{kind}:{app or '?'}" for kind, _, app in regions) + "\n")
        return hands.png_of(b"\x80\x80\x80\xff" * 64, 8, 8)[0]

    def wallpaper_png(self) -> bytes | str:
        """pc.json's "wallpaper": "picture" (a small grey PNG), "plain" (a plain colour), anything else: none to see."""
        kind = self.state().get("wallpaper", "")
        if kind == PLAIN_WALLPAPER:
            return PLAIN_WALLPAPER
        if kind != "picture":
            raise PcProblem("Windows didn't say which picture your wallpaper is")
        from kairu import hands
        with open(self.folder / "calls.log", "a", encoding="utf-8") as log:
            log.write("picture wallpaper\n")
        return hands.png_of(b"\x80\x80\x80\xff" * 64, 8, 8)[0]

    def known_folder(self, name: str) -> str:
        return str(self.state().get("folders", {}).get(name, ""))

    # --- a page's words and its question box (kairu/tasks/ask_ai.py): pc.json's "pages" {app: [line, ...]},
    #     "ask_box" {app: name}, "signin" [app, ...], "answers" {app: [line, ...]} (what the page adds after Enter) ---

    def read_page(self, window: Window) -> list[str]:
        return [str(line) for line in self.state().get("pages", {}).get(window.app, [])]

    def ask_box(self, window: Window) -> str:
        if window.app in self.state().get("signin", []):
            return SIGN_IN
        name = self.state().get("ask_box", {}).get(window.app, "")
        if name:
            self._change(f"askbox {window.app}", asking=[*self.state().get("asking", []), window.app])
        return name


class Windows:
    # --- windows ---------------------------------------------------------------------------------

    def windows(self) -> list[Window]:
        """The windows you can see, the front one first: not hidden, not tool windows, not owned by another window."""
        import ctypes
        from ctypes import wintypes
        user32, found = _user32(), []
        dwm = ctypes.WinDLL("dwmapi")

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            if user32.GetWindowLongW(hwnd, -20) & 0x80:  # GWL_EXSTYLE, WS_EX_TOOLWINDOW
                return True
            cloaked = wintypes.DWORD()
            dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))  # DWMWA_CLOAKED
            length = user32.GetWindowTextLengthW(hwnd)
            if cloaked.value or not length:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append(Window(int(hwnd), _program_of(pid.value), title.value))
            return True

        user32.EnumWindows(each, 0)
        return found

    def close(self, window: Window) -> bool:
        """Ask politely. True if it has gone within a second; it may be asking you to save."""
        user32 = _user32()
        user32.PostMessageW(window.handle, 0x0010, 0, 0)  # WM_CLOSE
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if not user32.IsWindow(window.handle):
                return True
            time.sleep(0.05)
        return False

    def arrange(self, window: Window, how: str) -> None:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32, hwnd = _user32(), window.handle
        if how == "minimize":
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return
        if how == "maximize":
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        else:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if how in ("left", "right"):
            info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
            if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):  # MONITOR_DEFAULTTONEAREST
                raise PcProblem("the screen's size could not be read")
            work = info.rcWork
            half = (work.right - work.left) // 2
            left = work.left if how == "left" else work.left + half
            user32.SetWindowPos(hwnd, None, left, work.top, half, work.bottom - work.top, 0x0004)  # SWP_NOZORDER
        user32.SetForegroundWindow(hwnd)

    # --- apps ------------------------------------------------------------------------------------

    def apps(self) -> dict[str, str]:
        """Name -> where it is: your Start Menu's shortcuts and the App Paths in the registry, nothing else."""
        import winreg
        found: dict[str, str] = {}
        for root in (os.environ.get("ProgramData"), os.environ.get("APPDATA")):
            if root:
                for link in (Path(root) / "Microsoft" / "Windows" / "Start Menu" / "Programs").rglob("*.lnk"):
                    found.setdefault(link.stem, str(link))
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                    for number in range(winreg.QueryInfoKey(key)[0]):
                        name = winreg.EnumKey(key, number)
                        try:
                            with winreg.OpenKey(key, name) as entry:
                                value = winreg.QueryValueEx(entry, "")[0]
                        except OSError:
                            continue
                        if name.lower().endswith(".exe") and isinstance(value, str) and value.strip():
                            found.setdefault(name[:-4], os.path.expandvars(value.strip().strip('"')))
            except OSError:
                pass
        return found

    def store_apps(self) -> dict[str, str]:
        """Microsoft Store apps, from Windows' own list of Start apps (Get-StartApps, a fixed script): name -> shell:AppsFolder\\ID.
        Asked only when an app isn't among the shortcuts and App Paths, as it takes PowerShell a second or two."""
        shell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                             "powershell.exe")
        try:
            done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", STORE_SCRIPT], capture_output=True,
                                  timeout=SCRIPT_SECONDS, creationflags=0x08000000)  # CREATE_NO_WINDOW
        except (OSError, subprocess.TimeoutExpired):
            return {}
        return store_apps_of(done.stdout.decode("utf-8", "replace"))

    def launch(self, path: str) -> None:
        """Through Explorer, so that the app belongs to your desktop and stays open when this action ends. A Store app is
        started by the app ID Windows listed (shell:AppsFolder\\ID), checked again here."""
        if path.startswith(STORE_PREFIX) and not is_store_app(path):
            raise PcProblem("that isn't an app Windows listed")
        explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
        _hand_to_desktop([str(explorer), path])

    def open_file(self, path: str) -> None:
        """A file or folder of the work folder, with its own app, through Explorer (as a double-click would). files.open has
        already refused programs, scripts and shortcuts; the path is the fence's real path, never typed into a command line."""
        self.launch(_plain(path))

    def show_file(self, path: str) -> None:
        """Explorer, with this file or folder selected. Explorer takes /select only joined to the path, so the command line is
        made here: the path is the fence's real path, inside the work folder, and Windows names never hold a \"."""
        path = _plain(path)
        if '"' in path:
            raise PcProblem("that name can't be shown")
        explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
        _hand_to_desktop(f'"{explorer}" /select,"{path}"')


    # --- Kairu's own browser (kairu/tasks/web.py) ---------------------------------------------------

    def browsers(self) -> dict[str, str]:
        """Chrome and Edge, where installed: from App Paths, then their usual folders. Nothing typed ever becomes this path."""
        import winreg
        found: dict[str, str] = {}
        for name, program in (("chrome", "chrome.exe"), ("edge", "msedge.exe")):
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{program}") as key:
                        value = os.path.expandvars(str(winreg.QueryValueEx(key, "")[0]).strip().strip('"'))
                except OSError:
                    continue
                if value.lower().endswith(program) and Path(value).is_file():
                    found.setdefault(name, value)
            for root, rest in ((os.environ.get("ProgramFiles"), BROWSER_FOLDERS[name]), (os.environ.get("ProgramFiles(x86)"), BROWSER_FOLDERS[name]),
                               (os.environ.get("LOCALAPPDATA"), BROWSER_FOLDERS[name])):
                if root and name not in found and (Path(root) / rest / program).is_file():
                    found[name] = str(Path(root) / rest / program)
        return found

    def browse(self, browser: str, arguments: list[str], shortcuts) -> None:
        """Start the browser with these arguments, through a shortcut that Explorer opens: no shell, no command line typed.

        Through Explorer, so the browser belongs to your desktop and stays open when this action ends.
        """
        folder = Path(shortcuts)
        folder.mkdir(parents=True, exist_ok=True)
        for old in sorted(folder.glob("open-*.lnk"))[:-5]:  # only the newest few are kept
            old.unlink(missing_ok=True)
        link = folder / f"open-{time.time_ns()}.lnk"
        make_shortcut(link, browser, subprocess.list2cmdline(arguments))
        self.launch(str(link))

    # --- Kairu's hands (kairu/tasks/screen.py): keys, clicks and UI Automation through kairu/hands.py -----------------------

    def foreground(self) -> Window | None:
        import ctypes
        from ctypes import wintypes
        user32 = _user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        return Window(int(hwnd), _program_of(pid.value), title.value)

    def bring_to_front(self, window: Window) -> None:
        """Make this window the one you type into. Windows guards the front, so: AttachThreadInput, then UI Automation's own
        SetFocus. No key is ever pressed to get there. If neither works, Kairu says so and types nothing."""
        from kairu import hands
        import ctypes
        user32, hwnd = _user32(), window.handle
        if not user32.IsWindow(hwnd):
            raise PcProblem(f"that {window.app} window has closed")
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if hands.in_front(hwnd):
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        front = user32.GetForegroundWindow()
        theirs, mine = user32.GetWindowThreadProcessId(front, None) if front else 0, kernel32.GetCurrentThreadId()
        attached = bool(theirs and theirs != mine and user32.AttachThreadInput(mine, theirs, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(mine, theirs, False)
        if hands.wait_front(hwnd, 0.6):
            return
        hands.uia("focus", window)
        if not hands.wait_front(hwnd, 1.0):
            raise PcProblem(f"Windows didn't let Kairu bring {window.app} to the front; click it once and try again")

    def command_line(self, window: Window) -> str:
        """The command line of a browser window's program: to know the workspace's own window (its own profile folder)."""
        from kairu import hands
        if window.app not in ("chrome", "msedge"):
            return ""
        return hands.command_line_of(hands.pid_of(window.handle))

    def focus_field(self, window: Window, field: str, browser: bool) -> str:
        """Put the cursor in the search or address bar. Where it went, in words. A browser's search bar is its address bar
        (Ctrl+L): instant, with no UI Automation."""
        from kairu import hands
        if browser:
            self.press(window, "ctrl+l")
            return "in the search bar"
        if window.app == "explorer":
            self.press(window, "ctrl+l" if field == "address" else "ctrl+e")
            return "in the address bar" if field == "address" else "in the search box"
        if not hands.uia("search", window).get("found"):
            raise PcProblem(f"I can't find a search box in {window.app}")
        self.press(window, "ctrl+a")
        return "in the search box"

    def type_text(self, window: Window, text: str) -> None:
        """Type, a few letters at a time, only while this window's program is in front: if another window comes to the front,
        typing stops there."""
        from kairu import hands
        hands.keys_released()
        if len(text) >= hands.PASTE_FROM:
            if not hands.in_front(window.handle):
                raise PcProblem("I stopped typing: another window came to the front")
            if hands.paste_text(text, window.handle):
                time.sleep(0.15)
                return
        units = text.encode("utf-16-le")
        letters = [int.from_bytes(units[at:at + 2], "little") for at in range(0, len(units), 2)]
        # One letter at a time (a surrogate pair stays together). Sent in batches, Windows 11's Notepad and other new apps
        # read a typed letter only when they get to it, by then the batch's last one: "milk is white" came out as
        # "milk    eeeee" (laptop test, 16 Nov 2026).
        at = 0
        while at < len(letters):
            size = 2 if 0xD800 <= letters[at] <= 0xDBFF and at + 1 < len(letters) else 1
            if not hands.in_front(window.handle):
                raise PcProblem("I stopped typing: another window came to the front")
            if letters[at] in (10, 13):  # a new line is Enter (a typed line break is not one in most apps)
                if letters[at] == 13 and at + 1 < len(letters) and letters[at + 1] == 10:
                    at += 1
                hands.send([hands.key(0x0D, False), hands.key(0x0D, True)], window.handle)
                at += 1
                time.sleep(hands.TYPE_GAP)
                continue
            events = []
            for unit in letters[at:at + size]:
                events += [hands.key(0, False, unit), hands.key(0, True, unit)]
            hands.send(events, window.handle)
            at += size
            time.sleep(hands.TYPE_GAP)
        time.sleep(0.15)  # the app's own suggestions settle before Enter

    def press(self, window: Window, keys: str) -> None:
        from kairu import hands
        hands.keys_released()
        if not hands.in_front(window.handle):
            raise PcProblem("another window came to the front, so I pressed nothing")
        names = keys.split("+")
        held, key = names[:-1], names[-1]
        vk = hands.VK
        events = [hands.key(vk[name], False) for name in held] + [hands.key(vk[key], False), hands.key(vk[key], True)]
        events += [hands.key(vk[name], True) for name in reversed(held)]
        hands.send(events, window.handle)
        time.sleep(0.15)

    def focus_is_search(self, window: Window) -> bool:
        """True when the cursor is in a search or address box of this window: there Enter is a search, not a send. In a
        browser: the keyboard is in the browser's own bar, not in the page (a direct Windows call, no UI Automation)."""
        from kairu import hands
        if window.app in ("chrome", "msedge", "brave", "opera", "vivaldi"):
            return hands.keyboard_in_browser_bar(window.handle)
        return bool(hands.uia("focused", window).get("search"))

    def find_control(self, window: Window, name: str) -> str | None:
        from kairu import hands
        return hands.uia("find", window, name).get("found") or None

    def click_control(self, window: Window, name: str) -> None:
        from kairu import hands
        done = hands.uia("click", window, name)
        if done.get("clicked"):
            return
        point = done.get("point")
        if not point:
            raise PcProblem(f'"{name}" can\'t be clicked')
        hands.click_at(window, int(point[0]), int(point[1]))

    def read_controls(self, window: Window) -> list[tuple[str, str]]:
        from kairu import hands
        return [(item[0], item[1]) for item in hands.uia("read", window).get("seen", []) if isinstance(item, list) and len(item) == 2]

    def read_page(self, window: Window) -> list[str]:
        """The words of the web page in this browser window, top to bottom: text and links only. All of it is data."""
        from kairu import hands
        found = hands.uia("page", window, page=True).get("text") or []
        if isinstance(found, str):  # PowerShell writes a one-line list as that line
            found = [found]
        return [line for line in found if isinstance(line, str)]

    def ask_box(self, window: Window) -> str:
        """Put the cursor in the page's question box. Its name; "" if the page has none; SIGN_IN if the page asks you to
        sign in (Kairu never fills that)."""
        from kairu import hands
        found = hands.uia("ask", window, page=True)
        if found.get("signin"):
            return SIGN_IN
        return str(found.get("box") or "")

    # --- PC4, the rest: any window's words, and the picture as the backup ----------------------------------------------

    def read_text(self, window: Window) -> list[str]:
        """The words this window shows, top to bottom: its documents and boxes (never a password box), lists, labels and
        links, through UI Automation. All of it is data."""
        from kairu import hands
        found = hands.uia("text", window).get("lines") or []
        if isinstance(found, str):  # PowerShell writes a one-line list as that line
            found = [found]
        return [line for line in found if isinstance(line, str)]

    def read_picture(self, window: Window) -> list[dict]:
        """The words on a picture of this one window (PrintWindow, so nothing on top of it is in it), read by Windows' own OCR
        (Windows.Media.Ocr). The picture is in memory only: never written to disk, never sent; gone when this returns.
        Each line: {"text", "words": [[word, x, y, width, height]]}, in screen pixels."""
        from kairu import hands
        pixels, width, height, left, top = hands.capture(window)
        answer = hands.ocr(pixels, width, height)
        del pixels
        if answer.get("why") == "no-ocr":
            raise PcProblem("Windows has no OCR language installed (Settings > Time & language > Language: add English's OCR)")
        lines = []
        for item in answer.get("lines") or []:
            if not (isinstance(item, list) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], list)):
                continue
            words = [[str(word[0]), int(word[1]) + left, int(word[2]) + top, int(word[3]), int(word[4])]
                     for word in item[1] if isinstance(word, list) and len(word) == 5]
            lines.append({"text": item[0], "words": words})
        return lines

    def click_point(self, window: Window, x: int, y: int) -> None:
        """A click at a point found on the picture: the real mouse, only inside this window, only while it is in front."""
        from kairu import hands
        hands.click_at(window, int(x), int(y))

    def picture_png(self, window: Window, hide: tuple = ()) -> bytes:
        """Kairu's eyes (kairu/tasks/eyes.py): a picture of this one window (PrintWindow: nothing on top of it is in it, the
        bar's card included) as a PNG, in memory only. Never written to disk; screen.look sends it to Gemini.
        hide: screen rectangles painted black first (ADR-054: the boxes Kairu filled with your details), with a small margin."""
        from kairu import hands
        pixels, width, height, left, top = hands.capture(window)
        try:
            if hide:
                painted = hands.paint_regions(pixels, width, height, left, top,
                                              [("hide", (r[0] - 4, r[1] - 4, r[2] + 4, r[3] + 4)) for r in hide])
                painted[3::4] = b"\xff" * (width * height)
                pixels = bytes(painted)
                del painted
            return hands.png_of(pixels, width, height)[0]
        finally:
            del pixels

    # --- the screen agent's other steps (ADR-054) ------------------------------------------------------------------------

    def scroll(self, window: Window, notches: int) -> None:
        from kairu import hands
        hands.wheel(window, notches)

    def choose(self, window: Window, box: str, item: str) -> str:
        from kairu import hands
        done = hands.uia("choose", window, box, item=item)
        if done.get("chosen"):
            return str(done["chosen"])
        if done.get("why") == "list":
            raise PcProblem(f'I can\'t find the list "{box}"')
        if done.get("why") == "item":
            raise PcProblem(f'"{done.get("list") or box}" has no "{item}"')
        raise PcProblem(f'"{item}" can\'t be chosen there')

    def tick(self, window: Window, box: str, on: bool) -> str:
        from kairu import hands
        done = hands.uia("tick", window, box, item="on" if on else "off")
        if not done.get("ticked"):
            raise PcProblem(f'I can\'t find the box "{box}"')
        return str(done["ticked"])

    def point_info(self, window: Window, x: int, y: int) -> dict:
        """What is at a point of a look's picture (x, y in the picture's pixels): its name from UI Automation, else the words
        the picture shows there (Windows' own OCR, in memory), and whether it is a password box."""
        from kairu import hands
        sx, sy = hands.picture_point(window, x, y)
        seen = hands.uia("at", window, f"{sx},{sy}")
        if not seen.get("inside"):
            raise PcProblem("that point doesn't show this window")
        name = str(seen.get("name") or "")
        if not name and not seen.get("password"):
            try:
                for line in self.read_picture(window):
                    for word in line.get("words", []):
                        if word[1] - 6 <= sx <= word[1] + word[3] + 6 and word[2] - 6 <= sy <= word[2] + word[4] + 6:
                            name = str(line.get("text", ""))[:80]
                            break
                    if name:
                        break
            except PcProblem:
                pass
        return {"name": name, "password": bool(seen.get("password"))}

    def click_picture_point(self, window: Window, x: int, y: int) -> None:
        from kairu import hands
        sx, sy = hands.picture_point(window, x, y)
        hands.click_at(window, sx, sy)

    def box_rects(self, window: Window, names: list[str]) -> list | None:
        from kairu import hands
        rects = hands.uia("rects", window, json.dumps(list(names))).get("rects")
        if not isinstance(rects, list) or len(rects) != len(names):
            return None
        good = [tuple(int(v) for v in rect) for rect in rects if isinstance(rect, list) and len(rect) == 4]
        return good if len(good) == len(names) else None

    def focus_is_password(self, window: Window) -> bool:
        """True when the keyboard is in a password box of this window (or Windows can't say: fails closed)."""
        from kairu import hands
        try:
            return bool(hands.uia("focused", window).get("password", True))
        except PcProblem:
            return True

    def address(self, window: Window) -> str:
        from kairu import hands
        return str(hands.uia("address", window).get("address") or "")

    def focus_box(self, window: Window, name: str) -> str:
        from kairu import hands
        found = hands.uia("fillbox", window, name)
        if found.get("password"):
            return PASSWORD_BOX
        if not found.get("found"):
            raise PcProblem(f'I can\'t find the box "{name}"')
        return str(found["found"])

    def pick_saved_login(self, window: Window, username: str) -> bool:
        """Click the username box (its place only) so the browser shows its saved logins, then pick only the one with this
        username. The password is filled by the browser itself; Kairu never reads or types it."""
        from kairu import hands
        point = hands.uia("loginbox", window).get("point")
        if not (isinstance(point, list) and len(point) == 2):
            return False
        hands.click_at(window, int(point[0]), int(point[1]))
        time.sleep(0.8)
        return bool(hands.uia("saved", window, username).get("picked"))

    def screen_windows(self) -> list[tuple[Window, tuple[int, int, int, int], tuple[int, int, int, int], bool]]:
        """Every window that may show on the screen now, front first: visible, not minimised, not cloaked, tool windows and
        untitled ones too. (window, its whole rectangle, its visible frame, opaque): opaque is an ordinary titled window that
        is not layered, see-through or a tool window. Rectangles in real pixels."""
        import ctypes
        from ctypes import wintypes
        user32, found = _user32(), []
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2, as hands.capture_screen
        except (AttributeError, OSError):
            pass
        dwm = ctypes.WinDLL("dwmapi")

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            cloaked = wintypes.DWORD()
            dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))  # DWMWA_CLOAKED
            outer = wintypes.RECT()
            if cloaked.value or not user32.GetWindowRect(hwnd, ctypes.byref(outer)) or outer.right <= outer.left or \
                    outer.bottom <= outer.top:
                return True
            frame = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(frame), ctypes.sizeof(frame)) != 0:
                frame = outer  # DWMWA_EXTENDED_FRAME_BOUNDS: without the invisible borders
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            if length:
                user32.GetWindowTextW(hwnd, title, length + 1)
            style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            opaque = bool(length) and not style & (0x80 | 0x20 | 0x80000)  # WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, WS_EX_LAYERED
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((Window(int(hwnd), _program_of(pid.value), title.value),
                          (outer.left, outer.top, outer.right, outer.bottom), (frame.left, frame.top, frame.right, frame.bottom),
                          opaque))
            return True

        user32.EnumWindows(each, 0)
        return found

    def screen_png(self, regions: list[tuple[str, tuple[int, int, int, int], str]]) -> bytes:
        """The whole screen as a PNG, in memory only, with the "hide" regions painted black (hands.capture_screen)."""
        from kairu import hands
        pixels, width, height = hands.capture_screen([(kind, rect) for kind, rect, _ in regions])
        try:
            return hands.png_of(pixels, width, height)[0]
        finally:
            del pixels

    def wallpaper_png(self) -> bytes | str:
        """Kairu's eyes, "what's on my wallpaper": a small PNG of your desktop's picture, in memory only (never written), or
        PLAIN_WALLPAPER for a plain colour. The picture is the file Windows names in HKCU\\Control Panel\\Desktop
        (WallPaper), else its own copy (Themes\\TranscodedWallpaper)."""
        import base64
        import winreg
        path = ""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
                path = os.path.expandvars(str(winreg.QueryValueEx(key, "WallPaper")[0]).strip())
        except OSError:
            pass
        copy = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
        if not path or not Path(path).is_file():
            if not path and not copy.is_file():
                return PLAIN_WALLPAPER
            path = str(copy)
        if not Path(path).is_file() or Path(path).stat().st_size > MOST_WALLPAPER_BYTES:
            raise PcProblem("Windows' wallpaper picture can't be read")
        shell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                             "powershell.exe")
        try:
            done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", WALLPAPER_SCRIPT],
                                  input=base64.b64encode(path.encode("utf-8")) + b"\n", capture_output=True, timeout=SCRIPT_SECONDS,
                                  creationflags=0x08000000)  # CREATE_NO_WINDOW
            png = base64.b64decode(done.stdout.strip(), validate=True)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            raise PcProblem("Windows couldn't make a picture of your wallpaper") from None
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise PcProblem("Windows couldn't make a picture of your wallpaper")
        return png

    def known_folder(self, name: str) -> str:
        """Your Downloads, Documents, Desktop, Pictures, Music or Videos folder, where Windows really keeps it (OneDrive may
        hold some), through SHGetKnownFolderPath. "" if Windows does not say or the folder is not there."""
        import ctypes
        from ctypes import wintypes
        ids = {"downloads": "374DE290-123F-4565-9164-39C4925E467B", "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
               "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
               "music": "4BD8D571-6D19-48D3-BE97-422220080E43", "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC"}
        if name not in ids:
            return ""
        shell32 = ctypes.WinDLL("shell32")
        ole32 = ctypes.WinDLL("ole32")
        shell32.SHGetKnownFolderPath.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p))
        ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
        folder_id = _guid(ids[name])
        path = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path)) != 0 or not path.value:
            return ""
        try:
            found = path.value
        finally:
            ole32.CoTaskMemFree(ctypes.cast(path, ctypes.c_void_p))
        return found if os.path.isdir(found) else ""

    # --- sound -----------------------------------------------------------------------------------

    def volume(self) -> tuple[int, bool]:
        import ctypes
        endpoint = _audio_endpoint()
        level, muted = ctypes.c_float(), ctypes.c_int()
        _com(endpoint, 9, ctypes.POINTER(ctypes.c_float))(endpoint, ctypes.byref(level))  # GetMasterVolumeLevelScalar
        _com(endpoint, 15, ctypes.POINTER(ctypes.c_int))(endpoint, ctypes.byref(muted))  # GetMute
        _release(endpoint)
        return round(level.value * 100), bool(muted.value)

    def set_volume(self, level: int | None = None, muted: bool | None = None) -> None:
        import ctypes
        endpoint = _audio_endpoint()
        if level is not None:
            _com(endpoint, 7, ctypes.c_float, ctypes.c_void_p)(endpoint, level / 100, None)  # SetMasterVolumeLevelScalar
        if muted is not None:
            _com(endpoint, 14, ctypes.c_int, ctypes.c_void_p)(endpoint, int(muted), None)  # SetMute
        _release(endpoint)

    # --- the screen and Wi-Fi: Windows' own PowerShell, fixed scripts ------------------------------------

    def brightness(self) -> int:
        out = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
        try:
            return int(out.split()[0])
        except (IndexError, ValueError):
            raise PcProblem("this screen does not say its brightness (a desktop monitor?)") from None

    def set_brightness(self, level: int) -> None:
        _powershell("Invoke-CimMethod -InputObject (Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods) "
                    f"-MethodName WmiSetBrightness -Arguments @{{Timeout=[uint32]1; Brightness=[byte]{int(level)}}} | Out-Null")

    def set_wifi(self, on: bool) -> None:
        answer = _powershell(WIFI_SCRIPT.replace("STATE", "On" if on else "Off"))
        if "Allowed" not in answer:
            raise PcProblem("Windows did not let Kairu change Wi-Fi")

    # --- status ----------------------------------------------------------------------------------

    def status(self) -> Status:
        import ctypes
        from ctypes import wintypes

        class Memory(ctypes.Structure):
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong)] + [(name, ctypes.c_ulonglong) for name in (
                            "ullTotalPageFile", "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]

        class Power(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                        ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        memory = Memory(dwLength=ctypes.sizeof(Memory))
        kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
        power = Power()
        kernel32.GetSystemPowerStatus(ctypes.byref(power))
        battery = None if power.BatteryFlag == 128 or power.BatteryLifePercent == 255 else int(power.BatteryLifePercent)
        return Status(memory.ullAvailPhys / 2**30, memory.ullTotalPhys / 2**30, battery, power.ACLineStatus == 1, _cpu_percent(),
                      _top_memory())

    # --- power -----------------------------------------------------------------------------------

    def lock(self) -> None:
        if not _user32().LockWorkStation():
            raise PcProblem("Windows did not lock the PC")

    def sleep(self) -> None:
        """Standby if this PC allows it from here; otherwise (Modern Standby PCs) the screen off, which leads to it."""
        import ctypes
        if not ctypes.WinDLL("powrprof").SetSuspendState(0, 0, 0):
            _user32().PostMessageW(0xFFFF, 0x0112, 0xF170, 2)  # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, off

    def restart(self) -> None:
        _shutdown("/r")

    def shutdown(self) -> None:
        _shutdown("/s")


BROWSER_FOLDERS = {"chrome": Path("Google") / "Chrome" / "Application", "edge": Path("Microsoft") / "Edge" / "Application"}


HANDOVER_SECONDS = 15


def _hand_to_desktop(command) -> None:
    """Start a helper Explorer and wait until it has handed the path to your desktop's own Explorer.

    The helper runs inside the action's job, and the job is ended as soon as the action ends. It used to get a fixed 0.3 s:
    on a slower laptop it was ended before it had handed over, so nothing opened while Kairu said "Opened Chrome". The
    desktop's Explorer, which starts the app, is outside the job, so once the helper has ended the app stays open.
    """
    helper = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        helper.wait(timeout=HANDOVER_SECONDS)  # Explorer's own exit code is 1 even when it worked, so it is not read
    except subprocess.TimeoutExpired:
        raise PcProblem("Windows did not open it in time; try again") from None


CLICKABLE = ("button", "link", "menu", "tab", "item")


def _best_control(name: str, names) -> str | None:
    """The control you mean: the same name (any capitals), else the shortest name that has your words in it."""
    wanted = " ".join(name.lower().split())
    names = [" ".join(str(found).split()) for found in names if str(found).strip()]
    exact = [found for found in names if found.lower() == wanted]
    if exact:
        return exact[0]
    holding = sorted((found for found in names if wanted in found.lower()), key=len)
    return holding[0] if holding else None


def _plain(path: str) -> str:
    """A path as Explorer reads it: without the \\\\?\\ that Python puts in front of a very long one."""
    return path[4:] if path.startswith("\\\\?\\") else path


def make_shortcut(link: Path, target: str, arguments: str) -> None:
    """A Windows shortcut (.lnk) to `target` with these arguments, through the Shell's own IShellLinkW (ctypes, no package)."""
    import ctypes
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitialize(None)
    shell_link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        made = ole32.CoCreateInstance(ctypes.byref(_guid("00021401-0000-0000-C000-000000000046")), None, 1,
                                      ctypes.byref(_guid("000214F9-0000-0000-C000-000000000046")), ctypes.byref(shell_link))
        if made or not shell_link:
            raise PcProblem("Windows could not make a shortcut for the browser")
        _com(shell_link, 20, ctypes.c_wchar_p)(shell_link, target)  # SetPath
        _com(shell_link, 11, ctypes.c_wchar_p)(shell_link, arguments)  # SetArguments
        _com(shell_link, 0, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            shell_link, ctypes.byref(_guid("0000010B-0000-0000-C000-000000000046")), ctypes.byref(persist))  # QueryInterface
        if not persist:
            raise PcProblem("Windows could not save the browser's shortcut")
        saved = _com(persist, 6, ctypes.c_wchar_p, ctypes.c_int)(persist, str(link), 1)  # IPersistFile::Save
        if saved:
            raise PcProblem("Windows could not save the browser's shortcut")
    except OSError as error:
        raise PcProblem(f"Windows' shell did not answer ({type(error).__name__})") from None
    finally:
        for held in (persist, shell_link):
            if held:
                _release(held)


def read_shortcut(link: Path) -> tuple[str, str]:
    """(target, arguments) of a shortcut: for the tests."""
    import ctypes
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitialize(None)
    shell_link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    ole32.CoCreateInstance(ctypes.byref(_guid("00021401-0000-0000-C000-000000000046")), None, 1,
                           ctypes.byref(_guid("000214F9-0000-0000-C000-000000000046")), ctypes.byref(shell_link))
    try:
        _com(shell_link, 0, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            shell_link, ctypes.byref(_guid("0000010B-0000-0000-C000-000000000046")), ctypes.byref(persist))
        _com(persist, 5, ctypes.c_wchar_p, ctypes.c_uint)(persist, str(link), 0)  # IPersistFile::Load
        target, arguments = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(4096)
        _com(shell_link, 3, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint)(shell_link, target, 1024, None, 0)
        _com(shell_link, 10, ctypes.c_wchar_p, ctypes.c_int)(shell_link, arguments, 4096)
        return target.value, arguments.value
    finally:
        for held in (persist, shell_link):
            if held:
                _release(held)


WIFI_SCRIPT = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($operation, $type) { $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation)); $task.Wait(-1) | Out-Null; $task.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | Where-Object { $_.Kind -eq 'WiFi' }
Await ($wifi.SetStateAsync('STATE')) ([Windows.Devices.Radios.RadioAccessStatus])
"""


def _powershell(script: str) -> str:
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    try:
        done = subprocess.run([str(program), "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True,
                              timeout=SCRIPT_SECONDS, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PcProblem(f"Windows' PowerShell did not answer ({type(error).__name__})") from None
    if done.returncode:
        raise PcProblem("Windows refused that")
    return done.stdout


def _shutdown(how: str) -> None:
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "shutdown.exe"
    done = subprocess.run([str(program), how, "/t", "5", "/c", "Kairu: you approved this with your PIN"], capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    if done.returncode:
        raise PcProblem("Windows refused that")


def _user32():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.WindowFromPoint.argtypes = (wintypes.POINT,)
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    return user32


def _program_of(pid: int) -> str:
    """The program's file name without .exe, lower case; "" if Windows does not say."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            return ""
        return Path(path.value).stem.lower()
    finally:
        kernel32.CloseHandle(handle)


def _cpu_percent() -> int:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def times():
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        return [(item.dwHighDateTime << 32) | item.dwLowDateTime for item in (idle, kernel, user)]

    idle_before, kernel_before, user_before = times()
    time.sleep(0.25)
    idle, kernel, user = times()
    busy_and_idle = (kernel - kernel_before) + (user - user_before)  # a system's kernel time includes its idle time
    return round(100 * (busy_and_idle - (idle - idle_before)) / busy_and_idle) if busy_and_idle else 0


def _top_memory(count: int = 3) -> tuple[tuple[str, int], ...]:
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                                 "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snapshot, totals = kernel32.CreateToolhelp32Snapshot(0x2, 0), {}
    try:
        entry = Entry(dwSize=ctypes.sizeof(Entry))
        more = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        while more:
            handle = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)
            if handle:
                counters = Counters(cb=ctypes.sizeof(Counters))
                if kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    name = Path(entry.szExeFile).stem.lower()
                    totals[name] = totals.get(name, 0) + counters.WorkingSetSize
                kernel32.CloseHandle(handle)
            more = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))
    top = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:count]
    return tuple((name, size // 2**20) for name, size in top)


# --- the sound system's COM objects, through ctypes -------------------------------------------------

def _guid(text: str):
    import ctypes
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    parts = text.split("-")
    tail = bytes.fromhex(parts[3] + parts[4])
    return Guid(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8)(*tail))


def _com(pointer, slot: int, *arguments):
    """Method number `slot` of a COM object, as a function that takes the object first."""
    import ctypes
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *arguments)
    return prototype(table[slot])


def _release(pointer) -> None:
    import ctypes
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(pointer)


def _audio_endpoint():
    """The default speakers' volume control (IAudioEndpointVolume)."""
    import ctypes
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitialize(None)
    enumerator, device, endpoint = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(ctypes.byref(_guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 1,
                               ctypes.byref(_guid("A95664D2-9614-4F35-A746-DE8DB63617E6")), ctypes.byref(enumerator))
        _com(enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(enumerator, 0, 1, ctypes.byref(device))
        _com(device, 3, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            device, ctypes.byref(_guid("5CDF2C82-841E-4546-9722-0CF74078229A")), 1, None, ctypes.byref(endpoint))
    except OSError as error:
        raise PcProblem(f"Windows' sound system did not answer ({type(error).__name__})") from None
    finally:
        for held in (device, enumerator):
            if held:
                _release(held)
    if not endpoint:
        raise PcProblem("this PC has no speakers to set")
    return endpoint
