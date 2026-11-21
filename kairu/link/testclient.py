"""kairu-link-test: a stand-in phone for Kairu Link, in pure Python (standard library only).

Run it in a second terminal (`kairu-link-test ...`), or copy this one file to an Android phone with
Termux (`pkg install python`) and run `python testclient.py ...` there:

    kairu-link-test pair "kairu-pair:1:..." 123456 --name "My phone"   the text and code `kairu device pair` shows
    kairu-link-test send status                                         ask the PC how it is
    kairu-link-test send command demo.count seconds=5 quiet=true        ask for an action (Guardian decides)
    kairu-link-test send command security.disable                       Critical: the PC must refuse
    kairu-link-test send mission "Find tomorrow's train times"          kept as a request only
    kairu-link-test ask "who is the prime minister of India"            ask Kairu's brain, wait for the answer
    kairu-link-test send status --age 600                               dated 10 minutes ago: must be refused
    kairu-link-test replay                                              the last message again: must be refused
    kairu-link-test listen [--seconds 60]                               show what the PC sends

After `send` and `replay` it shows the PC's replies for --wait seconds (default 30).

It keeps its keys and what it learned when pairing in ~/.kairu-link-test.json (readable by you only).
It is a test tool. Its crypto (Ed25519, X25519, XSalsa20-Poly1305, as in libsodium's crypto_sign and
crypto_box) is written out below so that it runs wherever Python does; Kairu's tests check it against
libsodium itself (PyNaCl). It is slow and makes no effort against timing attacks: the phone app
(Phase D) will use a real crypto library.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PREFIX = "kairu-pair:1:"
TYPES = ("command", "mission", "status", "call_request", "doubt", "report", "ask")
DEFAULT_STATE = Path.home() / ".kairu-link-test.json"

# --- X25519 (RFC 7748) ------------------------------------------------------------------------------

P = 2 ** 255 - 19


def x25519(scalar: bytes, point: bytes) -> bytes:
    k = bytearray(scalar)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    n = int.from_bytes(k, "little")
    x1 = int.from_bytes(point, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in reversed(range(255)):
        bit = (n >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b = (x2 + z2) % P, (x2 - z2) % P
        aa, bb = a * a % P, b * b % P
        e = (aa - bb) % P
        c, d = (x3 + z3) % P, (x3 - z3) % P
        da, cb = d * a % P, c * b % P
        x3, z3 = (da + cb) ** 2 % P, x1 * (da - cb) ** 2 % P
        x2, z2 = aa * bb % P, e * (aa + 121665 * e) % P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    return (x2 * pow(z2, P - 2, P) % P).to_bytes(32, "little")


def x25519_public(private: bytes) -> bytes:
    return x25519(private, (9).to_bytes(32, "little"))


# --- Salsa20, HSalsa20, XSalsa20 and Poly1305 (NaCl's crypto_box) ------------------------------------

MASK = 0xFFFFFFFF
SIGMA = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)  # "expand 32-byte k"


def _rotl(value: int, shift: int) -> int:
    return ((value << shift) & MASK) | (value >> (32 - shift))


def _salsa20_core(state: list, add: bool) -> list:
    x = list(state)

    def quarter(a, b, c, d):
        x[b] ^= _rotl((x[a] + x[d]) & MASK, 7)
        x[c] ^= _rotl((x[b] + x[a]) & MASK, 9)
        x[d] ^= _rotl((x[c] + x[b]) & MASK, 13)
        x[a] ^= _rotl((x[d] + x[c]) & MASK, 18)

    for _ in range(10):
        quarter(0, 4, 8, 12); quarter(5, 9, 13, 1); quarter(10, 14, 2, 6); quarter(15, 3, 7, 11)  # columns
        quarter(0, 1, 2, 3); quarter(5, 6, 7, 4); quarter(10, 11, 8, 9); quarter(15, 12, 13, 14)  # rows
    return [(a + b) & MASK for a, b in zip(x, state)] if add else x


def _state(key: bytes, sixteen: bytes) -> list:
    k, i = struct.unpack("<8I", key), struct.unpack("<4I", sixteen)
    return [SIGMA[0], k[0], k[1], k[2], k[3], SIGMA[1], i[0], i[1], i[2], i[3], SIGMA[2], k[4], k[5], k[6], k[7], SIGMA[3]]


def hsalsa20(key: bytes, sixteen: bytes) -> bytes:
    x = _salsa20_core(_state(key, sixteen), add=False)
    return struct.pack("<8I", x[0], x[5], x[10], x[15], x[6], x[7], x[8], x[9])


def xsalsa20_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    subkey, out, counter = hsalsa20(key, nonce[:16]), bytearray(), 0
    while len(out) < length:
        out += struct.pack("<16I", *_salsa20_core(_state(subkey, nonce[16:24] + struct.pack("<Q", counter)), add=True))
        counter += 1
    return bytes(out[:length])


def poly1305(key: bytes, message: bytes) -> bytes:
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s, p, acc = int.from_bytes(key[16:32], "little"), (1 << 130) - 5, 0
    for i in range(0, len(message), 16):
        acc = (acc + int.from_bytes(message[i:i + 16] + b"\x01", "little")) * r % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _xor(data: bytes, stream: bytes) -> bytes:
    return (int.from_bytes(data, "little") ^ int.from_bytes(stream[:len(data)], "little")).to_bytes(len(data), "little")


def _shared(private: bytes, public: bytes) -> bytes:
    secret = x25519(private, public)
    if secret == bytes(32):
        raise ValueError("a key that gives no shared secret")
    return hsalsa20(secret, bytes(16))


def box_encrypt(private: bytes, public: bytes, message: bytes, nonce: bytes | None = None) -> bytes:
    """crypto_box: nonce (24) + Poly1305 tag (16) + ciphertext, as PyNaCl's Box.encrypt gives."""
    nonce = nonce or os.urandom(24)
    stream = xsalsa20_stream(_shared(private, public), nonce, 32 + len(message))
    cipher = _xor(message, stream[32:])
    return nonce + poly1305(stream[:32], cipher) + cipher


def box_decrypt(private: bytes, public: bytes, data: bytes) -> bytes:
    if len(data) < 40:
        raise ValueError("too short")
    nonce, tag, cipher = data[:24], data[24:40], data[40:]
    stream = xsalsa20_stream(_shared(private, public), nonce, 32 + len(cipher))
    if not hmac.compare_digest(poly1305(stream[:32], cipher), tag):
        raise ValueError("it does not open: changed on the way, or not for this device")
    return _xor(cipher, stream[32:])


# --- Ed25519 (RFC 8032) -------------------------------------------------------------------------------

L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)


def _recover_x(y: int, sign: int):
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P:
        return None
    return P - x if (x & 1) != sign else x


_GY = 4 * pow(5, P - 2, P) % P
_GX = _recover_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % P)


def _add(a, b):
    p1 = (a[1] - a[0]) * (b[1] - b[0]) % P
    p2 = (a[1] + a[0]) * (b[1] + b[0]) % P
    c = 2 * a[3] * b[3] * D % P
    d = 2 * a[2] * b[2] % P
    e, f, g, h = p2 - p1, d - c, d + c, p2 + p1
    return e * f % P, g * h % P, f * g % P, e * h % P


def _mul(scalar: int, point):
    result = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point, scalar = _add(point, point), scalar >> 1
    return result


def _compress(point) -> bytes:
    zinv = pow(point[2], P - 2, P)
    x, y = point[0] * zinv % P, point[1] * zinv % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decompress(raw: bytes):
    y = int.from_bytes(raw, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % P)


def _expand(seed: bytes):
    digest = hashlib.sha512(seed).digest()
    a = int.from_bytes(digest[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, digest[32:]


def ed25519_public(seed: bytes) -> bytes:
    return _compress(_mul(_expand(seed)[0], G))


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    a, prefix = _expand(seed)
    public = _compress(_mul(a, G))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % L
    big_r = _compress(_mul(r, G))
    h = int.from_bytes(hashlib.sha512(big_r + public + message).digest(), "little") % L
    return big_r + ((r + h * a) % L).to_bytes(32, "little")


def ed25519_verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    point_a, point_r = _decompress(public), _decompress(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if point_a is None or point_r is None or s >= L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % L
    left, right = _mul(s, G), _add(point_r, _mul(h, point_a))
    return (left[0] * right[2] - right[0] * left[2]) % P == 0 and (left[1] * right[2] - right[1] * left[2]) % P == 0


# --- the relay (ntfy), with urllib -------------------------------------------------------------------

def publish(relay: str, topic: str, text: str, tries: int = 4) -> dict:
    for attempt in range(tries):
        request = urllib.request.Request(f"{relay}/{topic}", data=text.encode("utf-8"), method="POST",
                                         headers={"User-Agent": "kairu-link-test/1", "Firebase": "no"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == tries - 1:
                raise
            time.sleep(float(error.headers.get("Retry-After") or 5 * (attempt + 1)))
    raise RuntimeError("not sent")


def events(relay: str, topic: str, since: int, seconds: float):
    """The relay's messages on one topic since `since`, for `seconds`, as they come."""
    deadline, seen = time.monotonic() + seconds, set()
    while (left := deadline - time.monotonic()) > 0:
        request = urllib.request.Request(f"{relay}/{topic}/json?since={since}", headers={"User-Agent": "kairu-link-test/1"})
        try:
            with urllib.request.urlopen(request, timeout=min(left, 55)) as response:
                for line in response:
                    event = json.loads(line)
                    if event.get("event") == "message" and event.get("id") not in seen:
                        seen.add(event["id"])
                        since = max(since, int(event.get("time", since)) - 1)
                        yield event
                    if time.monotonic() > deadline:
                        return
        except (TimeoutError, OSError):
            if time.monotonic() > deadline:
                return
            time.sleep(1)


# --- the stand-in phone -------------------------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


class Replayed(ValueError):
    pass


class Phone:
    def __init__(self, state_path=DEFAULT_STATE):
        self.path = Path(state_path)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        if "sign_seed" not in self.state:
            self.state.update(sign_seed=_b64(os.urandom(32)), box_private=_b64(os.urandom(32)), seen={})
        self.seed, self.box_private = base64.b64decode(self.state["sign_seed"]), base64.b64decode(self.state["box_private"])
        self.sign_public, self.box_public = ed25519_public(self.seed), x25519_public(self.box_private)
        self.id = "dev-" + hashlib.sha256(self.sign_public).hexdigest()[:16]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        for attempt in range(10):  # on Windows a virus scanner may hold the file a moment after it is written
            try:
                with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
                    json.dump(self.state, out)
                os.replace(temp, self.path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1)

    @property
    def pc(self) -> dict:
        if "pc" not in self.state:
            raise SystemExit("not paired yet: run `kairu-link-test pair ...` first")
        return self.state["pc"]

    # pairing

    @staticmethod
    def read_offer(offer: str) -> dict:
        """What a pairing QR code holds: {"pc", "sign", "box", "topic", "relay", "expires"}."""
        if not offer.startswith(PREFIX):
            raise SystemExit("that is not the text of a Kairu pairing QR code")
        encoded = offer[len(PREFIX):]
        return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))

    def pair_request(self, data: dict, code: str, name: str, age: float = 0) -> str:
        """The pairing request: this phone's public keys and name, a proof it knows the code; signed, encrypted to the PC."""
        nonce, sign, box = secrets.token_hex(16), _b64(self.sign_public), _b64(self.box_public)
        proof = hmac.new(code.encode(), f"kairu-pair-v1|{data['pc']}|{self.id}|{sign}|{box}|{nonce}".encode(),
                         hashlib.sha256).hexdigest()
        payload = json.dumps({"type": "pair", "from": self.id, "to": data["pc"], "name": name, "sign": sign, "box": box,
                              "ts": int((time.time() - age) * 1000), "nonce": nonce, "proof": proof}).encode()
        boxed = box_encrypt(self.box_private, base64.b64decode(data["box"]), ed25519_sign(self.seed, payload) + payload)
        return json.dumps({"v": 1, "pair": self.id, "to": data["pc"], "key": box, "box": _b64(boxed)})

    def pair(self, offer: str, code: str, name: str = "test phone", wait: float = 60, relay: str | None = None) -> dict:
        """Pair with the PC from the text in its QR code and its 6-digit code. The PC's "paired" report."""
        data = self.read_offer(offer)
        if data["expires"] < time.time():
            raise SystemExit("that pairing offer has expired; run `kairu device pair` again")
        self.state.update(pc={"id": data["pc"], "sign": data["sign"], "box": data["box"]}, relay=relay or data["relay"],
                          name=name, topic=None)
        since = int(time.time()) - 5
        publish(self.state["relay"], data["topic"], self.pair_request(data, code, name))
        for event in events(self.state["relay"], data["topic"], since, wait):
            try:
                said = self.open(event["message"], event.get("time"))
            except ValueError:
                continue  # its own request, or something else
            paired = json.loads(said["body"]).get("paired") if said["type"] == "report" else None
            if paired:
                self.state["topic"] = paired["topic"]
                self.save()
                return said
        raise SystemExit("the PC did not confirm the pairing (a wrong code, or the offer ended)")

    # messages

    def envelope(self, kind: str, body: str = "", tier: str = "Low", age: float = 0, nonce: str | None = None) -> str:
        """A Kairu Link message to the PC: signed with this phone's key, encrypted to the PC's."""
        pc = self.pc
        payload = json.dumps({"from": self.id, "to": pc["id"], "type": kind, "tier": tier,
                              "ts": int((time.time() - age) * 1000), "nonce": nonce or secrets.token_hex(16),
                              "body": body}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        boxed = box_encrypt(self.box_private, base64.b64decode(pc["box"]), ed25519_sign(self.seed, payload) + payload)
        return json.dumps({"v": 1, "from": self.id, "to": pc["id"], "box": _b64(boxed)}, separators=(",", ":"))

    def send(self, kind: str, body: str = "", tier: str = "Low", age: float = 0) -> str:
        text = self.envelope(kind, body, tier, age)
        self.publish(text)
        return text

    def publish(self, text: str) -> None:
        if not self.state.get("topic"):
            raise SystemExit("not paired yet: run `kairu-link-test pair ...` first")
        publish(self.state["relay"], self.state["topic"], text)
        self.state["last"] = text
        self.save()

    def open(self, text: str, relay_time=None) -> dict:
        """A message from the paired PC, checked like the PC checks the phone's. Raises ValueError why not."""
        pc = self.pc
        outer = json.loads(text)
        if not isinstance(outer, dict) or set(outer) != {"v", "from", "to", "box"} or outer["from"] != pc["id"]:
            raise ValueError("not from the paired PC")
        if outer["to"] != self.id:
            raise ValueError("not for this device")
        signed = box_decrypt(self.box_private, base64.b64decode(pc["box"]), base64.b64decode(outer["box"]))
        if not ed25519_verify(base64.b64decode(pc["sign"]), signed[64:], signed[:64]):
            raise ValueError("the PC's signature does not match")
        payload = json.loads(signed[64:].decode("utf-8"))
        if payload["from"] != pc["id"] or payload["to"] != self.id or payload["type"] not in TYPES:
            raise ValueError("its parts do not agree")
        if time.time() - payload["ts"] / 1000 > 12 * 3600:
            raise ValueError("too old")
        seen = self.state.setdefault("seen", {})
        if payload["nonce"] in seen:
            raise Replayed("already received once (a replay)")
        seen[payload["nonce"]] = payload["ts"]
        for nonce in [n for n, ts in seen.items() if ts < (time.time() - 13 * 3600) * 1000]:
            del seen[nonce]
        self.save()
        return payload

    def replies(self, since: int, seconds: float, until=None) -> list:
        """The PC's messages since `since`, for `seconds` or until until(messages so far) is true."""
        got = []
        for event in events(self.state["relay"], self.state["topic"], since, seconds):
            try:
                outer = json.loads(event["message"])
                if outer.get("from") == self.id:
                    continue  # this phone's own message
                got.append(self.open(event["message"], event.get("time")))
            except Replayed:
                continue  # shown before (reading again starts a little early)
            except (ValueError, KeyError) as error:
                print(f"  (refused a message: {error})", file=sys.stderr)
                continue
            if until and until(got):
                break
        return got


# --- the command ------------------------------------------------------------------------------------

def _show(message: dict) -> None:
    when = time.strftime("%H:%M:%S", time.localtime(message["ts"] / 1000))
    print(f"  {when}  PC {message['type']}: {message['body']}")


def _command_body(words: list) -> str:
    if not words:
        raise SystemExit("send command ACTION [name=value ...]")
    details = {}
    for word in words[1:]:
        name, _, value = word.partition("=")
        if value.lower() in ("true", "false"):
            details[name] = value.lower() == "true"
        else:
            try:
                details[name] = float(value) if "." in value else int(value)
            except ValueError:
                details[name] = value
    return json.dumps({"action": words[0], "details": details})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kairu-link-test", description="A stand-in phone for Kairu Link (tests only).")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="where this stand-in keeps its keys")
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("pair", help="pair with the PC (`kairu device pair` shows the text and the code)")
    pair.add_argument("offer")
    pair.add_argument("code")
    pair.add_argument("--name", default="test phone")
    pair.add_argument("--relay", help="another relay than the one in the offer")
    send = commands.add_parser("send", help="send one message to the PC")
    send.add_argument("type", choices=TYPES)
    send.add_argument("words", nargs="*", help="the text; for a command: ACTION name=value ...")
    send.add_argument("--tier", default="Low", choices=("Low", "Medium", "High", "Critical"))
    send.add_argument("--age", type=float, default=0, help="date it this many seconds ago")
    send.add_argument("--wait", type=float, default=30, help="seconds to show the PC's replies")
    replay = commands.add_parser("replay", help="send the last message again, unchanged")
    replay.add_argument("--wait", type=float, default=15)
    listen = commands.add_parser("listen", help="show what the PC sends")
    listen.add_argument("--seconds", type=float, default=60)
    question = commands.add_parser("ask", help="ask Kairu's brain a question and show the answer")
    question.add_argument("words", nargs="+", help="the question")
    question.add_argument("--wait", type=float, default=60, help="seconds to wait for the answer")
    args = parser.parse_args(argv)
    phone = Phone(args.state)

    if args.command == "pair":
        phone.pair(args.offer, args.code, args.name, relay=args.relay)
        print(f"Paired as {phone.id} ({args.name}) with PC {phone.pc['id']}. Keys and the Gate topic are in {phone.path}.")
        return 0
    since = int(time.time()) - 1
    if args.command == "listen":
        print(f"Listening for {args.seconds:g} s ...")
        for message in phone.replies(since, args.seconds):
            _show(message)
        return 0
    if args.command == "ask":
        phone.send("ask", " ".join(args.words))
        print("Asked. Kairu's answer:")
        got = phone.replies(since, args.wait, until=lambda messages: bool(messages))
        for message in got:
            _show(message)
        if not got:
            print(f"  (no answer within {args.wait:g} s: is Guardian running on the PC, and the receiver?)")
        return 0
    if args.command == "replay":
        if not phone.state.get("last"):
            raise SystemExit("nothing was sent yet")
        phone.publish(phone.state["last"])
        print("Sent the last message again, unchanged. The PC must refuse it as a replay (no reply expected).")
    else:
        body = _command_body(args.words) if args.type == "command" else " ".join(args.words)
        phone.send(args.type, body, args.tier, args.age)
        print(f"Sent {args.type}{' dated ' + format(args.age, 'g') + ' s ago' if args.age else ''}. Replies:")
    for message in phone.replies(since, args.wait):
        _show(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
