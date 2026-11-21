"""What the small model heard, made into an order (kairu/voice/words.py): rules only, no model needed."""

import pytest

from kairu.voice import words as w
from kairu.voice.hearing import wake_end


@pytest.mark.parametrize("heard,order", [
    ("open chrome and said volume to thirty", "open chrome and set volume to 30"),
    ("um okay so open notepad", "open notepad"), ("i'm okay so open notepad", "open notepad"),
    ("open uh notepad", "open notepad"), ("so um set the volume to twenty five", "set the volume to 25"),
    ("set volume two thirty", "set volume to 30"), ("volume fifty percent", "volume 50 percent"),
    ("brightness to a hundred", "brightness to 100"), ("open note pad", "open notepad"), ("turn wi fi off", "turn wifi off"),
    ("volume to zero", "volume to 0"), ("what is the weather in delhi", "what is the weather in delhi"),
])
def test_fillers_go_levels_become_digits_and_the_usual_mishearings_are_put_right(heard, order):
    assert w.clean(heard.split()) == order


def test_numbers_from_0_to_100_and_nothing_else():
    assert [w.number(n.split()) for n in ("zero", "nine", "thirty", "twenty five", "a hundred", "one hundred")] == [0, 9, 30, 25, 100, 100]
    assert [w.number(n.split()) for n in ("two thirty", "thirty twenty", "five hundred", "")] == [None, None, None, None]


@pytest.mark.parametrize("text", ["thank you", "thanks", "thank you so much", "thank you cairo", "thanks kaoru"])
def test_thank_you_ends_a_session(text):
    assert w.is_thanks(text)


@pytest.mark.parametrize("text", ["thank you for the gift", "open notepad", "no thanks to you"])
def test_other_words_do_not(text):
    assert not w.is_thanks(text)


@pytest.mark.parametrize("text", ["yes", "yeah", "no", "okay", "four eight two nine one six", "for eight to nine won six", "4 8 2"])
def test_a_spoken_yes_no_or_pin_is_never_an_order(text):
    assert w.is_yes_or_digits(text)


@pytest.mark.parametrize("text", ["yes open notepad", "set volume to 30", "restart"])
def test_an_order_is_not_a_yes(text):
    assert not w.is_yes_or_digits(text)


def test_an_order_that_is_only_its_verb_gets_one_short_question_never_a_guess():
    assert w.unclear("open", 1.0) == "Open what?" and w.unclear("set volume to", 1.0) == "Volume to what?"
    assert w.unclear("close", 1.0) == "Close what?" and w.unclear("open notepad", 1.0) == ""
    assert w.unclear("open notepad", 0.3) == w.NOT_CAUGHT  # the model was not sure what it heard


def test_stop_on_its_own_is_the_stop_in_a_session():
    assert all(w.is_stop(text) for text in ("stop", "stop everything", "stop it"))
    assert not any(w.is_stop(text) for text in ("stop the music player", "bus stop", "unstoppable"))


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


def test_kairu_is_found_at_the_start_of_what_was_said_and_where_it_ends():
    assert wake_end([word("cairo", 0.1, 0.6), word("[unk]", 0.7, 1.5)], 0.1) == 0.6
    assert wake_end([word("kai", 0.1, 0.6), word("[unk]", 0.6, 1.0), word("carew", 1.0, 1.4), word("[unk]", 2.0, 3.0)], 0.1) == 1.4
    assert wake_end([word("kai", 0.1, 0.4), word("ru", 0.4, 0.7), word("stop", 1.0, 1.4)], 0.1) == 0.7
    assert wake_end([word("kai", 0.1, 0.5), word("[unk]", 0.5, 0.8)], 0.1) == 0.8  # "kai" and the rest of "Kairu", then nothing


def test_kairu_must_come_first():
    assert wake_end([word("[unk]", 0.1, 1.0), word("cairo", 1.0, 1.5)], 0.1) is None  # "... Cairo ...": not a wake
    assert wake_end([word("[unk]", 0.1, 1.0)], 0.1) is None and wake_end([], 0.1) is None
    assert wake_end([word("ru", 0.1, 0.4)], 0.1) is None


def test_the_wake_grammar_hears_only_kairu_stop_and_everything_else_as_unknown():
    assert set(w.WAKE_GRAMMAR) == {"cairo", "kai ru", "kai rue", "carew", "stop", "[unk]"}
    assert set(w.WAKE_START) <= w.WAKE_PARTS
