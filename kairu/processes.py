"""Action processes: each action and every program it starts, kept together so a stop ends them all.

On Windows each action runs inside its own Job Object, set to "kill on job close". The process is
created suspended, put in the job, and only then resumed, so it cannot start a child before the
job holds it. Every program it starts afterwards is in the same job. Ending the job ends them all
at once, and if Kairu itself dies, Windows closes the job and ends them too.

On Linux each action starts in a new session, so it and everything it starts share one process
group, and the whole group is signalled together: first asked to end (SIGTERM), then killed
(SIGKILL), which cannot be ignored.

When an action ends by itself, anything it left running is ended too.
"""

import os
import signal
import subprocess
import sys


class ActionProcess:
    """One action's main process plus its whole family of child programs."""

    def __init__(self, argv: list[str], cwd):
        if sys.platform == "win32":
            self._job = _windows_job()
            try:
                # CREATE_NEW_PROCESS_GROUP: Ctrl+C in your terminal reaches Kairu, which then ends the job
                self._popen = subprocess.Popen(argv, cwd=cwd, creationflags=_CREATE_SUSPENDED | subprocess.CREATE_NEW_PROCESS_GROUP)
            except BaseException:
                _kernel32().CloseHandle(self._job)
                raise
            try:
                _assign_and_resume(self._job, self._popen.pid)
            except BaseException:
                self._popen.kill()  # never let an action run outside its job
                self._popen.wait()
                _kernel32().CloseHandle(self._job)
                raise
        else:
            self._popen = subprocess.Popen(argv, cwd=cwd, start_new_session=True)  # its own process group
        self.pid = self._popen.pid
        self._closed = False

    @property
    def returncode(self) -> int | None:
        return self._popen.returncode

    def poll(self) -> int | None:
        return self._popen.poll()

    def wait(self, timeout: float | None = None) -> int:
        return self._popen.wait(timeout)

    def ask_to_end(self) -> None:
        """Ask the whole family to end. Windows has no polite way for a program it cannot see, so there it ends at once."""
        if sys.platform == "win32":
            self.kill()
        else:
            self._signal_group(signal.SIGTERM)

    def kill(self) -> None:
        """End the whole family now; this cannot be ignored."""
        if sys.platform == "win32":
            if not self._closed:
                _kernel32().TerminateJobObject(self._job, 1)
        else:
            self._signal_group(signal.SIGKILL)

    def close(self) -> None:
        """Once the main process has ended: end anything it left running, and let go of the job."""
        if self._closed:
            return
        self.kill()
        if sys.platform == "win32":
            _kernel32().CloseHandle(self._job)
        self._closed = True

    def _signal_group(self, sig) -> None:
        try:
            os.killpg(self.pid, sig)
        except ProcessLookupError:  # the whole group has already gone
            pass


# --- Windows: a Job Object through ctypes -----------------------------------------------------

_CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
_PROCESS_SET_QUOTA, _PROCESS_TERMINATE = 0x0100, 0x0001
_THREAD_SUSPEND_RESUME = 0x0002
_TH32CS_SNAPTHREAD = 0x00000004


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k.TerminateJobObject.restype = wintypes.BOOL
    k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.OpenThread.restype = wintypes.HANDLE
    k.ResumeThread.argtypes = (wintypes.HANDLE,)
    k.ResumeThread.restype = wintypes.DWORD
    k.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.Thread32First.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    k.Thread32First.restype = wintypes.BOOL
    k.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    k.Thread32Next.restype = wintypes.BOOL
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    k.CloseHandle.restype = wintypes.BOOL
    return k


def _check(ok, what: str):
    import ctypes

    if not ok:
        raise OSError(f"{what} failed (Windows error {ctypes.get_last_error()})")
    return ok


def _windows_job():
    """A new, empty Job Object that ends every process in it when its last handle is closed."""
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER), ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                             "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = _kernel32()
    job = _check(k.CreateJobObjectW(None, None), "CreateJobObject")
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        k.CloseHandle(job)
        raise OSError(f"SetInformationJobObject failed (Windows error {error})")
    return job


def _assign_and_resume(job, pid: int) -> None:
    """Put the suspended process in the job, then start its (only) thread."""
    import ctypes
    from ctypes import wintypes

    class ThreadEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD)]

    k = _kernel32()
    process = _check(k.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid), "OpenProcess")
    try:
        _check(k.AssignProcessToJobObject(job, process), "AssignProcessToJobObject")
    finally:
        k.CloseHandle(process)

    snapshot = k.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
    if snapshot in (None, wintypes.HANDLE(-1).value):
        raise OSError(f"CreateToolhelp32Snapshot failed (Windows error {ctypes.get_last_error()})")
    resumed = 0
    try:
        entry = ThreadEntry(dwSize=ctypes.sizeof(ThreadEntry))
        more = k.Thread32First(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                thread = _check(k.OpenThread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID), "OpenThread")
                try:
                    if k.ResumeThread(thread) == 0xFFFFFFFF:
                        raise OSError(f"ResumeThread failed (Windows error {ctypes.get_last_error()})")
                    resumed += 1
                finally:
                    k.CloseHandle(thread)
            more = k.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    if not resumed:
        raise OSError("the action's process had no thread to resume")
