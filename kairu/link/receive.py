"""link.receive: reads Kairu Link messages from your paired devices through the Gate, and hands each to Guardian.

Guardian starts it (Linker, in kairu/guardian_program.py) while link.enabled is on and a device is
paired, and a stop ends it with every other action. It:
  1. opens one long poll on the Gate for every paired device's topic, starting where it stopped last
     time, so the messages that waited in the Gate's queue while Guardian was off come first;
  2. checks each message (kairu/link/message.py), remembering its nonce before anything else, so a
     message is handled at most once, even if this program is stopped half-way;
  3. tells Guardian, with the `link` request, only: which device, the message type, the message's
     hash and, for a command, the action and its details, for a question (ask, Phase B) its words,
     for a mission that is an order for the task core (D4: {"action": "task.order", ...}) that order;
     or that the message was refused, and why.
Guardian decides. This program never runs an action and never sends anything: replies go out as
Guardian's own link.send actions. A message's words never reach Guardian's audit log, and the text of
any other mission, doubt or report never leaves this program: messages are data, never orders to Kairu. A
question's words go to Guardian only to be handed to the brain (brain.ask, kept in the log as a hash).

It ends by itself (exit code 0) when no device is paired. When the relay cannot be reached or says
"too many requests", it waits (relay.Backoff) and tries again.
"""

import json
import re
import sys
import threading
import time

from kairu import channel
from kairu.link import keys
from kairu.link.kinds import QUEUE_SECONDS
from kairu.link.message import Rejected, open_envelope, sender_of
from kairu.link.relay import Backoff, RateLimited, Relay, RelayError
from kairu.link.store import LinkStore

ACTION_NAME = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")
MOST_QUESTION = 2000  # characters; Guardian takes no longer detail
VERSION_SECONDS = 1.0  # how often a new or removed device is looked for


def main(data_dir: str, relay: str) -> None:
    raise SystemExit(Receiver(data_dir, relay).run())


def log(text: str) -> None:
    print(f"link.receive: {text}", file=sys.stderr, flush=True)


ORDER = "task.order"  # D4: the only action a mission may carry


def parse_command(body: str) -> tuple[str, dict] | None:
    """A command's body: {"action": "demo.count", "details": {"seconds": 5}}. None if it is not one."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict) or set(data) - {"action", "details"}:
        return None
    action, details = data.get("action"), data.get("details") or {}
    if not isinstance(action, str) or len(action) > 100 or not ACTION_NAME.fullmatch(action) or not isinstance(details, dict):
        return None
    if len(details) > 50 or any(len(key) > 100 or (value is not None and type(value) not in (str, int, float, bool))
                                or (type(value) is str and len(value) > 2000) for key, value in details.items()):
        return None  # Guardian takes only short plain details; tell the phone, rather than have Guardian refuse it
    return action, details


class Receiver:
    def __init__(self, data_dir: str, relay: str | Relay, tell=None, clock=time.time, sleep=None):
        self.data_dir, self.clock = data_dir, clock
        self.store = LinkStore(data_dir)
        self.relay = relay if isinstance(relay, Relay) else Relay(relay)
        self.tell = tell or self._tell_guardian
        self.me = keys.load(data_dir)
        self._closed = threading.Event()
        self.sleep = sleep or self._closed.wait  # waits that close() cuts short
        self._subscription = None

    def close(self) -> None:
        """End run() (the action itself is simply ended by Guardian; the tests use this)."""
        self._closed.set()
        if self._subscription is not None:
            self._subscription.close()

    def run(self) -> int:
        backoff = Backoff()
        while not self._closed.is_set():
            devices = self.store.devices()
            if not devices or self.me is None:
                log("no device is paired, so there is nothing to receive")
                return 0
            version = self.store.version()
            try:
                subscription = self.relay.subscribe([device.topic for device in devices], self.since(devices))
            except RateLimited as limited:
                wait = backoff.next(limited.retry_after, rate_limited=True)
                log(f"the relay says too many requests; trying again in {wait:.0f} s")
                self.sleep(wait)
                continue
            except RelayError as error:
                wait = backoff.next()
                log(f"{error}; trying again in {wait:.0f} s")
                self.sleep(wait)
                continue
            self._subscription = subscription
            threading.Thread(target=self._watch_devices, args=(subscription, version), daemon=True).start()
            try:
                for event in subscription:
                    if event.get("event") == "open":
                        backoff.reset()
                    elif event.get("event") == "message":
                        self.handle(event)
            except RelayError as error:
                wait = backoff.next()
                log(f"{error}; reading again in {wait:.0f} s")
                self.sleep(wait)
            finally:
                subscription.close()
        return 0

    def since(self, devices) -> int:
        """Where reading starts: just before the newest message handled, or when the first device was paired."""
        cursor = self.store.cursor()
        start = cursor if cursor is not None else min(device.paired_at for device in devices)
        return int(max(start, self.clock() - QUEUE_SECONDS)) - 1  # a message seen again is known by its Gate id

    def _watch_devices(self, subscription, version: int) -> None:
        while not subscription.closed:
            time.sleep(VERSION_SECONDS)
            try:
                if self.store.version() != version:
                    subscription.close()  # read again, with the devices as they are now
            except Exception as error:
                log(f"could not look at the paired devices ({type(error).__name__})")

    def handle(self, event: dict) -> None:
        """One message from the Gate: checked, then told to Guardian. Never handled twice."""
        relay_id, relay_time, text = event.get("id"), event.get("time"), event.get("message")
        if not isinstance(relay_id, str) or not relay_id or len(relay_id) > 64 or not isinstance(text, str) \
                or type(relay_time) not in (int, float):
            return
        if sender_of(text) == self.me.id:
            return  # this PC's own reply, on the topic it shares with the device
        now = self.clock()
        if not self.store.first_sight(relay_id, now):
            return
        self.store.set_cursor(min(relay_time, now + 60))
        try:
            message = open_envelope(text, self.me, self.store.device, self.store.new_nonce, relay_time, now)
        except Rejected as refusal:
            known = refusal.sender if refusal.sender and self.store.device(refusal.sender) else ""
            self.tell({"op": "link", "device": known, "type": "?", "digest": refusal.digest, "problem": refusal.problem})
            return
        self.store.touch(message.sender, now)
        request = {"op": "link", "device": message.sender, "type": message.type, "digest": message.digest}
        if message.type == "command":
            command = parse_command(message.body)
            if command is None:
                request["problem"] = "malformed"
            else:
                request["action"], request["details"] = command
        elif message.type == "mission":  # D4: a mission that is an order goes to Guardian like the phone's order; any
            command = parse_command(message.body)  # other mission's words stay here, kept as a request only
            if command is not None and command[0] == ORDER:
                request["action"], request["details"] = command
        elif message.type == "ask":
            question = message.body.strip()
            if not question or len(question) > MOST_QUESTION:
                request["problem"] = "malformed"
            else:
                request["details"] = {"question": question}
        self.tell(request)

    def _tell_guardian(self, request: dict) -> None:
        try:
            reply = channel.request(self.data_dir, request, timeout=15)
        except channel.ChannelError as error:  # handled at most once: this message is not tried again
            log(f"Guardian did not take message {request['digest'][:12]} ({error})")
            return
        if reply.get("verdict") != "ok":
            log(f"Guardian refused message {request['digest'][:12]}: {reply.get('reason')}")
