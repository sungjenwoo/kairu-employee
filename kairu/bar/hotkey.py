"""Ctrl+Alt+Space, which shows and hides the bar, held by the bar with RegisterHotKey, as kairu/hotkey.py holds Ctrl+Alt+K.

Ctrl+Alt+K stays Guardian's emergency stop, untouched: this is another key, in another program, and K can never be chosen
for it. While another program holds the key, it tries again every few seconds and says so. If another program always holds
it, tasks.bar_key in config.yaml chooses another letter. Windows only.

The same class holds Ctrl+Alt+V, which starts listening (VOICE.md), with its own number (LISTEN_ID); voice.key chooses
another letter for it.
"""

import sys
import threading

RETRY_SECONDS = 5
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_SPACE = 0x20
DEFAULT_KEY = "Space"
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
HOTKEY_ID = 0x4B42
LISTEN_ID = 0x4B43  # Ctrl+Alt+V, start listening


def _virtual_key(key: str) -> int:
    return VK_SPACE if key == DEFAULT_KEY else ord(key.upper())  # Windows' code for a letter is its capital


class ShowHideKey:
    def __init__(self, on_press, key: str = DEFAULT_KEY, ident: int = HOTKEY_ID):
        self.on_press, self.key, self.ident = on_press, key, ident
        self.name = f"Ctrl+Alt+{key.capitalize() if key == DEFAULT_KEY else key.upper()}"
        self.state = "not started"  # "held", or why not
        self._closed = threading.Event()
        self._thread = None
        self._thread_id = 0

    def start(self) -> None:
        if sys.platform != "win32":
            self.state = f"{self.name} is built for Windows only"
            return
        self._thread = threading.Thread(target=self._hold, name="kairu-bar-hotkey", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._thread and self._thread_id:
            self._user32().PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(1)

    @staticmethod
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

    def _hold(self) -> None:  # Windows delivers the hotkey to the thread that registered it
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        self._thread_id = ctypes.WinDLL("kernel32").GetCurrentThreadId()
        while not user32.RegisterHotKey(None, self.ident, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, _virtual_key(self.key)):
            self.state = f"{self.name} is taken by another program"
            if self._closed.wait(RETRY_SECONDS):
                return
        self.state = "held"
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == self.ident:
                    self.on_press()
        finally:
            user32.UnregisterHotKey(None, self.ident)
