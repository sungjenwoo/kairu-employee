"""Does Gemini hearing work on this PC? An owner command, run in PowerShell; it opens no microphone and runs no order.

    py -3.12 tools\\gemini_hearing_test.py

It sends two of Kairu's own recorded test sentences (tests_kairu/voice/*.wav, a voice saying "Kairu, stop" and
"Kairu, search the weather") to Gemini with your key from `kairu provider add gemini`, and prints what Gemini wrote,
how long it took, or exactly why it failed. Nothing is written.
"""

import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kairu import config  # noqa: E402
from kairu.voice import gemini  # noqa: E402


def main() -> int:
    cfg = config.load()
    print(f"voice.hearing in config.yaml: {cfg.voice_hearing}" + ("" if cfg.voice_hearing == "gemini" else
          "   <- put  hearing: gemini  under voice: and restart Guardian"))
    hearing = gemini.GeminiHearing(cfg.data_dir, cfg.voice_gemini_model)
    try:
        hearing.key()
    except Exception as problem:  # noqa: BLE001  an owner's check: say what it is
        print(f"No key: {problem}")
        return 1
    print("Gemini key: found (not shown)")
    worked = 0
    for name in ("kairu_stop", "kairu_search_weather"):
        with wave.open(str(ROOT / "tests_kairu" / "voice" / f"{name}.wav")) as file:
            sound = file.readframes(file.getnframes())
        started = time.monotonic()
        try:
            heard = hearing.gemini(sound)
        except Exception as problem:  # noqa: BLE001
            print(f"- {name}: FAILED after {time.monotonic() - started:.1f} s: {problem}")
            continue
        worked += 1
        print(f"- {name}: Gemini heard {heard.text!r} in {time.monotonic() - started:.1f} s (model {hearing.models[0]})")
    print("Gemini hearing works." if worked == 2 else "Gemini hearing does NOT work yet: send this to Claude.")
    return 0 if worked == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
