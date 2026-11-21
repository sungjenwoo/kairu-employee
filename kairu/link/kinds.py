"""The fixed words and limits of Kairu Link messages. Constants only, so Guardian can check them without the crypto.

Freshness (LINK.md, "Old messages and the queue"):
  - every message must have reached the Gate (the relay) within MAX_AGE_SECONDS of being signed;
  - a LIVE message (command, status, call_request, ask) must also be at most MAX_AGE_SECONDS old when
    this PC reads it, so a command that waited in the queue is refused, never run late, and a question is
    never answered hours after you asked it (Phase B: the phone is told to ask again);
  - a QUEUED message (mission, doubt, report) may wait in the Gate's queue, up to QUEUE_SECONDS
    (ntfy.sh keeps messages 12 hours), and is handled when Guardian next runs;
  - no message may claim to be from more than FUTURE_SECONDS in the future.
Each message's random nonce is kept for NONCE_SECONDS, longer than any message can stay acceptable, so
a message seen once is refused if it comes again.
"""

import re

TYPES = ("command", "mission", "status", "call_request", "doubt", "report", "ask")  # ask: a question (Phase B)
LIVE = ("command", "status", "call_request", "ask")
QUEUED = ("mission", "doubt", "report")
TIERS = ("Low", "Medium", "High", "Critical")

MAX_AGE_SECONDS = 300  # 5 minutes
FUTURE_SECONDS = 60  # clocks may differ this much
QUEUE_SECONDS = 12 * 3600
NONCE_SECONDS = QUEUE_SECONDS + 3600

MAX_BODY_BYTES = 2000  # a message's text, so that the whole envelope fits ntfy's 4,096-byte message limit
MAX_ENVELOPE_BYTES = 4000
MAX_NAME = 40  # a device's name

PAIR_SECONDS = 600  # a pairing offer (QR code and 6-digit code) is valid 10 minutes
PAIR_TRIES = 5  # wrong codes before the offer is cancelled
MOST_DEVICES = 5

# Why a message was refused. The receiver tells Guardian one of these, never the message's words.
PROBLEMS = {
    "unknown_sender": "not from a paired device",
    "malformed": "not a Kairu Link message",
    "wrong_receiver": "addressed to another device",
    "tampered": "changed on the way, or not encrypted for this PC",
    "bad_signature": "the signature does not match the sender's key",
    "expired": "too old (more than 5 minutes)",
    "from_future": "dated in the future",
    "replayed": "already received once (a replay)",
}
TELL_SENDER = ("expired", "malformed")  # refusals the paired phone is told about, so it can send again

SEAL_PURPOSE = b"Kairu Link keys v1"  # mixed into the DPAPI seal of the PC's keys and of the pairing offer

TOPIC = re.compile(r"[0-9a-f]{32}")  # a Gate topic: 128 random bits
DEVICE_ID = re.compile(r"(pc|dev)-[0-9a-f]{16}")
DIGEST = re.compile(r"[0-9a-f]{64}")
