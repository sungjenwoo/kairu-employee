"""Why can't the pill be seen? Opens a small red box at the bottom middle of the screen in a few ways, reads back what the
screen shows there, and prints which ways work. Each box shows for about half a second; then the pill's own pictures, and the real pill for a few seconds. It only
shows: nothing else runs.

    .venv-guardian\\Scripts\\python tools\\pill_probe.py
"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kairu.bar import pill  # noqa: E402

W, H = 160, 80
RED = bytes((0, 0, 255, 255)) * (W * H)  # premultiplied BGRA: solid red
HALF = bytes((0, 0, 128, 128)) * (W * H)  # half see-through red

user32, gdi32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32"), ctypes.WinDLL("kernel32")


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", wintypes.UINT), ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT), ("private", wintypes.DWORD)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("proc", ctypes.c_void_p), ("cls_extra", ctypes.c_int), ("wnd_extra", ctypes.c_int),
                ("instance", ctypes.c_void_p), ("icon", ctypes.c_void_p), ("cursor", ctypes.c_void_p), ("brush", ctypes.c_void_p),
                ("menu", wintypes.LPCWSTR), ("name", wintypes.LPCWSTR)]


for library, name, result, arguments in (
        (user32, "PeekMessageW", wintypes.BOOL, (ctypes.POINTER(MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT, wintypes.UINT)),
        (user32, "TranslateMessage", wintypes.BOOL, (ctypes.POINTER(MSG),)),
        (user32, "DispatchMessageW", ctypes.c_ssize_t, (ctypes.POINTER(MSG),)),
        (user32, "GetDC", ctypes.c_void_p, (ctypes.c_void_p,)),
        (user32, "ReleaseDC", ctypes.c_int, (ctypes.c_void_p, ctypes.c_void_p)),
        (user32, "GetWindowLongW", ctypes.c_long, (ctypes.c_void_p, ctypes.c_int)),
        (user32, "RegisterClassW", wintypes.ATOM, (ctypes.POINTER(WNDCLASSW),)),
        (user32, "ShowWindow", wintypes.BOOL, (ctypes.c_void_p, ctypes.c_int)),
        (kernel32, "GetModuleHandleW", ctypes.c_void_p, (wintypes.LPCWSTR,)),
        (gdi32, "SelectObject", ctypes.c_void_p, (ctypes.c_void_p, ctypes.c_void_p)),
        (gdi32, "DeleteObject", wintypes.BOOL, (ctypes.c_void_p,)),
        (gdi32, "DeleteDC", wintypes.BOOL, (ctypes.c_void_p,)),
        (gdi32, "BitBlt", wintypes.BOOL, (ctypes.c_void_p,) + (ctypes.c_int,) * 4 + (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD))):
    function = getattr(library, name)
    function.restype, function.argtypes = result, arguments


def pump(seconds: float) -> None:
    message, ends = MSG(), time.monotonic() + seconds
    while time.monotonic() < ends:
        while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):  # PM_REMOVE
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        time.sleep(0.01)


def seen(screen, x: int, y: int) -> tuple:
    """The colour the screen shows at (x, y), layered windows included."""
    dc, bitmap, bits, old = screen.picture(1, 1)
    desktop = user32.GetDC(None)
    gdi32.BitBlt(dc, 0, 0, 1, 1, desktop, x, y, 0x00CC0020 | 0x40000000)  # SRCCOPY | CAPTUREBLT
    user32.ReleaseDC(None, desktop)
    blue, green, red = ctypes.string_at(bits, 3)
    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    return red, green, blue


def grab(screen, x: int, y: int, width: int, height: int) -> bytes:
    """What the screen shows in this rectangle (BGRA rows), layered windows included."""
    dc, bitmap, bits, old = screen.picture(width, height)
    desktop = user32.GetDC(None)
    gdi32.BitBlt(dc, 0, 0, width, height, desktop, x, y, 0x00CC0020 | 0x40000000)
    user32.ReleaseDC(None, desktop)
    pixels = ctypes.string_at(bits, width * height * 4)
    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    return pixels


def changed(before: bytes, after: bytes) -> str:
    """How many pixels changed clearly, how many became bright (text), and the most changed colour."""
    count = bright = 0
    most, most_colour = 0, None
    for i in range(0, len(after), 4):
        change = max(abs(after[i + k] - before[i + k]) for k in range(3))
        if change > 25:
            count += 1
            if min(after[i:i + 3]) > 170:
                bright += 1
        if change > most:
            most, most_colour = change, (after[i + 2], after[i + 1], after[i])
    return f"{count} pixels changed, {bright} bright, most changed {most_colour}"


def shown_picture(screen, label: str, width: int, height: int, pixels: bytes, show_w: int, show_h: int, x: int, y: int) -> None:
    """A picture of width by height, showing show_w by show_h of it from its top left."""
    before = grab(screen, x, y, show_w, show_h)
    try:
        layer = screen.layer(width, height)
        layer.put(pixels)
        layer.update(x, y, show_w, show_h, 255)
        layer.raise_()
        pump(0.5)
        after = grab(screen, x, y, show_w, show_h)
        layer.close()
        pump(0.1)
        result = changed(before, after)
    except Exception as error:
        result = f"{type(error).__name__}: {error}"
    print(f"          {label:44} {result}", flush=True)


def pill_pictures(screen) -> None:
    left, top, right, bottom = screen.work_area()
    centre = (left + right) // 2
    text = screen.text("Done · Chrome is open")
    width, pixels = pill.pill_pixels("listening", text, False, pill.icon_rows("tick"))
    full_w = width + 2 * pill.MARGIN
    x, y = centre - full_w // 2, bottom - 320
    shown_picture(screen, "8. pill picture, part of a wide one (as now)", pill.STRIDE, pill.PILL_H, pixels, full_w, pill.PILL_H, x, y)
    row = pill.STRIDE * 4
    exact = b"".join(pixels[r * row:r * row + full_w * 4] for r in range(pill.PILL_H))
    shown_picture(screen, "9. pill picture, exactly its own size", full_w, pill.PILL_H, exact, full_w, pill.PILL_H, x, y)
    glow = pill.glow_pixels(*pill.POOLS["listening"])
    gx = centre - pill.GLOW_W // 2
    shown_picture(screen, "10. glow, part of its picture (as now)", pill.GLOW_W, pill.GLOW_H, glow, pill.GLOW_W, 180, gx, bottom - 420)
    shown_picture(screen, "11. glow, all of its picture", pill.GLOW_W, pill.GLOW_H, glow, pill.GLOW_W, pill.GLOW_H, gx, bottom - 420)
    spark = pill.ember_pixels((255, 255, 255), 8)
    shown_picture(screen, "12. one big white ember", pill.SPARK, pill.SPARK, spark, pill.SPARK, pill.SPARK, centre, bottom - 420)


def real_pill(screen, with_tk: bool) -> None:
    """The real pill, listening then done, driven as the bar drives it; what the screen shows round it."""
    left, top, right, bottom = screen.work_area()
    centre = (left + right) // 2
    x, y, width, height = centre - 300, bottom - 300, 600, 300
    before = grab(screen, x, y, width, height)
    label = "14. the real pill, in a Tk program like the bar" if with_tk else "13. the real pill, on its own"
    results = []
    try:
        if with_tk:
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            the_pill = pill.Pill(root.after, root.after_cancel, screen)

            def look(name):
                results.append(f"{name}: {changed(before, grab(screen, x, y, width, height))}, state {the_pill.state}")
            the_pill.show("listen", True)
            root.after(1500, lambda: look("listening"))
            root.after(1600, lambda: (the_pill.show("work", True), the_pill.order("open chrome")))
            root.after(1700, lambda: (the_pill.done("Chrome is open."), the_pill.show(None)))
            root.after(2600, lambda: look("done"))
            root.after(2700, root.quit)
            root.mainloop()
            the_pill.close()
            root.destroy()
        else:
            jobs = []
            the_pill = pill.Pill(lambda ms, call: jobs.append((time.monotonic() + ms / 1000, call)) or len(jobs), lambda job: None, screen)

            def run(seconds):
                ends = time.monotonic() + seconds
                while time.monotonic() < ends:
                    due = [job for job in jobs if job[0] <= time.monotonic()]
                    for job in due:
                        jobs.remove(job)
                        job[1]()
                    pump(0.01)
            the_pill.show("listen", True)
            run(1.5)
            results.append(f"listening: {changed(before, grab(screen, x, y, width, height))}, state {the_pill.state}")
            the_pill.show("work", True)
            the_pill.order("open chrome")
            run(0.1)
            the_pill.done("Chrome is open.")
            the_pill.show(None)
            run(0.9)
            results.append(f"done: {changed(before, grab(screen, x, y, width, height))}, state {the_pill.state}")
            the_pill.close()
        pump(0.2)
    except Exception as error:
        results.append(f"{type(error).__name__}: {error}")
    print(f"          {label}", flush=True)
    for line in results:
        print(f"              {line}", flush=True)


def own_class() -> str:
    """A window class of our own, with Windows' plain window code, in place of "Static"."""
    name = "KairuPillProbe"
    entry = WNDCLASSW(proc=ctypes.cast(user32.DefWindowProcW, ctypes.c_void_p).value, instance=kernel32.GetModuleHandleW(None), name=name)
    user32.RegisterClassW(ctypes.byref(entry))
    return name


def trial(screen, label: str, pixels: bytes, x: int, y: int, class_name: str = "Static", show: str = "raise") -> None:
    before = seen(screen, x + W // 2, y + H // 2)
    note = ""
    try:
        if class_name != "Static":
            original = pill._Layer.__init__

            def made(self, windows, width, height):
                self.windows, self.width, self.height, self.shown = windows, width, height, False
                self.hwnd = windows.user32.CreateWindowExW(pill._Layer.STYLE, class_name, None, 0x80000000, 0, 0, width, height,
                                                           None, None, kernel32.GetModuleHandleW(None), None)
                if not self.hwnd:
                    raise OSError(f"no window (error {ctypes.get_last_error()})")
                self.dc, self.bitmap, self.bits, self.old = windows.picture(width, height)
            pill._Layer.__init__ = made
            try:
                layer = screen.layer(W, H)
            finally:
                pill._Layer.__init__ = original
        else:
            layer = screen.layer(W, H)
        layer.put(pixels)
        written = ctypes.string_at(layer.bits, 4)
        layer.update(x, y, W, H, 255)
        if show == "raise":
            layer.raise_()
        else:
            user32.ShowWindow(layer.hwnd, 4)  # SW_SHOWNOACTIVATE
        pump(0.5)
        after = seen(screen, x + W // 2, y + H // 2)
        style = user32.GetWindowLongW(layer.hwnd, -20) & 0xFFFFFFFF
        layer.close()
        pump(0.1)
        works = after[0] > before[0] + 40 and after[0] > after[2] + 40
        note = f"picture holds {tuple(written)}, extended style {style:#010x}"
    except Exception as error:
        after, works, note = None, False, f"{type(error).__name__}: {error}"
    print(f"{'SHOWS' if works else 'NOT SEEN':9} {label:44} screen before {before}, with the box {after}; {note}", flush=True)


def main() -> int:
    if sys.platform != "win32":
        print("Windows only.")
        return 1
    screen = pill._Windows()
    left, top, right, bottom = screen.work_area()
    x, y = (left + right) // 2 - W // 2, bottom - 200
    print(f"work area {screen.work_area()}; the box goes at ({x}, {y})", flush=True)
    trial(screen, "1. as the pill does it", RED, x, y)
    trial(screen, "2. half see-through, as the pill's glass", HALF, x, y)
    trial(screen, "3. shown without raising", RED, x, y, show="show")
    trial(screen, "4. our own window class, not Static", RED, x, y, class_name=own_class())
    trial(screen, "5. own class, half see-through", HALF, x, y, class_name="KairuPillProbe")
    pill_pictures(screen)
    real_pill(screen, with_tk=False)
    real_pill(screen, with_tk=True)
    aware = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if aware:
        aware.restype, aware.argtypes = ctypes.c_void_p, (ctypes.c_void_p,)
        aware(ctypes.c_void_p(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        screen2 = pill._Windows()
        left, top, right, bottom = screen2.work_area()
        x2, y2 = (left + right) // 2 - W // 2, bottom - 200
        print(f"after DPI awareness: work area {screen2.work_area()}; the box goes at ({x2}, {y2})", flush=True)
        trial(screen2, "6. as the pill, DPI aware", RED, x2, y2)
        trial(screen2, "7. own class, DPI aware", RED, x2, y2, class_name="KairuPillProbe")
    print("Finished.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
