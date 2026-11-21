"""The microphone: 16 kHz, 16-bit, mono, a tenth of a second at a time, kept only in memory. Nothing is written to disk.

    Windows    winmm's waveIn functions through ctypes (no package), from the default microphone
    elsewhere  "not on this system": the voice is built for Windows
    StandIn    KAIRU_TEST_MIC names a folder: each cue put in it (a small text file, NNN_name.cue) names one of the tests'
               own recordings, which is "heard" in name order, in real time, with silence between them, so tests run with
               no microphone and no sound is copied anywhere. It writes the names it played to played.log. While the
               tests' pretend speaker (KAIRU_TEST_VOICE) says a line and its folder has echo.cue, that recording reaches
               this pretend mic too, as Kairu's own voice reaches a real microphone.

Before the microphone opens, Windows' privacy setting is read (it is only read, never changed). If it blocks the
microphone for desktop apps, Kairu says so plainly and does not try another way in.
"""

import os
import sys
import time
import wave
from pathlib import Path

RATE = 16000
CHUNK_SECONDS = 0.1
CHUNK_BYTES = int(RATE * CHUNK_SECONDS) * 2
TEST_MIC = "KAIRU_TEST_MIC"
PRIVACY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
SETTINGS = "Settings > Privacy & security > Microphone"


class MicProblem(Exception):
    """Why the microphone cannot be used, in words for the bar."""


def privacy_problem(read=None) -> str:
    """What Windows' microphone privacy setting blocks, or "" if it lets desktop apps use the microphone. Only reads."""
    read = read or _registry_value
    if read("HKLM", PRIVACY) == "Deny":
        return f"Windows has the microphone turned off for this PC ({SETTINGS} > Microphone access)."
    if read("HKCU", PRIVACY) == "Deny":
        return f"Windows' privacy setting blocks the microphone ({SETTINGS} > Microphone access)."
    if read("HKCU", PRIVACY + r"\NonPackaged") == "Deny":
        return f"Windows' privacy setting blocks the microphone for desktop apps ({SETTINGS} > Let desktop apps access your microphone)."
    return ""


def _registry_value(hive: str, key: str):
    import winreg
    root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
    try:
        with winreg.OpenKey(root, key) as opened:
            return winreg.QueryValueEx(opened, "Value")[0]
    except OSError:
        return None


def open_mic():
    """The microphone Kairu hears from. Raises MicProblem with a plain reason."""
    if os.environ.get(TEST_MIC):
        return StandIn(Path(os.environ[TEST_MIC]))
    if sys.platform != "win32":
        raise MicProblem("Voice is built for Windows; this system has no microphone Kairu can use.")
    problem = privacy_problem()
    if problem:
        raise MicProblem(problem)
    return WaveIn()


class StandIn:
    """A pretend microphone for the tests: cues dropped in a folder, each naming a recording heard once, in real time."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.played: set[str] = set()
        self._queue: list[bytes] = []
        self._next = time.monotonic()
        self.speaker = Path(os.environ["KAIRU_TEST_VOICE"]) if os.environ.get("KAIRU_TEST_VOICE") else None
        self._lines_spoken = 0

    def read(self) -> bytes:
        """The next tenth of a second, waiting for it as a real microphone would."""
        self._next += CHUNK_SECONDS
        time.sleep(max(0.0, self._next - time.monotonic()))
        if not self._queue:
            self._load_next()
        return self._queue.pop(0) if self._queue else b"\0" * CHUNK_BYTES

    def _load_next(self) -> None:
        for cue in sorted(self.folder.glob("*.cue")):
            if cue.name not in self.played:
                self.played.add(cue.name)
                return self._hear(cue.name, Path(cue.read_text(encoding="utf-8").strip()))
        echo = self.speaker / "echo.cue" if self.speaker else None
        if echo and echo.exists() and (self.speaker / "spoken.log").exists():
            spoken = len((self.speaker / "spoken.log").read_text(encoding="utf-8").splitlines())
            if spoken > self._lines_spoken:  # Kairu is saying a new line: the room hears it
                self._lines_spoken = spoken
                return self._hear(f"zz{spoken:03}_echo", Path(echo.read_text(encoding="utf-8").strip()))

    def _hear(self, name: str, recording: Path) -> None:
        with wave.open(str(recording)) as sound:
            if (sound.getframerate(), sound.getsampwidth(), sound.getnchannels()) != (RATE, 2, 1):
                raise MicProblem(f"{recording.name} is not 16 kHz 16-bit mono")
            audio = sound.readframes(sound.getnframes())
        with open(self.folder / "played.log", "a", encoding="utf-8") as log:
            log.write(name + "\n")
        audio += b"\0" * (-len(audio) % CHUNK_BYTES)
        self._queue = [audio[i:i + CHUNK_BYTES] for i in range(0, len(audio), CHUNK_BYTES)]

    def close(self) -> None:
        self._queue.clear()


class WaveIn:
    """The default microphone through winmm's waveIn, with a few small buffers that Windows fills in turn."""

    BUFFERS = 6

    def __init__(self):
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

        self.winmm = winmm = ctypes.WinDLL("winmm")
        self.kernel32 = kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        winmm.waveInGetNumDevs.restype = wintypes.UINT
        winmm.waveInOpen.argtypes = (ctypes.POINTER(ctypes.c_void_p), wintypes.UINT, ctypes.POINTER(Format), ctypes.c_size_t,
                                     ctypes.c_size_t, wintypes.DWORD)
        for name in ("waveInPrepareHeader", "waveInUnprepareHeader", "waveInAddBuffer"):
            getattr(winmm, name).argtypes = (ctypes.c_void_p, ctypes.POINTER(Header), wintypes.UINT)
        for name in ("waveInStart", "waveInStop", "waveInReset", "waveInClose"):
            getattr(winmm, name).argtypes = (ctypes.c_void_p,)
        kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        if winmm.waveInGetNumDevs() == 0:
            raise MicProblem("No microphone was found. Plug one in, or turn it on in Windows' sound settings.")
        self.header_size = ctypes.sizeof(Header)
        self.event = kernel32.CreateEventW(None, False, False, None)
        block = 2
        wanted = Format(1, 1, RATE, RATE * block, block, 16, 0)  # WAVE_FORMAT_PCM, mono, 16 kHz, 16-bit
        self.handle = ctypes.c_void_p()
        failed = winmm.waveInOpen(ctypes.byref(self.handle), 0xFFFFFFFF, ctypes.byref(wanted), self.event, 0, 0x00050000)  # WAVE_MAPPER, CALLBACK_EVENT
        if failed:
            kernel32.CloseHandle(self.event)
            reasons = {2: "no microphone is there", 4: "another program holds the microphone", 6: "its driver is missing",
                       32: "it cannot record at 16 kHz"}
            raise MicProblem(f"The microphone could not be opened: {reasons.get(failed, f'Windows error {failed}')}.")
        self.buffers = [ctypes.create_string_buffer(CHUNK_BYTES) for _ in range(self.BUFFERS)]
        self.headers = [Header(ctypes.cast(buffer, ctypes.c_void_p), CHUNK_BYTES, 0, 0, 0, 0, None, 0) for buffer in self.buffers]
        for header in self.headers:
            winmm.waveInPrepareHeader(self.handle, ctypes.byref(header), self.header_size)
            winmm.waveInAddBuffer(self.handle, ctypes.byref(header), self.header_size)
        self.turn = 0
        winmm.waveInStart(self.handle)

    def read(self) -> bytes:
        """The next tenth of a second from the microphone."""
        header = self.headers[self.turn]
        deadline = time.monotonic() + 2.0
        while not header.dwFlags & 0x1:  # WHDR_DONE
            if time.monotonic() > deadline:
                raise MicProblem("The microphone stopped sending sound.")
            self.kernel32.WaitForSingleObject(self.event, 200)
        sound = self.buffers[self.turn].raw[:header.dwBytesRecorded]
        header.dwFlags &= ~0x1
        self.winmm.waveInAddBuffer(self.handle, self.ctypes.byref(header), self.header_size)
        self.turn = (self.turn + 1) % self.BUFFERS
        return sound

    def close(self) -> None:
        if not self.handle:
            return
        self.winmm.waveInReset(self.handle)
        for header in self.headers:
            self.winmm.waveInUnprepareHeader(self.handle, self.ctypes.byref(header), self.header_size)
        self.winmm.waveInClose(self.handle)
        self.kernel32.CloseHandle(self.event)
        self.handle = None
        for buffer in self.buffers:  # what was heard does not linger in memory
            self.ctypes.memset(buffer, 0, CHUNK_BYTES)
