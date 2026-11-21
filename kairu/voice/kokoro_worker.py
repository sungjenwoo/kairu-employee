"""Kokoro's own program (VOICE.md "Kokoro"): voice.speak starts it for one answer, writes the parts to say, reads the sound.

It is a separate program, like piper.exe: Kairu never imports it, and it imports nothing of Kairu. Only it loads
kokoro-onnx (MIT), onnxruntime (MIT), phonemizer (GPL-3.0) and espeak-ng (GPL-3.0, through espeakng-loader), so those
stay out of every other Kairu program. It writes nothing to disk and reaches no network: the model and the voices are
files `kairu voice setup` put on this PC, SHA-256 checked, named on its command line.

    python -I kokoro_worker.py MODEL VOICES VOICE
    stdin:  one line of JSON, {"parts": [[text, speed], ...], "lang": "en-us" or "en-gb"}
    stdout: 4 bytes, the sample rate; then, for each part, frames of a 4-byte length and that many bytes of 16-bit mono
            sound; a frame of length 0 ends a part
    exit 0 when every part was said; 1 (with the reason on stderr) when it could not start or say one
"""

import json
import struct
import sys

LONGEST = 600  # characters in one part
FRAME = 24000  # bytes of sound in one frame (half a second at 24 kHz)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("kokoro: MODEL VOICES VOICE", file=sys.stderr)
        return 1
    model, voices, voice = argv
    try:
        request = json.loads(sys.stdin.readline())
        parts = [(str(text)[:LONGEST], float(speed)) for text, speed in request["parts"]]
        lang = request.get("lang", "en-us") if request.get("lang") in ("en-us", "en-gb") else "en-us"
    except (ValueError, KeyError, TypeError) as error:
        print(f"kokoro: the request is not readable ({type(error).__name__})", file=sys.stderr)
        return 1
    try:
        import numpy as np
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(model, voices)
    except Exception as error:  # not installed, or the files do not load: voice.speak falls back to Piper
        print(f"kokoro: could not start ({type(error).__name__}: {error})", file=sys.stderr)
        return 1
    out = sys.stdout.buffer
    started = False
    for text, speed in parts:
        if not text.strip():
            continue
        try:
            samples, rate = kokoro.create(text, voice=voice, speed=min(1.5, max(0.6, speed)), lang=lang)
        except Exception as error:
            print(f"kokoro: could not say a part ({type(error).__name__})", file=sys.stderr)
            return 1
        if not started:
            out.write(struct.pack("<I", int(rate)))
            started = True
        sound = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        for start in range(0, len(sound), FRAME):
            piece = sound[start:start + FRAME]
            out.write(struct.pack("<I", len(piece)) + piece)
        out.write(struct.pack("<I", 0))
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
