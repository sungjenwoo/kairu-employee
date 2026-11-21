"""Guardian's keepers (the Missioner and the Linker) look again when their cards or devices change, whatever else ended.

Found on Ubuntu CI (4 Nov 2026): a mission.run that ended, and `kairu mission continue` queuing a card, both within
one 1-second look. "It ended, wait" overwrote "look again", so the card stayed queued for ever.
"""

from dataclasses import dataclass
from types import SimpleNamespace

from kairu import guardian_program, safemode
from kairu.guardian_program import Linker, Missioner
from kairu.missions.store import MissionStore
from kairu.store import Store


@dataclass
class FakeRun:
    action: str = guardian_program.RUN_MISSIONS
    outcome: str | None = None
    run_id: int = 1


class FakeService:
    """Only what a keeper uses: which runs are running, and starting one."""

    def __init__(self, data_dir):
        self.data_dir, self.store = str(data_dir), Store(data_dir)
        self.quit_requested, self.started, self.current = False, 0, []
        self.runner = SimpleNamespace(running=lambda: list(self.current))
        self.runs = {}

    def _run(self, action):
        self.started += 1
        run = FakeRun(action, run_id=self.started)
        self.current, self.runs[run.run_id] = [run], run
        return {"run": run.run_id}

    def report_missions(self):
        pass


def finish(service):
    """The running mission.run ends by itself."""
    for run in service.current:
        run.outcome = "finished"
    service.current = []


def a_card(store) -> int:
    return store.create("goal", [], [("ask", "a question")], None, "pc")


def keeper(tmp_path):
    service = FakeService(tmp_path)
    assert not safemode.is_safe(service.store)
    return service, MissionStore(tmp_path), Missioner(service, log=lambda text: None)


def test_a_card_queued_in_the_same_look_as_the_last_run_ended_still_runs(tmp_path):
    service, store, missioner = keeper(tmp_path)
    card = a_card(store)
    missioner.tick()
    assert service.started == 1
    store.start(card)
    store.finish_step(card, 1, "waiting")
    store.settle(card)  # the card waits for you
    missioner.tick()  # still running: it has not ended yet
    finish(service)  # between two looks: the run ends ...
    assert store.resume(card, False)  # ... and `kairu mission continue` queues the card
    missioner.tick()
    assert service.started == 2, "the queued card was left waiting for ever"


def test_a_card_queued_while_the_last_run_is_ending_still_runs(tmp_path):
    service, store, missioner = keeper(tmp_path)
    card = a_card(store)
    missioner.tick()
    store.start(card)
    store.finish_step(card, 1, "waiting")
    store.settle(card)
    assert store.resume(card, False)  # queued while the old run is past its last look at the cards
    missioner.tick()  # seen as running: nothing to start yet
    assert service.started == 1
    finish(service)
    missioner.tick()
    assert service.started == 2, "the queued card was left waiting for ever"


def test_with_nothing_queued_a_run_that_ended_is_not_started_again(tmp_path):
    service, store, missioner = keeper(tmp_path)
    card = a_card(store)
    missioner.tick()
    store.start(card)
    store.finish_step(card, 1, "done", "an answer")
    store.settle(card)
    finish(service)
    for _ in range(3):
        missioner.tick()
    assert service.started == 1


def test_a_failed_run_with_nothing_changed_still_waits_before_it_starts_again(tmp_path):
    service, store, missioner = keeper(tmp_path)
    a_card(store)
    missioner.tick()
    missioner.tick()
    [run] = service.current
    run.outcome, service.current = "failed", []
    missioner.tick()
    assert service.started == 1 and missioner._next > 0  # 30 s first, as before


def test_the_receiver_starts_for_a_device_paired_in_the_same_look_as_it_ended(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    linker = Linker(service, log=lambda text: None)
    state = {"version": 1, "paired": True}
    monkeypatch.setattr(guardian_program.link_store, "version", lambda data_dir: state["version"])
    monkeypatch.setattr(guardian_program.link_store, "paired", lambda data_dir: [object()] if state["paired"] else [])
    linker.tick()
    assert service.started == 1
    finish(service)  # the last device was removed, so the receiver ended ...
    state["version"] = 2  # ... and a device was paired again, both between two looks
    linker.tick()
    assert service.started == 2


def test_safe_mode_still_starts_nothing(tmp_path):
    service, store, missioner = keeper(tmp_path)
    a_card(store)
    safemode.enter(service.store, "a test")
    missioner.tick()
    assert service.started == 0
