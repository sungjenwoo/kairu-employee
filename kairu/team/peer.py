"""Main Kairu's side of the Link to one Clone (TEAM.md).

Towards a Clone, Main Kairu is a paired device, exactly like your phone: the Clone's own Guardian paired it with a 6-digit
code typed at the Clone (`kairu device pair` there), so every order Main Kairu sends is only a request that the Clone's
Guardian decides, step by step, with "yes" and that laptop's PIN for anything High. Main Kairu holds no approval for a
Clone and can't send one.

The crypto and the relay calls are kairu/link/testclient.py's (standard library only), so the `kairu` command and the
Guardian program never load PyNaCl. Its keys are in data/team/<name>.json, sealed for your Windows account with DPAPI
(kairu/protect/sealed.py, its own purpose), like the Link's own keys; on Linux, readable by you only. A file from before
the seal is read once and written back sealed.
"""

import base64
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path

from kairu.link import testclient
from kairu.protect import sealed

SEAL_PURPOSE = b"Kairu team keys v1"  # mixed into the seal, so these keys can't be read as any other sealed file

ORDER = "task.order"
TAG = re.compile(r"\[K(\d{1,6})\.(\d{1,2})\.(\d{1,2})(?: (finished))?\] ?")


def key_file(data_dir, name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "clone"
    return Path(data_dir) / "team" / f"{slug}.json"


NOTE = "\nNOTE "  # Main Kairu's note, after the order (kairu/tasks/remote.py takes it off before the task core sees the order)
LONGEST_NOTE = 600


def with_note(order: str, note: str) -> str:
    note = " ".join(str(note or "").split())[:LONGEST_NOTE]
    return f"{order}{NOTE}{note}" if note else order


def tag(project: int, task: int, step: int) -> str:
    return f"[K{project}.{task}.{step}]"


class SealedPhone(testclient.Phone):
    """testclient.Phone with its state sealed on disk (Main Kairu's keys towards one Clone)."""

    def __init__(self, path):  # testclient.Phone.__init__'s work, with the state read sealed
        self.path = Path(path)
        state, plain = None, False
        if self.path.exists():
            try:
                state = sealed.read(self.path, SEAL_PURPOSE)
            except sealed.SealBroken:
                state = None
            if state is None:  # a file from before the seal: plain JSON, readable by you only
                try:
                    state = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeDecodeError):
                    raise RuntimeError(f"Main Kairu's keys for this Clone ({self.path.name}) can't be read") from None
                plain = True
        self.state = state if isinstance(state, dict) else {}
        if "sign_seed" not in self.state:
            self.state.update(sign_seed=testclient._b64(os.urandom(32)), box_private=testclient._b64(os.urandom(32)), seen={})
        self.seed, self.box_private = base64.b64decode(self.state["sign_seed"]), base64.b64decode(self.state["box_private"])
        self.sign_public, self.box_public = testclient.ed25519_public(self.seed), testclient.x25519_public(self.box_private)
        self.id = "dev-" + hashlib.sha256(self.sign_public).hexdigest()[:16]
        if plain:
            self.save()

    def save(self) -> None:
        sealed.write(self.path, self.state, SEAL_PURPOSE)


class Peer:
    def __init__(self, data_dir, name: str):
        self.name = name
        self.phone = SealedPhone(key_file(data_dir, name))

    @property
    def device(self) -> str:
        return self.phone.id

    def pair(self, offer: str, code: str, wait: float = 90) -> dict:
        try:
            return self.phone.pair(offer, code, name="Main Kairu", wait=wait)
        except SystemExit as why:  # testclient's command-line way of saying no
            raise RuntimeError(str(why)) from None

    def send_order(self, project: int, task: int, step: int, order: str, note: str = "") -> None:
        """One order of one task, as a D4 mission (it may wait in the Gate while the Clone's PC is off). Main Kairu's own
        note, if any, rides on it after a NOTE line: the Clone keeps it in its team inbox; its task core never sees it."""
        body = json.dumps({"action": ORDER, "details": {"order": with_note(f"{tag(project, task, step)} {order}", note)}},
                          separators=(",", ":"))
        self.phone.send("mission", body, "Low")

    def news(self, since: int) -> tuple[list[dict], int]:
        """What the Clone said since `since` (a Gate time), read once, and the time to read from next."""
        state = self.phone.state
        if not state.get("topic"):
            return [], since
        url = f"{state['relay']}/{state['topic']}/json?since={max(since - 1, 0) or 'all'}&poll=1"
        request = urllib.request.Request(url, headers={"User-Agent": "kairu-team/1"})
        got, newest = [], since
        with urllib.request.urlopen(request, timeout=20) as response:
            for line in response:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("event") != "message":
                    continue
                newest = max(newest, int(event.get("time", 0)))
                try:
                    if json.loads(event["message"]).get("from") == self.phone.id:
                        continue  # Main Kairu's own order
                    got.append(self.phone.open(event["message"], event.get("time")))
                except (ValueError, KeyError, TypeError):
                    continue  # read before (a replay), or not from this Clone: never trusted
        return got, newest


def read_report(body: str) -> tuple[tuple[int, int, int] | None, bool, str]:
    """A Clone's report: which task step it is about (from its tag, if any), whether that step finished, and the words."""
    found = TAG.match(body or "")
    if not found:
        return None, False, (body or "").strip()
    return (int(found.group(1)), int(found.group(2)), int(found.group(3))), bool(found.group(4)), body[found.end():].strip()


FAILED = re.compile(r"^(?:refused|not done|guardian refused|stopped|i can'?t|sorry|that didn'?t work|not approved)"
                    r"|nothing ran|did not start|didn'?t start|isn'?t allowed|was refused"
                    # the hands' own words when a step did nothing (found on the laptop, 21 Nov 2026: "Another window came to
                    # the front, so I pressed nothing." finished a save step that never happened, and the task counted done)
                    r"|so i (?:pressed|typed|clicked) nothing", re.I)


def failed(words: str) -> bool:
    return bool(FAILED.search(words or ""))


def now() -> float:
    return time.time()
