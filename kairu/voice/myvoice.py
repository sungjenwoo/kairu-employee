"""Your voice print, for voice.only_my_voice (VOICE.md "Only your voice"; the owner's GO of 15 Nov 2026).

`kairu voice enroll` is an owner command you type in PowerShell, never a Kairu action, like `kairu voice check`. It opens
the microphone for at most ENROLL_SECONDS, asks you to say a few sentences, and keeps only the average of their voice prints
(Vosk's speaker model, vosk-model-spk-0.4: 128 numbers per sentence) in data/voice/my-voice.json. No sound is written,
nothing is sent anywhere, and the words you said are not kept. `kairu voice enroll --forget` deletes it.

A voice print says who is speaking, not what was said; it stays on this PC like everything in the data folder.
"""

import json
import time
from pathlib import Path

FILE = "my-voice.json"
SIZE = 128  # numbers in a voice print (vosk-model-spk-0.4)
SENTENCES = (
    "Kairu, open Microsoft Edge and show me the news.",
    "Kairu, set the volume to thirty and the brightness to sixty.",
    "The quick brown fox jumps over the lazy dog near the river bank.",
    "Kairu, what is the weather like in Hyderabad today?",
    "I am setting up my own voice so that only I can give you orders.",
    "Kairu, open Notepad.",  # short orders too (16 Nov 2026): most orders are short, and a short one's voice print differs
    "Kairu, volume fifty.",
    "Kairu, what's open?",
)
SHORT_SENTENCES = frozenset(SENTENCES[5:])
LEAST_SECONDS = 1.5  # a long sentence shorter than this gives a poor voice print: asked again
SHORTEST_SECONDS = 0.6  # and a short order shorter than this
ENROLL_SECONDS = 120


def path(data_dir) -> Path:
    return Path(data_dir) / "voice" / FILE


def load(data_dir) -> list[float] | None:
    """Your voice print, or None when there is none (or it is not one: then it is as if there were none)."""
    try:
        kept = json.loads(path(data_dir).read_text(encoding="utf-8"))
        vector = kept["vector"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not (isinstance(vector, list) and len(vector) == SIZE and all(isinstance(value, (int, float)) for value in vector)):
        return None
    return [float(value) for value in vector]


def save(data_dir, vector: list[float], sentences: int) -> Path:
    place = path(data_dir)
    place.parent.mkdir(parents=True, exist_ok=True)
    part = place.with_suffix(".part")
    part.write_text(json.dumps({"vector": [round(value, 6) for value in vector], "sentences": sentences,
                                "model": "vosk-model-spk-0.4", "made": time.strftime("%Y-%m-%d")}), encoding="utf-8")
    part.replace(place)
    return place


def forget(data_dir) -> bool:
    try:
        path(data_dir).unlink()
        return True
    except FileNotFoundError:
        return False


def average(prints: list[tuple[list[float], int]]) -> list[float]:
    frames = sum(count for _, count in prints)
    return [sum(vector[i] * count for vector, count in prints) / frames for i in range(SIZE)]


def blend(prints: list[tuple[list[float], int]]) -> list[float]:
    """Your voice print from your sentences: each one counts the same (made the same length first), so the short orders
    weigh as much as the long sentences, however few frames they have."""
    import math
    units, sizes = [], []
    for vector, _ in prints:
        size = math.sqrt(sum(value * value for value in vector)) or 1.0
        units.append([value / size for value in vector])
        sizes.append(size)
    scale = sum(sizes) / len(sizes)  # back to a voice print's own size (the match looks only at its direction)
    return [scale * sum(unit[i] for unit in units) / len(units) for i in range(SIZE)]


def enroll(cfg, say=print, clock=time.monotonic, opened=None) -> int:
    """Say each sentence; keep the average voice print. `opened` is (mic, words recognizer, quick recognizer) for the tests."""
    from kairu.voice import fastlane, models
    from kairu.voice import whisper as kw
    if opened is None:
        try:
            vosk_place, speaker_place = models.ready(cfg.data_dir, cfg.voice_model), models.speaker_ready(cfg.data_dir)
        except models.NotSetUp as error:
            say(f"Not ready: {error}.")
            return 1
        from kairu.voice import mic as microphone
        from kairu.voice.listen import load_vosk
        vosk = load_vosk()
        vosk.SetLogLevel(-1)
        try:
            mic = microphone.open_mic()
        except microphone.MicProblem as error:
            say(f"The microphone could not be opened: {error}")
            return 1
        heard, quick = fastlane.recognizers(vosk.Model(str(vosk_place)), vosk.SpkModel(str(speaker_place)))
    else:
        mic, heard, quick = opened
    lane = fastlane.FastLane(heard, quick)
    gate, prints, end = kw.SpeechGate(), [], clock() + ENROLL_SECONDS
    say("Switch the bar's mic off first. Say each sentence in your normal voice, then pause.")
    try:
        for number, sentence in enumerate(SENTENCES, 1):
            say(f"{number} of {len(SENTENCES)}: \"{sentence}\"")
            while clock() < end:
                sound = mic.read()
                happened, utterance = gate.feed(sound)
                if happened == "start":
                    lane.begin(gate.kept)
                elif gate.speaking:
                    lane.feed(sound)
                if happened == "dropped":
                    lane.drop()
                elif happened == "end":
                    lane._piece(json.loads(lane.words.FinalResult()))
                    got, frames = lane._prints, sum(count for _, count in lane._prints)
                    lane.drop()
                    least = SHORTEST_SECONDS if sentence in SHORT_SENTENCES else LEAST_SECONDS
                    if len(utterance) / 2 / kw.RATE < least or frames < fastlane.LEAST_FRAMES:
                        say("  That was short; please say the whole sentence again.")
                        continue
                    prints.append((average(got), frames))
                    break
            else:
                say("Time is up; nothing was kept.")
                return 1
    finally:
        mic.close()
    mine = blend(prints)
    scores = [fastlane.cosine(vector, mine) for vector, _ in prints]
    place = save(cfg.data_dir, mine, len(prints))
    say(f"Kept your voice print in {place} (numbers only, no sound).")
    say("How close each sentence was to it (1.00 is the same; Kairu takes " f"{fastlane.MATCH:.2f} or more as you, "
        f"{fastlane.MATCH_SHORT:.2f} for a short order): " + ", ".join(f"{score:.2f}" for score in scores))
    if min(scores) < fastlane.MATCH_SHORT + 0.1:
        say("One sentence was close to the line: run this again in a quiet room, in your usual voice.")
    say("To use it: voice.only_my_voice: true in config.yaml, then restart Guardian.")
    return 0
