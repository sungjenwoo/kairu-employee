"""mission.run: works through the Mission Cards, one step at a time, with a checkpoint after every step.

Guardian starts it by itself (the Missioner in kairu/guardian_program.py) whenever a card is queued, and again
after a restart or a crash if a card was cut off half-way: a mission goes on from its last checkpoint. It is
the Orchestration brain's part of Phase B (ADR-011): it never answers a question itself, and never runs a
step itself. Each step is a request to Guardian, decided and recorded like any other:

    ask   brain.ask (Low): the question goes through the Model Gateway and the privacy filter. A question
          with personal data is not sent: the step waits for your approval (`kairu mission continue N`
          shows it with the other waiting ones), and the mission goes on with the next steps
    wait  demo.count (Low): a practice step that counts seconds, to try Stop and a restart

Phase B steps only ask and count: reading files, writing, sending and anything High come later. A stop
(Ctrl+Alt+K, the tray, `kairu stop`) ends this program and its step within a second; the card keeps its
checkpoint and waits for `kairu mission continue`. Its only requests to Guardian are run, run_status and end.
"""

import json
import secrets
import sys
import time

from kairu import channel
from kairu.brain.store import BrainStore
from kairu.missions.store import MOST_TRIES, MissionStore

ASK_SECONDS = 150  # a question gets this long, providers switching included
POLL_SECONDS = 0.2


def main(data_dir: str) -> None:
    raise SystemExit(Conductor(data_dir).run())


def log(text: str) -> None:
    print(f"mission.run: {text}", file=sys.stderr, flush=True)


class Conductor:
    def __init__(self, data_dir: str, request=None, poll: float = POLL_SECONDS):
        self.data_dir, self.poll = data_dir, poll
        self.store, self.answers = MissionStore(data_dir), BrainStore(data_dir)
        self.request = request or (lambda message: channel.request(data_dir, message, timeout=15))

    def run(self) -> int:
        while (card_id := self.store.next_runnable()) is not None:
            if not self.work(card_id):
                return 0  # Guardian could not be asked, or refused: the card says why; nothing more now
        return 0

    def work(self, card_id: int) -> bool:
        """One card, from its last checkpoint. False if Guardian refused a step or could not be asked."""
        if not self.store.start(card_id):
            return True
        card = self.store.card(card_id)
        for step in card.steps:
            if step.status in ("done", "skipped", "failed"):
                continue  # finished before: never run twice
            if self.store.status(card_id) != "running":
                return True  # you stopped it
            if step.status == "waiting":
                self.collect(card_id, step)
                continue
            if step.tries >= MOST_TRIES:
                self.store.finish_step(card_id, step.number, "failed", "",
                                       f"cut off {step.tries} times, so not tried again")
                continue
            if not self.do(card_id, step):
                return False
            if self.store.status(card_id) != "running":
                return True
        self.store.settle(card_id)
        return True

    def collect(self, card_id: int, step) -> None:
        """A step that waited for your approval: if you approved it, its answer is there now."""
        answer = self.answers.take_answer(step.ask) if step.ask else None
        if answer is None or answer.status == "needs_approval":
            return
        if answer.status == "answered":
            self.store.finish_step(card_id, step.number, "done", answer.text, f"{answer.level} {answer.provider}".strip())
        else:
            self.store.finish_step(card_id, step.number, "failed", answer.text, answer.status)

    def do(self, card_id: int, step) -> bool:
        ask = None
        if step.kind == "wait":
            seconds = float(step.text)
            action, details, limit = "demo.count", {"seconds": seconds, "quiet": True}, seconds + 30
        else:
            ask = secrets.token_hex(8)
            action, details, limit = "brain.ask", {"question": step.text, "ask": ask,
                                                   "source": f"mission:{card_id}"}, ASK_SECONDS
        self.store.begin_step(card_id, step.number, ask)  # the checkpoint: this step has started
        try:
            started = self.request({"op": "run", "action": action, "details": details})
        except channel.ChannelError as error:
            self.store.undo_step(card_id, step.number)
            self.store.stop(card_id, f"Guardian could not be asked ({error})", told=False)
            return False
        if started.get("verdict") != "ok":
            self.store.undo_step(card_id, step.number)
            self.store.stop(card_id, f"Guardian refused {action}: {started.get('reason')}", told=False)
            return False
        run, deadline = started["run"], time.monotonic() + limit
        while True:
            try:
                outcome = self.request({"op": "run_status", "run": run}).get("outcome")
            except channel.ChannelError:
                outcome = None
            if outcome is not None:
                break
            if self.store.status(card_id) != "running":  # you stopped this mission: end its step, keep the checkpoint
                self._end(run)
                self.store.undo_step(card_id, step.number)
                return True
            if time.monotonic() > deadline:
                self._end(run)
                self.store.finish_step(card_id, step.number, "failed", "", f"took longer than {limit:.0f} s")
                return True
            time.sleep(self.poll)
        self.finish(card_id, step, outcome, ask)
        return True

    def finish(self, card_id: int, step, outcome: str, ask: str | None) -> None:
        if outcome != "finished":
            self.store.finish_step(card_id, step.number, "failed", "",
                                   f"the step {outcome} (Guardian's log says why)")
            return
        if step.kind == "wait":
            self.store.finish_step(card_id, step.number, "done", f"counted {step.text} s")
            return
        answer = self.answers.take_answer(ask)
        if answer is None:
            self.store.finish_step(card_id, step.number, "failed", "", "the brain gave no answer")
        elif answer.status == "answered":
            self.store.finish_step(card_id, step.number, "done", answer.text, f"{answer.level} {answer.provider}".strip())
        elif answer.status == "needs_approval":
            waiting = {"provider": answer.provider, "reasons": list(answer.reasons)}
            if answer.search:
                waiting["search"] = answer.search
            self.store.finish_step(card_id, step.number, "waiting", "", json.dumps(waiting))
        else:
            self.store.finish_step(card_id, step.number, "failed", answer.text, answer.status)

    def _end(self, run: int) -> None:
        try:
            self.request({"op": "end", "run": run})
        except channel.ChannelError:
            pass
