"""A harmless practice action for trying the emergency stop: it counts seconds and does nothing else.

It never checks for a stop on purpose, so it shows that the runner ends an action from outside.
`heartbeat`, if given, is a file it rewrites every 0.05 s; the tests watch it to see when it stops.
"""

import time
from pathlib import Path


def count(seconds: float = 60, heartbeat: str | None = None, quiet: bool = False) -> None:
    start = last_print = time.monotonic()
    while (elapsed := time.monotonic() - start) < seconds:
        if heartbeat:
            Path(heartbeat).write_text(repr(time.time()))
        if not quiet and time.monotonic() - last_print >= 1:
            last_print = time.monotonic()
            print(f"  demo.count: {int(elapsed)} s", flush=True)
        time.sleep(0.05)
