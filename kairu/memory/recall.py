"""What Kairu tells you from its memory. It only reads data/memory.db, on this PC: no AI, nothing sent (MEMORY.md).

    told(data_dir, about)        "what do you remember (about X)": the lines, newest first
    about_me(data_dir, question) a question about something of yours ("what is my sister's name"): the line you told
                                 Kairu, or "" if it has none, and then the question goes on as before. Also a question
                                 about someone or something you told Kairu about ("who is Anu", "when is Anu's
                                 birthday", "what do you know about Anu"), but only when a line has every telling word:
                                 otherwise "" and the question goes on (so "who is the prime minister" is never taken)

Rules only: the same question always gets the same lines. The lines are your own words, shown as you said them. When
no line matches a "my ..." question exactly, the closest lines are told as the closest, never as the answer.
"""

import re

from kairu.memory import store as memory

MOST_SHOWN = 20
MOST_ANSWER = 3
MINE = re.compile(r"(?:(?:kairu[\s,:!.-]*)?(?:please\s+)?(?:what|who|when|where|which|how old)(?:'s|\s+is|\s+are|\s+was|\s+were)?\s+my\s+(?P<a>.+)|"
                  r"(?:kairu[\s,:!.-]*)?(?:do|did|can)\s+you\s+(?:remember|know|recall|tell me)\s+my\s+(?P<b>.+)|"
                  r"(?:kairu[\s,:!.-]*)?(?:tell me|say)\s+my\s+(?P<c>.+))", re.IGNORECASE)
OTHER = re.compile(r"(?:kairu[\s,:!.-]*)?(?:please\s+)?(?:"
                   r"(?:who|what|when|where)(?:'s|\s+is|\s+are|\s+was|\s+were)\s+(?P<a>(?!my\b).+)|"
                   r"where\s+(?:does|do|did)\s+(?P<b>(?!i\b).+?\s+(?:live|stay|work|study))|"
                   r"what\s+(?:does|do|did)\s+(?P<c>(?!i\b).+?\s+(?:like|love|study))|"
                   r"(?:what\s+do\s+you\s+know|tell\s+me|do\s+you\s+know\s+anything)\s+about\s+(?P<d>(?!me\b).+))",
                   re.IGNORECASE)
CLOSEST = "I don't have that exactly. The closest I remember:"
NONE_YET = "I don't remember anything yet. Say \"remember that ...\" and I'll keep it on this PC."


def told(data_dir, about: str = "") -> str:
    if not memory.exists(data_dir):
        return NONE_YET
    store = memory.MemoryStore(data_dir)
    facts = store.find(about) if about else store.all()
    if not facts:
        return f"I don't remember anything about {about}." if about else NONE_YET
    shown = facts[:MOST_SHOWN]
    more = f"\n... and {len(facts) - len(shown)} more." if len(facts) > len(shown) else ""
    lead = f"Here is what I remember about {about}:" if about else "Here is what I remember:"
    return "\n".join([lead, *[f"- {fact['text']}" for fact in shown]]) + more


def about_me(data_dir, question: str) -> str:
    said = " ".join(question.split()).strip(" .!?")
    asked = MINE.fullmatch(said)
    if not asked:
        return _about_other(data_dir, said)
    if not memory.exists(data_dir):
        memory.MemoryStore(data_dir)
    store = memory.MemoryStore(data_dir)
    thing = next(group for group in asked.groups() if group)
    facts = store.find(thing)[:MOST_ANSWER]
    if facts:
        return _you_told(facts)
    close = store.related(thing)[:MOST_ANSWER]
    if close:
        return "\n".join([CLOSEST, *[f"- {fact['text']}" for fact in close]])
    if asked["b"]:  # "do you remember my ...": only Kairu's memory can say, so it says so here; other questions go on
        return f"I don't remember your {thing.strip(' ?.!')} yet. Say \"remember that ...\" and I'll keep it."
    return ""


def _about_other(data_dir, said: str) -> str:
    """"who is Anu": a line only if it has every telling word of the question (no closest lines here, so a general
    question is never answered from memory by chance)."""
    asked = OTHER.fullmatch(said)
    if not asked or not memory.exists(data_dir):
        return ""
    thing = next(group for group in asked.groups() if group)
    wanted = memory.keys(thing)
    if not wanted or wanted <= memory.SOFT_KEYS:
        return ""
    facts = memory.MemoryStore(data_dir).find(thing)[:MOST_ANSWER]
    return _you_told(facts) if facts else ""


def _you_told(facts: list[dict]) -> str:
    if len(facts) == 1:
        return f"You told me: {facts[0]['text']}."
    return "\n".join(["You told me:", *[f"- {fact['text']}" for fact in facts]])
