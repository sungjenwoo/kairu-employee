"""Ctrl+Alt+K, the emergency-stop hotkey, system-wide on Windows.

It uses the Windows RegisterHotKey function through ctypes, so no extra package is needed. The
hotkey works whichever window is in front, for as long as the Kairu process that holds it runs.
The Guardian program holds it for its whole life (Keeper, below), so it works whenever Guardian
runs, with no Kairu window open; `kairu hotkey` and `kairu demo` hold it only when Guardian does
not. Only one program can hold Ctrl+Alt+K at a time; if another one already does, start() says
so, and `kairu stop` still works.

There is no hotkey on other systems; use `kairu stop` there.
"""

import sys
import threading
from typing import Callable

RETRY_SECONDS = 5  # how often the Keeper tries again while another program holds the key

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_K = 0x4B
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
HOTKEY_ID = 0x4B41  # any number, unique within this program
NAME = "Ctrl+Alt+K"


class Hotkey:
    def __init__(self, on_press: Callable[[], None]):
        self.on_press = on_press
        self.error = ""
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def start(self) -> bool:
        """Start listening. False (with the reason in .error) if the hotkey is not available."""
        if sys.platform != "win32":
            self.error = f"the {NAME} hotkey is built for Windows only; use `kairu stop`"
            return False
        self._thread = threading.Thread(target=self._listen, name="kairu-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(2):
            self.error = f"the {NAME} hotkey did not start"
        return not self.error

    def close(self) -> None:
        if self._thread and self._thread.is_alive() and self._thread_id:
            _user32().PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(1)

    def _listen(self) -> None:  # runs in its own thread: Windows delivers the hotkey to the thread that registered it
        import ctypes
        from ctypes import wintypes

        user32 = _user32()
        self._thread_id = ctypes.WinDLL("kernel32").GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_K):
            self.error = (f"{NAME} is already taken by another program (Windows error {ctypes.get_last_error()}). "
                          "If that program is `kairu hotkey`, the key still stops everything; otherwise use `kairu stop`")
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    try:
                        self.on_press()
                    except Exception as error:  # keep listening; the next press must still work
                        print(f"kairu: {NAME} was pressed but the stop failed: {error}", file=sys.stderr)
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)


class Keeper:
    """Holds Ctrl+Alt+K for as long as it is open; while another program has it, tries again every few seconds."""

    def __init__(self, on_press: Callable[[], None]):
        self.on_press = on_press
        self.state = "not started"  # "held", or why not
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def held(self) -> bool:
        return self.state == "held"

    def start(self) -> bool:
        """Start holding the key. True if it is held now; otherwise it keeps trying, and .state says why."""
        if sys.platform != "win32":
            self.state = Hotkey(self.on_press).error or f"the {NAME} hotkey is built for Windows only; use `kairu stop`"
            return False
        first = threading.Event()
        self._thread = threading.Thread(target=self._keep, args=(first,), name="kairu-hotkey-keeper", daemon=True)
        self._thread.start()
        first.wait(5)
        return self.held

    def close(self) -> None:
        """Let go of the key."""
        self._closed.set()
        if self._thread:
            self._thread.join(3)

    def _keep(self, first: threading.Event) -> None:
        while not self._closed.is_set():
            key = Hotkey(self.on_press)
            if key.start():
                self.state = "held"
                first.set()
                self._closed.wait()
                key.close()
                return
            self.state = key.error
            first.set()
            self._closed.wait(RETRY_SECONDS)


def _user32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    user32.GetMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    return user32
