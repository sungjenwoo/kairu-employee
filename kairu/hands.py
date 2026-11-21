"""Kairu's hands, the lowest layer (Windows only): keys and letters (SendInput), a mouse click, and UI Automation.

Only kairu/tasks/pc.py (class Windows) imports this, and only Kairu's hands (kairu/tasks/screen.py, inside Guardian's screen.*
actions) call it there. It lives outside kairu/tasks/ and kairu/bar/ on purpose: no code in those folders may make key presses,
so nothing there could ever fill or press the bar's "yes" and PIN card (tests_kairu/test_bar.py). These hands can't reach the card:

  - every key, letter and click is sent only while the window in front belongs to the program it is meant for (in_front),
    checked again before each few letters; if anything else comes to the front, it stops;
  - kairu/tasks/screen.py refuses Kairu's own windows (the bar and the workspace are Python and Kairu's own browser profile)
    before any window is brought to the front, and tests_kairu/test_screen.py proves both.

PC4's backup eyes (capture, ocr): a picture of ONE window (PrintWindow, so nothing on top of it is in it), handed to Windows'
own OCR (Windows.Media.Ocr) through a fixed PowerShell script on its standard input. The picture is only ever in memory: it is
never written to disk, never sent anywhere, and is gone when the step ends. Only its words come back, and they are data.

Kairu's eyes (ADR-051 proposed, BAR.md "Kairu's eyes"): the same picture of ONE window, made a PNG in memory by png_of, is
the one picture that leaves the PC: screen.look (kairu/tasks/eyes.py) sends it to Google Gemini, only for a window that is not
Kairu's own, a security, password, terminal or money window (and on the safe list when it takes control). It is still
never written to disk.
"""

import functools
import json
import os
import subprocess
import time
from pathlib import Path

from kairu.tasks.pc import PcProblem, Window, _program_of, _user32

TYPE_GAP = 0.035  # seconds between two letters, each its own SendInput (pc.Windows.type_text). 0.012 was too fast for
# Windows 11's Notepad with spell check and several tabs: "a short to-do list" came out as "a tttttt eeee" (16 Nov 2026)
UIA_SECONDS = 15
OCR_SECONDS = 25
MOST_PIXELS = 40_000_000  # a picture larger than this (about 6300 x 6300) is not taken
VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "space": 0x20,
      "backspace": 0x08, "delete": 0x2E, "insert": 0x2D, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24,
      "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "plus": 0xBB, "minus": 0xBD,
      **{f"f{number}": 0x6F + number for number in range(1, 13)},
      **{letter: ord(letter.upper()) for letter in "abcdefghijklmnopqrstuvwxyz0123456789"}}
EXTENDED = {0x2E, 0x2D, 0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22}


@functools.lru_cache(maxsize=1)
def input_types():
    """SendInput's structures, made once, so every event of one call is the same type."""
    import ctypes
    from ctypes import wintypes

    class KeyInput(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class Either(ctypes.Union):
        _fields_ = [("ki", KeyInput), ("mi", MouseInput), ("padding", ctypes.c_byte * 32)]

    class Input(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", Either)]

    return Input, KeyInput, MouseInput


def key(vk: int, up: bool, unit: int | None = None):
    """One key event: a virtual key, or (unit given) one UTF-16 letter typed as itself (KEYEVENTF_UNICODE)."""
    Input, KeyInput, _ = input_types()
    flags = (0x0002 if up else 0) | (0x0004 if unit is not None else 0) | (0x0001 if vk in EXTENDED else 0)
    return Input(type=1, ki=KeyInput(wVk=vk, wScan=unit or 0, dwFlags=flags, time=0, dwExtraInfo=0))


KAIRU_PROGRAMS = ("python", "pythonw", "py", "pyw", "kairu")  # the bar and the workspace's server are Python programs


def send(events, to: int) -> None:
    """Send these key or mouse events, only if the window `to` belongs to the program in front, and that program is not
    Kairu's own. Checked right before Windows is given the events: this is the only place Kairu makes key presses or clicks."""
    import ctypes
    if not events:
        return
    user32 = _user32()
    front = user32.GetForegroundWindow()
    if not front or pid_of(front) != pid_of(to):
        raise PcProblem("another window came to the front, so Kairu stopped")
    if _program_of(pid_of(front)) in KAIRU_PROGRAMS:
        raise PcProblem("Kairu never types or clicks in its own windows")
    Input = type(events[0])
    array = (Input * len(events))(*events)
    sender = ctypes.WinDLL("user32", use_last_error=True)
    sent = sender.SendInput(len(events), array, ctypes.sizeof(Input))
    if sent != len(events):
        raise PcProblem("Windows blocked the keys (an app run as administrator can't be typed into)")


PASTE_FROM = 20  # letters: longer words are pasted (pc.Windows.type_text); typed letter by letter, Windows 11's Notepad
# garbled them even at 35 ms a letter ("a short to-do list" came out as "a hhort sssssssst", laptop test, 16 Nov 2026)
TEXT_FORMATS = {1, 7, 13, 16}  # CF_TEXT, CF_OEMTEXT, CF_UNICODETEXT, CF_LOCALE: what Windows makes from one piece of text


def _clipboard():
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.GetClipboardData.argtypes, user32.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    user32.EnumClipboardFormats.argtypes, user32.EnumClipboardFormats.restype = [wintypes.UINT], wintypes.UINT
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [wintypes.HGLOBAL], ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes, kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL], [wintypes.HGLOBAL]
    return user32, kernel32


def _open_clipboard(user32) -> bool:
    for _ in range(20):  # another program may hold it a moment
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.025)
    return False


def _put_text(user32, kernel32, text: str | None) -> bool:
    """With the clipboard open: empty it and, if text is given, put it there."""
    import ctypes
    user32.EmptyClipboard()
    if text is None:
        return True
    data = text.encode("utf-16-le") + b"\0\0"
    handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
    pointer = kernel32.GlobalLock(handle) if handle else None
    if not pointer:
        return False
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT; Windows owns the memory once it is set
        kernel32.GlobalFree(handle)
        return False
    return True


def paste_text(text: str, to: int) -> bool:
    """Paste these words into window `to` with Ctrl+V, and give your clipboard back as it was. Only when your clipboard holds
    nothing or plain text (a picture or copied files are never touched: then False, and the words are typed instead).
    The keys go through the one sender above and its checks. Windows only; False anywhere else or if the clipboard can't be had."""
    import ctypes
    try:
        user32, kernel32 = _clipboard()
    except (AttributeError, OSError):
        return False
    if not _open_clipboard(user32):
        return False
    try:
        kind, kinds = 0, set()
        while True:
            kind = user32.EnumClipboardFormats(kind)
            if not kind:
                break
            kinds.add(kind)
        if kinds - TEXT_FORMATS:
            return False
        before = None
        if 13 in kinds:
            handle = user32.GetClipboardData(13)
            pointer = kernel32.GlobalLock(handle) if handle else None
            if pointer:
                before = ctypes.wstring_at(pointer)
                kernel32.GlobalUnlock(handle)
        if not _put_text(user32, kernel32, text):
            return False
    finally:
        user32.CloseClipboard()
    try:
        events = [key(VK["ctrl"], False), key(0x56, False), key(0x56, True), key(VK["ctrl"], True)]  # Ctrl+V
        send(events, to)
        time.sleep(0.35)  # the app reads the clipboard
    finally:
        if _open_clipboard(user32):
            try:
                _put_text(user32, kernel32, before)
            finally:
                user32.CloseClipboard()
    return True


def keys_released(seconds: float = 2.0) -> None:
    """Wait until you have let go of Ctrl, Alt, Shift and the Windows key, so a held key never joins Kairu's keys."""
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    deadline = time.monotonic() + seconds
    while any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        if time.monotonic() > deadline:
            raise PcProblem("let go of Ctrl, Alt, Shift and the Windows key, then try again")
        time.sleep(0.05)


def pid_of(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes
    pid = wintypes.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def in_front(hwnd: int) -> bool:
    """True when the window in front belongs to the same program (process) as this one."""
    front = _user32().GetForegroundWindow()
    return bool(front) and pid_of(front) == pid_of(hwnd)


def wait_front(hwnd: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if in_front(hwnd):
            return True
        time.sleep(0.05)
    return in_front(hwnd)


def keyboard_in_browser_bar(hwnd: int) -> bool:
    """True when a Chromium browser's keyboard focus is in its own top bar (the address and search bar), not in the page.
    The page is a child window (Chrome_RenderWidgetHostHWND); the browser's own bar belongs to the top window itself."""
    import ctypes
    from ctypes import wintypes

    class GuiInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                    ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

    user32 = _user32()
    thread = user32.GetWindowThreadProcessId(hwnd, None)
    info = GuiInfo(cbSize=ctypes.sizeof(GuiInfo))
    if not thread or not ctypes.WinDLL("user32").GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.hwndFocus:
        return False
    name = ctypes.create_unicode_buffer(64)
    ctypes.WinDLL("user32").GetClassNameW(info.hwndFocus, name, 64)
    return name.value != "Chrome_RenderWidgetHostHWND" and user32.GetAncestor(info.hwndFocus, 2) == hwnd


def command_line_of(pid: int) -> str:
    """A process's command line (NtQueryInformationProcess, ProcessCommandLineInformation); "" if Windows does not say."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtQueryInformationProcess.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                                ctypes.POINTER(wintypes.ULONG))
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.ULONG(0)
        ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(size))
        if not size.value or size.value > 1 << 20:
            return ""
        buffer = ctypes.create_string_buffer(size.value)
        if ntdll.NtQueryInformationProcess(handle, 60, buffer, size, ctypes.byref(size)) != 0:
            return ""

        class Text(ctypes.Structure):
            _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]

        text = Text.from_buffer(buffer)
        return ctypes.wstring_at(text.Buffer, text.Length // 2) if text.Buffer else ""
    finally:
        kernel32.CloseHandle(handle)


def click_at(window: Window, x: int, y: int) -> None:
    """The last way to click: the real mouse, only at a point that is inside this window and shows this window."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: UI Automation's points are real pixels
    except (AttributeError, OSError):
        pass
    rect = wintypes.RECT()
    user32.GetWindowRect(window.handle, ctypes.byref(rect))
    hit = user32.WindowFromPoint(wintypes.POINT(x, y))
    if not (rect.left <= x < rect.right and rect.top <= y < rect.bottom) or not hit or \
            user32.GetAncestor(hit, 2) != window.handle:  # GA_ROOT
        raise PcProblem("that button isn't where it can be clicked safely")
    if not in_front(window.handle):
        raise PcProblem("another window came to the front, so I clicked nothing")
    Input, _, MouseInput = input_types()
    user32.SetCursorPos(x, y)
    send([Input(type=0, mi=MouseInput(0, 0, 0, 0x0002, 0, 0)), Input(type=0, mi=MouseInput(0, 0, 0, 0x0004, 0, 0))], window.handle)
    time.sleep(0.15)


def window_rect(window: Window) -> tuple[int, int, int, int]:
    """This window's rectangle in real screen pixels (left, top, right, bottom), as capture() and click_at() see it."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2, as capture() and click_at()
    except (AttributeError, OSError):
        pass
    rect = wintypes.RECT()
    if not user32.GetWindowRect(window.handle, ctypes.byref(rect)) or rect.right <= rect.left or rect.bottom <= rect.top:
        raise PcProblem(f"that {window.app} window has closed")
    return rect.left, rect.top, rect.right, rect.bottom


def picture_point(window: Window, x: int, y: int, most_width: int | None = None) -> tuple[int, int]:
    """A point on a look's picture of this window (png_of may have sent it smaller) as a point on the screen."""
    left, top, right, bottom = window_rect(window)
    step = max(1, -(-(right - left) // max(1, most_width or MOST_SEEN_WIDTH)))
    sx, sy = left + int(x) * step + step // 2, top + int(y) * step + step // 2
    if not (left <= sx < right and top <= sy < bottom):
        raise PcProblem("that point isn't inside the window")
    return sx, sy


def wheel(window: Window, notches: int) -> None:
    """Scroll by the real mouse wheel over the middle of this window (ADR-054 screen.scroll): only while it is in front and the
    middle shows this window. notches > 0 scrolls up, < 0 down. Nothing is clicked."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    left, top, right, bottom = window_rect(window)
    x, y = (left + right) // 2, (top + bottom) // 2
    hit = user32.WindowFromPoint(wintypes.POINT(x, y))
    if not hit or user32.GetAncestor(hit, 2) != window.handle:  # GA_ROOT
        raise PcProblem("something else covers the middle of that window, so I didn't scroll")
    if not in_front(window.handle):
        raise PcProblem("another window came to the front, so I didn't scroll")
    Input, _, MouseInput = input_types()
    user32.SetCursorPos(x, y)
    for _ in range(abs(int(notches))):
        amount = (120 if notches > 0 else -120) & 0xFFFFFFFF  # WHEEL_DELTA, as a DWORD; 0x0800 is MOUSEEVENTF_WHEEL
        send([Input(type=0, mi=MouseInput(0, 0, amount, 0x0800, 0, 0))], window.handle)
        time.sleep(0.05)
    time.sleep(0.2)


def capture(window: Window) -> tuple[bytes, int, int, int, int]:
    """A picture of this one window, in memory: (BGRA pixels, width, height, left, top), in screen pixels. PrintWindow draws
    only this window, so a window on top of it (the bar's card included) is never in it. Nothing is written to disk."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: the same real pixels as click_at
    except (AttributeError, OSError):
        pass
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = (wintypes.HWND, ctypes.c_void_p)
    user32.PrintWindow.argtypes = (wintypes.HWND, ctypes.c_void_p, wintypes.UINT)
    user32.PrintWindow.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = (ctypes.c_void_p,)
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.c_void_p, wintypes.DWORD)
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
    gdi32.DeleteDC.argtypes = (ctypes.c_void_p,)
    if user32.IsIconic(window.handle):
        raise PcProblem(f"{window.app}'s window is minimised, so there is nothing to see; bring it up and ask again")
    rect = wintypes.RECT()
    if not user32.GetWindowRect(window.handle, ctypes.byref(rect)):
        raise PcProblem(f"that {window.app} window has closed")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0 or width * height > MOST_PIXELS:
        raise PcProblem(f"I can't take a picture of {window.app}'s window")

    class Header(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down, 32 bits a pixel, BGRA
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(screen, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(memory, bitmap) if bitmap and memory else None
    try:
        drawn = bool(bitmap and memory and bits.value and user32.PrintWindow(window.handle, memory, 2))  # PW_RENDERFULLCONTENT
        pixels = bytearray(ctypes.string_at(bits.value, width * height * 4)) if drawn else bytearray()
    finally:
        if old:
            gdi32.SelectObject(memory, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
    if not pixels:
        raise PcProblem(f"Windows didn't let Kairu see {window.app}'s window")
    pixels[3::4] = b"\xff" * (width * height)  # opaque: PrintWindow leaves the alpha byte at 0
    return bytes(pixels), width, height, rect.left, rect.top


def capture_screen(regions: list[tuple[str, tuple[int, int, int, int]]]) -> tuple[bytes, int, int]:
    """The whole screen (every monitor), in memory: (BGRA pixels, width, height). Nothing is written to disk.

    "What's on my whole screen" (kairu/tasks/eyes.py, the owner's ask of 19 Nov 2026). `regions` come back to front, in screen
    pixels: ("hide", rect) is painted black (a window Kairu must never show: its own, security, password, terminal, money,
    unknown); ("show", rect) puts back what the screen showed there (an ordinary window in front of a hidden one). So a hidden
    window behind an ordinary one only loses what is really its own, and one in front of an ordinary one stays black."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixels, as screen_windows gives
    except (AttributeError, OSError):
        pass
    user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = (wintypes.HWND, ctypes.c_void_p)
    gdi32.CreateCompatibleDC.argtypes = (ctypes.c_void_p,)
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.c_void_p, wintypes.DWORD)
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.BitBlt.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                             ctypes.c_int, ctypes.c_int, wintypes.DWORD)
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
    gdi32.DeleteDC.argtypes = (ctypes.c_void_p,)
    left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    width, height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)  # SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
    if width <= 0 or height <= 0 or width * height > MOST_PIXELS:
        raise PcProblem("I can't take a picture of this screen")

    class Header(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down, 32 bits a pixel, BGRA
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(screen, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(memory, bitmap) if bitmap and memory else None
    try:
        drawn = bool(bitmap and memory and bits.value and
                     gdi32.BitBlt(memory, 0, 0, width, height, screen, left, top, 0x00CC0020 | 0x40000000))  # SRCCOPY|CAPTUREBLT
        original = bytes(ctypes.string_at(bits.value, width * height * 4)) if drawn else b""
    finally:
        if old:
            gdi32.SelectObject(memory, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
    if not original:
        raise PcProblem("Windows didn't let Kairu see the screen")
    pixels = paint_regions(original, width, height, left, top, regions)
    pixels[3::4] = b"\xff" * (width * height)
    return bytes(pixels), width, height


def paint_regions(original: bytes, width: int, height: int, left: int, top: int,
                  regions: list[tuple[str, tuple[int, int, int, int]]]) -> bytearray:
    """capture_screen's painting, on its own so it can be tested anywhere: back to front, "hide" paints black and "show" puts
    back the screen's own pixels. Rectangles are screen pixels (left, top, right, bottom), cut to the picture."""
    pixels = bytearray(original)
    for kind, (x0, y0, x1, y1) in regions:
        x0, x1 = max(0, x0 - left), min(width, x1 - left)
        y0, y1 = max(0, y0 - top), min(height, y1 - top)
        if x0 >= x1 or y0 >= y1:
            continue
        black = bytes((x1 - x0) * 4)
        for y in range(y0, y1):
            start, end = (y * width + x0) * 4, (y * width + x1) * 4
            pixels[start:end] = black if kind == "hide" else original[start:end]
    return pixels


MOST_SEEN_WIDTH = 2000  # Kairu's eyes (ADR-051 proposed): a wider window is sent at half (or a third ...) of its size


def png_of(pixels: bytes, width: int, height: int, most_width: int = MOST_SEEN_WIDTH) -> tuple[bytes, int, int]:
    """A picture held in memory (BGRA pixels, top-down, as capture() gives it) as a PNG, also in memory: (png, width, height).

    For Kairu's eyes (kairu/tasks/eyes.py): only every Nth pixel of every Nth row is kept when the window is wider than
    most_width, and the alpha byte is dropped. Standard library only (zlib); nothing is ever written to disk."""
    import struct
    import zlib
    if width <= 0 or height <= 0 or len(pixels) != width * height * 4:
        raise PcProblem("that picture isn't whole")
    step = max(1, -(-width // max(1, most_width)))
    view = memoryview(pixels).cast("B").cast("I")  # one 32-bit BGRA pixel each
    small = bytearray()
    for y in range(0, height, step):
        small += view[y * width:(y + 1) * width:step].tobytes()
    out_width, out_height = len(range(0, width, step)), len(range(0, height, step))
    rgb = bytearray(out_width * out_height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = small[2::4], small[1::4], small[0::4]
    del small
    stride = out_width * 3
    rows = b"".join(b"\x00" + bytes(rgb[row * stride:(row + 1) * stride]) for row in range(out_height))
    del rgb

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", out_width, out_height, 8, 2, 0, 0, 0)  # 8 bits a channel, RGB
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""),
            out_width, out_height)


def ocr(pixels: bytes, width: int, height: int) -> dict:
    """Windows' own OCR over a picture held in memory, through Windows' own PowerShell and a fixed script. The pixels go in on
    its standard input and the size as environment variables, never into the script's text; only words come back, as JSON:
    {"lines": [[line, [[word, x, y, width, height], ...]], ...]} in the picture's pixels, or {"why": ...}."""
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    env = {**os.environ, "KAIRU_OCR_WIDTH": str(int(width)), "KAIRU_OCR_HEIGHT": str(int(height))}
    try:
        done = subprocess.run([str(program), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", OCR_SCRIPT],
                              input=pixels, capture_output=True, timeout=OCR_SECONDS, env=env,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PcProblem(f"Windows' OCR did not answer ({type(error).__name__})") from None
    try:
        answer = json.loads(done.stdout.decode("utf-8", errors="replace").strip() or "{}")
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise PcProblem("Windows' OCR couldn't read that window")
    if answer.get("why") not in (None, "no-ocr"):
        raise PcProblem(f"Windows' OCR couldn't read that window ({str(answer.get('why'))[:20]})")
    return answer


def uia(mode: str, window: Window, name: str = "", page: bool = False, item: str = "") -> dict:
    """UI Automation, through Windows' own PowerShell and a fixed script. The window and the names go in as environment
    variables, never into the script's text; the answer is JSON."""
    program = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    env = {**os.environ, "KAIRU_UIA_MODE": mode, "KAIRU_UIA_WINDOW": str(int(window.handle)), "KAIRU_UIA_NAME": name,
           "KAIRU_UIA_PAGE": "1" if page else "0", "KAIRU_UIA_ITEM": item}
    try:
        done = subprocess.run([str(program), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", UIA_SCRIPT],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=UIA_SECONDS, env=env,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PcProblem(f"Windows' UI Automation did not answer ({type(error).__name__})") from None
    try:
        answer = json.loads(done.stdout.strip() or "{}")
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise PcProblem(f"I couldn't read {window.app}'s window")
    return answer


UIA_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false  # a page's words in any language, as UTF-8 (15 Nov 2026)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$AE = [System.Windows.Automation.AutomationElement]
$CT = [System.Windows.Automation.ControlType]
$mode = $env:KAIRU_UIA_MODE
$want = ([string]$env:KAIRU_UIA_NAME).Trim().ToLower() -replace '\s+', ' '
function Say($value) { [Console]::Out.Write((ConvertTo-Json -InputObject $value -Compress -Depth 4)) }
try { $root = $AE::FromHandle([IntPtr][Int64]$env:KAIRU_UIA_WINDOW) } catch { Say @{}; exit 0 }
$kinds = @{}
$kinds[$CT::Button.Id] = 'button'; $kinds[$CT::SplitButton.Id] = 'button'; $kinds[$CT::CheckBox.Id] = 'button'
$kinds[$CT::RadioButton.Id] = 'button'; $kinds[$CT::Hyperlink.Id] = 'link'; $kinds[$CT::Edit.Id] = 'box'
$kinds[$CT::ComboBox.Id] = 'box'; $kinds[$CT::MenuItem.Id] = 'menu'; $kinds[$CT::TabItem.Id] = 'tab'
$kinds[$CT::ListItem.Id] = 'item'; $kinds[$CT::TreeItem.Id] = 'item'; $kinds[$CT::Text.Id] = 'text'
$clickable = @('button', 'link', 'menu', 'tab', 'item')
function Walk($start, $limit) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $found = New-Object System.Collections.ArrayList
  $stack = New-Object System.Collections.Stack
  $stack.Push($start)
  $watch = [Diagnostics.Stopwatch]::StartNew()
  while ($stack.Count -gt 0 -and $found.Count -lt $limit -and $watch.ElapsedMilliseconds -lt 5000) {
    $element = $stack.Pop()
    if (-not [object]::ReferenceEquals($element, $start)) { [void]$found.Add($element) }
    $children = New-Object System.Collections.ArrayList
    try {
      $child = $walker.GetFirstChild($element)
      while ($child -ne $null) { [void]$children.Add($child); $child = $walker.GetNextSibling($child) }
    } catch { }
    for ($i = $children.Count - 1; $i -ge 0; $i--) { $stack.Push($children[$i]) }
  }
  return ,$found
}
function Info($element) {
  try {
    $c = $element.Current
    if ($c.IsOffscreen -or -not $c.IsEnabled) { return $null }
    $kind = $kinds[$c.ControlType.Id]
    if (-not $kind) { return $null }
    return @{ kind = $kind; name = (([string]$c.Name).Trim() -replace '\s+', ' '); id = [string]$c.AutomationId; help = [string]$c.HelpText }
  } catch { return $null }
}
function Clickables($start) {
  $list = New-Object System.Collections.ArrayList
  foreach ($element in (Walk $start 3000)) {
    $info = Info $element
    if ($info -and $info.name -and ($clickable -contains $info.kind)) { [void]$list.Add(@($element, $info.name)) }
  }
  return ,$list
}
if ($mode -eq 'focus') {
  try { $root.SetFocus(); Say @{ ok = $true } } catch { Say @{ ok = $false } }
  exit 0
}
if ($mode -eq 'focused') {
  try {
    $focused = $AE::FocusedElement
    $c = $focused.Current
    $inside = $false
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $up = $focused
    for ($i = 0; $i -lt 60 -and $up -ne $null; $i++) {
      if ($up.Current.NativeWindowHandle -eq [Int32][Int64]$env:KAIRU_UIA_WINDOW) { $inside = $true; break }
      $up = $walker.GetParent($up)
    }
    $box = ($c.ControlType.Id -eq $CT::Edit.Id) -or ($c.ControlType.Id -eq $CT::ComboBox.Id)
    $words = ([string]$c.Name + ' ' + [string]$c.AutomationId + ' ' + [string]$c.HelpText).ToLower()
    Say @{ search = ($inside -and $box -and ($words -match 'search|address|url|omnibox')); password = ($inside -and [bool]$c.IsPassword) }
  } catch { Say @{ search = $false; password = $true } }
  exit 0
}
if ($mode -eq 'read') {
  $seen = New-Object System.Collections.ArrayList
  $texts = 0
  foreach ($element in (Walk $root 2000)) {
    $info = Info $element
    if (-not $info -or -not $info.name) { continue }
    if ($info.kind -eq 'text') { $texts++; if ($texts -gt 40) { continue } }
    $short = $info.name; if ($short.Length -gt 80) { $short = $short.Substring(0, 80) }
    [void]$seen.Add(@($info.kind, $short))
    if ($seen.Count -ge 300) { break }
  }
  Say @{ seen = $seen }
  exit 0
}
if ($mode -eq 'text') {
  # PC4: the words any window shows, top to bottom: its documents and boxes (never a password box), lists, labels and links
  $lines = New-Object System.Collections.ArrayList
  $total = 0
  $boxes = @($CT::Document.Id, $CT::Edit.Id)
  $named = @($CT::Text.Id, $CT::ListItem.Id, $CT::TreeItem.Id, $CT::DataItem.Id, $CT::Hyperlink.Id, $CT::HeaderItem.Id)
  $all = Walk $root 4000
  # a status bar ("Line 1, Column 19, 18 characters, UTF-8" in Notepad) is the app's, not the window's words: left out
  $skip = @{}
  foreach ($element in $all) {
    try {
      $c = $element.Current
      if ($c.ControlType.Id -eq $CT::StatusBar.Id -or $c.AutomationId -match 'status' -or $c.Name -match '^status( ?bar)?$') {
        $skip[[string]::Join(',', $element.GetRuntimeId())] = $true
        foreach ($part in (Walk $element 300)) { $skip[[string]::Join(',', $part.GetRuntimeId())] = $true }
      }
    } catch { }
  }
  foreach ($element in $all) {
    try {
      if ($skip.Count -gt 0 -and $skip.ContainsKey([string]::Join(',', $element.GetRuntimeId()))) { continue }
      $c = $element.Current
      $id = $c.ControlType.Id
      $words = $null
      if ($boxes -contains $id) {
        if ($c.IsPassword) { continue }
        $pattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) { $words = $pattern.DocumentRange.GetText(20000) }
        elseif ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) { $words = [string]$pattern.Current.Value }
      } elseif ($named -contains $id) {
        if ($c.IsOffscreen) { continue }
        $words = [string]$c.Name
      } else { continue }
      if (-not $words) { continue }
      foreach ($line in ($words -split "`r`n|`r|`n")) {
        $line = ($line.Trim() -replace '\s+', ' ')
        if (-not $line) { continue }
        if ($line.Length -gt 600) { $line = $line.Substring(0, 600) }
        [void]$lines.Add($line)
        $total += $line.Length
      }
      if ($total -gt 30000) { break }
    } catch { }
  }
  Say @{ lines = $lines }
  exit 0
}
if ($mode -eq 'page' -or $mode -eq 'ask') {
  # the web page's own part of a browser window (its Document), never the browser's bars
  $doc = $null
  for ($try = 0; $try -lt 3 -and $doc -eq $null; $try++) {
    $condition = New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty, $CT::Document)
    $doc = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    if ($doc -eq $null) { Start-Sleep -Milliseconds 400 }
  }
  if ($doc -eq $null) { Say @{ found = $false }; exit 0 }
  if ($mode -eq 'page') {
    # the words a person would read, top to bottom, on or off the screen: text and links only, as data
    $lines = New-Object System.Collections.ArrayList
    $total = 0
    foreach ($element in (Walk $doc 4000)) {
      try {
        $c = $element.Current
        $id = $c.ControlType.Id
        if ($id -ne $CT::Text.Id -and $id -ne $CT::Hyperlink.Id) { continue }
        $name = (([string]$c.Name).Trim() -replace '\s+', ' ')
        if (-not $name) { continue }
        if ($name.Length -gt 600) { $name = $name.Substring(0, 600) }
        [void]$lines.Add($name)
        $total += $name.Length
        if ($total -gt 30000) { break }
      } catch { }
    }
    Say @{ found = $true; text = $lines }
    exit 0
  }
  # 'ask': put the cursor in the page's question box. A page that asks you to sign in is yours to fill, never Kairu's
  $boxes = New-Object System.Collections.ArrayList
  foreach ($element in (Walk $doc 3000)) {
    $info = Info $element
    if (-not $info -or $info.kind -ne 'box') { continue }
    $words = ($info.name + ' ' + $info.id + ' ' + $info.help).ToLower()
    if ($words -match 'password|passcode|e-?mail|username|user name|phone number|verification code|otp') { Say @{ found = $true; signin = $true }; exit 0 }
    [void]$boxes.Add(@($element, $info.name, $words))
  }
  $pick = $null
  foreach ($box in $boxes) { if ($box[2] -match 'message|ask|prompt|reply|chat|write|talk|help|anything|question') { $pick = $box; break } }
  if ($pick -eq $null -and $boxes.Count -gt 0) { $pick = $boxes[$boxes.Count - 1] }
  if ($pick -eq $null) { Say @{ found = $true; box = $null }; exit 0 }
  try { $pick[0].SetFocus(); Say @{ found = $true; box = $(if ($pick[1]) { $pick[1] } else { 'the question box' }) } } catch { Say @{ found = $true; box = $null } }
  exit 0
}
if ($mode -eq 'search') {
  $start = $root
  if ($env:KAIRU_UIA_PAGE -eq '1') {
    $start = $null
    for ($try = 0; $try -lt 2 -and $start -eq $null; $try++) {
      $condition = New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty, $CT::Document)
      $start = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
      if ($start -eq $null) { Start-Sleep -Milliseconds 400 }
    }
    if ($start -eq $null) { Say @{ found = $null }; exit 0 }
  }
  foreach ($element in (Walk $start 3000)) {
    $info = Info $element
    if (-not $info -or $info.kind -ne 'box') { continue }
    $words = ($info.name + ' ' + $info.id + ' ' + $info.help).ToLower()
    if ($words -match 'search') {
      try { $element.SetFocus(); Say @{ found = $(if ($info.name) { $info.name } else { 'search' }) }; exit 0 } catch { }
    }
  }
  Say @{ found = $null }
  exit 0
}
if ($mode -eq 'find') {
  $best = $null
  foreach ($pair in (Clickables $root)) {
    $name = $pair[1]
    if ($name.ToLower() -eq $want) { Say @{ found = $name }; exit 0 }
    if ($name.ToLower().Contains($want) -and ($best -eq $null -or $name.Length -lt $best.Length)) { $best = $name }
  }
  Say @{ found = $best }
  exit 0
}
if ($mode -eq 'click') {
  foreach ($pair in (Clickables $root)) {
    if ($pair[1].ToLower() -ne $want) { continue }
    $element = $pair[0]
    $pattern = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $pattern.Invoke(); Say @{ clicked = 'invoke' }; exit 0 }
    if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { $pattern.Select(); Say @{ clicked = 'select' }; exit 0 }
    if ($element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) { $pattern.Toggle(); Say @{ clicked = 'toggle' }; exit 0 }
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) { $pattern.Expand(); Say @{ clicked = 'expand' }; exit 0 }
    $box = $element.Current.BoundingRectangle
    if ($box.IsEmpty) { break }
    Say @{ point = @([int]($box.X + $box.Width / 2), [int]($box.Y + $box.Height / 2)) }
    exit 0
  }
  Say @{}
  exit 0
}
# --- ADR-054: the screen agent's form steps, a point's name, boxes' rectangles, the browser's address, a saved login ---
function Boxes($start) {
  $list = New-Object System.Collections.ArrayList
  foreach ($element in (Walk $start 4000)) {
    try {
      $c = $element.Current
      if ($c.IsOffscreen -or -not $c.IsEnabled) { continue }
      if ($c.ControlType.Id -ne $CT::Edit.Id -and $c.ControlType.Id -ne $CT::ComboBox.Id) { continue }
      $label = (([string]$c.Name).Trim() -replace '\s+', ' ')
      [void]$list.Add(@($element, $label, [bool]$c.IsPassword, (($label + ' ' + [string]$c.AutomationId + ' ' + [string]$c.HelpText).ToLower())))
    } catch { }
  }
  return ,$list
}
function Named($items, $index) {
  # the one whose name is the wanted name; else the shortest that has it
  $best = $null
  foreach ($one in $items) {
    $name = ([string]$one[$index]).ToLower()
    if (-not $name) { continue }
    if ($name -eq $want) { return ,$one }
    if ($name.Contains($want) -and ($best -eq $null -or $name.Length -lt ([string]$best[$index]).Length)) { $best = $one }
  }
  return ,$best
}
if ($mode -eq 'fillbox') {
  $pick = Named (Boxes $root) 1
  if ($pick -eq $null) { Say @{ found = $null }; exit 0 }
  if ($pick[2]) { Say @{ password = $true }; exit 0 }
  try { $pick[0].SetFocus(); Say @{ found = $(if ($pick[1]) { $pick[1] } else { $want }) } } catch { Say @{ found = $null } }
  exit 0
}
if ($mode -eq 'loginbox') {
  # where a browser shows its saved logins: the username or email box, else the password box (only its place, never its value)
  $pick = $null
  foreach ($box in (Boxes $root)) { if (-not $box[2] -and $box[3] -match 'e-?mail|user|login|phone|mobile|account') { $pick = $box; break } }
  if ($pick -eq $null) { foreach ($box in (Boxes $root)) { if ($box[2]) { $pick = $box; break } } }
  if ($pick -eq $null) { Say @{ point = $null }; exit 0 }
  $r = $pick[0].Current.BoundingRectangle
  if ($r.IsEmpty) { Say @{ point = $null }; exit 0 }
  Say @{ point = @([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2)) }
  exit 0
}
if ($mode -eq 'rects') {
  $names = @()
  try { $names = @(ConvertFrom-Json ([string]$env:KAIRU_UIA_NAME)) } catch { Say @{ rects = $null }; exit 0 }
  $all = Boxes $root
  $rects = New-Object System.Collections.ArrayList
  foreach ($wanted in $names) {
    $want = ([string]$wanted).Trim().ToLower() -replace '\s+', ' '
    $pick = Named $all 1
    if ($pick -eq $null) { Say @{ rects = $null }; exit 0 }
    $r = $pick[0].Current.BoundingRectangle
    if ($r.IsEmpty) { Say @{ rects = $null }; exit 0 }
    [void]$rects.Add(@([int]$r.Left, [int]$r.Top, [int]$r.Right, [int]$r.Bottom))
  }
  Say @{ rects = $rects }
  exit 0
}
if ($mode -eq 'choose') {
  $item = ([string]$env:KAIRU_UIA_ITEM).Trim().ToLower() -replace '\s+', ' '
  $lists = New-Object System.Collections.ArrayList
  foreach ($element in (Walk $root 4000)) {
    try {
      $c = $element.Current
      if ($c.IsOffscreen -or -not $c.IsEnabled) { continue }
      if ($c.ControlType.Id -eq $CT::ComboBox.Id -or $c.ControlType.Id -eq $CT::List.Id) {
        [void]$lists.Add(@($element, (([string]$c.Name).Trim() -replace '\s+', ' ')))
      }
    } catch { }
  }
  $pick = Named $lists 1
  if ($pick -eq $null) { Say @{ chosen = $null; why = 'list' }; exit 0 }
  $pattern = $null
  if ($pick[0].TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) {
    try { $pattern.Expand(); Start-Sleep -Milliseconds 300 } catch { }
  }
  $best = $null
  foreach ($element in (Walk $pick[0] 2000)) {
    try {
      $c = $element.Current
      if ($c.ControlType.Id -ne $CT::ListItem.Id) { continue }
      $name = (([string]$c.Name).Trim() -replace '\s+', ' ')
      if ($name.ToLower() -eq $item) { $best = @($element, $name); break }
      if ($name.ToLower().Contains($item) -and ($best -eq $null -or $name.Length -lt $best[1].Length)) { $best = @($element, $name) }
    } catch { }
  }
  if ($best -eq $null) { Say @{ chosen = $null; why = 'item'; list = $pick[1] }; exit 0 }
  $done = $false
  if ($best[0].TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { $pattern.Select(); $done = $true }
  elseif ($best[0].TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $pattern.Invoke(); $done = $true }
  if ($pick[0].TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) {
    try { $pattern.Collapse() } catch { }
  }
  if (-not $done) { Say @{ chosen = $null; why = 'select' }; exit 0 }
  Say @{ chosen = $best[1]; list = $pick[1] }
  exit 0
}
if ($mode -eq 'tick') {
  $boxes = New-Object System.Collections.ArrayList
  foreach ($element in (Walk $root 4000)) {
    try {
      $c = $element.Current
      if ($c.IsOffscreen -or -not $c.IsEnabled) { continue }
      if ($c.ControlType.Id -eq $CT::CheckBox.Id -or $c.ControlType.Id -eq $CT::RadioButton.Id) {
        [void]$boxes.Add(@($element, (([string]$c.Name).Trim() -replace '\s+', ' ')))
      }
    } catch { }
  }
  $pick = Named $boxes 1
  if ($pick -eq $null) { Say @{ ticked = $null }; exit 0 }
  $on = ($env:KAIRU_UIA_ITEM -eq 'on')
  $pattern = $null
  if ($pick[0].TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) {
    $now = ($pattern.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On)
    if ($now -ne $on) { $pattern.Toggle() }
    Say @{ ticked = $pick[1]; on = $on; was = $now }
    exit 0
  }
  if ($on -and $pick[0].TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) {
    $pattern.Select(); Say @{ ticked = $pick[1]; on = $true }; exit 0
  }
  Say @{ ticked = $null }
  exit 0
}
if ($mode -eq 'at') {
  # what is at a point of the screen, only if that point shows this window: its name, kind and whether it's a password box
  try {
    $xy = ([string]$env:KAIRU_UIA_NAME).Split(',')
    $point = New-Object System.Windows.Point([double]$xy[0], [double]$xy[1])
    $element = $AE::FromPoint($point)
    $c = $element.Current
    if ($c.ProcessId -ne $root.Current.ProcessId) { Say @{ inside = $false }; exit 0 }
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $up = $element; $name = (([string]$c.Name).Trim() -replace '\s+', ' '); $kind = $kinds[$c.ControlType.Id]
    for ($i = 0; $i -lt 4 -and -not $name -and $up -ne $null; $i++) {
      $up = $walker.GetParent($up)
      if ($up -ne $null) { $name = (([string]$up.Current.Name).Trim() -replace '\s+', ' '); if (-not $kind) { $kind = $kinds[$up.Current.ControlType.Id] } }
    }
    if ($name.Length -gt 80) { $name = $name.Substring(0, 80) }
    Say @{ inside = $true; name = $name; kind = [string]$kind; password = [bool]$c.IsPassword }
  } catch { Say @{ inside = $false } }
  exit 0
}
if ($mode -eq 'address') {
  # the browser's own address bar (never the page): what it shows, as data
  foreach ($element in (Walk $root 800)) {
    try {
      $c = $element.Current
      if ($c.ControlType.Id -ne $CT::Edit.Id) { continue }
      $words = ([string]$c.Name + ' ' + [string]$c.AutomationId).ToLower()
      if ($words -notmatch 'address|url|location|omnibox') { continue }
      $pattern = $null
      if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        $value = [string]$pattern.Current.Value
        if ($value.Length -gt 300) { $value = $value.Substring(0, 300) }
        Say @{ address = $value }; exit 0
      }
    } catch { }
  }
  Say @{ address = $null }
  exit 0
}
if ($mode -eq 'saved') {
  # the browser's own list of saved logins (its own small window): pick only the entry whose name has your username
  $condition = New-Object System.Windows.Automation.PropertyCondition($AE::ProcessIdProperty, $root.Current.ProcessId)
  $tops = $AE::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
  foreach ($top in $tops) {
    foreach ($element in (Walk $top 600)) {
      try {
        $c = $element.Current
        $name = ([string]$c.Name).ToLower()
        if (-not $name.Contains($want)) { continue }
        $id = $c.ControlType.Id
        if ($id -ne $CT::ListItem.Id -and $id -ne $CT::MenuItem.Id -and $id -ne $CT::Button.Id -and $id -ne $CT::DataItem.Id) { continue }
        $pattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $pattern.Invoke(); Say @{ picked = $true }; exit 0 }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { $pattern.Select(); Say @{ picked = $true }; exit 0 }
      } catch { }
    }
  }
  Say @{ picked = $false }
  exit 0
}
Say @{}
"""


OCR_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
function Say($value) { [Console]::Out.Write((ConvertTo-Json -InputObject $value -Compress -Depth 6)) }
try {
  $width = [int]$env:KAIRU_OCR_WIDTH
  $height = [int]$env:KAIRU_OCR_HEIGHT
  $stream = [Console]::OpenStandardInput()
  $memory = New-Object System.IO.MemoryStream
  $stream.CopyTo($memory)
  $bytes = $memory.ToArray()
  $memory.Dispose()
  if ($width -le 0 -or $height -le 0 -or $bytes.Length -ne ($width * $height * 4)) { Say @{ why = 'size' }; exit 0 }
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
  $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
  $most = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
  if ($width -gt $most -or $height -gt $most) { Say @{ why = 'big' }; exit 0 }
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($engine -eq $null) { Say @{ why = 'no-ocr' }; exit 0 }
  $buffer = [System.Runtime.InteropServices.WindowsRuntime.WindowsRuntimeBufferExtensions]::AsBuffer($bytes)
  $bitmap = [Windows.Graphics.Imaging.SoftwareBitmap]::CreateCopyFromBuffer($buffer, [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, $width, $height)
  $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  $task = $asTask.MakeGenericMethod([Windows.Media.Ocr.OcrResult]).Invoke($null, @($engine.RecognizeAsync($bitmap)))
  if (-not $task.Wait(15000)) { Say @{ why = 'slow' }; exit 0 }
  $lines = New-Object System.Collections.ArrayList
  foreach ($line in $task.Result.Lines) {
    $words = New-Object System.Collections.ArrayList
    foreach ($word in $line.Words) {
      $box = $word.BoundingRect
      [void]$words.Add(@([string]$word.Text, [int]$box.X, [int]$box.Y, [int]$box.Width, [int]$box.Height))
    }
    [void]$lines.Add(@([string]$line.Text, $words))
    if ($lines.Count -ge 400) { break }
  }
  $bitmap.Dispose()
  Say @{ lines = $lines }
} catch { Say @{ why = 'failed' } }
"""
