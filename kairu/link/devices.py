"""device.remove: unpair a device. From then on every message from it is refused as "not from a paired device".

Its public keys, its Gate topic and its remembered nonces are deleted from data/link.db; link.receive
stops reading its topic within a second. Exit code 1 if there is no such device.
"""

import sys

from kairu.link.store import LinkStore


def remove(data_dir: str, device: str) -> None:
    if not LinkStore(data_dir).remove_device(device):
        print(f"kairu: {device[:40]} is not a paired device", file=sys.stderr)
        raise SystemExit(1)
