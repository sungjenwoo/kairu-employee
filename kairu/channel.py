"""Guardian's private channel: how Kairu asks the Guardian program. Local only; no network at all.

Windows: a named pipe that only your Windows account can open; connections from other PCs and
network logons are refused (kairu/winpipe.py). Guardian creates it as the first and only instance
of its name, so no other program can open an instance beside it.
Linux: guardian.sock in the data folder, a socket file that only you can open (mode 600).

One request per connection:
  1. A program connects. Guardian checks it runs as you, and greets it.
  2. Kairu checks, with the operating system rather than with anything the other end says, that
     the other end is Guardian running as you (why_not_guardian). If it is not, Kairu hangs up and
     refuses the request: nothing is sent, not the request and not your PIN.
  3. Kairu sends one message; Guardian answers it; Kairu hangs up.

Each message is one JSON object, sent as its length (4 bytes) followed by its bytes. Guardian
refuses anything longer than MAX_REQUEST; what it accepts is in kairu/guardian_program.py.
"""

import errno
import hashlib
import json
import os
import socket
import stat
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROTOCOL = 1
GUARDIAN_MODULE = "kairu.guardian_program"  # Guardian runs as: python -m kairu.guardian_program
MAX_REQUEST = 16 * 1024  # bytes; a request is a few hundred
MAX_REPLY = 64 * 1024
SOCKET_NAME = "guardian.sock"
CONNECT_SECONDS = 5.0  # Kairu waits this long to get through while Guardian answers someone else
REQUEST_SECONDS = 5.0  # Guardian waits this long for a request to arrive, then hangs up
ANSWER_SECONDS = 60.0  # Kairu waits this long for an answer
_HEADER = struct.Struct(">I")


class ChannelError(Exception):
    """No usable answer from Guardian, so whatever was asked is refused."""


class NotRunning(ChannelError):
    pass


class NotGuardian(ChannelError):
    pass


class ChannelTaken(ChannelError):
    """Guardian cannot claim its channel, because another program already holds it."""


class TooLarge(Exception):
    pass


class Truncated(Exception):
    pass


def address(data_dir) -> str:
    """The channel's name: one per Windows account and data folder, or the socket file in the data folder."""
    data_dir = Path(data_dir).resolve()
    if sys.platform == "win32":
        from kairu import winpipe
        key = f"{winpipe.current_user_sid()}|{os.path.normcase(str(data_dir))}"
        return rf"\\.\pipe\kairu-guardian-{hashlib.sha256(key.encode()).hexdigest()[:24]}"
    return str(data_dir / SOCKET_NAME)


# --- one connection, either end ------------------------------------------------------------------

class _PipeLink:
    def __init__(self, handle, guardian_end: bool):
        self.handle, self.guardian_end = handle, guardian_end

    def peer_pid(self) -> int:
        from kairu import winpipe
        return winpipe.client_pid(self.handle) if self.guardian_end else winpipe.server_pid(self.handle)

    def read(self, size: int, timeout: float) -> bytes:
        from kairu import winpipe
        return winpipe.read(self.handle, size, timeout)

    def write(self, data: bytes, timeout: float) -> None:
        from kairu import winpipe
        winpipe.write(self.handle, data, timeout)

    def close(self) -> None:
        from kairu import winpipe
        (winpipe.disconnect if self.guardian_end else winpipe.close)(self.handle)


class _SocketLink:
    def __init__(self, sock: socket.socket):
        self.sock = sock

    def credentials(self) -> tuple[int, int]:
        """(pid, uid) of the process at the other end, from the kernel (SO_PEERCRED)."""
        pid, uid, _ = struct.unpack("3i", self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        return pid, uid

    def peer_pid(self) -> int:
        return self.credentials()[0]

    def read(self, size: int, timeout: float) -> bytes:
        self.sock.settimeout(max(timeout, 0.001))
        try:
            return self.sock.recv(size)
        except ConnectionResetError:
            return b""

    def write(self, data: bytes, timeout: float) -> None:
        self.sock.settimeout(max(timeout, 0.001))
        self.sock.sendall(data)

    def close(self) -> None:
        self.sock.close()


def send(link, message: dict, timeout: float) -> None:
    body = json.dumps(message, separators=(",", ":")).encode()
    link.write(_HEADER.pack(len(body)) + body, timeout)


def receive(link, limit: int, timeout: float) -> bytes:
    """One message. EOFError if the other end hung up first, Truncated if it hung up halfway, TooLarge if over `limit`."""
    deadline = time.monotonic() + timeout
    size = _HEADER.unpack(_read_exactly(link, _HEADER.size, deadline, first=True))[0]
    if size > limit:
        raise TooLarge(f"the message is {size} bytes; the limit is {limit}")
    return _read_exactly(link, size, deadline)


def _read_exactly(link, size: int, deadline: float, first: bool = False) -> bytes:
    data = b""
    while len(data) < size:
        chunk = link.read(size - len(data), deadline - time.monotonic())
        if not chunk:
            if first and not data:
                raise EOFError("the other end hung up")
            raise Truncated("the connection closed in the middle of a message")
        data += chunk
    return data


# --- who is at the other end ---------------------------------------------------------------------

@dataclass(frozen=True)
class Peer:
    """The process at the other end of a connection, as the operating system reports it."""
    pid: int
    same_user: bool  # runs under your account
    integrity_ok: bool  # Windows: medium integrity or above, so not sandboxed; always True on Linux
    program: str  # its program file
    argv: tuple[str, ...]  # how it was started


def identify(link) -> Peer:
    """Raises OSError if the process cannot be examined."""
    if sys.platform == "win32":
        from kairu import winpipe
        pid = link.peer_pid()
        sid, integrity, program, argv = winpipe.process_identity(pid)
        return Peer(pid, sid == winpipe.current_user_sid(), integrity >= winpipe.MEDIUM_INTEGRITY, program, tuple(argv))
    pid, uid = link.credentials()
    program = os.readlink(f"/proc/{pid}/exe")
    argv = tuple(os.fsdecode(part) for part in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1])
    return Peer(pid, uid == os.getuid(), True, program, argv)


def why_not_guardian(peer: Peer) -> str:
    """Why the process at the other end is not Guardian running as you, or "" if it is."""
    if not peer.same_user:
        return "it runs under another account"
    if not peer.integrity_ok:
        return "it runs at low integrity, as sandboxed programs do"
    if _file_key(peer.program) not in kairu_pythons():
        return f"its program file is not Kairu's Python: {peer.program}"
    if list(peer.argv[1:3]) != ["-m", GUARDIAN_MODULE]:
        started = " ".join(peer.argv[1:4])[:120] or "nothing"
        return f"it is not the Guardian program (it was started with: {started})"
    return ""


def kairu_pythons() -> set[str]:
    """The program files Guardian may run as: the Python running Kairu, and the one behind its venv."""
    files = set()
    for executable in {sys.executable, getattr(sys, "_base_executable", None) or sys.executable}:
        path = Path(executable)
        files.add(path)
        if sys.platform == "win32":
            files |= {path.with_name("python.exe"), path.with_name("pythonw.exe")}
    return {_file_key(path) for path in files}


def _file_key(path) -> str:
    return os.path.normcase(os.path.realpath(path))


def greeting(data_dir) -> dict:
    return {"guardian": "kairu", "protocol": PROTOCOL, "pid": os.getpid(), "data_dir": str(Path(data_dir).resolve())}


def greeting_problem(said, pid: int, data_dir) -> str:
    if not isinstance(said, dict) or said.get("guardian") != "kairu":
        return "it did not greet as Guardian"
    if said.get("protocol") != PROTOCOL:
        return f"it speaks protocol {said.get('protocol')!r}, not {PROTOCOL}"
    if said.get("pid") != pid:
        return f"it says it is process {said.get('pid')!r}"
    if not isinstance(said.get("data_dir"), str) or _file_key(said["data_dir"]) != _file_key(data_dir):
        return "it serves another data folder"
    return ""


# --- Kairu's end ----------------------------------------------------------------------------------

def connect(data_dir, timeout: float = CONNECT_SECONDS):
    """Open the channel and make sure Guardian, running as you, is at the other end.

    Raises NotRunning, NotGuardian or ChannelError; in every one of those cases nothing was sent.
    """
    data_dir = Path(data_dir).resolve()
    link = _open(address(data_dir), timeout)
    try:
        try:
            peer = identify(link)
        except OSError as error:
            raise NotGuardian(f"the program on Guardian's channel could not be checked ({error}). Nothing was sent "
                              "to it") from None
        problem = why_not_guardian(peer)
        if not problem:
            try:
                said = json.loads(receive(link, MAX_REPLY, timeout))  # reading its greeting sends nothing
            except (EOFError, Truncated, TooLarge, ValueError, OSError):
                said = None
            problem = greeting_problem(said, peer.pid, data_dir)
        if problem:
            raise NotGuardian(f"the program on Guardian's channel (process {peer.pid}) is not Guardian: {problem}. "
                              "Nothing was sent to it")
    except BaseException:
        link.close()
        raise
    return link


def _open(where: str, timeout: float):
    if sys.platform == "win32":
        from kairu import winpipe
        try:
            return _PipeLink(winpipe.open_client(where, timeout), guardian_end=False)
        except FileNotFoundError:
            raise NotRunning("Guardian is not running") from None
        except PermissionError:
            raise NotGuardian("Guardian's channel is held by a program that does not let your account in (another "
                              "account's, so not your Guardian). Nothing was sent to it") from None
        except OSError as error:
            raise ChannelError(f"Guardian's channel could not be opened ({error})") from None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(where)
    except (FileNotFoundError, ConnectionRefusedError):
        sock.close()
        raise NotRunning("Guardian is not running") from None
    except PermissionError:
        sock.close()
        raise NotGuardian("Guardian's socket file does not let your account in (it is another account's, so not "
                          "your Guardian). Nothing was sent to it") from None
    except OSError as error:
        sock.close()
        raise ChannelError(f"Guardian's channel could not be opened ({error})") from None
    return _SocketLink(sock)


def request(data_dir, message: dict, timeout: float = ANSWER_SECONDS) -> dict:
    """Ask Guardian one thing and return its answer. Raises ChannelError when there is no usable answer."""
    body = json.dumps(message, separators=(",", ":")).encode()
    return request_raw(data_dir, _HEADER.pack(len(body)) + body, timeout)


def request_raw(data_dir, raw: bytes, timeout: float = ANSWER_SECONDS) -> dict:
    """Send these exact bytes to the checked Guardian and return its answer (the tests send broken messages this way)."""
    link = connect(data_dir)
    try:
        link.write(raw, timeout)
        body = receive(link, MAX_REPLY, timeout)
    except (EOFError, Truncated, TooLarge, OSError) as error:
        raise ChannelError(f"Guardian did not answer ({error})") from None
    finally:
        link.close()
    try:
        answer = json.loads(body)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or not isinstance(answer.get("verdict"), str):
        raise ChannelError("Guardian's answer could not be read")
    return answer


# --- Guardian's end -------------------------------------------------------------------------------

class Server:
    """Guardian's end of the channel. Making one claims the channel as its first and only holder.

    Raises ChannelTaken if another program already holds it.
    """

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.address = address(self.data_dir)
        self._stopping = False
        if sys.platform == "win32":
            from kairu import winpipe
            try:
                self._pipe = winpipe.create_server(self.address)
            except PermissionError as error:
                raise ChannelTaken(f"another program already holds Guardian's channel ({error})") from None
        else:
            self._sock, self._inode = _claim_socket(Path(self.address))

    def stop(self) -> None:
        self._stopping = True

    def accept(self, poll: float = 0.5):
        """The next program that connects, if it runs as you; None if nobody came, or it is not you."""
        if sys.platform == "win32":
            from kairu import winpipe
            if not winpipe.wait_for_client(self._pipe, lambda: self._stopping, poll):
                return None
            link = _PipeLink(self._pipe, guardian_end=True)
        else:
            self._sock.settimeout(poll)
            try:
                connection, _ = self._sock.accept()
            except TimeoutError:
                return None
            link = _SocketLink(connection)
        try:
            peer = identify(link)
        except OSError:
            peer = None
        if peer is None or not peer.same_user:
            print(f"guardian: refused a connection from {'another account' if peer else 'a process that could not be checked'}",
                  file=sys.stderr, flush=True)
            link.close()
            return None
        return link

    def serve(self, answer, refuse) -> None:
        """Answer one request per connection until stop(). answer(body) and refuse(reason) return the reply."""
        while not self._stopping:
            link = self.accept()
            if link is None:
                continue
            try:
                self._answer_one(link, answer, refuse)
            except Exception as error:  # one bad connection never ends Guardian
                print(f"guardian: a connection failed: {error}", file=sys.stderr, flush=True)
            finally:
                link.close()

    def _answer_one(self, link, answer, refuse) -> None:
        send(link, greeting(self.data_dir), REQUEST_SECONDS)
        try:
            body = receive(link, MAX_REQUEST, REQUEST_SECONDS)
        except EOFError:  # it hung up without asking anything
            return
        except Truncated as error:
            refuse(str(error))  # recorded; there is no one left to tell
            return
        except TooLarge as error:
            reply = refuse(str(error))
        except TimeoutError:
            reply = refuse(f"the message did not arrive within {REQUEST_SECONDS:g} s")
        else:
            reply = answer(body)
        send(link, reply, REQUEST_SECONDS)
        _drain_until_hangup(link)

    def close(self) -> None:
        if sys.platform == "win32":
            from kairu import winpipe
            winpipe.close(self._pipe)
            return
        self._sock.close()
        try:
            if os.lstat(self.address).st_ino == self._inode:
                os.unlink(self.address)
        except FileNotFoundError:
            pass


def _drain_until_hangup(link, seconds: float = 2.0, most: int = 1 << 20) -> None:
    """Let Kairu read the answer before hanging up: on Windows, hanging up first would discard it."""
    deadline, drained = time.monotonic() + seconds, 0
    try:
        while drained < most and (chunk := link.read(64 * 1024, deadline - time.monotonic())):
            drained += len(chunk)
    except OSError:  # includes running out of time
        pass


def _claim_socket(path: Path):
    """Linux: bind guardian.sock, readable and writable by you only. Refuses if a program is already listening on it."""
    if len(os.fsencode(path)) >= 108:
        raise ChannelError(f"{path} is too long a path for a socket file; set a shorter guardian.data_dir in config.yaml")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise ChannelTaken(f"{path} is in the way, and is not a socket of yours")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1)
        try:
            probe.connect(str(path))
        except (ConnectionRefusedError, FileNotFoundError):
            path.unlink(missing_ok=True)  # left behind by a Guardian that did not end cleanly
        else:
            raise ChannelTaken("another program already holds Guardian's channel")
        finally:
            probe.close()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    mask = os.umask(0o177)  # the socket file is born private
    try:
        sock.bind(str(path))
    except OSError as error:
        sock.close()
        if error.errno == errno.EADDRINUSE:
            raise ChannelTaken("another program already holds Guardian's channel") from None
        raise ChannelError(f"{path} could not be made ({error})") from None
    finally:
        os.umask(mask)
    os.chmod(path, 0o600)
    sock.listen(16)
    return sock, os.stat(path).st_ino
