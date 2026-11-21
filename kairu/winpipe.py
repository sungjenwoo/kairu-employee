"""Windows named pipes and process identity through ctypes, for Guardian's private channel (kairu/channel.py).

Guardian's end of the pipe is created as the first and only instance of its name
(FILE_FLAG_FIRST_PIPE_INSTANCE, at most one instance), with an access list that lets only your
Windows account open it and refuses network logons, and with PIPE_REJECT_REMOTE_CLIENTS, so a
connection from another PC is refused. Kairu's end opens it at identification level only, so the
program at the other end cannot act as you.

Every read and write uses overlapped I/O with a time limit, so a program that connects and then
says nothing cannot hold Guardian up.
"""

import ctypes
import functools
import time
from ctypes import wintypes

MEDIUM_INTEGRITY = 0x2000  # SECURITY_MANDATORY_MEDIUM_RID: an ordinary program; sandboxes run lower

_PIPE_ACCESS_DUPLEX = 0x00000003
_FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
_FILE_FLAG_OVERLAPPED = 0x40000000
_PIPE_TYPE_BYTE_READMODE_BYTE_WAIT = 0x00000000
_PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
_GENERIC_READ, _GENERIC_WRITE = 0x80000000, 0x40000000
_OPEN_EXISTING = 3
_SECURITY_SQOS_PRESENT, _SECURITY_IDENTIFICATION = 0x00100000, 0x00010000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_USER, _TOKEN_INTEGRITY_LEVEL = 1, 25
_PROCESS_COMMAND_LINE_INFORMATION = 60
_SE_KERNEL_OBJECT = 6
_OWNER_SECURITY_INFORMATION, _DACL_SECURITY_INFORMATION = 0x1, 0x4
_WAIT_OBJECT_0, _WAIT_TIMEOUT = 0x0, 0x102
_BUFFER = 64 * 1024

ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED = 5
ERROR_BROKEN_PIPE = 109
ERROR_PIPE_BUSY = 231
ERROR_NO_DATA = 232
ERROR_PIPE_NOT_CONNECTED = 233
ERROR_PIPE_CONNECTED = 535
ERROR_IO_PENDING = 997
_HANGUPS = (ERROR_BROKEN_PIPE, ERROR_NO_DATA, ERROR_PIPE_NOT_CONNECTED)
_INVALID_HANDLE = ctypes.c_void_p(-1).value


class _Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", wintypes.BOOL)]


class _UnicodeString(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]


@functools.cache
def _api():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    n = ctypes.WinDLL("ntdll")
    s = ctypes.WinDLL("shell32", use_last_error=True)
    H, D, B, P = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p
    for dll, name, args, result in [
        (k, "CreateNamedPipeW", (wintypes.LPCWSTR, D, D, D, D, D, D, P), H),
        (k, "ConnectNamedPipe", (H, P), B),
        (k, "DisconnectNamedPipe", (H,), B),
        (k, "CreateFileW", (wintypes.LPCWSTR, D, D, P, D, D, H), H),
        (k, "WaitNamedPipeW", (wintypes.LPCWSTR, D), B),
        (k, "ReadFile", (H, P, D, P, P), B),
        (k, "WriteFile", (H, P, D, P, P), B),
        (k, "GetOverlappedResult", (H, P, ctypes.POINTER(D), B), B),
        (k, "CancelIoEx", (H, P), B),
        (k, "CreateEventW", (P, B, B, wintypes.LPCWSTR), H),
        (k, "WaitForSingleObject", (H, D), D),
        (k, "GetNamedPipeServerProcessId", (H, ctypes.POINTER(wintypes.ULONG)), B),
        (k, "GetNamedPipeClientProcessId", (H, ctypes.POINTER(wintypes.ULONG)), B),
        (k, "OpenProcess", (D, B, D), H),
        (k, "GetCurrentProcess", (), H),
        (k, "QueryFullProcessImageNameW", (H, D, wintypes.LPWSTR, ctypes.POINTER(D)), B),
        (k, "CloseHandle", (H,), B),
        (k, "LocalFree", (P,), P),
        (k, "CreateMutexW", (P, B, wintypes.LPCWSTR), H),
        (a, "OpenProcessToken", (H, D, ctypes.POINTER(H)), B),
        (a, "GetTokenInformation", (H, ctypes.c_int, P, D, ctypes.POINTER(D)), B),
        (a, "ConvertSidToStringSidW", (P, ctypes.POINTER(P)), B),
        (a, "ConvertStringSidToSidW", (wintypes.LPCWSTR, ctypes.POINTER(P)), B),
        (a, "GetSidSubAuthorityCount", (P,), ctypes.POINTER(ctypes.c_ubyte)),
        (a, "GetSidSubAuthority", (P, D), ctypes.POINTER(D)),
        (a, "ConvertStringSecurityDescriptorToSecurityDescriptorW", (wintypes.LPCWSTR, D, ctypes.POINTER(P), P), B),
        (a, "ConvertSecurityDescriptorToStringSecurityDescriptorW", (P, D, D, ctypes.POINTER(P), P), B),
        (a, "GetSecurityInfo", (H, ctypes.c_int, D, P, P, P, P, ctypes.POINTER(P)), D),
        (n, "NtQueryInformationProcess", (H, ctypes.c_int, P, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)), ctypes.c_long),
        (s, "CommandLineToArgvW", (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)), ctypes.POINTER(wintypes.LPWSTR)),
    ]:
        function = getattr(dll, name)
        function.argtypes, function.restype = args, result
    return k, a, n, s


def _fail(what: str, error: int | None = None) -> OSError:
    error = ctypes.get_last_error() if error is None else error
    if error in _HANGUPS:
        return BrokenPipeError(f"{what}: the other end hung up")
    return OSError(f"{what} failed (Windows error {error})")


def _check(ok, what: str):
    if not ok:
        raise _fail(what)
    return ok


# --- who a process is ---------------------------------------------------------------------------

def _wide(pointer) -> str:
    text = ctypes.wstring_at(pointer)
    _api()[0].LocalFree(pointer)
    return text


def _token_info(token, info_class: int):
    _, advapi32, _, _ = _api()
    size = wintypes.DWORD()
    advapi32.GetTokenInformation(token, info_class, None, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    _check(advapi32.GetTokenInformation(token, info_class, buffer, size, ctypes.byref(size)), "GetTokenInformation")
    return buffer, ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]  # the buffer, and the SID at its start


def _user_and_integrity(process) -> tuple[str, int]:
    kernel32, advapi32, _, _ = _api()
    token = wintypes.HANDLE()
    _check(advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)), "OpenProcessToken")
    try:
        user, user_sid = _token_info(token, _TOKEN_USER)
        text = ctypes.c_void_p()
        _check(advapi32.ConvertSidToStringSidW(user_sid, ctypes.byref(text)), "ConvertSidToStringSid")
        sid = _wide(text.value)
        label, label_sid = _token_info(token, _TOKEN_INTEGRITY_LEVEL)
        count = advapi32.GetSidSubAuthorityCount(label_sid)[0]
        integrity = advapi32.GetSidSubAuthority(label_sid, count - 1)[0]
        return sid, integrity
    finally:
        kernel32.CloseHandle(token)


def canonical_sid(text: str) -> str:
    """A SID written as S-1-..., also when Windows wrote it as a short alias such as LA or NU."""
    kernel32, advapi32, _, _ = _api()
    sid, out = ctypes.c_void_p(), ctypes.c_void_p()
    _check(advapi32.ConvertStringSidToSidW(text, ctypes.byref(sid)), "ConvertStringSidToSid")
    try:
        _check(advapi32.ConvertSidToStringSidW(sid, ctypes.byref(out)), "ConvertSidToStringSid")
        return _wide(out.value)
    finally:
        kernel32.LocalFree(sid)


@functools.cache
def current_user_sid() -> str:
    return _user_and_integrity(_api()[0].GetCurrentProcess())[0]


def _image(process) -> str:
    buffer, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
    _check(_api()[0].QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)), "QueryFullProcessImageName")
    return buffer.value


def _command_line(process) -> list[str]:
    _, _, ntdll, shell32 = _api()
    size = wintypes.ULONG()
    ntdll.NtQueryInformationProcess(process, _PROCESS_COMMAND_LINE_INFORMATION, None, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(max(size.value, ctypes.sizeof(_UnicodeString)))
    status = ntdll.NtQueryInformationProcess(process, _PROCESS_COMMAND_LINE_INFORMATION, buffer, len(buffer), ctypes.byref(size))
    if status != 0:
        raise OSError(f"NtQueryInformationProcess failed (status {status & 0xFFFFFFFF:#x})")
    line = _UnicodeString.from_buffer(buffer)
    text = ctypes.wstring_at(line.Buffer, line.Length // 2) if line.Buffer else ""
    count = ctypes.c_int()
    argv = shell32.CommandLineToArgvW(text, ctypes.byref(count))
    if not argv:
        raise _fail("CommandLineToArgvW")
    try:
        return [argv[i] for i in range(count.value)]
    finally:
        _api()[0].LocalFree(ctypes.cast(argv, ctypes.c_void_p))


def parent_pid(pid: int) -> int:
    """The process that started this one (its id may since have been reused, so compare start order if it matters)."""
    class BasicInformation(ctypes.Structure):
        _fields_ = [("ExitStatus", ctypes.c_long), ("PebBaseAddress", ctypes.c_void_p), ("AffinityMask", ctypes.c_size_t),
                    ("BasePriority", ctypes.c_long), ("UniqueProcessId", ctypes.c_size_t),
                    ("InheritedFromUniqueProcessId", ctypes.c_size_t)]

    kernel32, _, ntdll, _ = _api()
    process = _check(kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid), f"OpenProcess({pid})")
    try:
        info = BasicInformation()
        status = ntdll.NtQueryInformationProcess(process, 0, ctypes.byref(info), ctypes.sizeof(info), None)
        if status != 0:
            raise OSError(f"NtQueryInformationProcess failed (status {status & 0xFFFFFFFF:#x})")
        return info.InheritedFromUniqueProcessId
    finally:
        kernel32.CloseHandle(process)


def claim_mutex(name: str):
    """A handle to the named mutex if this call created it, or None if it already exists (someone else has it).

    The mutex goes away when the last handle to it closes, also when its holder is killed.
    """
    kernel32 = _api()[0]
    ctypes.set_last_error(0)
    handle = _check(kernel32.CreateMutexW(None, False, name), f"CreateMutex({name})")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return handle


def process_identity(pid: int) -> tuple[str, int, str, list[str]]:
    """(user SID, integrity level, program file, command line) of a running process, as Windows reports them."""
    kernel32 = _api()[0]
    process = _check(kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid), f"OpenProcess({pid})")
    try:
        sid, integrity = _user_and_integrity(process)
        return sid, integrity, _image(process), _command_line(process)
    finally:
        kernel32.CloseHandle(process)


# --- the pipe -----------------------------------------------------------------------------------

def create_server(name: str):
    """Guardian's end: the first and only instance of `name`, which only your account can open.

    Raises PermissionError if another program already holds the name.
    """
    kernel32, advapi32, _, _ = _api()
    sid = current_user_sid()
    sddl = f"O:{sid}D:P(D;;GA;;;NU)(A;;GA;;;{sid})"  # protected: you only; network logons refused
    descriptor = ctypes.c_void_p()
    _check(advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None),
           "ConvertStringSecurityDescriptorToSecurityDescriptor")
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        handle = kernel32.CreateNamedPipeW(
            name, _PIPE_ACCESS_DUPLEX | _FILE_FLAG_FIRST_PIPE_INSTANCE | _FILE_FLAG_OVERLAPPED,
            _PIPE_TYPE_BYTE_READMODE_BYTE_WAIT | _PIPE_REJECT_REMOTE_CLIENTS, 1, _BUFFER, _BUFFER, 0,
            ctypes.byref(attributes))
    finally:
        kernel32.LocalFree(descriptor)
    if handle in (None, _INVALID_HANDLE):
        error = ctypes.get_last_error()
        if error in (ERROR_ACCESS_DENIED, ERROR_PIPE_BUSY):
            raise PermissionError(f"another program already holds the pipe {name} (Windows error {error})")
        raise _fail("CreateNamedPipe", error)
    return handle


def wait_for_client(handle, stopping, poll: float = 0.5) -> bool:
    """Wait until a program connects. False if stopping() became true first, or it hung up at once."""
    kernel32 = _api()[0]
    event = _check(kernel32.CreateEventW(None, True, False, None), "CreateEvent")
    overlapped = _Overlapped(hEvent=event)
    try:
        if kernel32.ConnectNamedPipe(handle, ctypes.byref(overlapped)):
            return True
        error = ctypes.get_last_error()
        if error == ERROR_PIPE_CONNECTED:
            return True
        if error == ERROR_NO_DATA:  # it connected and left before we looked
            kernel32.DisconnectNamedPipe(handle)
            return False
        if error != ERROR_IO_PENDING:
            raise _fail("ConnectNamedPipe", error)
        try:
            while kernel32.WaitForSingleObject(event, int(poll * 1000)) == _WAIT_TIMEOUT:
                if stopping():
                    _cancel(handle, overlapped)
                    return False
        except BaseException:
            _cancel(handle, overlapped)
            raise
        done = wintypes.DWORD()
        if not kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done), False):
            error = ctypes.get_last_error()
            if error in _HANGUPS:
                kernel32.DisconnectNamedPipe(handle)
                return False
            raise _fail("ConnectNamedPipe", error)
        return True
    finally:
        kernel32.CloseHandle(event)


def open_client(name: str, timeout: float):
    """Kairu's end. FileNotFoundError: no such pipe; PermissionError: it does not let you in; TimeoutError: busy."""
    kernel32 = _api()[0]
    deadline = time.monotonic() + timeout
    while True:
        handle = kernel32.CreateFileW(name, _GENERIC_READ | _GENERIC_WRITE, 0, None, _OPEN_EXISTING,
                                      _FILE_FLAG_OVERLAPPED | _SECURITY_SQOS_PRESENT | _SECURITY_IDENTIFICATION, None)
        if handle not in (None, _INVALID_HANDLE):
            return handle
        error = ctypes.get_last_error()
        if error == ERROR_FILE_NOT_FOUND:
            raise FileNotFoundError(name)
        if error == ERROR_ACCESS_DENIED:
            raise PermissionError(name)
        if error != ERROR_PIPE_BUSY:
            raise _fail("CreateFile", error)
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("Guardian's channel stayed busy")
        if not kernel32.WaitNamedPipeW(name, max(1, int(left * 1000))):  # until it is free; then try again
            time.sleep(0.01)


def server_pid(handle) -> int:
    pid = wintypes.ULONG()
    _check(_api()[0].GetNamedPipeServerProcessId(handle, ctypes.byref(pid)), "GetNamedPipeServerProcessId")
    return pid.value


def client_pid(handle) -> int:
    pid = wintypes.ULONG()
    _check(_api()[0].GetNamedPipeClientProcessId(handle, ctypes.byref(pid)), "GetNamedPipeClientProcessId")
    return pid.value


def _cancel(handle, overlapped) -> None:
    """Cancel an operation and wait until Windows is done with its buffer."""
    kernel32 = _api()[0]
    kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
    kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(wintypes.DWORD()), True)


def _transfer(handle, start, timeout: float, what: str) -> int:
    kernel32 = _api()[0]
    event = _check(kernel32.CreateEventW(None, True, False, None), "CreateEvent")
    overlapped = _Overlapped(hEvent=event)
    try:
        if not start(ctypes.byref(overlapped)):
            error = ctypes.get_last_error()
            if error != ERROR_IO_PENDING:
                raise _fail(what, error)
            try:
                waited = kernel32.WaitForSingleObject(event, max(0, int(timeout * 1000)))
            except BaseException:
                _cancel(handle, overlapped)
                raise
            if waited != _WAIT_OBJECT_0:
                _cancel(handle, overlapped)
                raise TimeoutError(f"{what}: the other end did not answer in time")
        done = wintypes.DWORD()
        if not kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done), False):
            raise _fail(what)
        return done.value
    finally:
        kernel32.CloseHandle(event)


def read(handle, size: int, timeout: float) -> bytes:
    """Up to `size` bytes; b"" once the other end has hung up."""
    buffer = ctypes.create_string_buffer(size)
    try:
        count = _transfer(handle, lambda overlapped: _api()[0].ReadFile(handle, buffer, size, None, overlapped), timeout, "ReadFile")
    except BrokenPipeError:
        return b""
    return buffer.raw[:count]


def write(handle, data: bytes, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    view = memoryview(data)
    while view:
        buffer = ctypes.create_string_buffer(bytes(view), len(view))
        count = _transfer(handle, lambda overlapped: _api()[0].WriteFile(handle, buffer, len(view), None, overlapped),
                          deadline - time.monotonic(), "WriteFile")
        view = view[count:]


def disconnect(handle) -> None:
    _api()[0].DisconnectNamedPipe(handle)


def close(handle) -> None:
    _api()[0].CloseHandle(handle)


def security(handle) -> str:
    """The owner and access list of the pipe behind `handle`, in Windows' SDDL notation."""
    kernel32, advapi32, _, _ = _api()
    descriptor = ctypes.c_void_p()
    error = advapi32.GetSecurityInfo(handle, _SE_KERNEL_OBJECT, _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
                                     None, None, None, None, ctypes.byref(descriptor))
    if error:
        raise _fail("GetSecurityInfo", error)
    try:
        text = ctypes.c_void_p()
        _check(advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION, ctypes.byref(text), None),
            "ConvertSecurityDescriptorToStringSecurityDescriptor")
        return _wide(text.value)
    finally:
        kernel32.LocalFree(descriptor)
