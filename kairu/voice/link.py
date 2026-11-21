"""The voice link: the Kairu bar's private line to its listener (voice.listen), on this PC only. No network at all.

Windows: a named pipe that only your account can open, created by the bar as its first and only instance (kairu/winpipe.py).
Linux: voice.sock in the data folder, a socket file only you can open.

The bar (or the workspace) holds the line while its mic is on (W2, ADR-036: one mic for both); Guardian starts the
listener, which connects to it. The first message is the
listener's hello with the session token the bar gave Guardian for it (a private detail, so the audit log keeps its hash).
The bar answers only a listener with the token of the mic you just switched on; any other is refused before it opens the
microphone. So a voice.listen that anything else asked for (your phone, a mission, a test) hears nothing.

Then the listener sends what it heard about every 0.1 s, and the bar answers each message with what the listener must do:
pause while Kairu speaks, start a session (Ctrl+Alt+V), or end. Words travel here in memory only; nothing is written down.
"""

import hashlib
import json
import os
import socket
import stat
import sys
from pathlib import Path

from kairu import channel

SOCKET_NAME = "voice.sock"
MOST = 16 * 1024  # bytes in one message
SECONDS = 5.0  # a side that says nothing for this long is gone


class LinkError(Exception):
    pass


class LinkTaken(LinkError):
    """Another program (the bar or the workspace, W2) holds the line: its mic is on."""


def address(data_dir) -> str:
    data_dir = Path(data_dir).resolve()
    if sys.platform == "win32":
        from kairu import winpipe
        key = f"{winpipe.current_user_sid()}|{os.path.normcase(str(data_dir))}"
        return rf"\\.\pipe\kairu-voice-{hashlib.sha256(key.encode()).hexdigest()[:24]}"
    return str(data_dir / SOCKET_NAME)


class Line:
    """One connection, either end: JSON messages, each sent as its length and its bytes."""

    def __init__(self, link):
        self.link = link

    def send(self, message: dict, timeout: float = SECONDS) -> None:
        try:
            channel.send(self.link, message, timeout)
        except OSError as error:  # includes running out of time
            raise LinkError(f"the voice link closed ({type(error).__name__})") from None

    def receive(self, timeout: float = SECONDS) -> dict:
        """The next message. LinkError if the other end hung up, sent something broken, or said nothing in time."""
        try:
            message = json.loads(channel.receive(self.link, MOST, timeout))
        except (EOFError, channel.Truncated, channel.TooLarge, ValueError, OSError) as error:
            raise LinkError(f"the voice link closed ({type(error).__name__})") from None
        if not isinstance(message, dict):
            raise LinkError("the voice link sent something that is not a message")
        return message

    def last(self, message: dict) -> None:
        """Send a last answer and let the other end read it before hanging up (on Windows, hanging up first discards it)."""
        try:
            self.send(message)
            channel._drain_until_hangup(self.link, seconds=1.0)
        except (OSError, LinkError):
            pass

    def close(self) -> None:
        try:
            self.link.close()
        except OSError:
            pass


class Server:
    """The bar's end. Making one claims the line; LinkError if another program holds it."""

    def __init__(self, data_dir):
        self.address = address(data_dir)
        self._stopping = False
        if sys.platform == "win32":
            from kairu import winpipe
            try:
                self._pipe = winpipe.create_server(self.address)
            except PermissionError as error:
                raise LinkTaken(f"another program holds the voice link ({error})") from None
        else:
            self._sock = _claim(Path(self.address))

    def accept(self, poll: float = 0.5) -> Line | None:
        """The next program that connects, if it runs as you; None if nobody came in time, or it is not you."""
        if self._stopping:
            return None
        if sys.platform == "win32":
            from kairu import winpipe
            if not winpipe.wait_for_client(self._pipe, lambda: self._stopping, poll):
                return None
            link = channel._PipeLink(self._pipe, guardian_end=True)
        else:
            self._sock.settimeout(poll)
            try:
                connection, _ = self._sock.accept()
            except (TimeoutError, OSError):
                return None
            link = channel._SocketLink(connection)
        try:
            peer = channel.identify(link)
        except OSError:
            peer = None
        if peer is None or not peer.same_user or not peer.integrity_ok:
            link.close()
            return None
        return Line(link)

    def stop(self) -> None:
        self._stopping = True

    def close(self) -> None:
        self._stopping = True
        if sys.platform == "win32":
            from kairu import winpipe
            winpipe.close(self._pipe)
            return
        self._sock.close()
        Path(self.address).unlink(missing_ok=True)


def connect(data_dir, timeout: float = SECONDS) -> Line:
    """The listener's end. LinkError if no bar holds the line, or the program holding it is not running as you."""
    where = address(data_dir)
    if sys.platform == "win32":
        from kairu import winpipe
        try:
            link = channel._PipeLink(winpipe.open_client(where, timeout), guardian_end=False)
        except (OSError, TimeoutError) as error:
            raise LinkError(f"the Kairu bar is not running ({type(error).__name__})") from None
    else:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(where)
        except OSError as error:
            sock.close()
            raise LinkError(f"the Kairu bar is not running ({type(error).__name__})") from None
        link = channel._SocketLink(sock)
    try:
        peer = channel.identify(link)
    except OSError:
        peer = None
    if peer is None or not peer.same_user:
        link.close()
        raise LinkError("the program holding the voice link does not run as you")
    return Line(link)


def _claim(path: Path):
    if len(os.fsencode(path)) >= 108:
        raise LinkError(f"{path} is too long a path for a socket file; set a shorter guardian.data_dir in config.yaml")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise LinkError(f"{path} is in the way, and is not a socket of yours")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1)
        try:
            probe.connect(str(path))
        except (ConnectionRefusedError, FileNotFoundError):
            path.unlink(missing_ok=True)  # left behind by a bar that did not end cleanly
        else:
            raise LinkTaken("another program holds the voice link")
        finally:
            probe.close()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    mask = os.umask(0o177)
    try:
        sock.bind(str(path))
    except OSError as error:
        sock.close()
        raise LinkError(f"the voice link could not be made ({error})") from None
    finally:
        os.umask(mask)
    os.chmod(path, 0o600)
    sock.listen(2)
    return sock
