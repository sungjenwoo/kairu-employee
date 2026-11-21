"""voice.listen, the Guardian action that hears you: the microphone, the offline speech engine (voice.engine: Whisper
base.en by default, or tiny.en, kairu/voice/whisper.py; or the small Vosk model, kairu/voice/hearing.py), and the voice link to the bar.

Guardian starts it (kairu/executors.py) when you switch the mic on in the Kairu bar, and an emergency stop ends it with
everything it started. It first says hello to the bar with the session token the bar gave for it, and opens the
microphone only once the bar accepts that token: started any other way, it hears nothing and ends.

It never runs anything itself. It tells the bar what it heard (kairu/voice/hearing.py) and the bar hands each order to the
task core, which sends each step to Guardian. The one thing it does itself is "Kairu, stop": the same emergency stop as
Ctrl+Alt+K and the bar's Stop button, written straight to Guardian's database, which ends every action, this one too.

Sound stays in memory, a tenth of a second at a time; no sound and no words are written anywhere. While Kairu speaks, the
bar says "paused", and this hears silence instead of the microphone. With voice.barge_in the bar also says what Kairu is
saying ("speaking"): then Whisper keeps hearing the microphone, leaves out what is Kairu's own voice, and tells the bar
"barge" when you talk over it (kairu/voice/whisper.py). Vosk always hears silence while Kairu speaks.
"""

import array
import os
import sys
import threading

from kairu.voice import link, mic as microphone, models
from kairu.worker import FAILED, REFUSED

# vosk's package loads these for its model downloader and subtitles, which Kairu never uses (`kairu voice setup` downloads,
# kairu/voice/models.py): about 9 MiB, and the way to the network through urllib3 and ssl. They are stood in for while it loads.
DOWNLOADER_ONLY = {"requests": (), "tqdm": ("tqdm",), "srt": (), "urllib.request": ("urlretrieve",)}
LOADING_TICK = 0.5  # while the model loads, the listener tells the bar it is still here this often (the link's limit is 5 s)
QUIET_CHUNKS = 30  # 3 seconds of a microphone that sends nothing at all
QUIET_LEVEL = 2  # samples never above this: the microphone is off, at 0 % or blocked
SILENT_MIC = ("The microphone sends only silence. Check it is on and its volume is up (Settings > System > Sound > Input), "
              "and that Windows lets desktop apps use it.")


def main(session: str, data_dir: str, voice_model: str, voice_engine: str = "vosk", voice_live_every: float = 0.0,
         voice_fast: bool = False, voice_only_mine: bool = False, voice_hearing: str = "local", voice_gemini_model: str = "",
         voice_camera: bool = False):
    try:
        line = link.connect(data_dir)
    except link.LinkError as error:
        print(f"voice.listen: {error}; the mic stays off", file=sys.stderr, flush=True)
        return REFUSED
    try:
        try:
            line.send({"hello": session, "pid": os.getpid()})
            accepted = line.receive().get("ok") is True
        except link.LinkError:
            accepted = False
        if not accepted:
            print("voice.listen: the Kairu bar did not switch this mic on; it stays off", file=sys.stderr, flush=True)
            return REFUSED
        gemini = (data_dir, voice_gemini_model) if voice_hearing == "gemini" else None
        return _listen(line, data_dir, voice_model, voice_engine, voice_live_every, voice_fast, voice_only_mine, gemini,
                       voice_camera)
    except link.LinkError as error:
        print(f"voice.listen: {error}; the mic is off", file=sys.stderr, flush=True)
        return None
    finally:
        line.close()


def _tell(line, events: list[dict], **state) -> dict:
    line.send({"events": events, **state})
    return line.receive()


def _listen(line, data_dir: str, voice_model: str, voice_engine: str, live_every: float = 0.0, fast: bool = False,
            only_mine: bool = False, gemini=None, camera: bool = False):
    try:
        place = models.hearing_ready(data_dir, voice_engine, voice_model)
    except (models.NotSetUp, KeyError) as error:
        _tell(line, [{"problem": f"Voice is not ready: {error}."}])
        return FAILED
    lane = (data_dir, voice_model, fast, only_mine) if fast or only_mine else None
    hearing, problem, session = _load(line, place, voice_engine, live_every, lane, gemini)
    if hearing is None:
        if problem:
            _tell(line, [{"problem": problem}])
            return FAILED
        return None  # the bar ended it while the model loaded
    lips = _camera(line, hearing) if camera else None
    try:
        mic = microphone.open_mic()
    except microphone.MicProblem as error:
        _tell(line, [{"problem": str(error)}])
        if lips is not None:
            lips.close()
        return FAILED
    try:
        return _hear(line, hearing, mic, data_dir, session)
    finally:
        mic.close()
        if lips is not None:
            lips.close()  # the camera is released with the mic
        getattr(hearing, "close", lambda: None)()


def _camera(line, hearing):
    """voice.camera (VOICE.md "The camera check"): the camera, only while the mic is on. Without OpenCV or a camera, Kairu
    says so once and hears as before."""
    if not hasattr(hearing, "attach_lips"):
        return None
    from kairu.voice import lips
    try:
        watch = lips.LipWatch().start()
    except (lips.CameraProblem, OSError) as error:
        _tell(line, [{"problem": f"No camera check: {error}."}])
        return None
    hearing.attach_lips(watch)
    return watch


def _load(line, place, voice_engine: str, live_every: float = 0.0, lane=None, gemini=None):
    """(hearing, problem, session asked for): the model loads in a thread while the bar is told every LOADING_TICK that
    the listener is still here. A big Whisper (large-v3-turbo) takes 8-15 s to load; the voice link drops a side that says
    nothing for 5 s, which ended every listener before it started (laptop test, 15 Nov 2026)."""
    loaded: dict = {}

    def load():
        try:
            if gemini is not None and voice_engine in models.WHISPER_ENGINES:
                hearing = _gemini_hearing(place, *gemini)
            else:
                hearing = _hearing(place, voice_engine, live_every) if live_every else _hearing(place, voice_engine)
            if lane is not None:
                fast, problem, hard = _fast_lane(voice_engine, *lane)
                if hard:  # your-voice-only can't be kept: no orders at all, rather than anyone's
                    loaded["problem"] = problem
                    return
                if fast is not None:
                    hearing.attach_fast(fast)
                hearing.soft_problem = problem
            loaded["hearing"] = hearing
        except Exception as error:  # a model that can't load is told to the bar, never a silent end
            loaded["problem"] = f"The hearing model could not load ({type(error).__name__}: {error})"

    loading = threading.Thread(target=load, name="kairu-voice-load", daemon=True)
    loading.start()
    session = False
    while loading.is_alive():
        reply = _tell(line, [], talking=False, session=False)
        if reply.get("end"):
            return None, "", False
        session = session or bool(reply.get("session"))  # Ctrl+Alt+V pressed while loading: kept for when it is ready
        loading.join(LOADING_TICK)
    return loaded.get("hearing"), loaded.get("problem", ""), session


def _hearing(place, voice_engine: str, live_every: float = 0.0):
    """Whisper (the default) or Vosk (the fallback), by voice.engine in Guardian's config.yaml. live_every is
    voice.live_caption_every (Whisper's live words; Vosk always shows its own as you speak)."""
    if voice_engine in models.WHISPER_ENGINES:  # base.en or tiny.en: the folder says which
        from kairu.voice.whisper import WhisperHearing, transcriber, warm
        hear = transcriber(place)
        warm(hear)  # while the bar is told "still loading": the first real sentence is as quick as the rest
        return WhisperHearing(hear, live_every=live_every)
    vosk = load_vosk()
    vosk.SetLogLevel(-1)
    from kairu.voice.hearing import Hearing
    return Hearing(vosk.Model(str(place)))


def _gemini_hearing(place, data_dir: str, model: str):
    """voice.hearing: gemini (VOICE.md "Gemini hearing"): each utterance heard by Gemini; the offline Whisper is loaded only
    if Gemini can't be reached. No live looks: each would be one more request, and the free limit is per minute."""
    from kairu.voice.gemini import GeminiHearing
    from kairu.voice.whisper import WhisperHearing, transcriber
    hear = GeminiHearing(data_dir, model, fallback=lambda: transcriber(place))
    hear.warm()  # the connection to Gemini, open before your first sentence
    return WhisperHearing(hear, live_every=0.0)


def _fast_lane(voice_engine: str, data_dir: str, voice_model: str, fast: bool, only_mine: bool):
    """(the fast lane or None, a problem to tell, whether it stops the listener). Your-voice-only fails closed: without
    its voice print and models the mic stays off. Without the Vosk model, fast orders are only skipped (Whisper hears)."""
    from kairu.voice import fastlane, myvoice
    if voice_engine not in models.WHISPER_ENGINES:
        return None, ("Only-your-voice works with Whisper (voice.engine); the mic stays off." if only_mine else ""), only_mine
    voiceprint = myvoice.load(data_dir) if only_mine else None
    if only_mine and voiceprint is None:
        return None, "Only-your-voice is on, but there is no voice print yet: run `kairu voice enroll`. The mic stays off.", True
    try:
        vosk_place = models.ready(data_dir, voice_model)
        speaker_place = models.speaker_ready(data_dir) if only_mine else None
    except models.NotSetUp as error:
        if only_mine:
            return None, f"Only-your-voice needs {error}; the mic stays off.", True
        return None, f"Fast orders are off for now: {error}.", False
    vosk = load_vosk()
    vosk.SetLogLevel(-1)
    speaker = vosk.SpkModel(str(speaker_place)) if speaker_place else None
    words, quick = fastlane.recognizers(vosk.Model(str(vosk_place)), speaker)
    return fastlane.FastLane(words, quick, voiceprint), "", False


def load_vosk():
    """vosk without its downloader: stand-ins for DOWNLOADER_ONLY while its package loads, gone from sys.modules after it,
    so the real ones still load if anything asks for them. What vosk took from them refuses to run."""
    import types

    def downloader_only(*args, **kwargs):
        raise RuntimeError("vosk's downloader is not loaded in the listener: `kairu voice setup` downloads models")

    stand_ins = {}
    for name, names in DOWNLOADER_ONLY.items():
        if name not in sys.modules:
            stand_ins[name] = types.ModuleType(name)
            for attribute in names:
                setattr(stand_ins[name], attribute, downloader_only)
    sys.modules.update(stand_ins)
    try:
        import vosk
    finally:
        for name, stand_in in stand_ins.items():
            if sys.modules.get(name) is stand_in:
                del sys.modules[name]
    return vosk


def _hear(line, hearing, mic, data_dir: str, session: bool = False):
    events, paused, loudest, chunks = [{"ready": True}] + (hearing.start_session() if session else []), False, 0, 0
    if getattr(hearing, "soft_problem", ""):
        events.append({"problem": hearing.soft_problem, "soft": True})
    while True:
        reply = _tell(line, events, talking=hearing.talking, session=hearing.session)
        if reply.get("end"):
            return None
        paused = bool(reply.get("paused"))
        speaking = reply.get("speaking") if isinstance(reply.get("speaking"), str) else ""
        barge = paused and bool(speaking) and hasattr(hearing, "set_echo")
        if hasattr(hearing, "set_echo"):
            hearing.set_echo(speaking if barge else "")
        events = hearing.start_session() if reply.get("session") and not hearing.session else []
        if reply.get("reply") and not paused:  # Kairu just asked its follow-up question: listen for your answer a little
            events += hearing.listen_for_reply(float(reply["reply"]))
        try:
            sound = mic.read()
        except microphone.MicProblem as error:
            _tell(line, events + [{"problem": str(error)}])
            return FAILED
        if chunks < QUIET_CHUNKS:
            chunks += 1
            loudest = max(loudest, max(map(abs, array.array("h", sound)), default=0))
            if chunks == QUIET_CHUNKS and loudest <= QUIET_LEVEL:
                events.append({"problem": SILENT_MIC, "soft": True})
        if paused and not barge:
            sound = bytes(len(sound))  # Kairu is speaking: it hears silence, never itself
        heard = hearing.feed(sound)
        events += heard
        if any("stop" in event for event in heard):
            _emergency_stop(data_dir)
            line.send({"events": events, "talking": False, "session": False})
            return None


def _emergency_stop(data_dir: str) -> None:
    """The same stop as Ctrl+Alt+K and the bar's Stop: every action halts, Safe Mode until `kairu resume`."""
    from kairu import safemode
    from kairu.store import Store
    safemode.emergency_stop(Store(data_dir), "Kairu, stop (voice)")
