"""The hearing test: which offline speech engine hears you best. You read 10 short orders aloud; each engine hears them.

    .venv-guardian\\Scripts\\python tools\\hearing_test.py --setup    once: the engines and their models (about 420 MiB)
    .venv-hearing\\Scripts\\python tools\\hearing_test.py              read the 10 orders aloud, then see what each engine heard
    .venv-hearing\\Scripts\\python tools\\hearing_test.py --piper      the same orders said by Piper's four Indian English voices

The engines, all offline and free; your voice never leaves the PC:

    vosk-small-en-us    Vosk, vosk-model-small-en-us-0.15: the fallback (voice.engine: vosk; Apache-2.0)
    vosk-small-en-in    Vosk, vosk-model-small-en-in-0.4: Indian English (Apache-2.0)
    vosk-en-us-lgraph   Vosk, vosk-model-en-us-0.22-lgraph: the smallest of the big English models (Apache-2.0)
    whisper-tiny.en     Whisper tiny.en through faster-whisper 1.2.1, int8 on the CPU (MIT; the weights MIT), told only how
                        "Kairu", "Notepad" and "Chrome" are spelled (as before 10 Nov 2026)
    whisper-base.en     Whisper base.en, the same way
    whisper-base.en+hint  what Kairu now does (voice.engine: whisper-base.en, the default since 10 Nov 2026): base.en with
                        Kairu's order words as its hint, through the listener's own hearing (kairu/voice/whisper.py: the
                        speech gate, Whisper, the words)
    whisper-tiny.en+hint  tiny.en the same way (voice.engine: whisper-tiny.en): smaller, and it heard you less well

To hear your voice with the hint, compared with tiny.en without it:

    .venv-hearing\\Scripts\\python tools\\hearing_test.py --engines whisper-tiny.en,whisper-tiny.en+hint,whisper-base.en+hint

For each order the test shows what each engine heard, whether it heard "Kairu", the order Kairu would act on, and a word
error score (the share of the order's words it got wrong). For each engine: how long after you stop speaking its words are
ready, and its memory, against the voice's limits (under 200 MB at rest, 400 MB while Kairu speaks).

Your recordings stay in this program's memory and go to each engine through a pipe: no sound is ever written to disk, and
they are gone when it ends. The engines run one at a time, each in its own process, so each one's memory is its own. The
models are downloaded only by --setup, from alphacephei.com and huggingface.co, each file SHA-256 checked. .venv-hearing
keeps the test apart from Guardian's .venv-guardian (which now has faster-whisper too, as Kairu's default engine).

The bigger Vosk models (vosk-model-en-us-0.22, 1.8 GiB; vosk-model-en-in-0.5, 926 MiB) are not tried: alphacephei.com says
the big models need several GB of memory, far over the voice's limits.
"""

import argparse
import array
import difflib
import json
import os
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kairu.voice import models  # noqa: E402
from kairu.voice import words as w  # noqa: E402
from kairu.voice.whisper import KAIRU_END, KAIRU_HEARD, PROMPT, split_wake, tokens  # noqa: E402,F401 (Kairu's own)

RATE = 16000
CHUNK = 3200  # bytes: 0.1 s of 16-bit mono at 16 kHz
VENV = ROOT / ".venv-hearing"
FASTER_WHISPER = "faster-whisper==1.2.1"
AT_REST_MIB, SPEAKING_MIB, PIPER_MIB = 190, 381, 192  # 200 MB and 400 MB; Piper's measured share (VOICE.md)
ENDPOINT_SECONDS = 0.5  # every engine waits for this pause before an utterance counts as ended

ORDERS = [  # (what you say, what Kairu should do: "wake", "stop", "thanks" or the order's words)
    ("Kairu", "wake"),
    ("Kairu, set the volume to 30", "set the volume to 30"),
    ("Kairu, open Chrome", "open chrome"),
    ("Kairu, close Notepad", "close notepad"),
    ("Kairu, what's open?", "what's open"),
    ("Kairu, search the weather today", "search the weather today"),
    ("Kairu, set the brightness to 50", "set the brightness to 50"),
    ("Kairu, open Notepad", "open notepad"),
    ("Kairu, thank you", "thanks"),
    ("Kairu, stop", "stop"),
]
PIPER_SPEAKERS = {"SVBI": 2, "TNI": 9, "ASI": 10, "RRBI": 19}  # L2-ARCTIC's Indian English speakers in en_US-l2arctic-medium


# --- the engines and their models ----------------------------------------------------------------------------------

LGRAPH = models.Model("en-us-lgraph", "vosk-model-en-us-0.22-lgraph",
                      "d9838b4aaa82a75c4a17f5aca300eaca129aaab2a7cbf951bafbb500eb9c4334", 130557655, "US English")  # md5 as listed


Whisper = models.Whisper  # the models are pinned in kairu/voice/models.py, where `kairu voice setup` finds them too
WHISPERS = models.WHISPERS
ENGINES = {  # name -> (kind, model)
    "vosk-small-en-us": ("vosk", models.MODELS["small-en-us"]),
    "vosk-small-en-in": ("vosk", models.MODELS["small-en-in"]),
    "vosk-en-us-lgraph": ("vosk", LGRAPH),
    "whisper-tiny.en": ("whisper", WHISPERS["tiny.en"]),
    "whisper-base.en": ("whisper", WHISPERS["base.en"]),
    "whisper-tiny.en+hint": ("whisper+hint", WHISPERS["tiny.en"]),
    "whisper-base.en+hint": ("whisper+hint", WHISPERS["base.en"]),
}


def vosk_place(data_dir, model: models.Model) -> Path:
    return Path(data_dir) / models.FOLDER / model.name


def vosk_ready(data_dir, model: models.Model) -> bool:
    try:
        mark = json.loads((vosk_place(data_dir, model) / models.MARK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(mark, dict) and mark.get("sha256") == model.sha256


def whisper_ready(data_dir, whisper: Whisper) -> bool:
    try:
        mark = json.loads((whisper.folder(data_dir) / "kairu-whisper.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return mark == {"repo": whisper.repo, "commit": whisper.commit, "sha256": [sha for _, sha, _ in whisper.files]}


def ready(data_dir, name: str) -> bool:
    kind, model = ENGINES[name]
    return vosk_ready(data_dir, model) if kind == "vosk" else whisper_ready(data_dir, model)


def set_up(data_dir, say=print) -> int:
    """.venv-hearing with Kairu, Vosk and faster-whisper, and every engine's model, each file SHA-256 checked."""
    python = venv_python()
    if not python.exists():
        say(f"Making {VENV.name} (only for this test; Guardian's .venv-guardian is not touched) ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    say(f"Installing Kairu, Vosk and {FASTER_WHISPER} into {VENV.name} ...")
    done = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-e", str(ROOT), FASTER_WHISPER])
    if done.returncode:
        say("FAILED: pip could not install them (see above).")
        return 1
    for name, (kind, model) in ENGINES.items():
        if ready(data_dir, name):
            say(f"  {name}: ready")
            continue
        try:
            set_up_vosk(data_dir, model, say) if kind == "vosk" else set_up_whisper(data_dir, model, say)
        except models.SetupError as error:
            say(f"FAILED: {name}: {error}")
            return 1
        say(f"  {name}: ready, SHA-256 checked")
    say(f"\nReady. Now: {VENV.name}\\Scripts\\python tools\\hearing_test.py")
    return 0


def set_up_vosk(data_dir, model: models.Model, say) -> None:
    target = vosk_place(data_dir, model)
    target.parent.mkdir(parents=True, exist_ok=True)
    download = target.parent / f"{model.name}.zip.part"
    try:
        say(f"Downloading {model.name} ({model.mib:.1f} MiB) from {models.HOST} ...")
        models._fetch(model.url, model.sha256, model.size, model.name, download, None, say, (models.HOST,))
        models._unpack(model.name, download, target)
        (target / models.MARK).write_text(json.dumps({"name": model.name, "sha256": model.sha256}), encoding="utf-8")
    finally:
        download.unlink(missing_ok=True)


def set_up_whisper(data_dir, whisper: Whisper, say) -> None:
    place = whisper.folder(data_dir)
    place.mkdir(parents=True, exist_ok=True)
    say(f"Downloading Whisper {whisper.key} ({sum(size for *_, size in whisper.files) / 2**20:.0f} MiB) from huggingface.co/{whisper.repo} ...")
    for name, sha256, size in whisper.files:
        part = place / f"{name}.part"
        try:
            models._fetch(f"https://huggingface.co/{whisper.repo}/resolve/{whisper.commit}/{name}", sha256, size, name, part,
                          None, say, models.VOICE_HOSTS)
            os.replace(part, place / name)
        finally:
            part.unlink(missing_ok=True)
    mark = {"repo": whisper.repo, "commit": whisper.commit, "sha256": [sha for _, sha, _ in whisper.files]}
    (place / "kairu-whisper.json").write_text(json.dumps(mark), encoding="utf-8")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


# --- what was heard, scored ------------------------------------------------------------------------------------------

# PROMPT (how the names are spelled; never a whole order, which Whisper would then "hear"), tokens() and split_wake() are
# the listener's own, from kairu/voice/whisper.py.


def outcome(wake: bool, order_words: list[str]) -> str:
    """What Kairu would do with it: "wake", "stop", "thanks", the order, or "" (dropped: no "Kairu")."""
    if not wake:
        return ""
    order = w.clean(order_words)
    if not order:
        return "wake"
    if w.is_stop(order):
        return "stop"
    if w.is_thanks(order):
        return "thanks"
    return order


def word_errors(expected: str, heard: str) -> tuple[int, int]:
    """(words wrong, words expected): substitutions, insertions and deletions, on the cleaned words."""
    ref, hyp = expected.split(), heard.split()
    row = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        last, row[0] = row[0], i
        for j, other in enumerate(hyp, 1):
            last, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, last + (word != other))
    return row[-1], len(ref)


def expected_outcome(order: str) -> str:
    return order if order in ("wake", "stop", "thanks") else w.clean(order.split())


# --- one engine, in its own process ------------------------------------------------------------------------------------

def engine_main(name: str, data_dir: str) -> int:
    """Load one engine, say "loaded", then hear each clip from stdin (4-byte length, then 16-bit 16 kHz mono) and answer
    with one JSON line each. Then "measure": the parent reads this process's memory as Kairu would use the engine. Only then
    the raw words, where the engine needs more for them (Vosk: a third recognizer). Nothing is written but those lines."""
    os.environ["HF_HUB_OFFLINE"] = "1"  # faster-whisper never reaches the network: the model is a folder here
    kind, model = ENGINES[name]
    began = time.perf_counter()
    if kind == "vosk":
        hear, raw = vosk_engine(vosk_place(data_dir, model))
    elif kind == "whisper+hint":
        hear, raw = whisper_hint_engine(model.folder(data_dir))
    else:
        hear, raw = whisper_engine(model.folder(data_dir))
    send({"loaded": round(time.perf_counter() - began, 2)})
    stdin, clips = sys.stdin.buffer, []
    while size := struct.unpack("<I", stdin.read(4))[0]:
        clips.append(stdin.read(size))
        send(hear(clips[-1]))
    send({"measure": True})
    stdin.read(1)
    for clip in clips:
        send({"raw": raw(clip)} if raw else {})
    clips.clear()
    send({"done": True})
    return 0


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def vosk_engine(place: Path):
    """What Kairu would do: the listener's own hearing (kairu/voice/hearing.py), its two recognizers, the wake grammar,
    the order. What the model heard: a plain recognizer of the whole vocabulary, beside it."""
    from kairu.voice.hearing import Hearing
    from kairu.voice.listen import load_vosk
    vosk = load_vosk()
    vosk.SetLogLevel(-1)
    model = vosk.Model(str(place))
    tail = bytes(int(RATE * 1.2) * 2)  # the pause after you stop, which ends the utterance

    def hear(sound: bytes) -> dict:
        hearing, events = Hearing(model), []  # a new one each time: no session carried over from the order before
        began = time.perf_counter()
        for i in range(0, len(sound), CHUNK):
            events += hearing.feed(sound[i:i + CHUNK])
        spoken = time.perf_counter()
        for i in range(0, len(tail), CHUNK):
            events += hearing.feed(tail[i:i + CHUNK])
        ended = time.perf_counter()
        return {"raw": "", "events": vosk_outcome(events), "compute": round(ended - began, 3),
                "after_end": round(ended - spoken, 3)}

    plain = []

    def words(sound: bytes) -> str:
        if not plain:
            plain.append(vosk.KaldiRecognizer(model, RATE))
        heard = []
        for i in range(0, len(sound + tail), CHUNK):
            if plain[0].AcceptWaveform((sound + tail)[i:i + CHUNK]):
                heard.append(json.loads(plain[0].Result()).get("text", ""))
        heard.append(json.loads(plain[0].FinalResult()).get("text", ""))
        return " ".join(text for text in heard if text)

    return hear, words


def vosk_outcome(events: list[dict]) -> str:
    for event in events:
        if event.get("stop"):
            return "stop"
        if event.get("thanks"):
            return "thanks"
        if "order" in event:
            return event["order"]
        if "unclear" in event:
            return f"(asks: {event['unclear']})"
        if event.get("ignored"):
            return "(ignored)"
    return "wake" if any(event.get("wake") for event in events) else ""


def whisper_engine(place: Path):
    import types
    import numpy
    sys.modules.setdefault("av", types.ModuleType("av"))  # PyAV only decodes sound files; Kairu hands sound over from memory
    from faster_whisper import WhisperModel
    model = WhisperModel(str(place), device="cpu", compute_type="int8", cpu_threads=min(4, os.cpu_count() or 1))

    def transcribe(samples) -> str:
        segments, _ = model.transcribe(samples, language="en", beam_size=5, initial_prompt=PROMPT, vad_filter=False,
                                       condition_on_previous_text=False, without_timestamps=True)
        return " ".join(segment.text.strip() for segment in segments)

    def hear(sound: bytes) -> dict:
        samples = numpy.frombuffer(sound, numpy.int16).astype(numpy.float32) / 32768
        began = time.perf_counter()
        text = transcribe(samples)
        ended = time.perf_counter()
        part = time.perf_counter()
        transcribe(samples[:RATE * 3 // 2])  # what one "live words" update of the first 1.5 s costs
        wake, order_words = split_wake(text)
        return {"raw": text, "events": outcome(wake, order_words), "compute": round(ended - began, 3),
                "after_end": round(ended - began, 3), "live_update": round(time.perf_counter() - part, 3)}

    return hear, None


def whisper_hint_engine(place: Path):
    """What Kairu now does: the listener's own Whisper hearing (kairu/voice/whisper.py), its speech gate, Kairu's order
    words as the hint, and the same words rules, on each order and the pause after it."""
    from kairu.voice import whisper as kairu_whisper
    model = kairu_whisper.Whisper(place)
    tail = bytes(int(RATE * 1.2) * 2)
    said = []

    def heard(sound: bytes):
        said.append(model(sound))
        return said[-1]

    def hear(sound: bytes) -> dict:
        hearing, events = kairu_whisper.WhisperHearing(heard, background=False), []
        said.clear()
        began = time.perf_counter()
        for i in range(0, len(sound), CHUNK):
            events += hearing.feed(sound[i:i + CHUNK])
        spoken = time.perf_counter()
        for i in range(0, len(tail), CHUNK):
            events += hearing.feed(tail[i:i + CHUNK])
        ended = time.perf_counter()
        return {"raw": " | ".join(item.text for item in said), "events": vosk_outcome(events), "compute": round(ended - began, 3),
                "after_end": round(ended - spoken, 3), "gated": True}

    return hear, None


# --- the whole test ----------------------------------------------------------------------------------------------------

def family_mib(pid: int) -> tuple[float, float]:
    """(working set now, peak working set) of a process and the processes it started, in MiB (on Windows a venv's
    python.exe is a small starter whose child is the real Python). Linux: VmRSS and VmHWM."""
    now = peak = 0.0
    for member in [pid, *child_pids(pid)]:
        reading = memory_mib(member)
        now, peak = now + reading[0], peak + reading[1]
    return now, peak


def memory_mib(pid: int) -> tuple[float, float]:
    if sys.platform != "win32":
        try:
            fields = dict(line.split(":", 1) for line in Path(f"/proc/{pid}/status").read_text().splitlines() if ":" in line)
        except OSError:
            return 0.0, 0.0
        return int(fields["VmRSS"].split()[0]) / 1024, int(fields["VmHWM"].split()[0]) / 1024
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                 "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                                 "PagefileUsage", "PeakPagefileUsage")]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
    if not handle:
        return 0.0, 0.0
    try:
        counters = Counters(cb=ctypes.sizeof(Counters))
        if not kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return 0.0, 0.0
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))
    return counters.WorkingSetSize / 2**20, counters.PeakWorkingSetSize / 2**20


def child_pids(pid: int) -> list[int]:
    if sys.platform != "win32":
        found = []
        for stat in Path("/proc").glob("[0-9]*/stat"):
            try:
                if int(stat.read_text().rsplit(")", 1)[1].split()[1]) == pid:
                    found.append(int(stat.parent.name))
            except (OSError, ValueError, IndexError):
                pass
        return found
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    found, snapshot = [], kernel32.CreateToolhelp32Snapshot(0x2, 0)
    try:
        entry = Entry(dwSize=ctypes.sizeof(Entry))
        more = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        while more:
            if entry.th32ParentProcessID == pid:
                found.append(entry.th32ProcessID)
            more = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))
    return found


def run_engine(name: str, clips: list[bytes], data_dir) -> dict:
    process = subprocess.Popen([str(venv_python()), str(Path(__file__).resolve()), "--engine", name, "--data", str(data_dir)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=ROOT)
    try:
        loaded = json.loads(process.stdout.readline() or "{}")
        if "loaded" not in loaded:
            return {"error": "it did not start (see above)"}
        time.sleep(0.5)
        rest = family_mib(process.pid)[0]
        answers = []
        for clip in clips:
            process.stdin.write(struct.pack("<I", len(clip)) + clip)
            process.stdin.flush()
            answers.append(json.loads(process.stdout.readline()))
        process.stdin.write(struct.pack("<I", 0))
        process.stdin.flush()
        json.loads(process.stdout.readline())  # "measure": the engine as Kairu would use it, nothing more
        now, peak = family_mib(process.pid)
        process.stdin.write(b"m")
        process.stdin.flush()
        for answer in answers:
            answer["raw"] = json.loads(process.stdout.readline()).get("raw", answer["raw"])
        json.loads(process.stdout.readline())
        return {"loaded": loaded["loaded"], "steady": max(now, rest), "peak": max(peak, now, rest), "answers": answers}
    finally:
        process.stdin.close()
        process.wait(30)


def score(results: dict, said: list[tuple[str, str]]) -> None:
    names = [name for name in results if "answers" in results[name]]
    print("\nWhat each engine heard (raw), and what Kairu would do with it:")
    for number, (text, order) in enumerate(said):
        expected = expected_outcome(order)
        print(f"\n  {number + 1:>2}. you said: \"{text}\"   Kairu should do: {expected}")
        for name in names:
            answer = results[name]["answers"][number]
            mark = "ok " if answer["events"] == expected else "-- "
            print(f"      {mark}{name:18} heard \"{answer['raw']}\"  ->  {answer['events'] or '(dropped: no Kairu)'}")
    print("\nThe engines (right: Kairu would do exactly the right thing; Kairu: it heard the wake word; word errors: of"
          f"\nthe orders' words; memory in MiB, limits {AT_REST_MIB} at rest = 200 MB and {SPEAKING_MIB} with Piper speaking"
          " = 400 MB: steady after all the orders, and the peak, which may come while the model loads):")
    print(f"\n  {'engine':18} {'right':>6} {'Kairu':>6} {'word errors':>12} {'ready after you stop':>21} {'steady':>7} "
          f"{'peak':>9} {'+Piper':>9}  live words")
    for name in results:
        result = results[name]
        if "answers" not in result:
            print(f"  {name:18} {result['error']}")
            continue
        answers = result["answers"]
        right = sum(a["events"] == expected_outcome(order) for a, (_, order) in zip(answers, said))
        woke = sum(bool(a["events"]) for a in answers)
        wrong = total = 0
        for answer, (_, order) in zip(answers, said):
            expected = expected_outcome(order)
            heard = answer["events"] if not answer["events"].startswith("(") else ""
            errors, size = word_errors(expected, heard)
            wrong, total = wrong + errors, total + size
        after = sorted(a["after_end"] for a in answers)[len(answers) // 2] + ENDPOINT_SECONDS
        live = (f"each update {sorted(a['live_update'] for a in answers)[len(answers) // 2]:.2f} s"
                if "live_update" in answers[0] else "none: the words show once heard" if answers[0].get("gated")
                else "word by word, as you speak")
        speaking = result["steady"] + PIPER_MIB

        def over(value, limit):
            return f"{value:>4.0f}{'' if value < limit else ' OVER':5}"

        print(f"  {name:18} {right:>3}/{len(said):<2} {woke:>3}/{len(said):<2} {100 * wrong / max(total, 1):>10.0f} % "
              f"{after:>17.2f} s {over(result['steady'], AT_REST_MIB)} {over(result['peak'], AT_REST_MIB)} "
              f"{over(speaking, SPEAKING_MIB)}  {live}")
    print("\n  (\"ready after you stop\": the half-second pause every engine waits for, plus its own work after it.)")


def record(said: list[tuple[str, str]]) -> list[bytes]:
    """Each order from the microphone, kept in memory only. Enter starts it; it ends after a short pause."""
    from kairu.voice import mic as microphone
    try:
        mic = microphone.open_mic()
    except microphone.MicProblem as error:
        raise SystemExit(f"The microphone can't be used: {error}")
    clips = []
    try:
        print("Quiet, please, for one second ...")
        noise = sorted(level(mic.read()) for _ in range(10))[5]
        for number, (text, _) in enumerate(said, 1):
            while True:
                input(f"\n  {number}/{len(said)}  Press Enter, then say:  \"{text}\"  ")
                clip = listen(mic, max(500, noise * 4))
                answer = input(f"     heard {len(clip) / 2 / RATE:.1f} s of you. Enter for the next one, or r to say it again: ")
                if answer.strip().lower() != "r":
                    break
            clips.append(clip)
    finally:
        mic.close()
    return clips


def level(chunk: bytes) -> int:
    samples = array.array("h", chunk)
    return int((sum(s * s for s in samples) / max(len(samples), 1)) ** 0.5)


def listen(mic, threshold: int) -> bytes:
    """From just before you start to 0.8 s after you stop (at most 8 s), in memory."""
    before, kept, quiet, started = [], [], 0, False
    for _ in range(80):
        chunk = mic.read()
        loud = level(chunk) > threshold
        if not started:
            before = (before + [chunk])[-3:]
            if loud:
                started, kept = True, before[:]
            continue
        kept.append(chunk)
        quiet = 0 if loud else quiet + 1
        if quiet >= 8:
            break
    return b"".join(kept) if kept else b"".join(before)


def piper_clips(data_dir, said: list[tuple[str, str]]) -> dict[str, list[bytes]]:
    """The orders said by Piper's Indian English voices, made in memory and turned to 16 kHz (no sound is written)."""
    import warnings
    from kairu.voice import speak
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import audioop
    piper = models.piper_ready(data_dir)
    onnx, config, _ = models.voice_ready(data_dir, "indian-svbi")
    rate = speak.sample_rate(config)
    clips = {}
    for speaker, number in PIPER_SPEAKERS.items():
        clips[speaker] = []
        for text, _ in said:
            sound = b"".join(speak.synthesize(text, piper, onnx, number))
            clips[speaker].append(bytes(RATE // 4 * 2) + audioop.ratecv(sound, 2, 1, rate, RATE, None)[0])
    return clips


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Which offline speech engine hears you best (nothing is written to disk).")
    parser.add_argument("--setup", action="store_true", help=f"make {VENV.name} and download every engine's model")
    parser.add_argument("--piper", action="store_true", help="hear the orders said by Piper's four Indian English voices")
    parser.add_argument("--engines", default=",".join(ENGINES), help="which engines, comma-separated")
    parser.add_argument("--engine", help=argparse.SUPPRESS)  # one engine's own process
    parser.add_argument("--data", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.engine:
        return engine_main(args.engine, args.data)
    from kairu import config as kairu_config
    data_dir = kairu_config.load().data_dir
    if args.setup:
        return set_up(data_dir)
    names = [name.strip() for name in args.engines.split(",") if name.strip()]
    missing = [name for name in names if name not in ENGINES or not ready(data_dir, name)]
    if missing or not venv_python().exists():
        print(f"Not set up: {', '.join(missing) or VENV.name}. Run first:  .venv-guardian\\Scripts\\python tools\\hearing_test.py --setup")
        return 1
    print("Kairu hearing test: nothing you say is written to disk; your recordings are gone when this ends.")
    sets = piper_clips(data_dir, ORDERS) if args.piper else {"you": record(ORDERS)}
    for who, clips in sets.items():
        print(f"\n=== {who}: each engine hears the {len(clips)} orders (one engine at a time) ===")
        results = {}
        for name in names:
            print(f"  {name} ...", flush=True)
            results[name] = run_engine(name, clips, data_dir)
        score(results, ORDERS)
        clips.clear()
    print("\nPlease send me this whole output.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
