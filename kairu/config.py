"""Kairu settings from config.yaml: the voice and research switches, where Guardian keeps its files, and protection.

A missing file means the defaults: voice and research off, protection off. A file with a mistake in
it is refused rather than guessed at.

protect.enabled: Guardian starts its monitors (protect.watch) by itself when it starts and after a
resume, and again after a crash. They check deadlines every check_seconds and Gmail every
gmail_seconds. Off, the monitors run only when you start them (`kairu protect start`).

link.enabled: Guardian keeps the Kairu Link receiver (link.receive) running while a device is paired
(LINK.md). link.relay is the Gate's relay, an ntfy server: https://ntfy.sh to start, your own later.

mission_mode: the limits Mission Mode keeps (kairu/mission.py): at most max_hours; it ends early when
Windows reports max_celsius or more, or when the processor stays above cpu_percent for cpu_minutes.

brain (BRAIN.md): public_to_cloud is option A (29 Oct 2026): a question with no personal data goes to a free
provider that does not train on prompts without asking you; false makes every cloud send wait for "yes" and your
PIN (option B). Without a brain section it is false: Kairu fails closed. providers is the order Kairu tries
them in; daily_cap, if more than 0, is how many cloud questions a day you allow (ADR-006: none unless you set
one); models replaces a provider's model, only if it retires the one Kairu uses.

tasks.work_folder (BAR.md): the only folder Kairu's file skills may touch. Default: Kairu-files in your user folder, made
on first use. Guardian hands it to them itself, so a request can never set it; only you change it, here, and restart Guardian.
tasks.bar_key: the letter for Ctrl+Alt+letter that shows and hides the Kairu bar, if another program holds Ctrl+Alt+Space.
It can never be K, Guardian's emergency stop.
tasks.eyes (BAR.md "Kairu's eyes", ADR-051 proposed): true lets screen.look send a picture of ONE window to Google Gemini
for the screen agent ("take control and ...", a window on the safe list) and "what's on my screen" (any window it may see);
false, or no line at all, and no picture ever leaves this PC.

voice (VOICE.md): enabled switches speech in and out on; voice.engine is how Kairu hears you: whisper-base.en (the default;
plain "whisper" means it too), whisper-tiny.en (smaller, hears you less well) or vosk (the small Vosk model, kept as the
fallback); voice.model is the Vosk model when the engine is vosk
(small-en-us or small-en-in); `kairu voice setup` downloads the engine's model; voice.key is the letter for Ctrl+Alt+letter that starts
listening (V; never K, and not the bar's own letter); voice.voice is the Piper voice Kairu answers in (one of 16:
VOICE.md lists them; the gate test lets you hear each and pick); voice.style is how it says an answer: warm (the default:
the answer bright, a breath, then the follow-up question warmer and slower), lively, calm, or plain (as it is);
voice.tts is which voice engine speaks: kokoro (the default: human-sounding; `kairu voice setup` and `pip install -e .[kokoro]`,
else Piper speaks) or piper; voice.kokoro_voice is Kokoro's voice (af_heart by default; `kairu voice try --voices` plays each).
voice.listen_at_start (true/false, default false; your GO of 15 Nov 2026): the bar switches the mic on by itself when it
starts and when you unlock the PC, listening for "Kairu" (never a session without it). Off: the mic is off at every start.
voice.barge_in (true/false, default false; your GO of 15 Nov 2026): while Kairu speaks, it still listens (Whisper only),
and stops talking when you talk over it; what it hears of its own voice is left out.
voice.live_caption_every (seconds, default 0: off; your GO of 15 Nov 2026: 0.20): while you speak, the bar shows your words
in grey as Whisper hears them, this often, as Google does; when you stop, the whole sentence replaces them (Whisper only).
0, or a number from 0.1 to 2.
voice.fast_orders (true/false, default false; your "it must work fast", 15 Nov 2026): the small Vosk model (voice.model) hears
beside Whisper, so the live words come word by word and a quick order (open an app, volume, brightness, mute, what's open)
starts 0.2 s after you stop speaking. `kairu voice setup` downloads it.
voice.live (true/false, default false; the owner's GO of 18 Nov 2026, VOICE.md "Kairu Live", ADR-052 proposed): the mic button
and Ctrl+Alt+V start Kairu Live (LiveKit: Deepgram hears, Gemini thinks, ElevenLabs speaks) instead of the offline voice;
voice.live_folder is the Kairu Live folder, with its .venv (LiveKit installed) and its .env (the keys).
voice.only_my_voice (true/false, default false): orders only in your own voice (`kairu voice enroll` first); "Kairu, stop"
always works, from anyone. Needs the Vosk model and its speaker model (`kairu voice setup`).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"
FEATURES = ("voice", "research")
DEFAULT_RELAY = "https://ntfy.sh"
RELAY = re.compile(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~-]+)*")  # scheme, host, port, path; nothing else
BRAIN_DEFAULT = ("groq", "cloudflare", "openrouter")  # what the brain asks when brain.providers is not set
PROVIDER_NAMES = BRAIN_DEFAULT + ("gemini",)  # kairu/brain/providers.py describes each; gemini's key is for Gemini hearing
VOICE_ENGINES = ("whisper-base.en", "whisper-tiny.en", "whisper-large-v3-turbo", "whisper-distil-large-v3", "whisper-medium.en",
                 "whisper-small.en", "vosk")  # kairu/voice/models.py ENGINES, the same; the first is the default
VOICE_ENGINE_NAMES = {"whisper": "whisper-base.en"}  # what "whisper" alone means (the default since 10 Nov 2026; tiny.en before)
VOICE_TTS = ("kokoro", "piper")  # how Kairu speaks: Kokoro (human-sounding, when set up) or Piper; the first is the default
KOKORO_VOICES = ("af_heart", "af_bella", "af_nicole", "af_sarah", "af_aoede", "af_kore", "af_nova", "af_sky", "af_alloy",
                 "af_jessica", "af_river", "am_michael", "am_fenrir", "am_puck", "am_adam", "am_eric", "am_liam", "am_onyx",
                 "am_echo", "bf_emma", "bf_isabella", "bf_alice", "bf_lily", "bm_george", "bm_fable", "bm_lewis",
                 "bm_daniel")  # kairu/voice/models.py KOKORO_SPEAKERS, the same; the first is the default
VOICE_STYLES = ("warm", "lively", "calm", "plain")  # kairu/voice/speak.py STYLES and plain; the first is the default
VOICE_MODELS = ("small-en-us", "small-en-in")  # kairu/voice/models.py describes each; the first is the default
VOICE_VOICES = ("uk-jenny", "indian-svbi", "us-hfc-female", "indian-tni", "indian-asi", "indian-rrbi", "us-kristin", "us-ryan",
                "us-joe", "uk-alba", "uk-cori", "uk-northern-male", "us-libritts-1093", "us-libritts-3905", "us-libritts-6694",
                "us-libritts-3490")  # Piper's voices in kairu/voice/models.py; the first is the default (uk-jenny since 14 Nov
#                                         2026: the owner didn't like indian-svbi, the default before)
MODEL = re.compile(r"[A-Za-z0-9@._:/-]{1,100}")
MISSION_LIMITS = {  # setting -> (default, lowest, highest)
    "max_hours": (4, 0.001, 12),
    "cpu_percent": (85, 10, 100),
    "cpu_minutes": (10, 0.05, 120),
    "max_celsius": (85, 40, 105),
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    voice_enabled: bool
    research_enabled: bool
    policy_path: Path
    data_dir: Path
    anchor_path: Path | None = None  # None: audit.anchor in data_dir
    protect_enabled: bool = False
    protect_check_seconds: float = 60
    protect_gmail_seconds: float = 120
    link_enabled: bool = False
    link_relay: str = DEFAULT_RELAY
    mission_max_hours: float = 4
    mission_cpu_percent: float = 85
    mission_cpu_minutes: float = 10
    mission_max_celsius: float = 85
    brain_public_to_cloud: bool = False
    brain_providers: tuple[str, ...] = BRAIN_DEFAULT
    brain_build_providers: tuple[str, ...] = ()  # brain.build_providers: who the Builder asks (BUILDER.md); () = brain.providers
    brain_daily_cap: int = 0
    brain_talk_history: bool = True
    brain_models: tuple[tuple[str, str], ...] = ()
    tasks_work_folder: Path | None = None  # None: Kairu-files in your user folder
    tasks_eyes: bool = False  # tasks.eyes: Kairu's eyes may send a picture of one window to Gemini (fails closed: off)
    bar_key: str = "Space"
    voice_model: str = "small-en-us"
    voice_engine: str = "whisper-base.en"
    voice_key: str = "V"
    voice_voice: str = "uk-jenny"
    voice_style: str = "warm"
    voice_tts: str = "kokoro"
    voice_kokoro: str = "af_heart"
    voice_listen_at_start: bool = False
    voice_barge_in: bool = False
    voice_live_every: float = 0.0  # voice.live_caption_every: 0 (off) or 0.1 to 2 seconds
    voice_hearing: str = "local"  # voice.hearing: "local" (Whisper on this PC) or "gemini" (VOICE.md "Gemini hearing")
    voice_gemini_model: str = ""  # voice.gemini_model: a Gemini model name, or "" for Kairu's own choice
    voice_camera: bool = False  # voice.camera: the camera checks your lips moved (VOICE.md "The camera check")
    voice_fast: bool = False  # voice.fast_orders
    voice_only_mine: bool = False  # voice.only_my_voice
    voice_live: bool = False  # voice.live: Kairu Live (LiveKit) is the bar's voice (VOICE.md "Kairu Live", ADR-052 proposed)
    voice_live_folder: str = ""  # voice.live_folder: the Kairu Live folder, with its .venv and .env

    @property
    def work_folder(self) -> Path:
        return self.tasks_work_folder or Path.home() / "Kairu-files"

    def brain_settings(self) -> dict:
        """What the brain's actions get from Guardian's own config.yaml (never from a request)."""
        return {"public_to_cloud": self.brain_public_to_cloud, "providers": list(self.brain_providers),
                "build_providers": list(self.brain_build_providers or self.brain_providers),
                "daily_cap": self.brain_daily_cap, "models": dict(self.brain_models), "research": self.research_enabled,
                "talk_history": self.brain_talk_history, "eyes": self.tasks_eyes}

    def feature_enabled(self, feature: str) -> bool:
        return {"voice": self.voice_enabled, "research": self.research_enabled}.get(feature, False)


def config_path() -> Path:
    """config.yaml at the project root, or the file named by KAIRU_CONFIG."""
    return Path(os.environ.get("KAIRU_CONFIG", DEFAULT_CONFIG))


def load(path: Path | None = None) -> Config:
    path = Path(path or config_path())
    raw = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected sections voice, research, guardian, protect, link, mission_mode and brain")
    unknown = set(raw) - {*FEATURES, "guardian", "protect", "link", "mission_mode", "brain", "tasks"}
    if unknown:
        raise ConfigError(f"{path}: unknown section(s) {', '.join(sorted(unknown))}")

    switches = {}
    for feature in FEATURES:
        section = raw.get(feature) or {}
        enabled = section.get("enabled", False) if isinstance(section, dict) else None
        if not isinstance(enabled, bool):
            raise ConfigError(f"{path}: {feature}.enabled must be true or false")
        switches[feature] = enabled

    guardian = raw.get("guardian") or {}
    if not isinstance(guardian, dict):
        raise ConfigError(f"{path}: guardian must be a section")
    protect = raw.get("protect") or {}
    if not isinstance(protect, dict) or set(protect) - {"enabled", "check_seconds", "gmail_seconds"}:
        raise ConfigError(f"{path}: protect takes only enabled, check_seconds and gmail_seconds")
    if not isinstance(protect.get("enabled", False), bool):
        raise ConfigError(f"{path}: protect.enabled must be true or false")
    every = {}
    for name, default in (("check_seconds", 60), ("gmail_seconds", 120)):
        value = protect.get(name, default)
        if type(value) not in (int, float) or not 0 < value <= 3600:
            raise ConfigError(f"{path}: protect.{name} must be a number of seconds from 1 to 3600")
        every[name] = float(value)
    link = raw.get("link") or {}
    if not isinstance(link, dict) or set(link) - {"enabled", "relay"}:
        raise ConfigError(f"{path}: link takes only enabled and relay")
    if not isinstance(link.get("enabled", False), bool):
        raise ConfigError(f"{path}: link.enabled must be true or false")
    relay = link.get("relay", DEFAULT_RELAY)
    if not isinstance(relay, str) or not RELAY.fullmatch(relay.rstrip("/")):
        raise ConfigError(f"{path}: link.relay must be an address like https://ntfy.sh")
    mission = raw.get("mission_mode") or {}
    if not isinstance(mission, dict) or set(mission) - set(MISSION_LIMITS):
        raise ConfigError(f"{path}: mission_mode takes only {', '.join(MISSION_LIMITS)}")
    limits = {}
    for name, (default, lowest, highest) in MISSION_LIMITS.items():
        value = mission.get(name, default)
        if type(value) not in (int, float) or not lowest <= value <= highest:
            raise ConfigError(f"{path}: mission_mode.{name} must be a number from {lowest:g} to {highest:g}")
        limits[name] = float(value)
    brain = _brain(path, raw.get("brain"))
    base = path.resolve().parent
    return Config(
        voice_enabled=switches["voice"],
        research_enabled=switches["research"],
        policy_path=base / guardian.get("policy", "policy.yaml"),
        data_dir=base / guardian.get("data_dir", "data"),
        anchor_path=base / guardian["anchor"] if guardian.get("anchor") else None,
        protect_enabled=protect.get("enabled", False),
        protect_check_seconds=every["check_seconds"],
        protect_gmail_seconds=every["gmail_seconds"],
        link_enabled=link.get("enabled", False),
        link_relay=relay.rstrip("/"),
        mission_max_hours=limits["max_hours"],
        mission_cpu_percent=limits["cpu_percent"],
        mission_cpu_minutes=limits["cpu_minutes"],
        mission_max_celsius=limits["max_celsius"],
        tasks_work_folder=_work_folder(path, raw.get("tasks")),
        bar_key=_bar_key(path, raw.get("tasks")),
        tasks_eyes=_eyes(path, raw.get("tasks")),
        **_voice(path, raw.get("voice"), _bar_key(path, raw.get("tasks"))),
        **brain,
    )


def _voice(path, section, bar_key: str) -> dict:
    section = section or {}
    if set(section) - {"enabled", "engine", "model", "key", "voice", "style", "tts", "kokoro_voice", "listen_at_start", "barge_in",
                       "live_caption_every", "fast_orders", "only_my_voice", "hearing", "gemini_model", "camera", "live",
                       "live_folder"}:
        raise ConfigError(f"{path}: voice takes only enabled, engine, model, key, voice, style, tts, kokoro_voice, listen_at_start, "
                          "barge_in, live_caption_every, fast_orders, only_my_voice, hearing, gemini_model, camera, live and "
                          "live_folder")
    switches = {}
    for name, field_name in (("listen_at_start", "listen_at_start"), ("barge_in", "barge_in"), ("fast_orders", "fast"),
                             ("only_my_voice", "only_mine"), ("camera", "camera"), ("live", "live")):
        value = section.get(name, False)
        if not isinstance(value, bool):
            raise ConfigError(f"{path}: voice.{name} must be true or false")
        switches[f"voice_{field_name}"] = value
    live = section.get("live_caption_every", 0)
    if isinstance(live, bool) or not isinstance(live, (int, float)) or not (live == 0 or 0.1 <= live <= 2):
        raise ConfigError(f"{path}: voice.live_caption_every must be 0 (off) or a number of seconds from 0.1 to 2")
    engine = section.get("engine", VOICE_ENGINES[0])
    engine = VOICE_ENGINE_NAMES.get(engine, engine) if isinstance(engine, str) else engine
    if engine not in VOICE_ENGINES:
        raise ConfigError(f"{path}: voice.engine must be one of {', '.join(VOICE_ENGINES)}")
    model = section.get("model", VOICE_MODELS[0])
    if model not in VOICE_MODELS:
        raise ConfigError(f"{path}: voice.model must be one of {', '.join(VOICE_MODELS)}")
    key = section.get("key", "V")
    if not (isinstance(key, str) and re.fullmatch(r"[A-JL-Za-jl-z]", key)):
        raise ConfigError(f"{path}: voice.key must be one letter, not K (Ctrl+Alt+K is the emergency stop)")
    if key.upper() == bar_key.upper():
        raise ConfigError(f"{path}: voice.key and tasks.bar_key must be different letters")
    voice = section.get("voice", VOICE_VOICES[0])
    if voice not in VOICE_VOICES:
        raise ConfigError(f"{path}: voice.voice must be one of {', '.join(VOICE_VOICES)}")
    style = section.get("style", VOICE_STYLES[0])
    if style not in VOICE_STYLES:
        raise ConfigError(f"{path}: voice.style must be one of {', '.join(VOICE_STYLES)}")
    tts = section.get("tts", VOICE_TTS[0])
    if tts not in VOICE_TTS:
        raise ConfigError(f"{path}: voice.tts must be one of {', '.join(VOICE_TTS)}")
    kokoro = section.get("kokoro_voice", KOKORO_VOICES[0])
    if kokoro not in KOKORO_VOICES:
        raise ConfigError(f"{path}: voice.kokoro_voice must be one of {', '.join(KOKORO_VOICES)}")
    hearing = section.get("hearing", "local")
    if hearing not in ("local", "gemini"):
        raise ConfigError(f"{path}: voice.hearing must be local (Whisper on this PC) or gemini (each sentence heard by Gemini)")
    gemini_model = section.get("gemini_model", "")
    if not (isinstance(gemini_model, str) and re.fullmatch(r"(?:gemini-[a-z0-9.-]{1,60})?", gemini_model)):
        raise ConfigError(f"{path}: voice.gemini_model must be a Gemini model name such as gemini-flash-lite-latest")
    live_folder = section.get("live_folder", "")
    if not isinstance(live_folder, str) or len(live_folder) > 260 or any(ord(c) < 32 for c in live_folder):
        raise ConfigError(f"{path}: voice.live_folder must be the Kairu Live folder, such as C:\\Users\\you\\kairu-live")
    return {"voice_live_folder": live_folder.strip(), "voice_model": model, "voice_engine": engine, "voice_key": key.upper(), "voice_voice": voice, "voice_style": style,
            "voice_tts": tts, "voice_kokoro": kokoro, "voice_live_every": float(live), "voice_hearing": hearing,
            "voice_gemini_model": gemini_model, **switches}


def _eyes(path, section) -> bool:
    eyes = (section or {}).get("eyes", False) if isinstance(section, dict) else False
    if not isinstance(eyes, bool):
        raise ConfigError(f"{path}: tasks.eyes must be true or false")
    return eyes


def _bar_key(path, section) -> str:
    key = (section or {}).get("bar_key", "Space")
    if key != "Space" and not (isinstance(key, str) and re.fullmatch(r"[A-JL-Za-jl-z]", key)):
        raise ConfigError(f"{path}: tasks.bar_key must be one letter, not K (Ctrl+Alt+K is the emergency stop), or Space")
    return key


def _work_folder(path, section) -> Path | None:
    section = section or {}
    if not isinstance(section, dict) or set(section) - {"work_folder", "bar_key", "eyes"}:
        raise ConfigError(f"{path}: tasks takes only work_folder, bar_key and eyes")
    folder = section.get("work_folder")
    if folder is None:
        return None
    if not isinstance(folder, str) or not os.path.isabs(os.path.expanduser(os.path.expandvars(folder))):
        raise ConfigError(f"{path}: tasks.work_folder must be a whole path, such as %USERPROFILE%\\Kairu-files")
    return Path(os.path.expanduser(os.path.expandvars(folder)))


def _brain(path, section) -> dict:
    section = section or {}
    if not isinstance(section, dict) or set(section) - {"public_to_cloud", "providers", "build_providers", "daily_cap", "models",
                                                        "talk_history"}:
        raise ConfigError(f"{path}: brain takes only public_to_cloud, providers, build_providers, daily_cap, models and "
                          "talk_history")
    history = section.get("talk_history", True)
    if not isinstance(history, bool):
        raise ConfigError(f"{path}: brain.talk_history must be true or false")
    public = section.get("public_to_cloud", False)
    if not isinstance(public, bool):
        raise ConfigError(f"{path}: brain.public_to_cloud must be true or false")
    providers = section.get("providers", list(BRAIN_DEFAULT))
    if (not isinstance(providers, list) or not providers or len(set(providers)) != len(providers)
            or not all(name in PROVIDER_NAMES for name in providers)):
        raise ConfigError(f"{path}: brain.providers must list some of {', '.join(PROVIDER_NAMES)}, each once")
    building = section.get("build_providers", [])
    if (not isinstance(building, list) or len(set(building)) != len(building)
            or not all(name in PROVIDER_NAMES for name in building)):
        raise ConfigError(f"{path}: brain.build_providers must list some of {', '.join(PROVIDER_NAMES)}, each once")
    cap = section.get("daily_cap", 0)
    if type(cap) is not int or not 0 <= cap <= 100000:
        raise ConfigError(f"{path}: brain.daily_cap must be a whole number (0: no cap)")
    models = section.get("models") or {}
    if not isinstance(models, dict) or not all(name in PROVIDER_NAMES and isinstance(model, str) and MODEL.fullmatch(model)
                                               for name, model in models.items()):
        raise ConfigError(f"{path}: brain.models maps a provider ({', '.join(PROVIDER_NAMES)}) to a model name")
    return {"brain_public_to_cloud": public, "brain_providers": tuple(providers), "brain_build_providers": tuple(building),
            "brain_daily_cap": cap,
            "brain_models": tuple(sorted(models.items())), "brain_talk_history": history}
