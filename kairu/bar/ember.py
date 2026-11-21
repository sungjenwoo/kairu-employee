"""Ember Glow in the Kairu bar (W2, ADR-036): the owner's design of 10 Nov, as far as Tkinter can draw it.

A thin strip under the box you type in: a soft line of light with small embers drifting up from it. Blue while Kairu listens
(the mic is starting, or you are talking to it), red while it works on an order, and gone when there is no work. Tkinter has
no see-through colours, so the glow is drawn as layers blended towards the bar's own background.

It only shows what the bar already knows (bar.busy, the voice's state); it decides nothing and does nothing.
"""

BLUE, RED = "#4fc3ff", "#ff4545"
HEIGHT = 14
FRAME_MS = 60
# the design's embers: (where along the bar, size, start, seconds to rise)
EMBERS = ((0.30, 3, 0.0, 3.0), (0.56, 3, 1.1, 3.0), (0.78, 3, 2.0, 3.0), (0.10, 2, 0.4, 3.4), (0.18, 3, 1.6, 2.8),
          (0.24, 2, 2.6, 3.2), (0.38, 3, 0.7, 3.6), (0.45, 2, 1.9, 2.9), (0.50, 3, 0.2, 3.3), (0.63, 2, 2.3, 3.0),
          (0.69, 3, 0.9, 3.5), (0.85, 2, 1.4, 2.7), (0.91, 3, 2.8, 3.1))


def blend(colour: str, background: str, amount: float) -> str:
    """colour over background, `amount` of the way (0: only the background, 1: only the colour)."""
    top = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    under = [int(background[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(b + (t - b) * max(0.0, min(1.0, amount))):02x}" for t, b in zip(top, under))


def mode_of(busy: bool, voice) -> str | None:
    """"work" (red), "listen" (blue) or None (gone), from what the bar knows."""
    if busy or (voice is not None and voice.working):
        return "work"
    if voice is not None and (voice.state == "starting" or (voice.state == "on" and voice.session)):
        return "listen"
    return None


class EmberStrip:
    def __init__(self, root, background: str, width: int):
        import tkinter as tk
        self.root, self.background, self.width = root, background, width
        self.canvas = tk.Canvas(root, height=HEIGHT, width=width, bg=background, highlightthickness=0, bd=0)
        self.mode: str | None = None
        self._time = 0.0
        self._job = None

    def show(self, mode: str | None, before=None) -> bool:
        """Show this mode (or hide the strip for None). True if the bar's size changed."""
        if mode == self.mode:
            return False
        was, self.mode = self.mode, mode
        if mode is None:
            self.canvas.pack_forget()
            if self._job is not None:
                self.root.after_cancel(self._job)
                self._job = None
            return True
        if was is None:
            self.canvas.pack(fill="x", padx=6, pady=(2, 0), before=before) if before is not None else self.canvas.pack(fill="x", padx=6)
            self._job = self.root.after(FRAME_MS, self._frame)
        self.draw()
        return was is None

    def _frame(self) -> None:
        self._job = None
        if self.mode is None:
            return
        self._time += FRAME_MS / 1000
        self.draw()
        self._job = self.root.after(FRAME_MS, self._frame)

    def draw(self) -> None:
        canvas, glow = self.canvas, BLUE if self.mode == "listen" else RED
        canvas.delete("all")
        width = max(self.width - 12, 40)
        left, right, y = width * 0.12, width * 0.88, HEIGHT - 4
        breathe = 0.75 + 0.25 * abs(((self._time / 3) % 2) - 1)  # the glow breathes, every 3 s
        for line, amount in ((9, 0.12), (6, 0.25), (3, 0.55), (1, 1.0)):
            canvas.create_line(left, y, right, y, width=line, capstyle="round", fill=blend(glow, self.background, amount * breathe))
        for where, size, start, seconds in EMBERS:
            life = ((self._time + start) % seconds) / seconds
            if life < 0.05:
                continue
            x, rise = width * where, (HEIGHT - 4) * life
            light = blend(glow, self.background, min(1.0, life * 4) * (1 - life) * 1.3)
            canvas.create_oval(x - size / 2, y - rise - size / 2, x + size / 2, y - rise + size / 2, fill=light, outline="")
