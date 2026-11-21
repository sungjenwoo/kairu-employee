"""Tenmin: how Kairu talks (the owner's rule, 22-24 Oct 2026). Every spoken answer follows it.

    Warm and encouraging, like a kind teacher; explains simply.
    Correct and short: a simple question gets just the answer ("who is the prime minister of India" is only the name).
    Kairu waits, answers, then offers exactly one short follow-up question. It never leads, and never asks two.
    Short, quick turns; no speeches.
    Explain Mode: "explain it simply" or "explain like a teacher" gives simpler words and one small example.
    Finished tasks stay quiet (K-7): a short line in the bar, no speech. Kairu speaks only to answer or to ask.

Two halves. RULES and EXPLAIN go to the AI with every question (kairu/brain/gateway.py), so the answer is written this way.
spoken() then holds every spoken answer to it, whatever the AI wrote: the answer first and short, exactly one short
follow-up question at the end, no second question, no lists, links, notes in brackets or markdown. The whole answer is
still shown in the bar; only what is said aloud is cut. Rules only: the same answer always gives the same words.
"""

import re

RULES = (
    "- Speak like a kind, encouraging teacher: warm, simple words, never cold or bossy.\n"
    "- First line: the answer itself, in one short sentence. For a question like \"who is the prime minister of ...\", "
    "give just the name.\n"
    "- Then exactly one short follow-up offer on its own line, as a question, like \"Want to know more about him?\". "
    "Never two questions, and never take the lead: the person decides what comes next.\n"
    "- No lists, headings, links or long explanations unless the person asks for them; keep turns short and quick.")
EXPLAIN = (
    "\n- The person asked you to explain simply, like a teacher: use simple everyday words, at most three short sentences, "
    "and one small example (\"For example, ...\"). Then the one follow-up offer.")
EXPLAIN_MODE = re.compile(r"\bexplain\b.*\b(?:simply|simple|simpler|easy|easily|like a teacher|like i'?m (?:five|5|a child|a kid)|"
                          r"to a child|for a kid|in simple words|in plain words)\b", re.IGNORECASE)
FOLLOW_UP = "Want to know more?"
SHORT_WORDS, EXPLAIN_WORDS, FOLLOW_UP_WORDS = 30, 60, 12  # what is said aloud, at most
WHO = re.compile(r"^\s*(?:kairu,?\s*)?(?:who|who's|whos)\b(?: is| was| are)?\b", re.IGNORECASE)
NAME_FIRST = re.compile(r"^((?:[A-Z][\w.'-]*)(?:\s+(?:[A-Z][\w.'-]*|bin|de|da|van|von|al|ibn)){0,4})\s+(?:is|was|has been|became|serves as)\b")
SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
EXAMPLE = re.compile(r"(?:for example|for instance|like when|imagine)\b", re.IGNORECASE)
PLEASANTRY = re.compile(r"(?:great|good|nice|excellent|lovely) question[.!]*|(?:sure|of course|certainly|absolutely|happy to help|"
                        r"glad you asked|okay|ok|alright|hi|hello)(?: there)?[.!,]*", re.IGNORECASE)


def explain_mode(question: str) -> bool:
    return bool(EXPLAIN_MODE.search(question or ""))


def instructions(question: str) -> str:
    """What the AI is told, beyond Kairu's own rules, for this question."""
    return RULES + (EXPLAIN if explain_mode(question) else "")


def _plain(text: str) -> str:
    """No notes in brackets, links, markdown, list marks or hidden reasoning: none of that is said aloud."""
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL)
    text = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", text)  # Kairu's notes ("This may be out of date ...") and sources
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"(?m)^\s*(?:[-*•]+|\d+[.)])\s+", "", text)  # list marks
    text = re.sub(r"[*_#`>|]+", " ", text)
    text = re.sub(r"\s*\n+\s*", "\n", text)
    return text.strip()


def _sentences(text: str) -> list[str]:
    found = []
    for line in text.split("\n"):
        line = re.sub(r"\s+([,.!?;:])", r"\1", " ".join(line.split()))
        if line.endswith(":"):
            continue  # "Here are some tips:" leads in; the tips themselves follow
        found += [part.strip() for part in SENTENCE.findall(line) if part.strip(" .!?")]
    return [part if part[-1] in ".!?" else part + "." for part in found]


def _words(sentences: list[str], most: int) -> list[str]:
    kept, count = [], 0
    for sentence in sentences:
        words = sentence.split()
        if count + len(words) > most:
            if not kept:  # one long sentence: cut at a natural pause, never mid-thought where it can be helped
                cut = " ".join(words[:most])
                comma = cut.rfind(",")
                kept.append((cut[:comma] if comma > len(cut) // 2 else cut).rstrip(",;:") + ".")
            break
        kept.append(sentence)
        count += len(words)
    return kept


def _short_follow_up(question: str) -> str:
    words = question.split()
    return question if len(words) <= FOLLOW_UP_WORDS else FOLLOW_UP


def spoken(answer: str, question: str = "") -> str:
    """What Kairu says aloud for this answer: short, answer first, then exactly one short follow-up question."""
    sentences = _sentences(_plain(answer))
    if not sentences:
        return ""
    while len(sentences) > 1 and PLEASANTRY.fullmatch(sentences[0]):
        sentences.pop(0)  # "Great question!" first would push the answer back: the answer comes first
    statements = [sentence for sentence in sentences if not sentence.endswith("?")]
    if not statements:  # the answer is itself one question (Kairu asks what you meant): only that one
        return _short_follow_up(sentences[0])
    first = sentences.index(statements[0])
    explaining = explain_mode(question)
    told = _words(statements, EXPLAIN_WORDS if explaining else SHORT_WORDS)
    if explaining:
        told = told[:3]  # at most three short sentences, and the one small example among them
        example = next((sentence for sentence in statements if EXAMPLE.match(sentence)), None)
        if example and example not in told and len(" ".join(told[:2] + [example]).split()) <= EXPLAIN_WORDS:
            told = told[:2] + [example]
    else:
        told = told[:1]  # a simple question gets just the answer
        named = NAME_FIRST.match(told[0]) if WHO.match(question or "") else None
        if named:
            told = [named.group(1).rstrip(".,") + "."]  # "who is ...": only the name
    later = [sentence for number, sentence in enumerate(sentences) if sentence.endswith("?") and number > first]
    follow_up = _short_follow_up(later[0]) if later else FOLLOW_UP
    return " ".join(told + [follow_up])


def is_spoken_well(line: str) -> bool:
    """Tenmin's shape: some words, then exactly one question, at the end."""
    return line.count("?") == 1 and line.endswith("?") and len(line.split()) <= EXPLAIN_WORDS + FOLLOW_UP_WORDS
