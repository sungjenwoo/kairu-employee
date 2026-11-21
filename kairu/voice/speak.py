"""voice.speak, the Guardian action that answers aloud: one short line, in Piper's offline voice.

Piper (the MIT build of rhasspy/piper 2023.11.14-2, kairu/voice/models.py) runs as a separate program, piper.exe, started
by this action, so an emergency stop ends it mid-word with everything else. Kairu never imports or links it. It reads the
line as plain text (no markup), and its sound goes straight to Windows' own waveOut functions through ctypes, a little at a
time, as each sentence is ready, with a short pause between sentences. Nothing is written: not the text, not the sound.
The voice is voice.voice in Guardian's config.yaml, one of those pinned in kairu/voice/models.py, and how it is said is
voice.style (warm, the default; lively; calm; plain): a request never chooses either.

Until `kairu voice setup` has put Piper and the voice in place, Windows' own voice (SAPI's SpVoice, through COM) speaks
instead, as plain text (SPF_IS_NOT_XML), so words in it can never change the voice or its volume.

While it speaks, the bar keeps the mic paused, so Kairu never hears itself.

    KAIRU_TEST_VOICE names a folder: the tests' stand-in writes the line to spoken.log there and waits as if speaking.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from kairu.worker import FAILED

TEST_VOICE = "KAIRU_TEST_VOICE"
LONGEST = 300  # characters: one short line
SENTENCE_PAUSE = 0.25  # seconds of quiet between sentences
SPF_IS_NOT_XML = 0x10
CLSID_SPVOICE = "{96749377-3391-11D2-9EE3-00C04F797396}"
IID_ISPVOICE = "{6C44DF74-72B9-4992-A1EC-EF996E0422D4}"
SPEAK, RELEASE = 20, 2  # places in ISpVoice's table of functions


# Tenmin's expressive delivery (VOICE.md "How Kairu sounds", 14 Nov 2026): voice.style in Guardian's config.yaml.
# Piper's own three dials, for each part of a spoken answer:
#   length_scale  how slowly (1 is the voice's own pace; below 1 is quicker)
#   noise_scale   how much the voice's pitch and tone move (the voice's own is 0.667; more is livelier, less is flatter)
#   noise_w       how much the length of each sound varies (the voice's own is 0.8; more sounds less like a machine)
# The answer is said brighter and a little quicker; then a breath; then the one follow-up question, warmer and slower,
# as a teacher asks. "plain" is the voice exactly as Piper gives it, in one piece (as before 14 Nov).
Delivery = tuple[float, float, float]  # length_scale, noise_scale, noise_w
STYLES: dict[str, tuple[Delivery, Delivery, float]] = {  # style -> (the answer, the question, seconds of breath between)
    "warm": ((0.95, 0.75, 0.90), (1.08, 0.62, 0.85), 0.35),
    "lively": ((0.88, 0.80, 0.95), (0.98, 0.70, 0.90), 0.25),
    "calm": ((1.05, 0.62, 0.80), (1.15, 0.55, 0.80), 0.45),
}
PLAIN = "plain"
DEFAULT_STYLE = "warm"
LAST_QUESTION = re.compile(r"^(?P<answer>.*?[.!])\s+(?P<question>[^.!?]*\?)$", re.DOTALL)


def parts(line: str, style: str) -> list[tuple[str, Delivery | None]]:
    """The pieces of a line to say, each with its delivery; the breath goes between them. Plain: the line, as it is."""
    if style not in STYLES:
        return [(line, None)]
    answer, question, _ = STYLES[style]
    split = LAST_QUESTION.match(line)
    if not split:
        return [(line, answer if not line.endswith("?") else question)]
    return [(split["answer"].strip(), answer), (split["question"].strip(), question)]


KOKORO, PIPER = "kokoro", "piper"
KOKORO_FIRST_SOUND = 30  # seconds for Kokoro's program to start and make the first part (it loads its model each time)


def main(text: str, data_dir: str = "", voice_voice: str = "", voice_style: str = PLAIN, voice_tts: str = PIPER,
         voice_kokoro: str = ""):
    """voice_tts: kokoro (VOICE.md "Kokoro": the human-sounding voice, when set up) or piper. Kokoro that is not set up, or
    whose program does not start, falls back to Piper, so Kairu still answers aloud."""
    line = " ".join(text.split())[:LONGEST]
    if not line:
        return None
    style = voice_style if voice_style in STYLES else PLAIN
    if os.environ.get(TEST_VOICE):
        _stand_in(Path(os.environ[TEST_VOICE]), line, style)
        return None
    if sys.platform != "win32":
        print("voice.speak: Kairu's voice is built for Windows", file=sys.stderr, flush=True)
        return FAILED
    from kairu.voice import models
    if voice_tts == KOKORO:
        try:
            model, voices = models.kokoro_ready(data_dir)
        except models.NotSetUp as error:
            print(f"voice.speak: {error}; Piper speaks instead", file=sys.stderr, flush=True)
        else:
            said = say_with_kokoro(line, model, voices, voice_kokoro or models.DEFAULT_KOKORO, style)
            if said != NOT_STARTED:
                return said
            print("voice.speak: Kokoro's program did not start (`pip install -e .[kokoro]`?); Piper speaks instead",
                  file=sys.stderr, flush=True)
    try:
        piper = models.piper_ready(data_dir)
        onnx, config, speaker = models.voice_ready(data_dir, voice_voice or models.DEFAULT_VOICE)
    except (models.NotSetUp, KeyError) as error:
        print(f"voice.speak: {error}; Windows' own voice speaks instead", file=sys.stderr, flush=True)
        return speak(line)
    if style == PLAIN:
        return say_with_piper(line, piper, onnx, config, speaker)
    return say_with_piper(line, piper, onnx, config, speaker, style=style)


NOT_STARTED = "not started"  # say_with_kokoro: nothing was said, so Piper may say it instead


def kokoro_parts(line: str, style: str) -> list[tuple[str, float]]:
    """The parts to say with Kokoro and the speed of each: Kokoro's one dial is speed, so a style's length_scale becomes
    1 / length_scale (the answer a little quicker, the follow-up question a little slower). Plain: the line at speed 1."""
    return [(text, round(1 / delivery[0], 2) if delivery else 1.0) for text, delivery in parts(line, style)]


def kokoro_command(model: Path, voices: Path, voice: str) -> list[str]:
    """Kokoro's own program: this Python, isolated (-I), running kokoro_worker.py by its path, so it imports no Kairu."""
    return [sys.executable, "-I", str(Path(__file__).with_name("kokoro_worker.py")), str(model), str(voices), voice]


def kokoro_sound(line: str, model: Path, voices: Path, voice: str, style: str, wait: float = KOKORO_FIRST_SOUND):
    """Kokoro's sound for the line: the rate, then (part number, 16-bit mono sound) pieces as they come.
    Raises KokoroNotStarted if the program ends, or makes nothing, before the first sound."""
    import struct
    from kairu.voice import models
    lang = models.KOKORO_SPEAKERS.get(voice, ("", "en-us"))[1]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(kokoro_command(model, voices, voice), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=flags)
    try:
        process.stdin.write(json.dumps({"parts": kokoro_parts(line, style), "lang": lang}).encode("utf-8") + b"\n")
        process.stdin.close()
        head = process.stdout.read(4)
        if len(head) != 4:
            raise KokoroNotStarted()
        yield struct.unpack("<I", head)[0]
        number = 0
        while True:
            size = process.stdout.read(4)
            if len(size) != 4:
                break
            length = struct.unpack("<I", size)[0]
            if length == 0:
                number += 1
                continue
            yield number, process.stdout.read(length)
        process.wait(10)
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()


class KokoroNotStarted(Exception):
    pass


def say_with_kokoro(line: str, model: Path, voices: Path, voice: str, style: str = PLAIN):
    """Say the line in Kokoro's voice, the answer and the follow-up question each at its own speed, a breath between."""
    sound = kokoro_sound(line, model, voices, voice, style)
    try:
        rate = next(sound)
    except (KokoroNotStarted, StopIteration, OSError):
        return NOT_STARTED
    try:
        out = WaveOut(rate)
    except OSError as error:
        print(f"voice.speak: {error}", file=sys.stderr, flush=True)
        sound.close()
        return FAILED
    breath = STYLES[style][2] if style in STYLES else 0
    try:
        last = 0
        for number, piece in sound:
            if number != last and breath:
                out.play(bytes(int(rate * breath) * 2))
            last = number
            out.play(piece)
        out.wait()
    finally:
        sound.close()
        out.close()
    return None


def piper_command(piper: Path, onnx: Path, speaker: int | None, delivery: Delivery | None = None) -> list[str]:
    command = [str(piper), "--model", str(onnx), "--output-raw", "--sentence_silence", str(SENTENCE_PAUSE), "--quiet"]
    if delivery:
        length, noise, width = delivery
        command += ["--length_scale", f"{length:.2f}", "--noise_scale", f"{noise:.2f}", "--noise_w", f"{width:.2f}"]
    return command + (["--speaker", str(speaker)] if speaker is not None else [])


def sample_rate(config: Path) -> int:
    return int(json.loads(Path(config).read_text(encoding="utf-8"))["audio"]["sample_rate"])


def synthesize(line: str, piper: Path, onnx: Path, speaker: int | None, delivery: Delivery | None = None):
    """Piper's sound for the line, 16-bit mono, piece by piece as it comes (the first piece within about a second)."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(piper_command(piper, onnx, speaker, delivery), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=Path(piper).parent, creationflags=flags)
    try:
        process.stdin.write(line.encode("utf-8") + b"\n")
        process.stdin.close()
        while piece := process.stdout.read(8820):  # 0.2 s at 22050 Hz
            yield piece
        process.wait(10)
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()


def say_with_piper(line: str, piper: Path, onnx: Path, config: Path, speaker: int | None, style: str = PLAIN):
    """Say the line. With a style, the answer and the follow-up question each in their own delivery, one Piper at a time
    (the next starts when the last has finished making its sound, while that sound still plays), a breath between."""
    try:
        rate = sample_rate(config)
        out = WaveOut(rate)
    except OSError as error:
        print(f"voice.speak: {error}", file=sys.stderr, flush=True)
        return FAILED
    breath = STYLES[style][2] if style in STYLES else 0
    try:
        for number, (text, delivery) in enumerate(parts(line, style)):
            if number and breath:
                out.play(bytes(int(rate * breath) * 2))  # quiet: 16-bit zeros
            for piece in synthesize(text, piper, onnx, speaker, delivery):
                out.play(piece)
        out.wait()
    finally:
        out.close()
    return None


class WaveOut:
    """Windows' default speakers through winmm's waveOut: sound handed over piece by piece, played in order."""

    def __init__(self, rate: int):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes

        class Format(ctypes.Structure):
            _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                        ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                        ("cbSize", wintypes.WORD)]

        class Header(ctypes.Structure):
            _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD), ("dwBytesRecorded", wintypes.DWORD),
                        ("dwUser", ctypes.c_size_t), ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                        ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]

        self.Header = Header
        self.winmm = winmm = ctypes.WinDLL("winmm")
        winmm.waveOutOpen.argtypes = (ctypes.POINTER(ctypes.c_void_p), wintypes.UINT, ctypes.POINTER(Format), ctypes.c_size_t,
                                      ctypes.c_size_t, wintypes.DWORD)
        for name in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
            getattr(winmm, name).argtypes = (ctypes.c_void_p, ctypes.POINTER(Header), wintypes.UINT)
        for name in ("waveOutReset", "waveOutClose"):
            getattr(winmm, name).argtypes = (ctypes.c_void_p,)
        self.handle = ctypes.c_void_p()
        failed = winmm.waveOutOpen(ctypes.byref(self.handle), 0xFFFFFFFF, ctypes.byref(Format(1, 1, rate, rate * 2, 2, 16, 0)),
                                   0, 0, 0)  # WAVE_MAPPER, PCM mono 16-bit, CALLBACK_NULL
        if failed:
            self.handle = None
            raise OSError(f"the speakers could not be opened (Windows error {failed})")
        self.playing: list = []

    def play(self, sound: bytes) -> None:
        buffer = self.ctypes.create_string_buffer(sound, len(sound))
        header = self.Header(self.ctypes.cast(buffer, self.ctypes.c_void_p), len(sound), 0, 0, 0, 0, None, 0)
        size = self.ctypes.sizeof(self.Header)
        self.winmm.waveOutPrepareHeader(self.handle, self.ctypes.byref(header), size)
        self.winmm.waveOutWrite(self.handle, self.ctypes.byref(header), size)
        self.playing.append((buffer, header))  # kept until played
        self._tidy()

    def _tidy(self) -> None:
        size = self.ctypes.sizeof(self.Header)
        while self.playing and self.playing[0][1].dwFlags & 0x1:  # WHDR_DONE
            _, header = self.playing.pop(0)
            self.winmm.waveOutUnprepareHeader(self.handle, self.ctypes.byref(header), size)

    def wait(self, seconds: float = 60) -> None:
        deadline = time.monotonic() + seconds
        while self.playing and time.monotonic() < deadline:
            self._tidy()
            time.sleep(0.02)

    def close(self) -> None:
        if self.handle:
            self.winmm.waveOutReset(self.handle)
            self._tidy()
            self.playing.clear()
            self.winmm.waveOutClose(self.handle)
            self.handle = None


def _stand_in(folder: Path, line: str, style: str = PLAIN) -> None:
    """The tests' speaker. With echo.cue in its folder (naming one of the tests' recordings), the pretend mic hears that
    recording while this "speaks", as Kairu's own voice reaches a real microphone, so a test can show the paused mic never
    hears it (kairu/voice/mic.py). Nothing but the line is written (the style changes only how Piper would say it)."""
    with open(folder / "spoken.log", "a", encoding="utf-8") as log:
        log.write(line + "\n")
    seconds, echo = min(3.0, 0.04 * len(line)), folder / "echo.cue"
    if echo.exists():
        import wave
        with wave.open(echo.read_text(encoding="utf-8").strip()) as sound:
            seconds = sound.getnframes() / sound.getframerate()
    time.sleep(seconds)


def speak(line: str, volume: int | None = None):
    """Say it with SpVoice and wait until it is said. volume (0-100) only for checks; None leaves Windows' own."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    ole32 = ctypes.OleDLL("ole32")
    clsid, iid = GUID(), GUID()
    ole32.CLSIDFromString(CLSID_SPVOICE, ctypes.byref(clsid))
    ole32.CLSIDFromString(IID_ISPVOICE, ctypes.byref(iid))
    ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    voice = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(ctypes.byref(clsid), None, 0x17, ctypes.byref(iid), ctypes.byref(voice))  # CLSCTX_ALL
    except OSError as error:
        print(f"voice.speak: Windows' voice could not start ({error})", file=sys.stderr, flush=True)
        ole32.CoUninitialize()
        return FAILED
    table = ctypes.cast(ctypes.cast(voice, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    try:
        if volume is not None:
            set_volume = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.USHORT)(table[30])
            set_volume(voice, max(0, min(100, volume)))
        say = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)(table[SPEAK])
        result = say(voice, line, SPF_IS_NOT_XML, None)  # waits until it is said
        if result < 0:
            print(f"voice.speak: Windows' voice refused (HRESULT {result & 0xFFFFFFFF:#010x})", file=sys.stderr, flush=True)
            return FAILED
        return None
    finally:
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[RELEASE])(voice)
        ole32.CoUninitialize()
