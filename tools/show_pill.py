"""Show the Ember Glow pill on this screen for about 25 seconds, going through every state twice: listening (your words
appearing), working, done, hidden. It only shows: no order runs, Guardian is not asked, the mic is not opened.

    .venv-guardian\\Scripts\\python tools\\show_pill.py
    .venv-guardian\\Scripts\\python tools\\show_pill.py --check

Use it to see the pill without speaking to Kairu, or to check that Windows draws it. If Windows refuses, it says why.
With --check it also saves, in data\\pill-check, three pictures of the bottom middle of the screen (only the part round
the pill, 1000 by 380 pixels) while it shows, and a note of where Windows put its windows: for finding out why the pill
cannot be seen. Nothing is sent anywhere.
"""

import struct
import sys
import tkinter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kairu.bar.pill import Pill  # noqa: E402

STEPS = [  # (seconds from the start of a round, what happens)
    (0.0, lambda p: p.show("listen", True)),
    (1.2, lambda p: p.heard("open", True)),
    (1.6, lambda p: p.heard("open chro", True)),
    (2.0, lambda p: p.heard("open chrome", True)),
    (2.8, lambda p: p.heard("Open Chrome")),
    (3.6, lambda p: (p.show("work", True), p.order("open chrome"))),
    (6.4, lambda p: (p.done("Chrome is open."), p.show("listen", True))),
    (9.2, lambda p: p.show(None)),
]
ROUND = 11.0
SHOTS = ((2.5, "1-listening"), (5.0, "2-working"), (7.4, "3-done"))  # (seconds from the start, picture's name)
SHOT_W, SHOT_H = 1000, 380


def _windows():
    import ctypes
    from ctypes import wintypes
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    for library, name, result, arguments in (
            (user32, "GetDC", ctypes.c_void_p, (ctypes.c_void_p,)),
            (user32, "ReleaseDC", ctypes.c_int, (ctypes.c_void_p, ctypes.c_void_p)),
            (user32, "GetWindowRect", wintypes.BOOL, (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))),
            (user32, "IsWindowVisible", wintypes.BOOL, (ctypes.c_void_p,)),
            (user32, "GetSystemMetrics", ctypes.c_int, (ctypes.c_int,)),
            (gdi32, "CreateCompatibleDC", ctypes.c_void_p, (ctypes.c_void_p,)),
            (gdi32, "CreateCompatibleBitmap", ctypes.c_void_p, (ctypes.c_void_p, ctypes.c_int, ctypes.c_int)),
            (gdi32, "SelectObject", ctypes.c_void_p, (ctypes.c_void_p, ctypes.c_void_p)),
            (gdi32, "BitBlt", wintypes.BOOL, (ctypes.c_void_p,) + (ctypes.c_int,) * 4 + (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD)),
            (gdi32, "GetDIBits", ctypes.c_int, (ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                                 ctypes.c_void_p, wintypes.UINT)),
            (gdi32, "DeleteObject", wintypes.BOOL, (ctypes.c_void_p,)),
            (gdi32, "DeleteDC", wintypes.BOOL, (ctypes.c_void_p,))):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
    return ctypes, wintypes, user32, gdi32


def _shoot(pill, folder: Path, name: str, notes: list) -> None:
    """A picture of the bottom middle of the screen, and where the pill's windows are."""
    ctypes, wintypes, user32, gdi32 = _windows()
    left, top, right, bottom = pill.screen.work_area()
    x, y = max(0, (left + right) // 2 - SHOT_W // 2), max(0, bottom - SHOT_H)
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, SHOT_W, SHOT_H)
    old = gdi32.SelectObject(memory, bitmap)
    copied = gdi32.BitBlt(memory, 0, 0, SHOT_W, SHOT_H, screen, x, y, 0x00CC0020 | 0x40000000)  # SRCCOPY | CAPTUREBLT
    header = struct.pack("<IiiHHIIiiII", 40, SHOT_W, -SHOT_H, 1, 32, 0, SHOT_W * SHOT_H * 4, 2835, 2835, 0, 0)
    info = ctypes.create_string_buffer(header + bytes(12))
    pixels = ctypes.create_string_buffer(SHOT_W * SHOT_H * 4)
    gdi32.SelectObject(memory, old)
    rows = gdi32.GetDIBits(memory, bitmap, 0, SHOT_H, pixels, info, 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)
    (folder / f"{name}.bmp").write_bytes(b"BM" + struct.pack("<IHHI", 54 + len(pixels.raw), 0, 0, 54) + header + pixels.raw)
    notes.append(f"{name}: state {pill.state}, picture from ({x}, {y}), copied {bool(copied)}, rows {rows}")
    for layer_name, layer in (pill._layers or {}).items():
        rect = wintypes.RECT()
        user32.GetWindowRect(layer.hwnd, ctypes.byref(rect))
        notes.append(f"    {layer_name:8} at ({rect.left}, {rect.top}) to ({rect.right}, {rect.bottom}), visible {bool(user32.IsWindowVisible(layer.hwnd))}")


def main() -> int:
    check = "--check" in sys.argv[1:]
    root = tkinter.Tk()
    root.withdraw()
    pill = Pill(root.after, root.after_cancel)
    if not pill.works:
        print("No pill: Windows did not let it be drawn (the line above says why), or this is not Windows.")
        return 1
    print("Look at the bottom centre of the screen. The pill shows for about 25 seconds.")
    for number in range(2):
        for at, step in STEPS:
            root.after(int((number * ROUND + at) * 1000), lambda step=step: step(pill) if pill.works else None)
    folder, notes = Path(__file__).resolve().parent.parent / "data" / "pill-check", []
    if check:
        folder.mkdir(parents=True, exist_ok=True)
        ctypes, wintypes, user32, gdi32 = _windows()
        notes.append(f"screen {user32.GetSystemMetrics(0)} x {user32.GetSystemMetrics(1)}, all screens {user32.GetSystemMetrics(78)} x "
                     f"{user32.GetSystemMetrics(79)} from ({user32.GetSystemMetrics(76)}, {user32.GetSystemMetrics(77)}), "
                     f"monitors {user32.GetSystemMetrics(80)}, work area {pill.screen.work_area()}, tk scaling {root.tk.call('tk', 'scaling')}")

        def shoot(name):
            try:
                _shoot(pill, folder, name, notes)
            except Exception as error:
                notes.append(f"{name}: no picture ({type(error).__name__}: {error})")
        for at, name in SHOTS:
            root.after(int(at * 1000), lambda name=name: shoot(name))
    root.after(int(2 * ROUND * 1000) + 800, root.quit)
    root.mainloop()
    worked = pill.works
    pill.close()
    root.destroy()
    if check:
        (folder / "notes.txt").write_text("\n".join(notes + [f"pill worked to the end: {worked}"]) + "\n", encoding="utf-8")
        print(f"Saved in {folder}.")
    print("Done." if worked else "The pill went off while showing; the line above says why.")
    return 0 if worked else 1


if __name__ == "__main__":
    sys.exit(main())
