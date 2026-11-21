"""The Ember Glow pill (kairu/bar/pill.py, BAR.md "The pill"): what it shows and when, with a stand-in for Windows' drawing.
The last tests draw it for real, on Windows only. No test here opens the mic, runs an order or needs Guardian.
"""

import re
import sys

import pytest

from kairu.bar import pill
from kairu.config import ROOT

SOURCE = (ROOT / "kairu" / "bar" / "pill.py").read_text(encoding="utf-8")
APP = (ROOT / "kairu" / "bar" / "app.py").read_text(encoding="utf-8")


class Layer:
    def __init__(self, width, height):
        self.width, self.height, self.pixels, self.at, self.shown, self.closed = width, height, b"", None, False, False

    def put(self, pixels):
        self.pixels = pixels

    def update(self, x, y, width, height, alpha):
        self.at = (x, y, width, height, alpha)

    def raise_(self):
        self.shown = True

    def hide(self):
        self.shown = False

    def close(self):
        self.closed = True


class Screen:
    """Windows' part, pretended: a 1920 by 1032 screen above the taskbar, letters 8 pixels wide."""

    def __init__(self):
        self.layers, self.texts = [], []

    def work_area(self):
        return 0, 0, 1920, 1032

    def layer(self, width, height):
        self.layers.append(Layer(width, height))
        return self.layers[-1]

    def text(self, text):
        self.texts.append(text)
        return 8 * len(text), 20, [bytes([255]) * 8 * len(text)] * 20


class Clock:
    now = 50.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def at_100_percent():
    """These tests are at 100% display scale (the bar, or a test on Windows, may have set another)."""
    pill.set_scale(1.0)
    yield
    pill.set_scale(1.0)


@pytest.fixture
def made():
    clock, screen = Clock(), Screen()
    return pill.Pill(lambda ms, call: 1, lambda job: None, screen, clock), screen, clock


def run(the_pill, clock, seconds=1.0):
    """The bar's own timer, pretended: a frame every 33 ms."""
    ends = clock.now + seconds
    while clock.now < ends:
        clock.now += 0.033
        the_pill._job = None
        the_pill._frame()


def shown(screen):
    return screen.texts[-1]


def test_it_is_hidden_until_there_is_something_to_show_and_makes_no_window_before(made):
    the_pill, screen, clock = made
    the_pill.show(None)
    run(the_pill, clock)
    assert the_pill.state == "hidden" and screen.layers == [] and the_pill.works


def test_hidden_listening_working_done_and_hidden_again(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock)
    blue, red, *embers, glass = screen.layers
    assert the_pill.state == "listening" and shown(screen) == "Listening…"
    assert blue.at[4] > 100 and red.at[4] == 0 and glass.at[4] == 255 and all(layer.shown for layer in screen.layers)
    the_pill.show("work", True)
    the_pill.order("open chrome")
    run(the_pill, clock)
    assert the_pill.state == "working" and shown(screen) == "Opening Chrome…" and blue.at[4] == 0 and red.at[4] > 100
    the_pill.done("Chrome is open.")
    the_pill.show("listen", True)
    run(the_pill, clock)
    assert the_pill.state == "done" and shown(screen) == "Done · Chrome is open" and blue.at[4] == 0 and red.at[4] == 0
    assert all(ember.at[4] == 0 for ember in embers) and glass.at[4] == 255  # no glow, no embers: only the pill
    run(the_pill, clock, pill.DONE_SECONDS)
    assert the_pill.state == "listening" and shown(screen) == "Listening…"  # still in a talk with you
    the_pill.show(None)
    run(the_pill, clock, 2)
    assert the_pill.state == "hidden" and not any(layer.shown for layer in screen.layers)


def test_it_sits_at_the_bottom_centre_above_the_taskbar_and_the_light_ends_at_the_taskbar(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock)
    blue, glass = screen.layers[0], screen.layers[-1]
    x, y, width, height, _ = glass.at
    assert x + width // 2 == 960 and y + pill.MARGIN + pill.BAR_H == 1032 - pill.FROM_BOTTOM
    assert width == pill.STRIDE and height == pill.PILL_H and the_pill._width == pill.MIN_W  # the picture is the window's size
    assert blue.at[0] + blue.at[2] // 2 == 960 and blue.at[1] + blue.at[3] == 1032


def test_three_embers_drift_up_from_the_pill(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock, 0.4)
    first = screen.layers[2]
    low = first.at[1]
    run(the_pill, clock, 1.5)
    assert len(screen.layers) == 6 and first.at[1] < low - 20 and first.at[4] > 0


def test_your_words_are_grey_with_dots_while_you_speak_and_white_when_heard(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    the_pill.heard("open chro", True)
    run(the_pill, clock, 0.2)
    assert shown(screen) == "open chro…" and the_pill._painted[2] is True
    the_pill.heard("Open Chrome")
    run(the_pill, clock, 0.2)
    assert shown(screen) == "Open Chrome" and the_pill._painted[2] is False
    the_pill.heard("")
    run(the_pill, clock, 0.2)
    assert shown(screen) == "Listening…"


def test_an_order_is_never_shown_as_typed_only_an_app_it_opens():
    assert pill.working_text("open chrome") == "Opening Chrome…" and pill.working_text("Launch file explorer.") == "Opening File Explorer…"
    assert pill.working_text("open the workspace") == "Opening the workspace…"
    for order in ("remember my card number is 4111 1111", "open notepad and type my password hunter2", "what is my PIN",
                  "open chrome then search for my bank", "type hello in Notepad", "open passwords.txt"):
        assert pill.working_text(order) == pill.WORKING


def test_only_a_finished_task_gets_the_tick_and_done():
    assert pill.done_text("Chrome is open.") == ("Done · Chrome is open", True) and pill.done_text("Done.") == ("Done", True)
    assert pill.done_text("") == ("Done", True)
    assert pill.done_text("In short: a long answer.\n\nThe page said much more than fits.") == ("Done", True)
    assert pill.done_text("x" * 80) == ("Done", True)
    for reply in ("Guardian refused pc.open_app: not in the policy.", "Not done: you refused it.", "Guardian is not running.",
                  "I can't do that yet.", "Sorry, I didn't catch that. Could you say it again?", "Still on the last one.",
                  "Safe Mode (a test): nothing runs until you resume with `kairu resume`.", "pc.open_app was stopped.",
                  "Something went wrong in the bar; bar.log says what.", "pc.open_app failed; Guardian's log says why."):
        text, finished = pill.done_text(reply)
        assert not finished and "Done" not in text and len(text) <= 60
        assert text == reply or (text.endswith("…") and reply.startswith(text[:-1]))


def test_a_reply_that_is_not_a_finished_task_has_no_tick(made):
    the_pill, screen, clock = made
    the_pill.show("work")
    the_pill.order("open chrome")
    the_pill.done("Guardian refused pc.open_app: not in the policy.")
    run(the_pill, clock, 0.2)
    assert the_pill.state == "done" and the_pill._painted[3] is None and shown(screen).startswith("Guardian refused")


def test_kairu_speaking_is_not_working_and_a_reply_with_no_order_shows_nothing(made):
    the_pill, screen, clock = made
    the_pill.show("work", True)  # the greeting is being said: no order is in hand
    run(the_pill, clock, 0.2)
    assert the_pill.state == "listening"
    the_pill.done("Go ahead, I'm listening.")
    run(the_pill, clock, 0.2)
    assert the_pill.state == "listening"
    the_pill.show("work", False)
    run(the_pill, clock, 0.2)
    assert the_pill.state == "hidden"


def test_an_order_that_ends_without_a_reply_does_not_stay_working(made):
    the_pill, screen, clock = made
    the_pill.show("work")
    the_pill.order("open chrome")
    run(the_pill, clock, 0.2)
    assert the_pill.state == "working"
    the_pill.show(None)
    run(the_pill, clock, 0.2)
    the_pill.show("work")  # Kairu speaks later: that is not the old order
    run(the_pill, clock, 0.2)
    assert the_pill.state == "hidden"


def test_speaking_again_ends_done_at_once(made):
    the_pill, screen, clock = made
    the_pill.show("work", True)
    the_pill.order("open chrome")
    the_pill.done("Chrome is open.")
    the_pill.show("listen", True)
    the_pill.heard("and now", True)
    run(the_pill, clock, 0.2)
    assert the_pill.state == "listening" and shown(screen) == "and now…"


def test_words_too_long_for_the_pill_are_cut(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    the_pill.heard("word " * 60)
    run(the_pill, clock, 0.5)
    assert shown(screen).endswith("…") and pill.MAX_W - 60 < the_pill._width <= pill.MAX_W
    assert screen.layers[-1].at[2] == pill.STRIDE


def test_the_pill_grows_smoothly_to_longer_words_and_is_at_its_width_when_shown_again(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock, 0.5)
    glass = screen.layers[-1]
    assert the_pill._width == pill.MIN_W
    the_pill.heard("open the downloads folder and show me the newest file")  # 53 letters: 424 pixels of words
    goal = pill.pill_width(8 * 53, True)
    run(the_pill, clock, 0.1)
    assert pill.MIN_W < the_pill._width < goal and glass.at[2] == pill.STRIDE
    run(the_pill, clock, pill.RESIZE_SECONDS)
    assert the_pill._width == goal
    the_pill.show(None)
    run(the_pill, clock, 1)
    the_pill.show("listen", True)
    run(the_pill, clock, 0.05)
    assert the_pill._width == pill.MIN_W  # "Listening…" again, not shrinking from the old words


def test_the_pool_swells_as_it_breathes_and_each_size_is_drawn_once(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock, 0.2)
    assert ("listening", 0) in the_pill._pools or len(the_pill._pools) == 1  # one size drawn a frame, never all at once
    run(the_pill, clock, pill.BREATH_SECONDS * 2)
    assert {size for colour, size in the_pill._pools if colour == "listening"} == set(range(len(pill.SWELL)))
    assert not any(colour == "working" for colour, size in the_pill._pools)  # only the colour in use is drawn
    seen = set()
    for _ in range(90):
        run(the_pill, clock, 0.066)
        seen.add(the_pill._pool_shown["blue"])
    assert seen == set(range(len(pill.SWELL)))
    small, big = (pill.glow_pixels(*pill.POOLS["listening"], scale) for scale in (pill.SWELL[0], pill.SWELL[-1]))
    lit = lambda pixels: sum(1 for i in range(3, len(pixels), 4) if pixels[i] > 8)
    assert lit(big) > lit(small) * 1.2


def test_a_problem_reported_while_the_bar_is_hidden_shows_on_the_pill_and_nothing_else_does(made):
    the_pill, screen, clock = made
    the_pill.note("Mic on. Say \"Kairu\", or press Ctrl+Alt+V.")  # not a problem: nothing shown
    run(the_pill, clock, 0.2)
    assert the_pill.state == "hidden" and screen.layers == []
    the_pill.note("The mic can't be used: Guardian refused voice.listen.")
    run(the_pill, clock, 0.2)
    assert the_pill.state == "done" and shown(screen).startswith("The mic can't be used") and the_pill._painted[3] is None
    run(the_pill, clock, pill.NOTE_SECONDS)
    assert the_pill.state == "hidden"


def test_while_the_typing_bar_is_open_the_pill_draws_only_its_light(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock, 0.5)
    blue, glass = screen.layers[0], screen.layers[-1]
    assert glass.at[4] == 255 and the_pill.raises == 1
    the_pill.cover(True)
    run(the_pill, clock, 0.1)
    assert glass.at[4] == 0 and blue.at[4] > 100  # the typing bar is where the glass was; the light still shows
    the_pill.cover(False)
    run(the_pill, clock, 0.1)
    assert glass.at[4] == 255


def test_if_windows_refuses_the_pill_goes_off_and_nothing_else_does(made, capsys):
    the_pill, screen, clock = made

    def refuse(width, height):
        raise OSError("no window")
    screen.layer = refuse
    the_pill.show("listen", True)
    assert not the_pill.works and "the pill is off" in capsys.readouterr().err
    the_pill.show("work")
    the_pill.order("open chrome")
    the_pill.done("Chrome is open.")
    the_pill.heard("hello")
    the_pill.close()


def test_closing_lets_every_window_go(made):
    the_pill, screen, clock = made
    the_pill.show("listen", True)
    run(the_pill, clock, 0.2)
    the_pill.close()
    assert len(screen.layers) == 6 and all(layer.closed for layer in screen.layers) and not the_pill.works
    the_pill.show("listen", True)  # the bar's timer may still run once


def test_the_pictures_are_the_right_size_and_see_through_outside_the_pill():
    width, pixels = pill.pill_pixels("done", (160, 20, [bytes(160)] * 20), icon=pill.icon_rows("tick"))
    assert width == pill.MIN_W and len(pixels) == pill.STRIDE * pill.PILL_H * 4
    row = pill.STRIDE * 4

    start = (pill.STRIDE - width - 2 * pill.MARGIN) // 2  # the pill is in the middle of its window

    def pixel(x, y):
        return tuple(pixels[y * row + (start + x) * 4:y * row + (start + x) * 4 + 4])
    assert pixel(-start, 0) == (0, 0, 0, 0) and pixel(pill.MARGIN + 3, pill.MARGIN + 3) == (0, 0, 0, 0)  # outside the round end
    blue, green, red, alpha = pixel(pill.MARGIN + 60, pill.MARGIN + 10)
    assert alpha == round(255 * 0.66) and max(blue, green, red) < 20  # dark glass, two thirds solid
    assert all(max(pixels[i:i + 3]) <= pixels[i + 3] for i in range(0, len(pixels), 4))  # premultiplied, as Windows needs
    glow = pill.glow_pixels(*pill.POOLS["listening"])
    assert len(glow) == pill.GLOW_W * pill.GLOW_H * 4 and glow[:4] == bytes(4)
    under = (pill.GLOW_UP + 62) * pill.GLOW_W * 4 + (pill.GLOW_W // 2) * 4
    assert glow[under] > glow[under + 2] and glow[under + 3] > 150  # blue, strongest under the pill
    assert len(pill.ember_pixels(pill.EMBER["working"], 4)) == pill.SPARK * pill.SPARK * 4


def test_at_125_percent_everything_is_a_quarter_bigger_and_each_picture_is_its_window(made):
    the_pill, screen, clock = made
    pill.set_scale(1.25)
    assert (pill.BAR_H, pill.MIN_W, pill.FONT, pill.FROM_BOTTOM) == (80, 390, 20, 58)
    the_pill.show("listen", True)
    run(the_pill, clock, 0.5)
    for layer in screen.layers:  # Windows shows a see-through window reliably only when its picture is its own size
        assert layer.at[2:4] == (layer.width, layer.height)
        assert len(layer.pixels) in (0, layer.width * layer.height * 4)
    glass = screen.layers[-1]
    assert glass.at[1] + pill.MARGIN + pill.BAR_H == 1032 - pill.FROM_BOTTOM
    assert len(pill.icon_rows("mic")) == pill.ICON == 22
    assert len(pill.glow_pixels(*pill.POOLS["listening"])) == pill.GLOW_W * pill.GLOW_H * 4


def test_the_pill_only_shows_read_from_the_code():
    """No box, no button, no key or click made, and its windows let clicks through and never take the keyboard."""
    assert "tkinter" not in SOURCE and not re.search(r"\b(?:Entry|Button|bind|focus|SetForegroundWindow|SetFocus|mouse_event)\b", SOURCE)
    assert pill._Layer.STYLE & 0x20 and pill._Layer.STYLE & 0x08000000 and pill._Layer.STYLE & 0x80  # TRANSPARENT, NOACTIVATE, TOOLWINDOW
    assert not re.search(r"\b(?:client|core|guardian|Guardian|channel|store)\b", SOURCE.split('"""', 2)[2])  # it reaches nothing
    assert set(re.findall(r"self\.pill\.(\w+)", APP)) == {"show", "order", "done", "heard", "close", "note", "cover", "raises",
                                                                    "step"}  # ADR-054: "Step 3", never the step's words


@pytest.mark.skipif(sys.platform == "win32", reason="Windows draws it")
def test_where_it_cannot_be_drawn_there_is_no_pill_and_every_call_does_nothing():
    the_pill = pill.Pill(lambda ms, call: 1, lambda job: None)
    assert not the_pill.works
    the_pill.show("listen", True)
    the_pill.order("open chrome")
    the_pill.done("Chrome is open.")
    the_pill.heard("hello", True)
    the_pill.close()


# --- drawn for real, on Windows ----------------------------------------------------------------------------------------

@pytest.fixture
def windows():
    if sys.platform != "win32":
        pytest.skip("Windows only")
    screen = pill._windows_screen()
    if screen is None:
        pytest.skip("no screen here")
    return screen


def test_windows_draws_the_words(windows):
    width, height, rows = windows.text("Done · Chrome is open")
    assert 100 < width < 260 and 14 < height <= windows.TEXT_H and len(rows) == height
    assert all(len(row) == width for row in rows) and max(max(row) for row in rows) > 200  # white letters
    assert windows.text("Done")[0] < width


def test_windows_shows_every_state_and_lets_the_windows_go(windows, capsys):
    clock = Clock()
    the_pill = pill.Pill(lambda ms, call: 1, lambda job: None, windows, clock)
    try:
        the_pill.show("listen", True)
        the_pill.heard("open chro", True)
        run(the_pill, clock, 0.5)
        the_pill.show("work", True)
        the_pill.order("open chrome")
        run(the_pill, clock, 0.5)
        the_pill.done("Chrome is open.")
        run(the_pill, clock, 0.5)
        assert the_pill.works and the_pill.state == "done", capsys.readouterr().err
        left, top, right, bottom = windows.work_area()
        assert right - left >= 640 and bottom - top >= 400 and pill.SCALE == windows.display_scale()
        the_pill.show(None)
        run(the_pill, clock, pill.DONE_SECONDS + 1)
        assert the_pill.works and the_pill.state == "hidden", capsys.readouterr().err
    finally:
        the_pill.close()
