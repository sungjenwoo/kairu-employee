"""`kairu voice check`: what your microphone and Whisper hear, so a hearing problem can be found (VOICE.md "Hearing check").

You run it yourself in PowerShell, like `kairu voice try`: it is an owner command, never a Kairu action, and it is not the
listener. It opens the microphone for the seconds you give (15 by default) and prints, for each thing you say:

    how loud it was, against the line the speech gate needs; whether the gate passed it to Whisper; Whisper's words and
    how sure it was; and whether those words would wake Kairu, and why not.

The sound stays in memory and is gone when it ends: nothing is written to disk, sent anywhere, or kept. What Whisper
heard is printed on your screen only. Switch the bar's mic off first, so the two do not share the microphone.
"""

import math
import time
import types

from kairu.voice import mic as microphone
from kairu.voice import models
from kairu.voice import whisper as kw

LONGEST_SECONDS = 60


def dbfs(level: float) -> int:
    """A 16-bit RMS level in dB below full scale (0 is the loudest; normal speech near a laptop is about -35 to -20)."""
    return round(20 * math.log10(max(level, 1.0) / 32768))


def verdict(heard: kw.Heard) -> str:
    """Would these words wake Kairu (outside a session)? In words, with the reason."""
    woke, said = kw.split_wake(heard.text)
    if not heard.text:
        return "no words: Whisper dropped it as noise" if heard.dropped else "no words"
    if not woke:
        return f"would NOT wake Kairu: the first word is not \"Kairu\" (Whisper wrote {heard.text!r})"
    if heard.sure:
        return "WAKES Kairu" + (f", order: {' '.join(said)}" if said else "")
    if not said:
        return "WAKES Kairu (not sure, so only a short 8-second window opens; then say your order)"
    return "would NOT wake Kairu: Whisper was not sure, and an order heard unsure is never run. Say \"Kairu\", pause, then the order"


def run(cfg, seconds: float = 15, say=print, clock=time.monotonic) -> int:
    if cfg.voice_engine not in models.WHISPER_ENGINES:
        say(f"This check is for Whisper; voice.engine is {cfg.voice_engine}.")
        return 1
    seconds = max(3.0, min(float(seconds), LONGEST_SECONDS))
    try:
        place = models.hearing_ready(cfg.data_dir, cfg.voice_engine, cfg.voice_model)
    except (models.NotSetUp, KeyError) as error:
        say(f"Voice is not ready: {error}.")
        return 1
    say("Loading Whisper ...")
    hear = kw.transcriber(place)
    if not isinstance(hear, types.FunctionType):  # a plain function is a pretend transcriber: nothing to set up
        kw.warm(hear)  # the times below are what each sentence really takes, not Whisper setting itself up
    gate = kw.SpeechGate()
    try:
        mic = microphone.open_mic()
    except microphone.MicProblem as error:
        say(f"The microphone could not be opened: {error}")
        return 1
    say(f"Listening for {seconds:.0f} seconds. Say \"Kairu\" a few times, as you normally would, with a pause between.")
    say(f"(The gate needs a voice louder than {dbfs(kw.SPEECH_LEVEL)} dB, and {kw.OVER_NOISE:.0f} times the room's own noise.)")
    loudest, utterances, end = 0.0, 0, clock() + seconds
    try:
        while clock() < end:
            sound = mic.read()
            happened, utterance = gate.feed(sound)
            if gate.speaking or happened:
                loudest = max(loudest, max(gate.levels, default=0.0))
            if happened == "dropped":
                say(f"- something at {dbfs(loudest)} dB, too short (a tap, a cough, or a word cut by the gate)")
                loudest = 0.0
            elif happened == "end":
                utterances += 1
                took = clock()
                heard = hear(gate.clean(utterance))  # what the listener's Whisper hears: the room turned down
                took = clock() - took
                say(f"- {dbfs(loudest)} dB, {len(utterance) / 2 / kw.RATE:.1f} s: Whisper heard {heard.text!r} "
                    f"in {took:.1f} s (sure: {'yes' if heard.sure else 'no'}, score {heard.score}) -> {verdict(heard)}")
                loudest = 0.0
    finally:
        mic.close()
        close = getattr(hear, "close", None)
        if close:
            close()
    room = gate.noise()
    say(f"Room noise: {dbfs(room)} dB. Things heard: {utterances}.")
    if not utterances:
        say("Nothing reached Whisper. Speak closer or louder, or raise the microphone level in Windows "
            "(Settings > System > Sound > Input > Volume), then run this again.")
    return 0
