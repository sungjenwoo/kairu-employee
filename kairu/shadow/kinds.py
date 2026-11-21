"""The fixed words and limits of a Shadow (SHADOW.md). Constants only.

A Shadow's whole life, as the owner sees it in data/shadows.db:

    invited     the invite (text and 6-digit code) is waiting for the friend, for INVITE_SECONDS
    working     the friend joined: the Shadow is on their laptop, building the use case
    recalled    the owner said "come back now"; the Shadow has not answered yet
    returned    it came home with a finished use case (a skill pack on a branch of the repository)
    unfinished  it came home without one: called back, stopped by the friend, or out of time
    expired     nobody joined before the invite ended
    installed   the owner tested its use case and installed it ("yes" and the PIN)
"""

import re

INVITE_PREFIX = "kairu-shadow:1:"
INVITE_SECONDS = 15 * 60  # the invite and its 6-digit code (the owner's Shadow v0 flow, 12 Nov 2026)
INVITE_TRIES = 5  # wrong codes before the invite is cancelled
DEFAULT_HOURS = 3  # ADR-020: a Shadow mission's default limit
COWORK_HOURS = 24  # a Cowork Shadow: building a part of Kairu takes longer (ADR-039)
MOST_HOURS = 7 * 24  # the longest the owner may give one
MOST_SHADOWS = 5  # working at once

MODES = ("pack", "cowork")  # pack: brings home one skill pack (v0). cowork: a full Kairu there; brings home its changes
BASE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")
TREE = re.compile(r"[0-9a-f]{40}")  # git's id of a whole folder's content

ACTIVE = ("working", "recalled")
STATES = ("invited", "working", "recalled", "returned", "unfinished", "expired", "installed")

SHADOW_ID = re.compile(r"sh-[0-9a-f]{8}")
PACK_NAME = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")  # also its folder (packs/NAME) and the end of its branch
MAX_PACK_NAME = 30
BRANCH_PREFIX = "shadow/"
MAX_FRIEND = 40
MAX_MISSION = 300  # the mission's words travel in the invite, which must stay easy to copy
MAX_NOTE = 200

# what a Shadow may say to the owner's PC: never a command, a question or a request, only these two kinds
SAYS = ("progress", "return")
# ... and what the owner's PC may say to a Shadow
HEARS = ("joined", "recall")

MOST_LESSONS = 5
MAX_LESSON = 200

SEAL_PURPOSE = b"Kairu Shadow key v1"  # the Shadow's own temporary key on the friend's laptop
