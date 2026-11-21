"""Tells the bar when the PC locks, signs out or goes to sleep, so the mic goes off (VOICE.md).

Windows: a hidden window of its own, on its own thread, that Windows tells about the session (WTSRegisterSessionNotification:
lock, sign-out, disconnect) and about sleep (RegisterSuspendResumeNotification: suspend, including Modern Standby).
Everywhere, as a second way: a clock that notices when the PC was asleep (a jump of more than SLEPT_SECONDS between ticks).
It only listens; it changes nothing.
"""

import sys
import threading
import time

TICK_SECONDS = 1.0
SLEPT_SECONDS = 6.0  # a tick this late means the PC was asleep (or the bar was frozen): the mic goes off either way
WM_WTSSESSION_CHANGE, WM_POWERBROADCAST, WM_QUERYENDSESSION, WM_CLOSE, WM_QUIT = 0x02B1, 0x0218, 0x0011, 0x0010, 0x0012
LOCK_EVENTS = {0x2: "the PC was disconnected", 0x4: "the PC was disconnected", 0x6: "you signed out", 0x7: "the PC locked"}
PBT_APMSUSPEND = 0x4
BACK_EVENTS = {0x5: "you signed in", 0x8: "you unlocked the PC"}  # WTS_SESSION_LOGON, WTS_SESSION_UNLOCK


class SessionWatch:
    def __init__(self, on_change, on_back=None):
        self.on_change = on_change  # called with why, from a thread of its own
        self.on_back = on_back  # called with why when you unlock or sign in again (voice.listen_at_start), or None
        self._closed = threading.Event()
        self._thread_id = 0
        self._threads = [threading.Thread(target=self._clock, name="kairu-bar-clock", daemon=True)]
        if sys.platform == "win32":
            self._threads.append(threading.Thread(target=self._window, name="kairu-bar-session", daemon=True))
        for thread in self._threads:
            thread.start()

    def _clock(self) -> None:
        last = time.time()
        while not self._closed.wait(TICK_SECONDS):
            now = time.time()
            if now - last > SLEPT_SECONDS:
                self._tell("the PC was asleep")
            last = now

    def _tell(self, why: str, back: bool = False) -> None:
        told = self.on_back if back else self.on_change
        if told is None:
            return
        try:
            told(why)
        except Exception as error:  # the watch goes on; the next change must still be told
            print(f"kairu bar: the session watch could not tell the bar ({type(error).__name__})", file=sys.stderr, flush=True)

    def _window(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        wtsapi32 = ctypes.WinDLL("wtsapi32")
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.restype = LRESULT
        user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.RegisterSuspendResumeNotification.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        user32.RegisterSuspendResumeNotification.restype = wintypes.HANDLE
        user32.UnregisterSuspendResumeNotification.argtypes = (wintypes.HANDLE,)
        user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
        user32.DestroyWindow.argtypes = (wintypes.HWND,)
        wtsapi32.WTSRegisterSessionNotification.argtypes = (wintypes.HWND, wintypes.DWORD)
        wtsapi32.WTSUnRegisterSessionNotification.argtypes = (wintypes.HWND,)

        def procedure(hwnd, message, wparam, lparam):
            if message == WM_WTSSESSION_CHANGE and wparam in LOCK_EVENTS:
                self._tell(LOCK_EVENTS[wparam])
            elif message == WM_WTSSESSION_CHANGE and wparam in BACK_EVENTS:
                self._tell(BACK_EVENTS[wparam], back=True)
            elif message == WM_POWERBROADCAST and wparam == PBT_APMSUSPEND:
                self._tell("the PC is going to sleep")
            elif message == WM_QUERYENDSESSION:
                self._tell("you are signing out")
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE  # a whole 64-bit handle, not an int cut short
        user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASS),)
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.TranslateMessage.argtypes = user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
        self._procedure = WNDPROC(procedure)  # kept, so it is not collected while Windows can call it
        instance = kernel32.GetModuleHandleW(None)
        name = f"KairuBarSessionWatch{id(self)}"
        self._class = WNDCLASS(0, self._procedure, 0, 0, instance, None, None, None, None, name)  # kept as long as the window
        user32.RegisterClassW(ctypes.byref(self._class))
        hwnd = user32.CreateWindowExW(0, name, "Kairu bar session watch", 0, 0, 0, 0, 0, None, None, instance, None)
        if not hwnd:
            return
        self._thread_id = kernel32.GetCurrentThreadId()
        wtsapi32.WTSRegisterSessionNotification(hwnd, 0)  # NOTIFY_FOR_THIS_SESSION
        power = user32.RegisterSuspendResumeNotification(hwnd, 0)  # DEVICE_NOTIFY_WINDOW_HANDLE
        message = wintypes.MSG()
        try:
            while not self._closed.is_set() and user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            wtsapi32.WTSUnRegisterSessionNotification(hwnd)
            if power:
                user32.UnregisterSuspendResumeNotification(power)
            user32.DestroyWindow(hwnd)

    def close(self) -> None:
        self._closed.set()
        if self._thread_id:
            import ctypes
            ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        for thread in self._threads:
            thread.join(2)
