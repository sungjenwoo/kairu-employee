"""Guardian's tray icon (Windows): its state, and one big "Stop everything", the same as Ctrl+Alt+K.

The icon is one of Windows' own (no files, almost no memory), and changes with the state:
  shield       normal, nothing running
  information  normal, actions running
  warning      Safe Mode
Pointing at it shows the state in words. Clicking it (left or right) opens a menu: the state, then
STOP EVERYTHING in a large red band. There is no Quit and no Resume here on purpose: resuming
needs "yes" and your PIN, with `kairu resume`.

It belongs to Guardian's hidden window (kairu/session.py), which passes it its messages; it
follows Guardian's state once a second, and shows itself again if Explorer restarts or was not
ready when Guardian started.

notify() shows a pop-up from the icon (Windows shows it as a notification) when a monitor reports
an alert. Its words come from Guardian's fixed list (kairu/protect/kinds.py), never from an email.
"""

import ctypes
import functools
from ctypes import wintypes
from typing import Callable

CALLBACK = 0x8001  # WM_APP + 1: what the icon sends to the window
NOTIFY = 0x8002  # WM_APP + 2: show the waiting pop-up, from the window's own thread
STOP_ID = 1
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO, NIIF_WARNING = 0x1, 0x2
IDI_INFORMATION, IDI_WARNING, IDI_SHIELD = 32516, 32515, 32518
WM_LBUTTONUP, WM_RBUTTONUP, WM_COMMAND, WM_TIMER = 0x0202, 0x0205, 0x0111, 0x0113
WM_MEASUREITEM, WM_DRAWITEM, WM_NULL = 0x002C, 0x002B, 0x0000
STOP_TEXT = "STOP EVERYTHING"


def describe(mode: str, safe_reason: str, running: int, key_held: bool) -> tuple[str, int]:
    """(the words shown for Guardian's state, the icon for it)."""
    if mode == "safe":
        text, icon = f"Safe Mode: {safe_reason or 'stopped'}. `kairu resume` to leave it", IDI_WARNING
    elif running:
        text, icon = f"normal, {running} action{'s' if running != 1 else ''} running", IDI_INFORMATION
    else:
        text, icon = "normal, nothing running", IDI_SHIELD
    key = "Ctrl+Alt+K ready" if key_held else "Ctrl+Alt+K not held"
    return f"Kairu Guardian: {text}. {key}", icon


class Tray:
    def __init__(self, state: Callable[[], tuple[str, int]], on_stop: Callable[[], None], log=print):
        self.state, self.on_stop, self.log = state, on_stop, log
        self.shown = False
        self._icon = None
        self._window = None
        self._pending: tuple[str, str, bool] | None = None  # the pop-up waiting for the window's thread
        self.last_popup: tuple[str, str] | None = None  # (title, text) of the last pop-up shown, for the tests

    @property
    def status(self) -> str:
        return "shown" if self.shown else "not shown yet (the taskbar was not ready); trying again every second"

    def notify(self, title: str, text: str, warning: bool = False) -> None:
        """Show a pop-up from the icon. Safe to call from any thread: the window's own thread shows it."""
        self._pending = (title[:63], text[:255], warning)
        if self._window:
            _user32().PostMessageW(self._window, NOTIFY, 0, 0)

    def show(self, window) -> None:
        self._window = window
        text, icon = self._safe_state()
        self.shown = bool(_shell32().Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data(window, text, icon))))
        self._icon = icon if self.shown else None

    def hide(self, window) -> None:
        if self.shown:
            _shell32().Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(window, "", IDI_SHIELD)))
            self.shown = False

    def refresh(self, window) -> None:
        if not self.shown:
            return self.show(window)
        text, icon = self._safe_state()
        if not _shell32().Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._data(window, text, icon))):
            self.shown = False  # the taskbar went away; shown again on the next tick

    def handle(self, window, message, wparam, lparam):
        """The answer to a window message that is the tray's, or None if it is not."""
        if message == WM_TIMER:
            self.refresh(window)
            return 0
        if message == NOTIFY:
            self._popup(window)
            return 0
        if message == CALLBACK and (lparam & 0xFFFF) in (WM_LBUTTONUP, WM_RBUTTONUP):
            if self._menu(window) == STOP_ID:
                self._stop()
            return 0
        if message == WM_COMMAND and (wparam & 0xFFFF) == STOP_ID:  # the same choice, sent as a command
            self._stop()
            return 0
        if message == WM_MEASUREITEM:
            item = ctypes.cast(lparam, ctypes.POINTER(_MeasureItem)).contents
            if item.itemID != STOP_ID:
                return None
            item.itemWidth, item.itemHeight = 300, 56
            return 1
        if message == WM_DRAWITEM:
            item = ctypes.cast(lparam, ctypes.POINTER(_DrawItem)).contents
            if item.itemID != STOP_ID:
                return None
            _draw_stop(item)
            return 1
        return None

    def _stop(self) -> None:
        self.log("tray: Stop everything")
        self.on_stop()

    def _popup(self, window) -> None:
        pending, self._pending = self._pending, None
        if pending is None or not self.shown:
            return
        title, text, warning = pending
        tip, icon = self._safe_state()
        data = self._data(window, tip, icon)
        data.uFlags |= NIF_INFO
        data.szInfoTitle, data.szInfo = title, text
        data.dwInfoFlags = NIIF_WARNING if warning else NIIF_INFO
        if _shell32().Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data)):
            self.last_popup = (title, text)
        else:
            self.log(f"tray: the pop-up could not be shown ({title})")

    def _safe_state(self) -> tuple[str, int]:
        try:
            return self.state()
        except Exception as error:  # say so, rather than show an old state
            return f"Kairu Guardian: state not readable ({error})"[:127], IDI_WARNING

    def _menu(self, window) -> int:
        user32 = _user32()
        menu = user32.CreatePopupMenu()
        try:
            user32.AppendMenuW(menu, 0x1, 0, self._safe_state()[0][:200])  # MF_GRAYED: the state, not a choice
            user32.AppendMenuW(menu, 0x800, 0, None)  # MF_SEPARATOR
            user32.AppendMenuW(menu, 0x100, STOP_ID, None)  # MF_OWNERDRAW: the big red Stop everything
            user32.SetMenuDefaultItem(menu, STOP_ID, 0)
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(window)  # so the menu closes when you click elsewhere
            chosen = user32.TrackPopupMenu(menu, 0x0100 | 0x0080 | 0x0002, point.x, point.y, 0, window, None)
            user32.PostMessageW(window, WM_NULL, 0, 0)
            return chosen  # TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON
        finally:
            user32.DestroyMenu(menu)

    def _data(self, window, text: str, icon: int):
        data = _NotifyIconData(cbSize=ctypes.sizeof(_NotifyIconData), hWnd=window, uID=1,
                               uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP, uCallbackMessage=CALLBACK,
                               hIcon=_user32().LoadIconW(None, ctypes.c_void_p(icon)))
        data.szTip = text[:127]
        return data


def _draw_stop(item) -> None:
    gdi32, user32 = _gdi32(), _user32()
    selected = item.itemState & 0x1  # ODS_SELECTED
    brush = gdi32.CreateSolidBrush(0x00101090 if selected else 0x002020C8)  # dark red when pointed at; BGR
    user32.FillRect(item.hDC, ctypes.byref(item.rcItem), brush)
    gdi32.DeleteObject(brush)
    gdi32.SetBkMode(item.hDC, 1)  # TRANSPARENT
    gdi32.SetTextColor(item.hDC, 0x00FFFFFF)
    font = gdi32.CreateFontW(-24, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")  # bold, ClearType
    old = gdi32.SelectObject(item.hDC, font)
    rect = item.rcItem
    user32.DrawTextW(item.hDC, STOP_TEXT, -1, ctypes.byref(rect), 0x1 | 0x4 | 0x20)  # centred, one line
    gdi32.SelectObject(item.hDC, old)
    gdi32.DeleteObject(font)


class _NotifyIconData(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


class _MeasureItem(ctypes.Structure):
    _fields_ = [("CtlType", wintypes.UINT), ("CtlID", wintypes.UINT), ("itemID", wintypes.UINT),
                ("itemWidth", wintypes.UINT), ("itemHeight", wintypes.UINT), ("itemData", ctypes.c_size_t)]


class _DrawItem(ctypes.Structure):
    _fields_ = [("CtlType", wintypes.UINT), ("CtlID", wintypes.UINT), ("itemID", wintypes.UINT),
                ("itemAction", wintypes.UINT), ("itemState", wintypes.UINT), ("hwndItem", wintypes.HWND),
                ("hDC", wintypes.HDC), ("rcItem", wintypes.RECT), ("itemData", ctypes.c_size_t)]


@functools.cache
def _shell32():
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.c_void_p)
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    return shell32


@functools.cache
def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    H = wintypes.HANDLE
    for name, args, result in [
        ("LoadIconW", (wintypes.HINSTANCE, ctypes.c_void_p), wintypes.HICON),
        ("CreatePopupMenu", (), wintypes.HMENU),
        ("AppendMenuW", (wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR), wintypes.BOOL),
        ("SetMenuDefaultItem", (wintypes.HMENU, wintypes.UINT, wintypes.UINT), wintypes.BOOL),
        ("GetCursorPos", (ctypes.POINTER(wintypes.POINT),), wintypes.BOOL),
        ("SetForegroundWindow", (wintypes.HWND,), wintypes.BOOL),
        ("TrackPopupMenu", (wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                            ctypes.c_void_p), ctypes.c_int),
        ("PostMessageW", (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM), wintypes.BOOL),
        ("DestroyMenu", (wintypes.HMENU,), wintypes.BOOL),
        ("FillRect", (wintypes.HDC, ctypes.POINTER(wintypes.RECT), H), ctypes.c_int),
        ("DrawTextW", (wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT),
         ctypes.c_int),
    ]:
        function = getattr(user32, name)
        function.argtypes, function.restype = args, result
    return user32


@functools.cache
def _gdi32():
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    H = wintypes.HANDLE
    for name, args, result in [
        ("CreateSolidBrush", (wintypes.DWORD,), H),
        ("DeleteObject", (H,), wintypes.BOOL),
        ("SetBkMode", (wintypes.HDC, ctypes.c_int), ctypes.c_int),
        ("SetTextColor", (wintypes.HDC, wintypes.DWORD), wintypes.DWORD),
        ("CreateFontW", (ctypes.c_int,) * 5 + (wintypes.DWORD,) * 8 + (wintypes.LPCWSTR,), H),
        ("SelectObject", (wintypes.HDC, H), H),
    ]:
        function = getattr(gdi32, name)
        function.argtypes, function.restype = args, result
    return gdi32
