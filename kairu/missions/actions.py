"""The small mission actions Guardian runs for you (all Low): they change only data/missions.db.

    mission.create    save a new card, from a card file you wrote, or the practice card (`--practice`)
    mission.stop      stop one mission; its card keeps its last checkpoint
    mission.continue  queue a stopped, waiting or failed mission again: it goes on from its last checkpoint;
                      with skip, the steps still waiting for an approval you did not give are skipped
    mission.remove    delete a card that is not running

Guardian then runs the missions themselves (mission.run, kairu/missions/run.py) by itself. Each ends with
exit code 1, and a reason on Guardian's log, when there is nothing to do.
"""

import sys

from kairu.missions import card as cards
from kairu.missions.store import MissionStore


def create(data_dir: str, file: str = "", practice: bool = False) -> None:
    if bool(file) == bool(practice):
        _fail("give a card file, or practice, not both")
    try:
        card = cards.check(cards.PRACTICE) if practice else cards.read(file)
    except cards.CardProblem as problem:
        _fail(str(problem))
    MissionStore(data_dir).create(card["goal"], card["done"], card["steps"], card["deadline"], card["report"])


def stop(data_dir: str, card: float) -> None:
    if not MissionStore(data_dir).stop(_number(card), "you stopped it (`kairu mission continue` goes on from its "
                                                      "last checkpoint)"):
        _fail(f"mission {_number(card)} is not running, queued or waiting")


def resume(data_dir: str, card: float, skip: bool = False) -> None:
    from kairu.brain.store import BrainStore
    answers = BrainStore(data_dir)
    if not MissionStore(data_dir).resume(_number(card), skip, answered=answers.has_answer):
        _fail(f"mission {_number(card)} is not stopped, waiting or failed")


def remove(data_dir: str, card: float) -> None:
    if not MissionStore(data_dir).remove(_number(card)):
        _fail(f"there is no mission {_number(card)}, or it is running (`kairu mission stop` first)")


def _number(card: float) -> int:
    if card != int(card) or card < 1:
        _fail(f"a mission number is a whole number, not {card}")
    return int(card)


def _fail(why: str):
    print(f"kairu: {why}", file=sys.stderr)
    raise SystemExit(1)
