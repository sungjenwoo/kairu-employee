"""Runs one action in its own process: python -m kairu.worker module:function '{"arg": value}'

The runner (kairu/runner.py) starts this. Each action gets its own process so that an emergency
stop can end it at once, whether or not the action's code ever checks for a stop.

An action that would not do what it was asked (a file outside your work folder, say) returns REFUSED, and its exit code is
REFUSED_EXIT, which Guardian records as "refused", not as a normal finish. One that tried and could not returns FAILED.
"""

import importlib
import json
import sys

REFUSED, FAILED = object(), object()
REFUSED_EXIT, FAILED_EXIT = 3, 1


def main(argv: list[str]) -> int:
    target, kwargs = argv[0], json.loads(argv[1]) if len(argv) > 1 else {}
    module, _, function = target.partition(":")
    result = getattr(importlib.import_module(module), function)(**kwargs)
    marks = importlib.import_module("kairu.worker")  # this file runs as __main__: the marks an action returns are that module's
    return REFUSED_EXIT if result is marks.REFUSED else FAILED_EXIT if result is marks.FAILED else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
