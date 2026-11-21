"""Actions for the stop tests. They run in their own process, started by the runner."""

import signal
import sys

from kairu import demo


def stubborn(seconds: float, heartbeat: str, quiet: bool = True) -> None:
    """Like demo.count, but ignores the polite request to end, so the runner has to kill it."""
    if sys.platform != "win32":  # on Windows, ending a process is never polite: it cannot be ignored
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    demo.count(seconds, heartbeat, quiet)


def refuses():
    """An action that would not do what it was asked."""
    from kairu.worker import REFUSED
    return REFUSED


def fails():
    """An action that tried and could not."""
    from kairu.worker import FAILED
    return FAILED


def says_nothing():
    return None
