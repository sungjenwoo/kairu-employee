"""What a Shadow learned (ADR-032): general know-how only, never what it saw.

The friend, or the friend's own AI, may note up to MOST_LESSONS short lessons in LESSONS.md in the Shadow's workspace
(lines that start with "- "). keep_general() is run twice on them: on the friend's laptop before the Shadow leaves,
and again on the owner's PC when its report arrives. It drops a line, whole, when it has anything that could be the
friend's: a path, a file name, a web or email address, a long number, or one of the `private` words (the friend's
name, the pack's name and its files' names, the laptop's user name). Dropping too much is fine; a lesson is a bonus.

A lesson that arrives only waits: Kairu keeps it after the owner's own yes (`kairu shadow keep`), and a lesson is
words for the owner to read. It never grants a permission or changes a Guardian rule.
"""

import re

from kairu.shadow.kinds import MAX_LESSON, MOST_LESSONS

FILE_NAME = "LESSONS.md"
NOT_GENERAL = re.compile(r"[/\\@]|https?:|www\.|\d{5,}|\b[\w-]+\.(py|md|json|txt|ya?ml|csv|js|ts|html|exe|db)\b", re.IGNORECASE)


def read(text: str) -> list[str]:
    """The lesson lines of a LESSONS.md."""
    return [line.strip()[2:].strip() for line in text.splitlines() if line.strip().startswith("- ")]


ORDINARY = {"skill", "test", "tests", "readme", "pack", "lessons", "mission", "the", "and", "for"}  # in every pack


def keep_general(lines, private=()) -> list[str]:
    words = {word.lower() for item in private for word in re.findall(r"[^\W_]{3,}", str(item))} - ORDINARY
    kept = []
    for line in lines:
        line = " ".join("".join(ch for ch in str(line) if ch.isprintable()).split())
        if not 10 <= len(line) <= MAX_LESSON or NOT_GENERAL.search(line):
            continue
        if words & {word.lower() for word in re.findall(r"[^\W_]{3,}", line)}:
            continue
        if line not in kept:
            kept.append(line)
    return kept[:MOST_LESSONS]
