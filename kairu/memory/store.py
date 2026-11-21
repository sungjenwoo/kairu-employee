"""data/memory.db: the lines you told Kairu to remember, on this PC only (MEMORY.md).

    facts     one line each, exactly as you said it; the same line is never kept twice
    outcome   what a memory action did, for the question that asked for it to read once

Nothing here is ever sent anywhere: no cloud AI, no search, no phone sync, and Guardian's audit log keeps only hashes.
A line that holds a secret (a password, an OTP, a card number) is never kept: the action reads it with the privacy
filter first. Matching is by words, with rules only: the same question always finds the same lines.

Matching (M3, 15 Nov 2026, local only): each word is reduced to a key. Words that mean the same thing share one
(RELATED: "mom", "mum" and "mother"; "born" and "birthday"; "lives" and "address"), and endings are taken off
("likes", "liked" and "liking" are one key). find() keeps its old rule (every telling word must be in the line); the
lines with more of your words come first. related() is the looser match recall uses when nothing matches exactly: Kairu
then says it is only the closest line it has. forget always uses find(), so a loose match never deletes anything.
"""

import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

DB_NAME = "memory.db"
MOST_FACTS = 500
LONGEST_FACT = 300
OUTCOME_MINUTES = 10
WORD = re.compile(r"[a-z0-9]+")
COMMON = {"my", "your", "our", "the", "a", "an", "is", "are", "was", "were", "am", "be", "what", "who", "when", "where", "which",
          "how", "do", "does", "did", "you", "remember", "know", "about", "me", "i", "of", "that", "this", "it", "to", "in",
          "on", "at", "and", "or", "for", "have", "has", "tell", "told", "say", "said", "please", "kairu", "s"}
SOFT = {"name", "names", "called", "date", "day", "number", "time"}  # "my sister's name" finds "my sister is Anu"
RELATED = {  # words that mean the same thing for memory: one key each (a word in two groups would mix them, a test checks)
    "mother": ("mother", "mom", "mum", "mummy", "mommy", "amma", "maa", "mama", "ammi"),
    "father": ("father", "dad", "daddy", "papa", "nanna", "appa", "abba", "pappa"),
    "sister": ("sister", "sis", "didi", "akka", "chelli"),
    "brother": ("brother", "bro", "bhai", "bhaiya", "annayya", "thammudu"),
    "grandmother": ("grandmother", "grandma", "granny", "nani", "dadi", "ammamma", "nanamma"),
    "grandfather": ("grandfather", "grandpa", "thatha", "tatha"),
    "friend": ("friend", "buddy", "pal", "dost", "bestie"),
    "birthday": ("birthday", "bday", "born", "birth", "birthdate", "dob"),
    "exam": ("exam", "examination", "test", "exams"),
    "phone": ("phone", "mobile", "cell", "cellphone"),
    "address": ("address", "live", "lives", "living", "lived", "stay", "stays", "staying", "home"),
    "job": ("job", "work", "works", "working", "office", "company", "employer", "workplace"),
    "college": ("college", "school", "university", "uni", "campus"),
    "like": ("like", "likes", "liked", "love", "loves", "loved", "favourite", "favorite", "fav", "enjoy", "enjoys"),
    "doctor": ("doctor", "dr", "physician"),
    "meeting": ("meeting", "appointment", "appt"),
    "deadline": ("deadline", "due"),
    "medicine": ("medicine", "medicines", "tablet", "tablets", "pill", "pills", "meds"),
    "wedding": ("wedding", "marriage", "anniversary"),
}
PEOPLE = {"=" + key for key in ("mother", "father", "sister", "brother", "grandmother", "grandfather", "friend")}
_KEY_OF = {word: key for key, group in RELATED.items() for word in group}

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     REAL NOT NULL,
    text   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    source TEXT NOT NULL            -- pc, or a paired device's id
);
CREATE TABLE IF NOT EXISTS outcome (
    job  TEXT PRIMARY KEY,
    at   REAL NOT NULL,
    body TEXT NOT NULL
);
"""


def words(text: str) -> set[str]:
    """The words of a line that say what it is about: lower case, no "'s", no plural s, no common words."""
    found = WORD.findall(text.lower().replace("’", "'").replace("'s", " "))
    return {word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
            for word in found if word not in COMMON}


def _stem(word: str) -> str:
    """Endings off, the same way for every word: "likes", "liked", "liking" -> "lik"; "classes" -> "class"."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("es") and not word.endswith("sses"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def keys(text: str) -> set[str]:
    """What memory matches on: each telling word as its key (RELATED words share one, endings off)."""
    found = WORD.findall(text.lower().replace("’", "'").replace("'s", " "))
    out = set()
    for word in found:
        if word in COMMON:
            continue
        if word in _KEY_OF:
            out.add("=" + _KEY_OF[word])
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.add("=" + _KEY_OF[word] if word in _KEY_OF else _stem(word))
    return out


SOFT_KEYS = {key for word in SOFT for key in keys(word)}


def tidy(text: str) -> str:
    return " ".join(text.split()).strip(" .!,;:\"'`")


def exists(data_dir) -> bool:
    return (Path(data_dir) / DB_NAME).exists()


class MemoryStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / DB_NAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript(SCHEMA)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    # --- the lines ---------------------------------------------------------------------------------

    def add(self, text: str, source: str) -> str:
        """Keep a line: "saved", "known" (you told me this already) or "full"."""
        with closing(self.connect()) as db, db:
            if db.execute("SELECT 1 FROM facts WHERE text = ?", (text,)).fetchone():
                return "known"
            if db.execute("SELECT COUNT(*) FROM facts").fetchone()[0] >= MOST_FACTS:
                return "full"
            db.execute("INSERT INTO facts (at, text, source) VALUES (?, ?, ?)", (time.time(), text, source))
        return "saved"

    def all(self, most: int = MOST_FACTS) -> list[dict]:
        """The newest lines first."""
        with closing(self.connect()) as db:
            rows = db.execute("SELECT id, at, text FROM facts ORDER BY id DESC LIMIT ?", (most,)).fetchall()
        return [{"id": row[0], "at": row[1], "text": row[2]} for row in rows]

    def find(self, about: str) -> list[dict]:
        """The lines about these words: every telling word (or one that means the same) must be in the line. The lines
        with more of your words come first, then the newest."""
        wanted = keys(about)
        needed = (wanted - SOFT_KEYS) or wanted
        if not needed:
            return []
        found = [(fact, keys(fact["text"])) for fact in self.all()]
        return [fact for fact, have in sorted(((f, k) for f, k in found if needed <= k), key=lambda pair: -len(wanted & pair[1]))]

    def related(self, about: str) -> list[dict]:
        """The closest lines when find() has none: at least half of the telling words (and one word that is in few
        lines, so "my" things in general do not all match). Only recall uses it, and says it is only the closest."""
        wanted = keys(about)
        needed = (wanted - SOFT_KEYS) or wanted
        if len(needed) < 2:
            return []
        found = [(fact, keys(fact["text"])) for fact in self.all()]
        often = {key: sum(key in have for _, have in found) for key in needed}
        least = (len(needed) + 1) // 2
        people = needed & PEOPLE  # "my dad's birthday" is never answered with my mother's
        close = [(fact, have) for fact, have in found
                 if people <= have and len(needed & have) >= least and any(often[key] <= 2 for key in needed & have)]
        return [fact for fact, have in sorted(close, key=lambda pair: -len(needed & pair[1]))]

    def remove(self, ids: list[int]) -> int:
        with closing(self.connect()) as db, db:
            return sum(db.execute("DELETE FROM facts WHERE id = ?", (number,)).rowcount for number in ids)

    def clear(self) -> int:
        with closing(self.connect()) as db, db:
            return db.execute("DELETE FROM facts").rowcount

    # --- what an action did ---------------------------------------------------------------------------

    def put(self, job: str, body: dict) -> None:
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM outcome WHERE at < ?", (time.time() - OUTCOME_MINUTES * 60,))
            db.execute("INSERT OR REPLACE INTO outcome (job, at, body) VALUES (?, ?, ?)", (job, time.time(), json.dumps(body)))

    def take(self, job: str) -> dict | None:
        with closing(self.connect()) as db, db:
            row = db.execute("SELECT body FROM outcome WHERE job = ?", (job,)).fetchone()
            db.execute("DELETE FROM outcome WHERE job = ?", (job,))
        return json.loads(row[0]) if row else None
