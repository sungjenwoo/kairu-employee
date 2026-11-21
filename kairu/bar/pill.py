"""The Ember Glow pill (the owner's design "Anime 6 · Ember Glow", GO of 15 Nov 2026): what Kairu is doing, bottom centre.

A dark glass pill over every app, a little above the taskbar, with a soft pool of coloured light under it that breathes
and three small embers drifting up (the pool swells and brightens as it breathes; the pill grows and shrinks smoothly to its
words):

    hidden      nothing in hand: no pill
    listening   blue; your words as you say them (grey with "…" while you speak, white once the sentence is heard)
    working     warm red; "Opening Chrome…" for an order that opens an app, "Working…" for any other
    done        no glow; a tick and "Done · Chrome is open" for a few seconds, then hidden (or listening again)

It only shows what the bar already knows (bar.busy, the voice's state, the words line, the reply). It decides nothing and
does nothing: its windows let every click through to the app under them, never take the keyboard, and have no box or
button. An order is never shown as typed (only "Opening X…" or "Working…"), and a reply that is not a finished task is
shown as it is, without the tick or "Done". While the typing bar is open (Ctrl+Alt+Q) it sits where the pill is, and
the pill draws only its light and embers round it.

Windows only, with ctypes and no new package: six small layered windows (two pools of light, three embers, the pill),
each drawn once and then only moved and faded, so a frame costs a few calls and no drawing. Elsewhere, or if Windows
refuses any of it, there is no pill and the bar carries on as before (bar.log says why).
"""

import math
import re
import sys
import time

# Sizes in pixels at 100% display scale. set_scale() multiplies them for the display (125%: all 1.25 times bigger), so the
# pill looks the same on every screen. Each window's picture is exactly the window's size: Windows shows nothing
# reliable otherwise.
_SIZES = {"BAR_H": 64, "MIN_W": 312, "MAX_W": 720, "MARGIN": 24, "PAD": 30, "GAP": 12, "ICON": 18, "FROM_BOTTOM": 46,
          "GLOW_UP": 70, "SPARK": 24, "EMBER_RISE": 62, "SLIDE": 18, "LIFT": 8, "FONT": 16, "TEXT_H": 32}
_EMBERS = ((-118, -10, 0.0, 4), (14, 8, 0.9, 3), (102, 14, 1.8, 4))  # (from the centre, drift, starts after, size)
SCALE = 1.0
BAR_H = MIN_W = MAX_W = MARGIN = PAD = GAP = ICON = FROM_BOTTOM = GLOW_UP = SPARK = EMBER_RISE = SLIDE = LIFT = FONT = TEXT_H = 0
RADIUS = STRIDE = PILL_H = GLOW_W = GLOW_H = 0
EMBERS: tuple = ()
DONE_SECONDS = 2.8
NOTE_SECONDS = 4.0  # a problem the bar reports while it is hidden, such as "the mic can't be used"
FRAME_MS, IDLE_MS = 33, 200
FILL = (18, 18, 20, 0.66)
# the ring round the pill: its colour and strength, and the colour of the light it throws (None: no light)
RINGS = {"done": ((255, 255, 255), 0.26, None), "listening": ((120, 170, 255), 0.6, (77, 141, 255)),
         "working": ((255, 130, 95), 0.6, (255, 90, 60))}
POOLS = {"listening": ((77, 141, 255), (77, 141, 255)), "working": ((255, 90, 60), (255, 120, 60))}  # centre, part-way
EMBER = {"listening": (141, 184, 255), "working": (255, 138, 92)}
EMBER_SECONDS = 2.7
BREATH_SECONDS = 2.8
SWELL = (0.88, 0.93, 0.98, 1.03, 1.08)  # the pool's sizes as it breathes: each drawn once, one a frame, for the colour in use
RESIZE_SECONDS = 0.35  # the pill grows or shrinks to new words this smoothly
LISTENING, WORKING, DONE = "Listening…", "Working…", "Done"
OPENING = re.compile(r"(?:open|launch|start) (?P<app>[\w+#-]+(?: [\w+#-]+){0,2})[.!]?", re.IGNORECASE)
TROUBLE = re.compile(r"\b(?:refused|not done|not sent|not searched|not running|safe mode|stopped|failed|can't|couldn't|"
                     r"could not|cannot|did not|didn't|does not|doesn't|isn't|is not|not found|took too long|"
                     r"nothing ran|went wrong|still on|sorry|not yet)\b", re.IGNORECASE)


def set_scale(scale: float) -> None:
    """Size everything for a display at this scale (1.0 is 100%, 1.25 is 125%)."""
    global SCALE, RADIUS, STRIDE, PILL_H, GLOW_W, GLOW_H, EMBERS
    SCALE = scale
    for name, size in _SIZES.items():
        globals()[name] = max(1, round(size * scale))
    globals()["BAR_H"] = BAR_H + BAR_H % 2  # even, so its round ends are half of it
    RADIUS = BAR_H // 2
    STRIDE = MAX_W + 2 * MARGIN
    PILL_H = BAR_H + 2 * MARGIN
    GLOW_W = round(540 * scale / 4) * 4  # the pool is drawn at half size and mirrored
    GLOW_H = FROM_BOTTOM + BAR_H + GLOW_UP
    GLOW_H += GLOW_H % 2
    EMBERS = tuple((round(off * scale), round(drift * scale), starts, max(2, round(size * scale))) for off, drift, starts, size in _EMBERS)
    for cache in (_CAPS, _ICON_ROWS, _INK):
        cache.clear()


# --- the words -------------------------------------------------------------------------------------------------------

def working_text(order: str) -> str:
    """What the pill says while an order is in hand. The order itself is never shown: only an app's name, when the
    whole order is to open one."""
    said = OPENING.fullmatch(" ".join(order.split()))
    if not said or re.search(r"\b(?:and|then)\b", said["app"], re.IGNORECASE):
        return WORKING
    words = said["app"].split()
    if words[0].lower() not in ("the", "my", "a", "an"):
        words = [word[:1].upper() + word[1:] for word in words]
    return f"Opening {' '.join(words)}…"


def done_text(reply: str) -> tuple[str, bool]:
    """(what the pill says when the order has ended, whether it is a finished task: the tick and "Done")."""
    first = (reply or "").strip().split("\n")[0].strip()
    if TROUBLE.search(first):
        return (first if len(first) <= 60 else first[:57].rstrip() + "…"), False
    short = first.rstrip(".!")
    if not short or short.lower() == "done" or "\n" in (reply or "").strip() or len(short) > 48:
        return DONE, True  # a long answer stays in the bar's own line
    return f"{DONE} · {short}", True


# --- the pictures: premultiplied BGRA, drawn in plain Python ------------------------------------------------------------

def _clamp(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def _over(under: tuple, colour: tuple, alpha: float) -> tuple:
    """colour at this alpha over a premultiplied (r, g, b, a) with each part from 0 to 1."""
    keep = 1 - alpha
    return (colour[0] / 255 * alpha + under[0] * keep, colour[1] / 255 * alpha + under[1] * keep,
            colour[2] / 255 * alpha + under[2] * keep, alpha + under[3] * keep)


def _bgra(pixel: tuple) -> bytes:
    return bytes((round(pixel[2] * 255), round(pixel[1] * 255), round(pixel[0] * 255), round(pixel[3] * 255)))


def _pill_pixel(d: float, up: float, style: str) -> tuple:
    """One pixel of the pill, `d` pixels outside its edge (negative: inside); `up` is 1 on its top edge, 0 on its sides."""
    ring, strength, light = RINGS[style]
    pixel = (0.0, 0.0, 0.0, 0.0)
    if light and d > 3.5:
        fall = _clamp(1 - (d - 4) / 18)
        pixel = _over(pixel, light, 0.35 * fall * fall * _clamp(d - 3.5))
    pixel = _over(pixel, ring, strength * _clamp(d - 2.0) * _clamp(4.5 - d))  # a hairline 4 px out
    pixel = _over(pixel, FILL[:3], FILL[3] * _clamp(0.5 - d))
    edge = _clamp(d + 1.5) * _clamp(0.5 - d)  # the glass's own inner edge, brighter on top
    return _over(pixel, (255, 255, 255), edge * (0.07 + 0.14 * up))


_CAPS: dict = {}


def _caps(style: str) -> list:
    """For each row of the pill's window: its left end, one pixel of its straight middle, and its right end."""
    if style not in _CAPS:
        rows = []
        for y in range(PILL_H):
            down = y - MARGIN + 0.5 - BAR_H / 2
            left = []
            for x in range(MARGIN + RADIUS):
                across = x - MARGIN + 0.5 - RADIUS
                far = math.hypot(across, down)
                left.append(_bgra(_pill_pixel((far - RADIUS) / SCALE, _clamp(-down / far) if far else 0.0, style)))
            middle = _bgra(_pill_pixel((abs(down) - RADIUS) / SCALE, 1.0 if down < 0 else 0.0, style))
            rows.append((b"".join(left), middle, b"".join(reversed(left))))
        _CAPS[style] = rows
    return _CAPS[style]


def _on_glass(colour: tuple, alpha: float) -> bytes:
    return _bgra(_over(_over((0.0, 0.0, 0.0, 0.0), FILL[:3], FILL[3]), colour, alpha))


def _segment(x: float, y: float, a: tuple, b: tuple) -> float:
    """How far (x, y) is from the line from a to b."""
    ax, ay, bx, by = *a, *b
    along = _clamp(((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2))
    return math.hypot(x - ax - along * (bx - ax), y - ay - along * (by - ay))


def _tick(x: float, y: float, step: int) -> tuple:
    return (255, 255, 255), _clamp(1.5 - min(_segment(x, y, (3.4, 9.6), (7.2, 13.4)), _segment(x, y, (7.2, 13.4), (14.8, 5.0))))


def _mic(x: float, y: float, step: int) -> tuple:
    body = abs(_segment(x, y, (9, 5.0), (9, 8.3)) - 2.0)
    cup = abs(math.hypot(x - 9, y - 8.3) - 4.7) if y >= 8.3 else min(math.hypot(x - 4.3, y - 8.3), math.hypot(x - 13.7, y - 8.3))
    near = min(body, cup, _segment(x, y, (9, 13.0), (9, 15.0)))
    return (156, 192, 255), _clamp(1.25 - near) * (0.65 + 0.35 * math.sin(math.pi * step / 12) ** 2)  # it pulses


def _spinner(x: float, y: float, step: int) -> tuple:
    ring = _clamp(1.5 - abs(math.hypot(x - 9, y - 9) - 6.5))
    turn = (math.atan2(x - 9, 9 - y) - step * math.tau / 24 + math.pi) % math.tau - math.pi  # 0 at the bright quarter's middle
    return ((255, 177, 153), ring) if abs(turn) < math.pi / 4 else ((255, 255, 255), ring * 0.25)


ICONS = {"tick": (_tick, 1), "mic": (_mic, 12), "spinner": (_spinner, 24)}  # how it is drawn, and its steps
_ICON_ROWS: dict = {}


def icon_rows(kind: str, step: int = 0) -> list:
    """The icon's rows on the pill's glass, ICON pixels square."""
    draw, steps = ICONS[kind]
    key = (kind, step % steps)
    if key not in _ICON_ROWS:
        _ICON_ROWS[key] = [b"".join(_on_glass(*draw((x + 0.5) / SCALE, (y + 0.5) / SCALE, key[1])) for x in range(ICON))
                           for y in range(ICON)]
    return _ICON_ROWS[key]


_INK: dict = {}


def _ink(grey: bool) -> list:
    """White text (or grey, for words still being said) on the glass, for each strength from 0 to 255."""
    if grey not in _INK:
        _INK[grey] = [_on_glass((255, 255, 255), (0.55 if grey else 1.0) * strength / 255) for strength in range(256)]
    return _INK[grey]


def pill_width(text_width: int, icon: bool) -> int:
    return max(MIN_W, min(MAX_W, text_width + (ICON + GAP if icon else 0) + 2 * PAD))


def pill_pixels(style: str, text: tuple, grey: bool = False, icon: list | None = None,
                width: float | None = None) -> tuple[int, bytes]:
    """(the pill's width, its window's picture: PILL_H rows of STRIDE pixels, the pill in the middle).

    `text` is (width, height, rows): for each row, one byte for each pixel, how strongly the letters cover it. `width`,
    while the pill grows or shrinks: words wider than that are cut at the pill's inner edge until it has grown.
    """
    text_width, text_height, cover = text
    beside = ICON + GAP if icon else 0
    text_width = min(text_width, MAX_W - 2 * PAD - beside)
    width = pill_width(text_width, bool(icon)) if width is None else max(MIN_W, min(MAX_W, round(width)))
    text_width = min(text_width, width - 2 * (RADIUS // 2) - beside)
    rows = [bytearray(left + middle * (width - 2 * RADIUS) + right) for left, middle, right in _caps(style)]
    x = MARGIN + (width - text_width - beside) // 2
    if icon:
        for number, row in enumerate(icon):
            rows[MARGIN + (BAR_H - ICON) // 2 + number][x * 4:(x + ICON) * 4] = row
        x += ICON + GAP
    ink, top = _ink(grey), MARGIN + (BAR_H - text_height) // 2
    for number in range(text_height):
        rows[top + number][x * 4:(x + text_width) * 4] = b"".join(ink[strength] for strength in cover[number][:text_width])
    before = (STRIDE - width - 2 * MARGIN) // 2
    left, right = bytes(4 * before), bytes(4 * (STRIDE - width - 2 * MARGIN - before))
    return width, b"".join(left + bytes(row) + right for row in rows)


def glow_pixels(centre: tuple, partway: tuple, scale: float = 1.0) -> bytes:
    """The pool of light, at this size: strongest under the pill, fading to nothing. Drawn at half size and doubled: it
    has no edges."""
    rows = []
    for y in range(0, GLOW_H, 2):
        half = []
        for x in range(0, GLOW_W // 2, 2):
            across, down = (x + 1 - GLOW_W / 2) / SCALE / scale, ((y + 1 - GLOW_UP) / SCALE - 62.5) / scale + 62.5
            far = math.hypot(across / 232, (down - 62.5) / 82)
            alpha = 0.95 - 0.5 * far / 0.543 if far < 0.543 else 0.45 * (1 - far) / 0.457 if far < 1 else 0.0
            soft = _clamp(0.5 - (math.hypot(across / 235, (down - 55) / 75) - 1) * 75 / 40)
            alpha *= soft * soft * (3 - 2 * soft) * 0.9
            mix = _clamp(far / 0.543) if far < 0.543 else _clamp((1 - far) / 0.457)
            colour = tuple(a + (b - a) * mix for a, b in zip(centre, partway))
            half.append(_bgra(_over((0.0, 0.0, 0.0, 0.0), colour, alpha)) * 2)
        row = b"".join(half) + b"".join(reversed(half))
        rows += [row, row]
    return b"".join(rows)


def ember_pixels(colour: tuple, size: int) -> bytes:
    """One ember: a small bright dot with its own light round it."""
    pixels = []
    for y in range(SPARK):
        for x in range(SPARK):
            far = math.hypot(x + 0.5 - SPARK / 2, y + 0.5 - SPARK / 2)
            light = 0.6 * math.exp(-(far / 5.5 / SCALE) ** 2) * _clamp((SPARK / 2 - 0.5 - far) / 3 / SCALE)
            pixels.append(_bgra(_over((0.0, 0.0, 0.0, 0.0), colour, max(_clamp(size / 2 + 0.5 - far), light))))
    return b"".join(pixels)


set_scale(1.0)


def _toward(value: float, goal: float, step: float) -> float:
    return min(goal, value + step) if value < goal else max(goal, value - step)


# --- the pill -----------------------------------------------------------------------------------------------------------

class Pill:
    """`screen` draws: None means Windows' own (below), and where there is none, every call here does nothing."""

    def __init__(self, after, after_cancel, screen=None, clock=time.monotonic):
        self.after, self.after_cancel, self.clock = after, after_cancel, clock
        self.screen = screen if screen is not None else _windows_screen()
        self.state = "hidden"
        self._mode, self._session, self._order = None, False, None
        self._working, self._done, self._done_until = WORKING, (DONE, True), 0.0
        self._words, self._live = "", False
        self._face, self._shown, self._blue, self._red, self._sparks = "done", 0.0, 0.0, 0.0, 0.0
        self._job, self._last, self._lit = None, 0.0, 0.0
        self._layers = None
        self._painted, self._width, self._sparked, self._text, self._raise = None, MIN_W, None, None, False
        self._resize = None  # (from, to, since) while the pill grows or shrinks
        self._covered = False  # the typing bar is open where the pill is: its glass is not drawn, its light still is
        self.raises = 0  # how many times the pill came over every app (the bar then puts itself over it)
        self._pools: dict = {}  # (colour, size) to its picture
        self._pool_shown = {}  # layer name to the size it shows

    @property
    def works(self) -> bool:
        return self.screen is not None

    # --- what the bar tells it ---------------------------------------------------------------------------------------

    def show(self, mode: str | None, session: bool = False) -> None:
        """The bar's own look at itself, a few times a second: "work", "listen" or None (kairu/bar/ember.py's mode_of),
        and whether Kairu is in a talk with you."""
        self._mode, self._session = mode, session
        if mode != "work":
            self._order = None  # an order that ended without a reply
        self._wake()

    def order(self, text: str) -> None:
        """An order is in hand."""
        self._order, self._working, self._done_until = text, working_text(text), 0.0
        self._wake()

    def step(self, number: int) -> None:
        """A take-control run's step number (ADR-054): "Step 3". Never the step's words, as an order is never shown."""
        if self._order is None:
            return
        self._working = f"Step {int(number)}"
        self._wake()

    def done(self, reply: str) -> None:
        """The order ended, with this reply."""
        if self._order is None:
            return
        self._order, self._done, self._done_until = None, done_text(reply), self.clock() + DONE_SECONDS
        self._words, self._live = "", False
        self._wake()

    def note(self, text: str) -> None:
        """A problem the bar reports while it is hidden: shown like an unfinished reply (no tick, no "Done"), for a few
        seconds. Anything that is not a problem is not shown."""
        shown, finished = done_text(text)
        if finished:
            return
        self._done, self._done_until = (shown, False), self.clock() + NOTE_SECONDS
        self._wake()

    def cover(self, covered: bool) -> None:
        """The typing bar is open (True) or closed (False) where the pill is."""
        self._covered = covered
        self._wake()

    def heard(self, text: str, live: bool = False) -> None:
        """Your words, as the bar's words line shows them: `live` while you are still speaking."""
        self._words, self._live = text, live
        if text:
            self._done_until = 0.0  # you are speaking again
        self._wake()

    def close(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        layers, self._layers, self.screen = self._layers, None, None
        for layer in (layers or {}).values():
            try:
                layer.close()
            except Exception:
                pass

    # --- what it shows -----------------------------------------------------------------------------------------------

    def _state(self, now: float) -> str:
        if now < self._done_until:
            return "done"
        mode = self._mode
        if mode == "work" and self._order is None:  # Kairu is speaking, not working on an order
            mode = "listen" if self._session else None
        return {"work": "working", "listen": "listening"}.get(mode, "hidden")

    def _wake(self) -> None:
        if self.screen is None or self._job is not None:
            return
        if self._layers is None and self._state(self.clock()) == "hidden":
            return  # nothing to show yet: no window is made until there is
        self._last = self.clock()
        self._frame()

    def _frame(self) -> None:
        self._job = None
        if self.screen is None:
            return
        try:
            again = self._step()
        except Exception as error:  # the pill only shows: without it, the bar carries on
            print(f"kairu bar: the pill is off ({type(error).__name__}: {error})", file=sys.stderr, flush=True)
            self.close()
            return
        if again:
            self._job = self.after(again, self._frame)

    def _step(self) -> int:
        """Draw one frame. The milliseconds to the next, or 0 when the pill is hidden and still."""
        now = self.clock()
        passed, self._last = min(0.1, max(0.0, now - self._last)), now
        state, was = self._state(now), self.state
        if state != was:
            self.state = state
            if was == "hidden":
                self._lit, self._painted = now, None  # shown afresh: at its own width at once
                if state == "listening":
                    self._words, self._live = "", False
        if state != "hidden":
            self._face = state
        glowing = state in ("listening", "working")
        goals = (float(state != "hidden"), float(state == "listening"), float(state == "working"), float(glowing))
        self._shown = _toward(self._shown, goals[0], passed / 0.35)
        self._blue = _toward(self._blue, goals[1], passed / 0.6)
        self._red = _toward(self._red, goals[2], passed / 0.6)
        self._sparks = _toward(self._sparks, goals[3], passed / 0.5)
        still = (self._shown, self._blue, self._red, self._sparks) == goals
        if state == "hidden" and still:
            for layer in (self._layers or {}).values():
                layer.hide()
            return 0
        self._draw(now)
        return FRAME_MS if glowing or not still or self._resize is not None else IDLE_MS

    def _make_layers(self) -> None:
        screen = self.screen
        layers = {"blue": screen.layer(GLOW_W, GLOW_H), "red": screen.layer(GLOW_W, GLOW_H)}
        for number in range(len(EMBERS)):
            layers[f"ember{number}"] = screen.layer(SPARK, SPARK)
        layers["pill"] = screen.layer(STRIDE, PILL_H)
        self._layers = layers

    def _paint(self, now: float) -> None:
        """The pill's own picture, drawn again only when what it says changes."""
        face = self._face
        if face == "listening":
            text, grey = (f"{self._words}…" if self._live else self._words) if self._words else LISTENING, self._live or not self._words
            icon = ("mic", int(now / 1.4 * 12) % 12)
        elif face == "working":
            text, grey, icon = self._working, False, ("spinner", int(now / 0.8 * 24) % 24)
        else:
            text, grey, icon = self._done[0], False, ("tick", 0) if self._done[1] else None
        if self._text is None or self._text[0] != text:
            self._text = (text, self._measured(text, bool(icon)))
        width = self._grown(pill_width(min(self._text[1][0], MAX_W - 2 * PAD - (ICON + GAP if icon else 0)), bool(icon)), now)
        key = (face, text, grey, icon, width)
        if key == self._painted:
            return
        self._width, pixels = pill_pixels(face, self._text[1], grey, icon_rows(*icon) if icon else None, width)
        self._layers["pill"].put(pixels)
        self._painted = key

    def _grown(self, goal: int, now: float) -> int:
        """The pill's width this frame, on its way to `goal`. Shown afresh, it starts at the goal."""
        if self._painted is None:
            self._resize = None
            return goal
        if self._resize is None or self._resize[1] != goal:
            if self._resize is None and self._width == goal:
                return goal
            self._resize = (self._width, goal, now)
        start, end, since = self._resize
        done = _clamp((now - since) / RESIZE_SECONDS)
        if done >= 1:
            self._resize = None
            return end
        return round(start + (end - start) * (1 - (1 - done) ** 3))

    def _pool(self, name: str, colour: str, breath: float) -> None:
        """The pool's picture for this breath: the nearest size drawn so far, and one more size drawn, if any is missing."""
        wanted = round(breath * (len(SWELL) - 1))
        missing = [size for size in range(len(SWELL)) if (colour, size) not in self._pools]
        if missing:
            size = min(missing, key=lambda each: abs(each - wanted))
            self._pools[colour, size] = glow_pixels(*POOLS[colour], SWELL[size])
        size = min((each for each in range(len(SWELL)) if (colour, each) in self._pools), key=lambda each: abs(each - wanted))
        if self._pool_shown.get(name) != size:
            self._layers[name].put(self._pools[colour, size])
            self._pool_shown[name] = size

    def _measured(self, text: str, icon: bool) -> tuple:
        room = MAX_W - 2 * PAD - (ICON + GAP if icon else 0)
        measured = self.screen.text(text)
        while measured[0] > room and len(text) > 8:  # too long for the pill: cut, with "…"
            text = text[:-5].rstrip(" …") + "…"
            measured = self.screen.text(text)
        return measured

    def _draw(self, now: float) -> None:
        if self._layers is None:
            self._make_layers()
            self._raise = True
        if self.state != "hidden" and self._shown == 0:
            self._raise = True  # shown again: over every app again
        layers = self._layers
        left, top, right, bottom = self.screen.work_area()
        centre, pill_top = (left + right) // 2, bottom - FROM_BOTTOM - BAR_H
        self._paint(now)
        eased = 1 - (1 - self._shown) ** 3
        layers["pill"].update(centre - (self._width + 2 * MARGIN) // 2 - (STRIDE - self._width - 2 * MARGIN) // 2,
                              pill_top - MARGIN + round((1 - eased) * SLIDE), STRIDE, PILL_H,
                              0 if self._covered else round(255 * self._shown))
        swing = abs(((now / BREATH_SECONDS) % 2) - 1)
        breath = 0.6 + 0.4 * swing * swing * (3 - 2 * swing)
        glow_top = pill_top - GLOW_UP
        for name, colour, strength in (("blue", "listening", self._blue), ("red", "working", self._red)):
            if strength > 0:
                self._pool(name, colour, swing * swing * (3 - 2 * swing))
            layers[name].update(centre - GLOW_W // 2, glow_top, GLOW_W, GLOW_H, round(255 * strength * breath))
        colour = EMBER.get(self._face)
        if colour and colour != self._sparked:
            for number, (_, _, _, size) in enumerate(EMBERS):
                layers[f"ember{number}"].put(ember_pixels(colour, size))
            self._sparked = colour
        for number, (off, drift, starts, _) in enumerate(EMBERS):
            age = now - self._lit - starts
            life = (age % EMBER_SECONDS) / EMBER_SECONDS if age > 0 else 0.0
            bright = (life / 0.18 if life < 0.18 else (1 - life) / 0.82) * self._sparks if self._sparked else 0.0
            layers[f"ember{number}"].update(centre + round(off + drift * life) - SPARK // 2,
                                            pill_top + LIFT - round(EMBER_RISE * (1 - (1 - life) ** 2)) - SPARK // 2,
                                            SPARK, SPARK, round(255 * _clamp(bright)))
        if self._raise:
            for layer in layers.values():  # in this order: the light, the embers, then the pill over them
                layer.raise_()
            self._raise = False
            self.raises += 1


# --- Windows: layered windows through ctypes ---------------------------------------------------------------------------

def _windows_screen():
    if sys.platform != "win32":
        return None
    try:
        return _Windows()
    except Exception as error:
        print(f"kairu bar: no pill ({type(error).__name__}: {error})", file=sys.stderr, flush=True)
        return None


class _Windows:
    """The pill's windows are made and moved "per-monitor DPI aware", in the screen's own pixels: Windows does not show a
    see-through window of a program that is not, at any display scale but 100% (found on the owner's laptop at 125%,
    15 Nov 2026). Only these calls are: the bar's own window is not changed."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        user32, gdi32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32", use_last_error=True)
        self.user32, self.gdi32 = user32, gdi32
        handle, c_int, dword = ctypes.c_void_p, ctypes.c_int, wintypes.DWORD
        self._context = getattr(user32, "SetThreadDpiAwarenessContext", None)  # Windows 10 1607 and later
        if self._context is not None:
            self._context.restype, self._context.argtypes = handle, (handle,)

        class Blend(ctypes.Structure):
            _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]

        class BitmapInfo(ctypes.Structure):  # BITMAPINFOHEADER, and room for the colours it does not use
            _fields_ = [("size", dword), ("width", ctypes.c_long), ("height", ctypes.c_long), ("planes", wintypes.WORD),
                        ("bits", wintypes.WORD), ("compression", dword), ("image_size", dword), ("x_ppm", ctypes.c_long),
                        ("y_ppm", ctypes.c_long), ("used", dword), ("important", dword), ("colours", dword * 3)]

        self.Blend, self.BitmapInfo = Blend, BitmapInfo
        point, size = ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE)
        for library, name, result, arguments in (
                (user32, "CreateWindowExW", handle, (dword, wintypes.LPCWSTR, wintypes.LPCWSTR, dword, c_int, c_int, c_int, c_int,
                                                     handle, handle, handle, handle)),
                (user32, "DestroyWindow", wintypes.BOOL, (handle,)),
                (user32, "ShowWindow", wintypes.BOOL, (handle, c_int)),
                (user32, "SetWindowPos", wintypes.BOOL, (handle, handle, c_int, c_int, c_int, c_int, wintypes.UINT)),
                (user32, "UpdateLayeredWindow", wintypes.BOOL, (handle, handle, point, size, handle, point, dword,
                                                                 ctypes.POINTER(Blend), dword)),
                (user32, "SystemParametersInfoW", wintypes.BOOL, (wintypes.UINT, wintypes.UINT, handle, wintypes.UINT)),
                (gdi32, "CreateCompatibleDC", handle, (handle,)),
                (gdi32, "CreateDIBSection", handle, (handle, ctypes.POINTER(BitmapInfo), wintypes.UINT, ctypes.POINTER(handle),
                                                     handle, dword)),
                (gdi32, "SelectObject", handle, (handle, handle)),
                (gdi32, "DeleteObject", wintypes.BOOL, (handle,)),
                (gdi32, "DeleteDC", wintypes.BOOL, (handle,)),
                (gdi32, "CreateFontW", handle, (c_int,) * 5 + (dword,) * 8 + (wintypes.LPCWSTR,)),
                (gdi32, "SetTextColor", dword, (handle, dword)),
                (gdi32, "SetBkMode", c_int, (handle, c_int)),
                (gdi32, "TextOutW", wintypes.BOOL, (handle, c_int, c_int, wintypes.LPCWSTR, c_int)),
                (gdi32, "GetTextExtentPoint32W", wintypes.BOOL, (handle, wintypes.LPCWSTR, c_int, size)),
                (gdi32, "GdiFlush", wintypes.BOOL, ())):
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments
        set_scale(self.display_scale())
        self.TEXT_H = TEXT_H
        self._dc, self._bitmap, self._bits, self._old = self.picture(MAX_W, self.TEXT_H)
        self._font = gdi32.CreateFontW(-FONT, 0, 0, 0, 500, 0, 0, 0, 1, 0, 0, 4, 0, "Segoe UI")  # DEFAULT_CHARSET, ANTIALIASED_QUALITY
        if not self._font:
            raise OSError("Windows made no font")
        gdi32.SelectObject(self._dc, self._font)
        gdi32.SetTextColor(self._dc, 0x00FFFFFF)
        gdi32.SetBkMode(self._dc, 1)  # TRANSPARENT

    def picture(self, width: int, height: int) -> tuple:
        """A picture Windows can show, with 4 bytes for each pixel, top row first: (its DC, the bitmap, its bytes, what
        the DC held before)."""
        ctypes, gdi32 = self.ctypes, self.gdi32
        dc = gdi32.CreateCompatibleDC(None)
        if not dc:
            raise OSError("Windows made no drawing surface")
        info = self.BitmapInfo(size=40, width=width, height=-height, planes=1, bits=32)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        if not bitmap or not bits.value:
            gdi32.DeleteDC(dc)
            raise OSError("Windows made no picture")
        return dc, bitmap, bits, gdi32.SelectObject(dc, bitmap)

    def aware(self):
        """Run what follows as a per-monitor DPI aware program, then go back to how the bar runs."""
        windows = self

        class Aware:
            def __enter__(self):
                self.before = None
                if windows._context is not None:
                    for context in (-4, -3):  # PER_MONITOR_AWARE_V2, then PER_MONITOR_AWARE
                        self.before = windows._context(windows.ctypes.c_void_p(context))
                        if self.before:
                            break

            def __exit__(self, *problem):
                if self.before:
                    windows._context(windows.ctypes.c_void_p(self.before))
        return Aware()

    def display_scale(self) -> float:
        """The display's scale: 1.0 at 100%, 1.25 at 125%."""
        system = getattr(self.user32, "GetDpiForSystem", None)
        if system is None or self._context is None:
            return 1.0
        system.restype, system.argtypes = self.ctypes.c_uint, ()
        with self.aware():
            dpi = system()
        return max(1.0, min(4.0, dpi / 96)) if dpi else 1.0

    def work_area(self) -> tuple:
        """The screen without the taskbar, in the screen's own pixels: (left, top, right, bottom)."""
        area = self.wintypes.RECT()
        with self.aware():
            found = self.user32.SystemParametersInfoW(0x0030, 0, self.ctypes.byref(area), 0)  # SPI_GETWORKAREA
        if not found:
            raise OSError("Windows did not say the screen's size")
        return area.left, area.top, area.right, area.bottom

    def text(self, text: str) -> tuple:
        """(width, height, rows): how strongly the letters cover each pixel, drawn white on black by Windows."""
        ctypes, gdi32 = self.ctypes, self.gdi32
        units, size = len(text.encode("utf-16-le")) // 2, self.wintypes.SIZE()
        if not gdi32.GetTextExtentPoint32W(self._dc, text, units, ctypes.byref(size)):
            raise OSError("Windows did not measure the words")
        width, height, row = min(size.cx, MAX_W), min(size.cy, self.TEXT_H), MAX_W * 4
        ctypes.memset(self._bits, 0, row * self.TEXT_H)
        gdi32.TextOutW(self._dc, 0, 0, text, units)
        gdi32.GdiFlush()
        drawn = ctypes.string_at(self._bits, row * self.TEXT_H)
        return width, height, [drawn[y * row + 1:y * row + width * 4:4] for y in range(height)]  # the green of each pixel

    def layer(self, width: int, height: int) -> "_Layer":
        return _Layer(self, width, height)


class _Layer:
    """One see-through window over every app. Clicks pass through it, it never takes the keyboard, and it has no
    taskbar button, title or Alt+Tab entry."""

    STYLE = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000  # LAYERED, TRANSPARENT, TOPMOST, TOOLWINDOW, NOACTIVATE

    def __init__(self, windows: _Windows, width: int, height: int):
        self.windows, self.width, self.height, self.shown = windows, width, height, False
        with windows.aware():  # a window made now stays DPI aware: Windows shows its picture pixel for pixel
            self.hwnd = windows.user32.CreateWindowExW(self.STYLE, "Static", None, 0x80000000, 0, 0, width, height,  # WS_POPUP
                                                       None, None, None, None)
        if not self.hwnd:
            raise OSError(f"Windows made no window (error {windows.ctypes.get_last_error()})")
        try:
            self.dc, self.bitmap, self.bits, self.old = windows.picture(width, height)
        except OSError:
            windows.user32.DestroyWindow(self.hwnd)
            raise

    def put(self, pixels: bytes) -> None:
        self.windows.ctypes.memmove(self.bits, pixels, min(len(pixels), self.width * self.height * 4))

    def update(self, x: int, y: int, width: int, height: int, alpha: int) -> None:
        """Show the picture here, at this strength from 0 to 255. (`width` and `height` are always the picture's own.)"""
        windows = self.windows
        ctypes, wintypes = windows.ctypes, windows.wintypes
        blend = windows.Blend(0, 0, max(0, min(255, alpha)), 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        with windows.aware():
            drawn = windows.user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(wintypes.POINT(x, y)),
                                                       ctypes.byref(wintypes.SIZE(self.width, self.height)), self.dc,
                                                       ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), 2)  # ULW_ALPHA
        if not drawn:
            raise OSError(f"Windows did not draw the pill (error {ctypes.get_last_error()})")

    def raise_(self) -> None:
        """Shown, over every other window, without taking the keyboard."""
        with self.windows.aware():
            self.windows.user32.SetWindowPos(self.hwnd, self.windows.ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
        self.shown = True  # HWND_TOPMOST; SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW

    def hide(self) -> None:
        if self.shown:
            with self.windows.aware():
                self.windows.user32.ShowWindow(self.hwnd, 0)  # SW_HIDE
            self.shown = False

    def close(self) -> None:
        user32, gdi32 = self.windows.user32, self.windows.gdi32
        gdi32.SelectObject(self.dc, self.old)
        gdi32.DeleteObject(self.bitmap)
        gdi32.DeleteDC(self.dc)
        with self.windows.aware():
            user32.DestroyWindow(self.hwnd)
