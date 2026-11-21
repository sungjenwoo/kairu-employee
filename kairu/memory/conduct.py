"""How a question changes Kairu's memory: it asks Guardian to run memory.remember or memory.forget, and waits.

The brain (kairu/brain/) only thinks and answers; it changes nothing. When you say "remember that ..." or "forget ...",
this Orchestration part (ADR-011) runs in that question's own process and asks Guardian to `run` the action, follows it
with `run_status`, and `end`s one that takes too long. Those three are its only requests. Guardian decides each by
policy.yaml like any other action.
"""

import secrets
import time

from kairu import channel
from kairu.memory.store import MemoryStore

WAIT_SECONDS = 12
POLL_SECONDS = 0.05
NOTHING = "I couldn't change my memory just now"


class Keeper:
    def __init__(self, data_dir, request=None, poll: float = POLL_SECONDS):
        self.data_dir, self.poll = str(data_dir), poll
        self.request = request or (lambda message: channel.request(self.data_dir, message, timeout=15))

    def remember(self, text: str, source: str) -> str:
        """What to tell you after asking Guardian to keep this line."""
        done, problem = self._run("memory.remember", {"text": text, "source": source})
        if not done:
            return f"{NOTHING}: {problem}."
        if done["did"] == "saved":
            return "Got it, I'll remember that. It stays on this PC."
        if done["did"] == "known":
            return "I already remember that."
        if done["did"] == "full":
            return "My memory is full (500 lines). Say \"forget ...\" for something old first."
        return f"I didn't keep that: {done.get('why', 'it was refused')}."

    def forget(self, what: str) -> str:
        done, problem = self._run("memory.forget", {"what": what})
        if not done:
            return f"{NOTHING}: {problem}."
        count = done.get("count", 0)
        if done.get("talks"):
            return f"Done. I forgot our talks: {count} of them." if count else "There were no talks to forget."
        if done.get("all"):
            return f"Done. I forgot everything: {count} line{'s' if count != 1 else ''}." if count else "I had nothing to forget."
        if not count:
            return "I have nothing about that to forget."
        return f"Done. I forgot {count} line{'s' if count != 1 else ''} about that."

    def _run(self, action: str, details: dict) -> tuple[dict | None, str]:
        job = secrets.token_hex(8)
        try:
            started = self.request({"op": "run", "action": action, "details": {**details, "job": job}})
        except channel.ChannelError as error:
            return None, f"Guardian could not be asked ({type(error).__name__})"
        if started.get("verdict") != "ok":
            return None, f"Guardian refused {action}: {started.get('reason')}"
        run, deadline = started["run"], time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                outcome = self.request({"op": "run_status", "run": run}).get("outcome")
            except channel.ChannelError:
                outcome = None
            if outcome is not None:
                done = MemoryStore(self.data_dir).take(job) if outcome == "finished" else None
                return (done, "") if done else (None, f"{action} {outcome}")
            time.sleep(self.poll)
        try:
            self.request({"op": "end", "run": run})
        except channel.ChannelError:
            pass
        return None, f"{action} took longer than {WAIT_SECONDS} s"
