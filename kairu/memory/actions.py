"""memory.remember and memory.forget: the two Guardian actions that change Kairu's memory (MEMORY.md).

Guardian runs each in its own process, like any action, with the line as its detail; its audit log keeps only a hash
(policy.yaml: private). They change only data/memory.db. A line with a secret is never kept, whoever asks: the privacy
filter reads it here again, so a request that skips the brain cannot store one. What happened goes into memory.db under
the job's id, for the question that asked to read once; only labels and counts, never a secret.
"""

import re
import sys

from kairu.brain import privacy
from kairu.memory.store import LONGEST_FACT, MemoryStore, tidy
from kairu.memory.talks import TALKS

JOB = re.compile(r"[0-9a-f]{16}")
SOURCE = re.compile(r"pc|dev-[0-9a-f]{16}")
EVERYTHING = "*"


def remember(data_dir: str, text: str, job: str, source: str) -> None:
    _check(job)
    store = MemoryStore(data_dir)
    line = tidy(text)
    if not SOURCE.fullmatch(source):
        return store.put(job, {"did": "refused", "why": "only you, at the PC or on your paired phone, can tell me what to remember"})
    if not 3 <= len(line) <= LONGEST_FACT:
        return store.put(job, {"did": "refused", "why": f"a line to remember is 3 to {LONGEST_FACT} characters long"})
    verdict = privacy.classify(line)
    if verdict.secret:
        return store.put(job, {"did": "refused", "why": f"it has {verdict.why()}, and I never keep secrets"})
    store.put(job, {"did": store.add(line, source)})


def forget(data_dir: str, what: str, job: str) -> None:
    _check(job)
    store = MemoryStore(data_dir)
    if what == EVERYTHING:
        return store.put(job, {"did": "forgot", "count": store.clear(), "all": True})
    if what == TALKS:  # "forget our talks": the whole talk history in brain.db
        from kairu.brain.store import BrainStore
        return store.put(job, {"did": "forgot", "count": BrainStore(data_dir).forget_talks(), "talks": True})
    found = store.find(what)
    store.put(job, {"did": "forgot", "count": store.remove([fact["id"] for fact in found])})


def _check(job: str) -> None:
    if not JOB.fullmatch(job):
        print("memory: a job id is 16 hex digits", file=sys.stderr)
        raise SystemExit(1)
