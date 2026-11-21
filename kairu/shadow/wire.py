"""What a Shadow and the owner's PC say to each other, and how a Shadow joins (SHADOW.md).

Everything travels as Kairu Link envelopes (kairu/link/message.py: signed by the sender, encrypted to the receiver)
through the Gate, of the queued kind ("report"), so a message waits up to 12 hours for a laptop that is off.

The invite (`kairu shadow create` shows it, with a 6-digit code beside it, never inside it) is

    kairu-shadow:1:BASE64URL({"pc", "sign", "box", "topic", "relay", "expires", "shadow", "friend", "mission",
                              "pack", "branch", "repo", "hours"})

Joining is the phone's pairing (kairu/link/pairing.py), with a temporary key the Shadow makes on the friend's laptop:
a request encrypted to the owner's PC, signed by the new key, with a proof that the friend has the code. The PC
answers with a topic of the Shadow's own. The Shadow is never added to the paired devices (data/link.db), so no
message from it is ever read as a request: the PC reads a Shadow's topic only for the two things a Shadow may say,

    {"shadow": {"kind": "progress", "files", "tests", "ready", "note"}}
    {"shadow": {"kind": "return", "done", "why", "pack", "digest", "files", "tests", "commit", "pr", "uses", "lessons",
                "tree", "changed"}}     (tree and changed: a Cowork Shadow's changes to Kairu, ADR-039)

and the Shadow reads it only for {"shadow": {"kind": "joined", "topic", "pc"}} and {"shadow": {"kind": "recall"}}.
Anything else is dropped. Every text field is cut to printable characters of a fixed length before it is kept or
shown: a Shadow's words are data, never a request (and "yes" or a PIN in them is only text).

The crypto (PyNaCl) is loaded only inside the functions that need it, so the `kairu` command and the Guardian program,
which only name this module's constants, never load it.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from kairu.link.kinds import DEVICE_ID, DIGEST, TOPIC
from kairu.shadow.kinds import (BASE_BRANCH, BRANCH_PREFIX, HEARS, INVITE_PREFIX, MAX_FRIEND, MAX_LESSON, MAX_MISSION,
                                MAX_NOTE, MODES, MOST_HOURS, MOST_LESSONS, SAYS, SHADOW_ID, TREE)
from kairu.shadow.pack import good_name

INVITE_KEYS = {"pc", "sign", "box", "topic", "relay", "expires", "shadow", "friend", "mission", "pack", "branch", "repo",
               "hours", "mode", "base"}


class NotAnInvite(Exception):
    pass


def clean(text, most: int) -> str:
    """Words as they may be kept and shown: printable, single spaces, at most `most` characters."""
    return " ".join("".join(ch for ch in str(text) if ch.isprintable()).split())[:most]


def branch_of(shadow: str, pack: str) -> str:
    return f"{BRANCH_PREFIX}{shadow[3:]}-{pack}"


def invite_text(me, topic: str, relay: str, expires: float, card: dict) -> str:
    data = {"pc": me.id, "sign": _b64(me.sign_public), "box": _b64(me.box_public), "topic": topic, "relay": relay,
            "expires": int(expires), **{key: card[key] for key in ("shadow", "friend", "mission", "pack", "branch", "repo",
                                                                   "hours", "mode", "base")}}
    return INVITE_PREFIX + base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def read_invite(text: str) -> dict:
    """The invite's parts, checked. Raises NotAnInvite."""
    from kairu.link import keys
    text = "".join(str(text).split())
    if not text.startswith(INVITE_PREFIX):
        raise NotAnInvite(f"an invite starts with {INVITE_PREFIX}")
    encoded = text[len(INVITE_PREFIX):]
    try:
        data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        sign, box = base64.b64decode(data["sign"], validate=True), base64.b64decode(data["box"], validate=True)
    except (ValueError, KeyError, TypeError):
        raise NotAnInvite("that is not a whole invite: copy all of it") from None
    if (not isinstance(data, dict) or set(data) != INVITE_KEYS or len(sign) != 32 or len(box) != 32
            or data["pc"] != keys.device_id(sign, "pc") or not TOPIC.fullmatch(str(data["topic"]))
            or not isinstance(data["relay"], str) or not data["relay"].startswith(("https://", "http://"))
            or type(data["expires"]) is not int or not SHADOW_ID.fullmatch(str(data["shadow"]))
            or not good_name(data["pack"]) or data["branch"] != branch_of(data["shadow"], data["pack"])
            or not isinstance(data["repo"], str) or not isinstance(data["friend"], str)
            or not isinstance(data["mission"], str) or type(data["hours"]) not in (int, float)
            or not 0 < data["hours"] <= MOST_HOURS or data["mode"] not in MODES
            or not isinstance(data["base"], str)
            or (data["mode"] == "cowork" and (not BASE_BRANCH.fullmatch(data["base"]) or ".." in data["base"]))
            or (data["mode"] == "pack" and data["base"] != "")):
        raise NotAnInvite("that invite's parts do not agree: ask for a new one")
    data["friend"], data["mission"] = clean(data["friend"], MAX_FRIEND), clean(data["mission"], MAX_MISSION)
    return data


def join_request(me, invite: dict, code: str, name: str, now: float | None = None) -> str:
    """The Shadow's request to join: its new public keys and a proof that the friend has the code (as a phone pairs)."""
    from nacl.public import Box, PublicKey
    nonce, sign, box = secrets.token_hex(16), _b64(me.sign_public), _b64(me.box_public)
    proof = hmac.new(code.encode(), f"kairu-pair-v1|{invite['pc']}|{me.id}|{sign}|{box}|{nonce}".encode(),
                     hashlib.sha256).hexdigest()
    payload = json.dumps({"type": "pair", "from": me.id, "to": invite["pc"], "name": name, "sign": sign, "box": box,
                          "ts": int((time.time() if now is None else now) * 1000), "nonce": nonce, "proof": proof}).encode()
    boxed = Box(me.private, PublicKey(base64.b64decode(invite["box"]))).encrypt(me.signing.sign(payload).signature + payload)
    return json.dumps({"v": 1, "pair": me.id, "to": invite["pc"], "key": box, "box": _b64(boxed)})


def body(kind: str, **fields) -> str:
    return json.dumps({"shadow": {"kind": kind, **fields}}, ensure_ascii=False, separators=(",", ":"))


def _read(text: str, kinds: tuple[str, ...]) -> dict | None:
    try:
        said = json.loads(text)
    except ValueError:
        return None
    said = said.get("shadow") if isinstance(said, dict) and set(said) == {"shadow"} else None
    return said if isinstance(said, dict) and said.get("kind") in kinds else None


def _count(value, most: int = 100000) -> int:
    return value if type(value) is int and 0 <= value <= most else 0


def from_shadow(text: str) -> dict | None:
    """What a Shadow said, cut down to exactly the fields below; None if it is not one of the two things it may say."""
    said = _read(text, SAYS)
    if said is None:
        return None
    if said["kind"] == "progress":
        return {"kind": "progress", "files": _count(said.get("files")), "tests": clean(said.get("tests", ""), 40),
                "ready": said.get("ready") is True, "note": clean(said.get("note", ""), MAX_NOTE)}
    lessons = said.get("lessons") if isinstance(said.get("lessons"), list) else []
    found = str(said.get("digest", ""))
    return {"kind": "return", "done": said.get("done") is True, "why": clean(said.get("why", ""), MAX_NOTE),
            "pack": said.get("pack") if good_name(said.get("pack")) else "",
            "digest": found if DIGEST.fullmatch(found) else "", "files": _count(said.get("files")),
            "tests": _count(said.get("tests")), "commit": clean(said.get("commit", ""), 40),
            "tree": str(said.get("tree", "")) if TREE.fullmatch(str(said.get("tree", ""))) else "",
            "changed": [clean(item, 120) for item in said.get("changed", []) if isinstance(item, str)][:200]
            if isinstance(said.get("changed"), list) else [],
            "pr": clean(said.get("pr", ""), 200),
            "uses": [clean(item, 20) for item in said.get("uses", []) if isinstance(item, str)][:4]
            if isinstance(said.get("uses"), list) else [],
            "lessons": [clean(item, MAX_LESSON) for item in lessons if isinstance(item, str)][:MOST_LESSONS]}


def to_shadow(text: str) -> dict | None:
    """What the owner's PC said to a Shadow: joined (with the Shadow's own topic) or recall. None otherwise."""
    said = _read(text, HEARS)
    if said is None:
        return None
    if said["kind"] == "recall":
        return {"kind": "recall"}
    if not TOPIC.fullmatch(str(said.get("topic", ""))) or not DEVICE_ID.fullmatch(str(said.get("pc", ""))):
        return None
    return {"kind": "joined", "topic": said["topic"], "pc": said["pc"]}


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")
