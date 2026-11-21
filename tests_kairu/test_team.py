"""Clones (TEAM.md): Main Kairu splits a project, hands each Clone its orders over Kairu Link, follows what each says.

The Clone's side is the phone's D4 path (a mission that is a task.order), so its own Guardian decides every step; here we
check Main Kairu's side, the step tags both ends agree on, and that a Clone's words can never move a task they aren't about.
"""

import base64
import json
import time

import pytest

from kairu.link import keys
from kairu.link.message import open_envelope, seal
from kairu.link.store import Device, LinkStore
from kairu.tasks.remote import split_tag
from kairu.team import board as boards, conduct, peer as peers, split
from kairu.team.store import BLOCKED, DONE, SENT, WAITING, TeamError, TeamStore
from tests_kairu.fake_relay import FakeRelay

CLONES = [{"name": "Ravi", "share": 1.0}, {"name": "Anu", "share": 2.0}]


def answer(tasks) -> str:
    return "Here you go:\n```json\n" + json.dumps({"tasks": tasks}) + "\n```"


def task(title="Write the copy", clone="Ravi", orders=("open notepad",), after=(), minutes=10, done="a file exists"):
    return {"title": title, "clone": clone, "orders": list(orders), "after": list(after), "minutes": minutes, "done": done}


# --- the split ---------------------------------------------------------------------------------------

def test_a_good_split_is_read_with_its_clones_orders_and_waits():
    tasks = split.parse(answer([task(), task("Research", "anu", ["research bakery websites"], after=[1], minutes=20)]), CLONES)
    assert [t["clone"] for t in tasks] == ["Ravi", "Anu"]  # a Clone's name is matched without caring about capitals
    assert tasks[1]["after"] == [1] and tasks[1]["minutes"] == 20.0


@pytest.mark.parametrize("bad, why", [
    ([task(clone="Stranger")], "haven't added"),
    ([task(after=[1])], "earlier tasks"),
    ([task(), task(after=[3])], "earlier tasks"),
    ([task(orders=["type my PIN 1234 in notepad"])], "PIN"),
    ([task(orders=["yes"])], "approval"),
    ([task(orders=[])], "orders"),
    ([task(orders=["open notepad"] * 5)], "orders"),
    ([task()] * 9, "1 to 8 tasks"),
    ([task(minutes=0)], "minutes"),
    ([{**task(), "tier": "Low"}], "parts"),
])
def test_a_split_that_breaks_a_rule_is_no_split(bad, why):
    with pytest.raises(split.NoSplit, match=why):
        split.parse(answer(bad), CLONES)


def test_another_name_for_a_clone_is_it_when_there_is_one_or_clone_n_but_never_a_stranger_among_several():
    only = [{"name": "Me", "share": 1.0}]
    assert split.parse(answer([task(clone="Main Kairu")]), only)[0]["clone"] == "Me"
    assert split.parse(answer([task(clone="Clone 2")]), CLONES)[0]["clone"] == "Anu"
    with pytest.raises(split.NoSplit, match="haven't added"):
        split.parse(answer([task(clone="Clone 3")]), CLONES)


def test_words_that_are_not_json_are_no_split():
    with pytest.raises(split.NoSplit):
        split.parse("Sure! Ravi does the copy and Anu the research.", CLONES)


def test_the_instructions_name_every_clone_and_its_share():
    told = split.instructions(CLONES, 90)
    assert '"Ravi" (share 1)' in told and '"Anu" (share 2)' in told and "90 minutes" in told and "JSON only" in told


# --- the tags both ends agree on ---------------------------------------------------------------------

def test_the_clone_takes_the_tag_off_and_main_kairu_reads_it_back():
    label, order = split_tag("[K3.2.1] open notepad")
    assert (label, order) == ("[K3.2.1]", "open notepad")
    assert split_tag("open notepad") == ("", "open notepad")
    finished = f"{label[:-1]} finished] Opened notepad."
    assert peers.read_report(finished) == ((3, 2, 1), True, "Opened notepad.")
    assert peers.read_report("[K3.2.1] On it: open → type") == ((3, 2, 1), False, "On it: open → type")
    assert peers.read_report("Your mission reached the PC") == (None, False, "Your mission reached the PC")


@pytest.mark.parametrize("words, bad", [("Opened Notepad.", False), ("Refused: notepad isn't open.", True),
                                         ("Not done: you refused the plan. Nothing ran.", True), ("Done.", False),
                                         ("I can't do that yet.", True), ("Guardian refused step 1 (files.delete).", True)])
def test_a_finished_step_that_says_it_failed_blocks_its_task(words, bad):
    assert peers.failed(words) is bad


# --- running a project ---------------------------------------------------------------------------------

class FakePeer:
    def __init__(self, name, sent):
        self.name, self.sent, self.inbox, self.notes = name, sent, [], []

    def send_order(self, project, task, step, order, note=""):
        self.sent.append((self.name, project, task, step, order))
        self.notes.append((task, step, note))

    def news(self, since):
        got, self.inbox = self.inbox, []
        return [{"type": "report", "body": body} for body in got], since + (1 if got else 0)


@pytest.fixture
def team(tmp_path):
    store = TeamStore(tmp_path)
    store.add_clone("Ravi", "dev-" + "1" * 16)
    store.add_clone("Anu", "dev-" + "2" * 16, 2)
    sent, fakes = [], {}
    tasks = [task("Copy", "Ravi", ["open notepad", "type Fresh bread in notepad"]),
             task("Research", "Anu", ["research bakery sites"]),
             task("Review", "Anu", ["open file copy.txt"], after=[1, 2])]
    number = store.add_project("Bakery site", "a site for a bakery", time.time() + 3600, tasks)
    clock = [1000.0]
    runner = conduct.Runner(tmp_path, number, clock=lambda: clock[0], sleep=lambda s: None,
                            make_peer=lambda name: fakes.setdefault(name, FakePeer(name, sent)))
    runner.begin()
    return store, runner, number, sent, fakes


def states(store, number):
    return [(t["state"], t["step"]) for t in store.tasks(number)]


def test_each_clone_gets_one_order_at_a_time_and_a_task_waits_for_the_ones_it_needs(team):
    store, runner, number, sent, fakes = team
    runner.hand_out()
    assert sent == [("Ravi", number, 1, 1, "open notepad"), ("Anu", number, 2, 1, "research bakery sites")]
    runner.hand_out()
    assert len(sent) == 2  # each Clone is busy: nothing more is sent
    fakes["Ravi"].inbox.append(f"[K{number}.1.1 finished] Opened Notepad.")
    runner.listen()
    assert states(store, number)[0] == (WAITING, 1)
    runner.hand_out()
    assert sent[-1] == ("Ravi", number, 1, 2, "type Fresh bread in notepad")
    fakes["Ravi"].inbox.append(f"[K{number}.1.2 finished] Typed it.")
    fakes["Anu"].inbox.append(f"[K{number}.2.1] On it: searching")
    runner.listen()
    assert states(store, number)[:2] == [(DONE, 2), (SENT, 0)]
    assert store.tasks(number)[1]["last"] == "On it: searching"
    runner.hand_out()
    assert len(sent) == 3  # Review waits for Research, which is still running
    fakes["Anu"].inbox.append(f"[K{number}.2.1 finished] Three sites found.")
    runner.listen()
    runner.hand_out()
    assert sent[-1] == ("Anu", number, 3, 1, "open file copy.txt")  # the hand-off: Anu's next task, now that both are done


def test_a_report_about_another_task_clone_or_old_step_moves_nothing(team):
    store, runner, number, sent, fakes = team
    runner.hand_out()
    fakes["Anu"].inbox += [f"[K{number}.1.1 finished] Opened Notepad.",  # Ravi's task, said by Anu
                           f"[K{number + 1}.2.1 finished] Done.",          # another project
                           f"[K{number}.2.5 finished] Done."]              # a step that wasn't sent
    runner.listen()
    assert states(store, number) == [(SENT, 0), (SENT, 0), (WAITING, 0)]


def test_a_failed_step_blocks_its_task_and_starting_again_tries_it_once_more(team):
    store, runner, number, sent, fakes = team
    runner.hand_out()
    fakes["Ravi"].inbox.append(f"[K{number}.1.1 finished] Refused: notepad isn't installed.")
    runner.listen()
    assert states(store, number)[0] == (BLOCKED, 0)
    assert "Refused" in store.tasks(number)[0]["last"]
    runner.begin()
    assert states(store, number)[0] == (WAITING, 0)


def test_an_untagged_word_from_a_clone_is_only_a_note_on_its_running_task(team):
    store, runner, number, sent, fakes = team
    runner.hand_out()
    fakes["Ravi"].inbox.append("files.delete is High tier: it waits up to 10 minutes for your yes and PIN typed at the PC.")
    runner.listen()
    assert states(store, number)[0] == (SENT, 0) and "PIN" in store.tasks(number)[0]["last"]


def test_a_run_ends_done_when_every_task_is_done_and_stuck_when_nothing_can_go_on(tmp_path):
    store = TeamStore(tmp_path)
    store.add_clone("Ravi", "dev-" + "1" * 16)
    number = store.add_project("One", "one task", None, [task("Copy", "Ravi", ["open notepad"])])
    fake = FakePeer("Ravi", [])

    def sleep(seconds):
        fake.inbox.append(f"[K{number}.1.1 finished] Opened Notepad.")
    assert conduct.Runner(tmp_path, number, sleep=sleep, make_peer=lambda name: fake).run() == "done"
    assert store.project(number)["state"] == "done"
    other = store.add_project("Two", "two", None, [task("Copy", "Ravi", ["open notepad"])])
    fake2 = FakePeer("Ravi", [])
    fake2.news = lambda since: ([{"type": "report", "body": f"[K{other}.1.1 finished] Refused: no."}], since)
    assert conduct.Runner(tmp_path, other, sleep=lambda s: None, make_peer=lambda name: fake2).run() == "stuck"


def test_a_project_needs_its_clones(tmp_path):
    store = TeamStore(tmp_path)
    store.add_clone("Ravi", "dev-" + "1" * 16)
    number = store.add_project("One", "one", None, [task("Copy", "Ravi")])
    store.remove_clone("Ravi")
    with pytest.raises(TeamError, match="not a Clone"):
        conduct.Runner(tmp_path, number).begin()


def test_clone_names_shares_and_the_most_clones(tmp_path):
    store = TeamStore(tmp_path)
    with pytest.raises(TeamError):
        store.add_clone("<script>", "dev-" + "1" * 16)
    with pytest.raises(TeamError, match="share"):
        store.add_clone("Ravi", "dev-" + "1" * 16, 9)
    for n in range(5):
        store.add_clone(f"Clone {n}", f"dev-{n:016d}")
    with pytest.raises(TeamError, match="at most 5"):
        store.add_clone("Sixth", "dev-" + "6" * 16)


# --- the board -------------------------------------------------------------------------------------

def test_the_board_shows_progress_and_flags_a_slipping_task(team):
    store, runner, number, sent, fakes = team
    start = store.project(number)["started"]
    view = boards.board(store.data_dir, number, now=start + 60)
    assert view["project"]["progress"] == 0 and not view["project"]["slipping"]
    assert [c["name"] for c in view["clones"]] == ["Ravi", "Anu"]
    late = boards.board(store.data_dir, number, now=start + 11 * 60)  # Copy was planned for 10 minutes
    assert [t["slipping"] for t in late["project"]["tasks"]][:1] == [True]
    text = "\n".join(boards.lines(late))
    assert "SLIPPING" in text and "Bakery site" in text


def test_the_board_says_at_risk_when_the_rest_cannot_fit_before_the_deadline(tmp_path):
    store = TeamStore(tmp_path)
    store.add_clone("Ravi", "dev-" + "1" * 16)
    now = time.time()
    number = store.add_project("Tight", "tight", now + 15 * 60, [task("A", minutes=10), task("B", minutes=10, after=[1])])
    view = boards.board(tmp_path, number, now=now)
    assert view["project"]["at_risk"] and view["project"]["tasks"][1]["slipping"]


# --- over Kairu Link, through the stand-in Gate --------------------------------------------------------

@pytest.fixture
def relay():
    gate = FakeRelay()
    yield gate
    gate.close()


def test_an_order_reaches_the_clone_as_a_d4_mission_and_its_report_comes_back(tmp_path, relay):
    clone_pc = keys.new_identity("pc")
    main = peers.Peer(tmp_path, "Ravi laptop")
    topic = "a" * 32
    main.phone.state.update(pc={"id": clone_pc.id, "sign": base64.b64encode(clone_pc.sign_public).decode(),
                                "box": base64.b64encode(clone_pc.box_public).decode()}, relay=relay.url, topic=topic)
    main.phone.save()
    assert peers.key_file(tmp_path, "Ravi laptop").name == "ravi-laptop.json"
    main.send_order(4, 2, 1, "open notepad")
    links = LinkStore(tmp_path / "clone")
    links.add_device(Device(main.device, "Main Kairu", main.phone.sign_public, main.phone.box_public, topic, time.time()))
    message = open_envelope(relay.on(topic)[-1]["message"], clone_pc, links.device, links.new_nonce)
    assert message.type == "mission"
    assert json.loads(message.body) == {"action": "task.order", "details": {"order": "[K4.2.1] open notepad"}}
    relay.publish(topic, seal(clone_pc, main.device, main.phone.box_public, "report", "[K4.2.1 finished] Opened Notepad."))
    news, newest = main.news(0)
    assert [m["body"] for m in news] == ["[K4.2.1 finished] Opened Notepad."]  # its own mission is not read as news
    again, _ = main.news(newest)
    assert again == []  # read once: the same message is never taken twice


def test_a_message_from_someone_else_on_the_topic_is_never_news(tmp_path, relay):
    clone_pc, stranger = keys.new_identity("pc"), keys.new_identity("pc")
    main = peers.Peer(tmp_path, "Ravi")
    main.phone.state.update(pc={"id": clone_pc.id, "sign": base64.b64encode(clone_pc.sign_public).decode(),
                                "box": base64.b64encode(clone_pc.box_public).decode()}, relay=relay.url, topic="b" * 32)
    relay.publish("b" * 32, seal(stranger, main.device, main.phone.box_public, "report", "[K1.1.1 finished] Done."))
    assert main.news(0)[0] == []
