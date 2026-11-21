"""Mission Cards (Phase B, B3): the card file, the checkpoints, and going on after a crash, a stop or an approval.

Guardian here is a stand-in that records each step it is asked to run; the real Guardian program is in
tests_kairu/test_brain_program.py.
"""

import json
import time

import pytest

from kairu.brain.store import Answer, BrainStore
from kairu.missions import card as cards
from kairu.missions.run import Conductor
from kairu.missions.store import MOST_TRIES, MissionStore, report_text


class Crash(BaseException):
    """The PC lost power: the mission program ends where it is, with nothing written after."""


class StandInGuardian:
    """Runs each step at once: a count finishes; a question gets the answer `answers` gives it."""

    def __init__(self, data_dir, answers=None):
        self.data_dir, self.answers = data_dir, answers or {}
        self.runs, self.ended, self.crash_on = [], [], None

    def __call__(self, message):
        if message["op"] == "run":
            self.runs.append((message["action"], dict(message["details"])))
            if self.crash_on is not None and len(self.runs) == self.crash_on:
                raise Crash()
            if message["action"] == "brain.ask":
                details = message["details"]
                status, text = self.answers.get(details["question"], ("answered", f"About {details['question']}"))
                BrainStore(self.data_dir).put_answer(Answer(details["ask"], time.time(), details["source"], status, "L3",
                                                            "groq", text, "", ("a phone number",) if status ==
                                                            "needs_approval" else (), 0.1))
            return {"verdict": "ok", "run": len(self.runs), "pid": 1}
        if message["op"] == "run_status":
            return {"verdict": "ok", "outcome": "finished"}
        if message["op"] == "end":
            self.ended.append(message["run"])
            return {"verdict": "ok"}
        raise AssertionError(message)

    def steps_run(self):
        return [details.get("question") or details.get("seconds") for _, details in self.runs]


def new_card(data_dir, steps, report="pc"):
    card = cards.check({"goal": "Test mission", "done": ["all answered"], "steps": steps, "report": report})
    return MissionStore(data_dir).create(card["goal"], card["done"], card["steps"], card["deadline"], card["report"])


def test_a_card_runs_every_step_in_order_and_ends_done(tmp_path):
    card = new_card(tmp_path, [{"wait": 1}, {"ask": "What is the capital of India?"}, {"wait": 2}])
    guardian = StandInGuardian(tmp_path)
    Conductor(str(tmp_path), guardian, poll=0).run()
    assert [action for action, _ in guardian.runs] == ["demo.count", "brain.ask", "demo.count"]
    finished = MissionStore(tmp_path).card(card)
    assert finished.status == "done" and [step.status for step in finished.steps] == ["done"] * 3
    assert finished.steps[1].result == "About What is the capital of India?" and not finished.reported
    assert guardian.runs[1][1]["source"] == f"mission:{card}"
    assert "Mission 1 done" in report_text(finished) and "please tick it yourself" in report_text(finished)


def test_after_a_crash_a_mission_goes_on_from_its_last_checkpoint_and_never_repeats_a_finished_step(tmp_path):
    card = new_card(tmp_path, [{"ask": "one?"}, {"ask": "two?"}, {"ask": "three?"}, {"ask": "four?"}])
    first = StandInGuardian(tmp_path)
    first.crash_on = 3  # the power goes while the third step runs
    with pytest.raises(Crash):
        Conductor(str(tmp_path), first, poll=0).run()
    cut = MissionStore(tmp_path).card(card)
    assert [step.status for step in cut.steps] == ["done", "done", "running", "todo"] and cut.status == "running"
    again = StandInGuardian(tmp_path)  # Guardian starts again; its Missioner starts mission.run
    Conductor(str(tmp_path), again, poll=0).run()
    assert again.steps_run() == ["three?", "four?"]  # the finished ones are not asked again
    done = MissionStore(tmp_path).card(card)
    assert done.status == "done" and done.steps[2].tries == 2 and done.steps[0].tries == 1


def test_a_step_cut_off_again_and_again_is_not_tried_for_ever(tmp_path):
    card = new_card(tmp_path, [{"ask": "one?"}, {"ask": "two?"}])
    for _ in range(MOST_TRIES):
        guardian = StandInGuardian(tmp_path)
        guardian.crash_on = 1
        with pytest.raises(Crash):
            Conductor(str(tmp_path), guardian, poll=0).run()
    last = StandInGuardian(tmp_path)
    Conductor(str(tmp_path), last, poll=0).run()
    finished = MissionStore(tmp_path).card(card)
    assert last.steps_run() == ["two?"] and finished.steps[0].status == "failed" and "cut off 3 times" in finished.steps[0].note
    assert finished.status == "failed"


def test_a_personal_question_waits_for_approval_together_with_the_others_and_the_rest_goes_on(tmp_path):
    card = new_card(tmp_path, [{"ask": "my friend Ravi's number is 9876543210, what should I tell him?"}, {"ask": "two?"}, {"ask": "email sai@example.com?"}])
    guardian = StandInGuardian(tmp_path, {"my friend Ravi's number is 9876543210, what should I tell him?": ("needs_approval", ""),
                                          "email sai@example.com?": ("needs_approval", "")})
    Conductor(str(tmp_path), guardian, poll=0).run()
    waiting = MissionStore(tmp_path).card(card)
    assert waiting.status == "waiting" and "2 steps wait for your approval" in waiting.reason
    assert [step.status for step in waiting.steps] == ["waiting", "done", "waiting"]
    assert waiting.steps[0].waiting_for == {"provider": "groq", "reasons": ["a phone number"]}
    # you approve the first (`kairu mission continue`): its approved send leaves the answer under the same id
    BrainStore(tmp_path).put_answer(Answer(waiting.steps[0].ask, time.time(), f"mission:{card}", "answered", "L3", "groq",
                                           "Ravi is on his way.", "", (), 0.2))
    assert MissionStore(tmp_path).resume(card, skip=True, answered=BrainStore(tmp_path).has_answer)
    again = StandInGuardian(tmp_path)
    Conductor(str(tmp_path), again, poll=0).run()
    finished = MissionStore(tmp_path).card(card)
    assert again.runs == []  # nothing asked again: the approved answer is collected, the refused one skipped
    assert [step.status for step in finished.steps] == ["done", "done", "skipped"] and finished.status == "done"
    assert finished.steps[0].result == "Ravi is on his way."


def test_you_can_stop_a_mission_and_it_keeps_its_checkpoint(tmp_path):
    card = new_card(tmp_path, [{"wait": 1}, {"wait": 1}, {"wait": 1}])
    store = MissionStore(tmp_path)

    class Slow(StandInGuardian):
        def __call__(self, message):
            if message["op"] == "run_status" and len(self.runs) == 2:
                store.stop(card, "you stopped it")  # `kairu mission stop` while the second step counts
                return {"verdict": "ok", "outcome": None}
            return super().__call__(message)

    guardian = Slow(tmp_path)
    Conductor(str(tmp_path), guardian, poll=0).run()
    stopped = store.card(card)
    assert stopped.status == "stopped" and guardian.ended == [2]  # its step was ended too
    assert [step.status for step in stopped.steps] == ["done", "todo", "todo"] and stopped.steps[1].tries == 0
    assert store.resume(card, skip=False)
    again = StandInGuardian(tmp_path)
    Conductor(str(tmp_path), again, poll=0).run()
    assert len(again.runs) == 2 and store.card(card).status == "done"


def test_when_guardian_refuses_a_step_the_mission_stops_and_says_why(tmp_path):
    card = new_card(tmp_path, [{"wait": 1}])

    def refusing(message):
        return {"verdict": "deny", "reason": "Safe Mode (emergency stop)"}

    Conductor(str(tmp_path), refusing, poll=0).run()
    stopped = MissionStore(tmp_path).card(card)
    assert stopped.status == "stopped" and "Safe Mode" in stopped.reason and stopped.steps[0].status == "todo"


@pytest.mark.parametrize("card,problem", [
    ({"goal": "x"}, "steps"),
    ({"goal": "x", "steps": [{"delete": "C:/"}]}, "comes with a later phase"),
    ({"goal": "x", "steps": [{"wait": 9999}]}, "1 to 600"),
    ({"goal": "x", "steps": [{"ask": "a", "wait": 1}]}, "one of"),
    ({"goal": "x", "steps": [{"ask": "a"}], "report": "email"}, "pc, phone or both"),
    ({"goal": "x", "steps": [{"ask": "a"}], "approve": True}, "does not take"),
    ({"goal": "x", "steps": [{"ask": "a"}] * 21}, "1 to 20"),
])
def test_a_card_with_a_mistake_is_refused(card, problem):
    with pytest.raises(cards.CardProblem, match=problem):
        cards.check(card)


def test_the_example_and_the_practice_card_are_good_cards(tmp_path):
    (tmp_path / "card.yaml").write_text(cards.EXAMPLE, encoding="utf-8")
    example = cards.read(str(tmp_path / "card.yaml"))
    assert example["report"] == "both" and example["steps"][1] == ("wait", "20") and example["deadline"]
    practice = cards.check(cards.PRACTICE)
    assert [kind for kind, _ in practice["steps"]] == ["wait"] * 5 + ["ask"]


def test_the_card_store_is_yours_alone(tmp_path):
    import os
    new_card(tmp_path, [{"wait": 1}])
    if os.name != "nt":
        assert (tmp_path / "missions.db").stat().st_mode & 0o077 == 0
    assert json.loads(json.dumps(MissionStore(tmp_path).card(1).done)) == ["all answered"]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_a_card_written_by_powershell_or_notepad_is_read(tmp_path, encoding):
    """Windows PowerShell's `>` writes UTF-16, and Notepad may add a byte-order mark."""
    (tmp_path / "card.yaml").write_bytes(cards.EXAMPLE.encode(encoding))
    assert cards.read(str(tmp_path / "card.yaml"))["goal"] == "Learn about two rivers"
