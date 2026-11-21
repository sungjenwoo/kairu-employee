"""The growth record (TEAM.md "Growth", ADR-049 proposed), the safe version: tasks not people, no score, no ranking, the
employee sees everything recorded about them, the manager decides, and only the employee accepts an offer."""

import pytest

from kairu.team import board as boards, conduct, growth
from kairu.team.store import BLOCKED, DONE, SENT, TeamError, TeamStore
from tests_kairu.test_team import task
from tests_kairu.test_team_sync import runner_for


def finish(fakes, runner, number, task_number, step, words="Done."):
    fakes[next(name for name, fake in fakes.items() if any(sent[2] == task_number for sent in fake.sent))].inbox.append(
        f"[K{number}.{task_number}.{step} finished] {words}")
    runner.listen()


def test_a_done_task_becomes_a_record_entry_about_the_task_that_rides_on_the_clones_next_order(tmp_path):
    store, runner, number, sent, fakes, clock = runner_for(tmp_path, [
        task("Research bakeries", "Anu", ["research bakery sites"], minutes=30),
        task("Write the summary", "Anu", ["open notepad"], after=[1], minutes=20)])
    runner.hand_out()
    clock[0] += 18 * 60
    finish(fakes, runner, number, 1, 1)
    pending = store.pending("Anu")
    assert pending == [f"Record: task 1 'Research bakeries' in project {number} 'Bakery site' was delivered 12 min early; "
                       "it let 1 other task start."]
    runner.hand_out()
    note = fakes["Anu"].notes[-1][2]
    assert note.startswith("Hand-off:") and pending[0] in note and store.pending("Anu") == []
    for word in ("fast", "slow", "hard", "score", "rank", "best", "worst"):
        assert word not in pending[0].lower()  # about the task, never the person


def test_the_queue_waits_for_the_next_order_even_in_a_later_project(tmp_path):
    store, runner, number, sent, fakes, clock = runner_for(tmp_path, [task("Copy", "Ravi", ["open notepad"], minutes=10)])
    runner.hand_out()
    finish(fakes, runner, number, 1, 1)
    assert len(store.pending("Ravi")) == 1  # the project's last order: nothing to ride on yet
    later = store.add_project("Next", "brief", clock[0] + 3600, [task("Logo", "Ravi", ["open paint"])])
    again, more = [], {}
    from tests_kairu.test_team import FakePeer
    runner2 = conduct.Runner(tmp_path, later, clock=lambda: clock[0], sleep=lambda s: None,
                             make_peer=lambda name: more.setdefault(name, FakePeer(name, again)))
    runner2.begin()
    runner2.hand_out()
    assert "Record: task 1 'Copy'" in more["Ravi"].notes[-1][2] and store.pending("Ravi") == []


def test_a_note_never_grows_past_its_room_and_the_rest_waits(tmp_path):
    store, runner, number, sent, fakes, clock = runner_for(tmp_path, [task("Copy", "Ravi", ["open notepad", "save it"])])
    for n in range(12):
        store.add_pending("Ravi", f"Record: task {n} 'A long enough title for the record' was delivered on time.")
    runner.hand_out()
    assert len(fakes["Ravi"].notes[-1][2]) <= conduct.NOTE_ROOM
    assert 0 < len(store.pending("Ravi")) < 12


def test_the_record_counts_early_on_time_late_unblocked_stepped_in_and_checked(tmp_path):
    store, runner, number, sent, fakes, clock = runner_for(tmp_path, [
        task("Research rivals", "Anu", ["research rivals"], minutes=30),
        task("Test the page", "Anu", ["open notepad"], minutes=10),
        task("Write copy", "Ravi", ["open notepad"], after=[1], minutes=20)])
    runner.hand_out()
    clock[0] += 31 * 60
    finish(fakes, runner, number, 1, 1)                      # on time (1 min over, within 5)
    runner.hand_out()
    finish(fakes, runner, number, 2, 1, "Stopped: refused at that laptop.")
    assert store.tasks(number)[1]["state"] == BLOCKED
    runner.begin()                                           # the manager starts it again
    runner.hand_out()
    clock[0] += 30 * 60
    finish(fakes, runner, number, 2, 1)                      # late, but finished after the block
    conduct.check(tmp_path, number, 1)
    rec = growth.record(store, "Anu")
    assert {key: rec[key] for key in ("delivered", "on time", "late", "unblocked", "stepped_in", "checked")} == {
        "delivered": 2, "on time": 1, "late": 1, "unblocked": 1, "stepped_in": 1, "checked": 1}
    assert rec["kinds"]["research"]["delivered"] == 1 and rec["kinds"]["testing"]["late"] == 1
    assert any("your manager checked task 1" in item for item in store.pending("Anu"))
    with pytest.raises(SystemExit):
        conduct.check(tmp_path, number, 3)                   # not done: nothing to check


def test_nothing_ranks_people_the_clones_stay_in_name_order_whatever_they_delivered(tmp_path):
    store = TeamStore(tmp_path)
    for name in ("Zara", "Anu", "Ravi"):
        store.add_clone(name, "dev-" + str(len(store.clones())) * 16)
    tasks = [task(f"Research {n}", "Zara", minutes=10) for n in range(4)]
    number = store.add_project("P", "brief", 0, tasks)
    for n in range(1, 5):
        store.set_task(number, n, state=DONE, started=0, finished=60)
    view = boards.board(tmp_path, number)
    assert [person["clone"] for person in view["growth"]["people"]] == ["Anu", "Ravi", "Zara"]
    text = "\n".join(growth.lines(store))
    assert "no score, no ranking" in text and "rank" not in text.replace("no ranking", "") and "score" not in text.replace("no score", "")
    assert not any(key in person for person in view["growth"]["people"] for key in ("score", "rank", "rating"))


def test_suggestions_are_for_the_manager_with_evidence_and_never_for_late_work(tmp_path):
    store = TeamStore(tmp_path)
    store.add_clone("Anu", "dev-" + "1" * 16)
    store.add_clone("Ravi", "dev-" + "2" * 16)
    number = store.add_project("P", "brief", 0, [task(f"Research {n}", "Anu", minutes=30) for n in range(3)] +
                               [task(f"Write {n}", "Ravi", minutes=10) for n in range(3)])
    for n in range(1, 4):
        store.set_task(number, n, state=DONE, started=1, finished=1 + 10 * 60)    # 20 min early each
    for n in range(4, 7):
        store.set_task(number, n, state=DONE, started=1, finished=1 + 40 * 60)    # 30 min after plan each
    ideas = growth.suggestions(store)
    assert ideas == [{"clone": "Anu", "kind": "research", "offer": "Lead the next research task",
                      "evidence": "3 research tasks delivered, 3 early, 0 on time, none late"}]
    assert "Suggestions for you to decide (Kairu never assigns or promotes)" in "\n".join(growth.lines(store))
    store.set_task(number, 4, finished=None)
    store.set_task(number, 5, finished=None)
    store.set_task(number, 6, finished=None)
    assert [idea["clone"] for idea in growth.suggestions(store)] == ["Anu"]  # untimed work never earns a suggestion
    store.add_offer("Anu", "Lead the next research task")
    assert growth.suggestions(store) == []  # already offered


def test_an_offer_reaches_the_clone_and_only_that_clones_answer_counts(tmp_path):
    store, runner, number, sent, fakes, clock = runner_for(tmp_path, [
        task("Copy", "Ravi", ["open notepad", "save it"]), task("Research", "Anu", ["research", "summarise"])])
    conduct.offer(tmp_path, "Anu", "Lead the next research task")
    offer = store.offers("Anu")[0]
    runner.hand_out()
    assert f"Offer #{offer['number']} from your manager: Lead the next research task" in fakes["Anu"].notes[-1][2]
    assert "Offer" not in fakes["Ravi"].notes[-1][2]
    assert store.offers("Anu")[0]["state"] == "sent"
    fakes["Ravi"].inbox.append(f"[Kanswer] {offer['number']} yes")   # someone else's answer: words only
    runner.listen()
    assert store.offers("Anu")[0]["state"] == "sent"
    fakes["Anu"].inbox.append(f"[Kanswer] {offer['number']} no")
    runner.listen()
    assert store.offers("Anu")[0]["state"] == "declined"
    fakes["Anu"].inbox.append(f"[Kanswer] {offer['number']} yes")    # answered once
    runner.listen()
    assert store.offers("Anu")[0]["state"] == "declined"
    assert "Said no thanks to offer" in store.feed(number)[-1]["words"]


def test_an_answer_never_moves_a_task(tmp_path):
    store, runner, number, sent, fakes, clock = runner_for(tmp_path, [task("Copy", "Ravi", ["open notepad"])])
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[Kanswer] 1 yes [K{number}.1.1 finished] Done.")
    runner.listen()
    assert store.tasks(number)[0]["state"] == SENT


@pytest.mark.parametrize("words", ["", "hi", "Type your PIN to accept", "Share your password", "x" * 201, "Click <here>"])
def test_an_offer_is_the_managers_plain_words_and_never_asks_for_a_pin(tmp_path, words):
    store = TeamStore(tmp_path)
    store.add_clone("Anu", "dev-" + "1" * 16)
    with pytest.raises(TeamError):
        store.add_offer("Anu", words)
    with pytest.raises(TeamError, match="no Clone"):
        store.add_offer("Nobody", "Lead the next research task")


def test_the_new_growth_actions_are_medium():
    import yaml
    from kairu import executors
    from tests_kairu.helpers import POLICY
    actions = yaml.safe_load(open(POLICY, encoding="utf-8"))["actions"]
    assert actions["team.check"]["tier"] == "Medium" and actions["team.offer"]["tier"] == "Medium"
    assert "team.check" in executors.EXECUTORS and "team.offer" in executors.EXECUTORS
