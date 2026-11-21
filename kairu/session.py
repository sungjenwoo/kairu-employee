"""Guardian's one hidden window: it hears that you sign out or Windows shuts down or restarts, and owns the tray icon.

Windows tells programs about the end of a session only through their windows
(WM_QUERYENDSESSION, then WM_ENDSESSION); a program without a window is simply ended. So Guardian
keeps one window, never shown and not a message-only window (those do not get these messages),
titled "Kairu Guardian <process id>", in a thread of its own. Guardian also asks to be told among
the first programs (SetProcessShutdownParameters, the highest level an ordinary program may use).

  WM_QUERYENDSESSION  answered "yes" at once. If Windows itself says the session is ending
                      (GetSystemMetrics(SM_SHUTTINGDOWN)), the clean exit is recorded right
                      away (on_ending), in case Windows ends Guardian before the next message.
  WM_ENDSESSION       the session really ends: on_end("sign-out") or on_end("shutdown or
                      restart") records the clean exit first, then ends everything, before the
                      window answers. If another program cancelled the sign-out, on_cancel()
                      takes back a clean exit recorded too early.

Nothing else is a clean exit: a "close" request is ignored, and End task or a crash never reaches
the window. The tray icon and its menu are in kairu/tray.py. Windows only.
"""

import ctypes
import functools
import sys
import threading
from typing import Callable

WM_CLOSE, WM_QUERYENDSESSION, WM_ENDSESSION, WM_QUIT = 0x0010, 0x0011, 0x0016, 0x0012
WM_COMMAND, WM_TIMER, WM_MEASUREITEM, WM_DRAWITEM = 0x0111, 0x0113, 0x002C, 0x002B
ENDSESSION_LOGOFF = 0x80000000
SM_SHUTTINGDOWN = 0x2000
SHUTDOWN_LEVEL = 0x3FF  # the highest an ordinary program may ask for: told before the others
CLASS_NAME = "KairuGuardianSession"
TIMER_ID, TIMER_MS = 1, 1000  # the tray icon follows Guardian's state once a second


def title(pid: int) -> str:
    return f"Kairu Guardian {pid}"


def notify_early() -> bool:
    """Ask Windows to tell this program among the first when the session ends, and not to wait on it."""
    if sys.platform != "win32":
        return False
    return bool(ctypes.WinDLL("kernel32").SetProcessShutdownParameters(SHUTDOWN_LEVEL, 0x1))  # SHUTDOWN_NORETRY


def shutdown_level() -> int:
    level, flags = ctypes.c_uint32(), ctypes.c_uint32()
    ctypes.WinDLL("kernel32").GetProcessShutdownParameters(ctypes.byref(level), ctypes.byref(flags))
    return level.value


class GuardianWindow:
    def __init__(self, pid: int, on_end: Callable[[str], None], on_ending: Callable[[], None] = lambda: None,
                 on_cancel: Callable[[], None] = lambda: None, tray=None, log=print):
        self.pid, self.on_end, self.on_ending, self.on_cancel, self.tray, self.log = pid, on_end, on_ending, on_cancel, tray, log
        self.error = ""
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._taskbar_created = 0

    def start(self) -> bool:
        """Start listening. False (with the reason in .error) where it cannot."""
        if sys.platform != "win32":
            self.error = "Windows only"
            return False
        self._thread = threading.Thread(target=self._listen, name="kairu-window", daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            self.error = "the window did not start"
        return not self.error

    def close(self) -> None:
        if self._thread and self._thread.is_alive() and self._thread_id and threading.current_thread() is not self._thread:
            _user32().PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)

    def _window_procedure(self, window, message, wparam, lparam):
        try:
            if message == WM_QUERYENDSESSION:
                ending = bool(_user32().GetSystemMetrics(SM_SHUTTINGDOWN))
                self.log(f"Windows asks to end the session ({'sign-out' if lparam & ENDSESSION_LOGOFF else 'shutdown or restart'}); "
                         f"Windows says it is ending: {ending}")
                if ending:
                    self.on_ending()
                return 1  # Guardian never holds up a sign-out or shutdown
            if message == WM_ENDSESSION:
                if wparam:  # the session really ends
                    self.on_end("sign-out" if lparam & ENDSESSION_LOGOFF else "shutdown or restart")
                else:  # another program cancelled it
                    self.log("the end of the session was cancelled")
                    self.on_cancel()
                return 0
            if message == WM_CLOSE:
                return 0  # not a reason to end: only the end of the session is
            if self.tray is not None:
                if message == self._taskbar_created:  # Explorer restarted: show the icon again
                    self.tray.show(window)
                    return 0
                answer = self.tray.handle(window, message, wparam, lparam)
                if answer is not None:
                    return answer
        except Exception as error:  # Windows ends the program anyway at the end of a session; say what went wrong
            self.log(f"the window could not handle message {message:#x}: {error}")
            return 0
        return _user32().DefWindowProcW(window, message, wparam, lparam)

    def _listen(self) -> None:
        from ctypes import wintypes
        user32, kernel32 = _user32(), ctypes.WinDLL("kernel32", use_last_error=True)
        procedure_type, window_class_type = _types()
        self._thread_id = kernel32.GetCurrentThreadId()
        procedure = procedure_type(self._window_procedure)  # kept alive by this frame for the thread's life
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        instance = kernel32.GetModuleHandleW(None)
        window_class = window_class_type(cbSize=ctypes.sizeof(window_class_type), lpfnWndProc=procedure,
                                         hInstance=instance, lpszClassName=CLASS_NAME)
        user32.RegisterClassExW(ctypes.byref(window_class))  # fails harmlessly if this program registered it before
        # a top-level window that is never shown; not HWND_MESSAGE, which would miss the end of the session
        window = user32.CreateWindowExW(0, CLASS_NAME, title(self.pid), 0, 0, 0, 0, 0, None, None, instance, None)
        if not window:
            self.error = f"the window could not be made (Windows error {ctypes.get_last_error()})"
            self._ready.set()
            return
        if self.tray is not None:
            self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
            self.tray.show(window)
            user32.SetTimer(window, TIMER_ID, TIMER_MS, None)
        self._ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if self.tray is not None:
                self.tray.hide(window)
            user32.DestroyWindow(window)


_LRESULT = ctypes.c_ssize_t


@functools.cache
def _types():
    """The window procedure's type and WNDCLASSEXW (Windows only, so made on first use)."""
    from ctypes import wintypes
    procedure = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WindowClass(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", procedure),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    return procedure, WindowClass


@functools.cache
def _user32():
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.DefWindowProcW.restype = _LRESULT
    user32.RegisterClassExW.argtypes = (ctypes.c_void_p,)
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, ctypes.c_void_p)
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.DispatchMessageW.restype = _LRESULT
    user32.DestroyWindow.argtypes = (wintypes.HWND,)
    user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
    user32.RegisterWindowMessageW.argtypes = (wintypes.LPCWSTR,)
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.SetTimer.argtypes = (wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p)
    user32.SetTimer.restype = ctypes.c_size_t
    return user32
