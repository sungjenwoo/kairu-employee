"""The small offline speech models, and `kairu voice setup`, which you run yourself to download one.

Setup is never a Kairu action: no executor, skill or request can start it, and Guardian does not know it. It downloads
from alphacephei.com only (the address is built here, never taken from a setting), checks the file's SHA-256 against
the value pinned below, unpacks it into Guardian's data folder (data/voice/NAME), and deletes the download. A file whose
hash is wrong is deleted and nothing is unpacked. The models never go into the repository (.gitignore).

    small-en-us   vosk-model-small-en-us-0.15, US English, 39.3 MiB: the Vosk default (voice.engine: vosk, the fallback)
    small-en-in   vosk-model-small-en-in-0.4, Indian English, 35.8 MiB: the other choice, voice.model in config.yaml

Whisper base.en (voice.engine: whisper-base.en, the default) and tiny.en (whisper-tiny.en) come from huggingface.co
instead, file by file, each SHA-256 pinned below; Piper and its voices from github.com and huggingface.co, the same way.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

HOST = "alphacephei.com"
BASE = f"https://{HOST}/vosk/models/"
FOLDER = "voice"  # inside Guardian's data folder
MARK = "kairu-model.json"  # written last, once the model is unpacked and checked
MOST_UNPACKED = 300 * 2**20  # bytes; the small models unpack to under 70 MiB
READ = 64 * 1024


@dataclass(frozen=True)
class Model:
    key: str
    name: str  # the archive's name and its top folder
    sha256: str
    size: int  # bytes of the archive
    language: str

    @property
    def url(self) -> str:
        return f"{BASE}{self.name}.zip"

    @property
    def mib(self) -> float:
        return self.size / 2**20


MODELS = {
    "small-en-us": Model("small-en-us", "vosk-model-small-en-us-0.15",
                         "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498", 41205931, "US English"),
    "small-en-in": Model("small-en-in", "vosk-model-small-en-in-0.4",
                         "20663dcac4d5cb783a579c54d98339344a688e4ec6e1b4a4b059fd1235454cc7", 37573330, "Indian English"),
}
DEFAULT = "small-en-us"  # config.VOICE_MODELS lists the same names, this one first
# The speaker model for voice.only_my_voice (kairu/voice/myvoice.py): from alphacephei.com like the others. Its SHA-256 is the
# Git LFS oid of the copy on Hugging Face (mychen76/vosk-models, speaker_id/vosk-model-spk-0.4.zip, 13.9 MB, 15 Nov 2026):
# alphacephei publishes no hashes, so setup takes the file from alphacephei.com only if it is that same file. The size is
# a ceiling (the download stops past it); the SHA-256 is the check.
SPEAKER = Model("spk", "vosk-model-spk-0.4", "a74d8f51144484813e16af689bb0f916b7a111e2347f467c4933c1166097b5a7", 15_000_000,
                "speaker")


class SetupError(Exception):
    pass


class NotSetUp(Exception):
    pass


def folder(data_dir, key: str) -> Path:
    return Path(data_dir) / FOLDER / (SPEAKER if key == SPEAKER.key else MODELS[key]).name


def speaker_ready(data_dir) -> Path:
    """The speaker model's folder (voice.only_my_voice), if `kairu voice setup` put it there and checked it."""
    return ready(data_dir, SPEAKER.key)


def setup_speaker(data_dir, say=print, opener=None) -> Path:
    return setup(data_dir, SPEAKER.key, say, opener)


def ready(data_dir, key: str) -> Path:
    """The model's folder, if `kairu voice setup` put it there and checked it. Raises NotSetUp otherwise."""
    model = SPEAKER if key == SPEAKER.key else MODELS[key]
    place = folder(data_dir, key)
    try:
        mark = json.loads((place / MARK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mark = None
    if not isinstance(mark, dict) or mark.get("sha256") != model.sha256 or mark.get("name") != model.name:
        raise NotSetUp(f"the voice model ({model.name}) is not set up: run `kairu voice setup` (VOICE.md)")
    return place




def setup(data_dir, key: str, say=print, opener=None) -> Path:
    """Download, check and unpack one model. Returns its folder. Raises SetupError; then nothing is left half-done."""
    model = SPEAKER if key == SPEAKER.key else MODELS[key]
    target = folder(data_dir, key)
    try:
        return ready(data_dir, key)
    except NotSetUp:
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    download = target.parent / f"{model.name}.zip.part"
    try:
        say(f"Downloading {model.name} ({model.mib:.1f} MiB) from {HOST} ...")
        _fetch(model.url, model.sha256, model.size, model.name, download, opener, say, (HOST,))
        say("SHA-256 checked. Unpacking ...")
        _unpack(model.name, download, target)
        (target / MARK).write_text(json.dumps({"name": model.name, "sha256": model.sha256}), encoding="utf-8")
    finally:
        download.unlink(missing_ok=True)
    return ready(data_dir, key)


# --- Whisper, the default way Kairu hears you (voice.engine: whisper-base.en) -----------------------------------------
#
# OpenAI's Whisper base.en and tiny.en (MIT, weights MIT), converted for CTranslate2 by Systran, run by faster-whisper (MIT)
# on the CPU, int8. The files come from huggingface.co/Systran/faster-whisper-<model>, exactly as at the pinned commit, each
# SHA-256 checked, into data/voice/faster-whisper-<model> (the same folders and mark tools/hearing_test.py uses). base.en
# is the default since the owner's hearing test (10 Nov 2026: 10 of 10 orders right in their voice, tiny.en 8 of 10); its
# short peak of about 307 MiB, while it loads and with each sentence, is allowed by the owner (VOICE.md).

ENGINES = ("whisper-base.en", "whisper-tiny.en", "whisper-large-v3-turbo", "whisper-distil-large-v3", "whisper-medium.en",
           "whisper-small.en", "vosk")  # voice.engine; the first is the default (config.VOICE_ENGINES)
WHISPER_ENGINES = {"whisper-base.en": "base.en", "whisper-tiny.en": "tiny.en", "whisper-large-v3-turbo": "large-v3-turbo",
                   "whisper-distil-large-v3": "distil-large-v3", "whisper-medium.en": "medium.en",
                   "whisper-small.en": "small.en"}  # engine -> the Whisper model it hears with
WHISPER_MARK = "kairu-whisper.json"

# The bigger hearing models (your GO of 15 Nov 2026: "the top hearing one"). large-v3-turbo is the most accurate that still
# answers quickly on a laptop CPU (Whisper large-v3's encoder with 4 decoder layers, multilingual, about 1.6 GB on disk,
# about 1 GB of memory while it runs, int8); distil-large-v3 is English only and faster; medium.en and small.en are smaller
# steps up from base.en. They break the old "voice under 200 MB at rest" rule, with your OK. Their files are pinned the
# same way (a commit and each file's SHA-256), in whisper_pins.json beside this file: tools/pin_whisper.py writes it from
# Hugging Face's own file list at one commit, and it is reviewed in a pull request like any code. Without a pin, setup
# refuses and says how to make one; nothing unpinned is ever downloaded.
BIG_REPOS = {"large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
             "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
             "medium.en": "Systran/faster-whisper-medium.en", "small.en": "Systran/faster-whisper-small.en"}
PINS_FILE = Path(__file__).with_name("whisper_pins.json")
BIG_FIRST = ("large-v3-turbo", "distil-large-v3", "medium.en", "small.en")  # the most accurate first: the order tools/pin_whisper.py pins them in


@dataclass(frozen=True)
class Whisper:
    key: str
    repo: str
    commit: str  # the model's files exactly as at this commit
    files: tuple[tuple[str, str, int], ...]  # (name, SHA-256, size)

    def folder(self, data_dir) -> Path:
        return Path(data_dir) / FOLDER / f"faster-whisper-{self.key}"

    @property
    def mib(self) -> float:
        return sum(size for *_, size in self.files) / 2**20


_TOKENIZER = ("tokenizer.json", "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df", 2128466)
_VOCABULARY = ("vocabulary.txt", "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf", 422309)
WHISPERS = {
    "tiny.en": Whisper("tiny.en", "Systran/faster-whisper-tiny.en", "0d3d19a32d3338f10357c0889762bd8d64bbdeba", (
        ("config.json", "14b1b421a90349bc551b881461426b561a874049cb9e4c4864f2ca384f6a7cc5", 2317),
        ("model.bin", "1a5afae06a4db91c975c9a9d78be5cc110ee4ea022ad57d55492e4550e936b2a", 75537502), _TOKENIZER, _VOCABULARY)),
    "base.en": Whisper("base.en", "Systran/faster-whisper-base.en", "3d3d5dee26484f91867d81cb899cfcf72b96be6c", (
        ("config.json", "f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb", 2227),
        ("model.bin", "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef", 145216508), _TOKENIZER, _VOCABULARY)),
}
WHISPER = WHISPER_ENGINES[ENGINES[0]]  # base.en, the default engine's model


def _pinned(pins_file: Path = PINS_FILE) -> dict:
    """The bigger models whose files tools/pin_whisper.py pinned (whisper_pins.json); a model with a wrong entry is left out."""
    try:
        pins = json.loads(pins_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = {}
    for key, repo in BIG_REPOS.items():
        pin = pins.get(key) if isinstance(pins, dict) else None
        try:
            files = tuple((str(name), str(sha), int(size)) for name, sha, size in pin["files"])
            commit = str(pin["commit"])
        except (TypeError, KeyError, ValueError):
            continue
        names = {name for name, *_ in files}
        good = (pin.get("repo") == repo and len(commit) == 40 and {"config.json", "model.bin"} <= names and all(
            len(sha) == 64 and all(c in "0123456789abcdef" for c in sha) and size > 0 for _, sha, size in files) and all(
            "/" not in name and "\\" not in name and not name.startswith(".") for name in names))
        if good:
            found[key] = Whisper(key, repo, commit, files)
    return found


WHISPERS.update(_pinned())


def not_pinned(key: str) -> str:
    """Why this Whisper model can't be set up yet ("" if it can)."""
    if key in WHISPERS:
        return ""
    if key in BIG_REPOS:
        return (f"Whisper {key} is not pinned yet: run `py -3.12 tools\\pin_whisper.py` once (it reads Hugging Face's file "
                f"list for {BIG_REPOS[key]} and writes kairu\\voice\\whisper_pins.json), then `kairu voice setup` again")
    return f"there is no Whisper model {key}"


def whisper_mark(whisper: Whisper) -> dict:
    return {"repo": whisper.repo, "commit": whisper.commit, "sha256": [sha for _, sha, _ in whisper.files]}


def whisper_ready(data_dir, key: str = WHISPER) -> Path:
    """The Whisper model's folder, if `kairu voice setup` (or the hearing test) put it there and checked it."""
    if not_pinned(key):
        raise NotSetUp(not_pinned(key))
    whisper = WHISPERS[key]
    place = whisper.folder(data_dir)
    try:
        mark = json.loads((place / WHISPER_MARK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mark = None
    if mark != whisper_mark(whisper) or not all((place / name).is_file() for name, *_ in whisper.files):
        raise NotSetUp(f"the Whisper model ({whisper.key}) is not set up: run `kairu voice setup` (VOICE.md)")
    return place


def setup_whisper(data_dir, key: str = WHISPER, say=print, opener=None) -> Path:
    """Download and check the Whisper model's files. Returns its folder. Raises SetupError; a bad file is deleted."""
    if not_pinned(key):
        raise SetupError(not_pinned(key))
    try:
        return whisper_ready(data_dir, key)
    except NotSetUp:
        pass
    whisper = WHISPERS[key]
    place = whisper.folder(data_dir)
    place.mkdir(parents=True, exist_ok=True)
    (place / WHISPER_MARK).unlink(missing_ok=True)
    say(f"Downloading Whisper {whisper.key} ({whisper.mib:.0f} MiB) from huggingface.co/{whisper.repo} ...")
    for name, sha256, size in whisper.files:
        part = place / f"{name}.part"
        try:
            _fetch(f"https://huggingface.co/{whisper.repo}/resolve/{whisper.commit}/{name}", sha256, size, name, part, opener,
                   say, VOICE_HOSTS)
            os.replace(part, place / name)
        finally:
            part.unlink(missing_ok=True)
    (place / WHISPER_MARK).write_text(json.dumps(whisper_mark(whisper)), encoding="utf-8")
    say("SHA-256 checked.")
    return whisper_ready(data_dir, key)


def hearing_ready(data_dir, engine: str, vosk_model: str) -> Path:
    """The folder of the model this engine hears with (voice.engine, voice.model). Raises NotSetUp."""
    if engine in WHISPER_ENGINES:
        return whisper_ready(data_dir, WHISPER_ENGINES[engine])
    return ready(data_dir, vosk_model)


# --- Piper, the offline voice Kairu answers with ---------------------------------------------------------------------
#
# The MIT build of rhasspy/piper, release 2023.11.14-2, for Windows: piper.exe with onnxruntime (MIT) and espeak-ng
# (GPL-3.0), run as a separate program by voice.speak; nothing of it is imported or linked into Kairu. Its voices come from
# the official voice collection, rhasspy/piper-voices on Hugging Face, at its release v1.0.0. Each file's SHA-256 is pinned.

PIPER_RELEASE = "2023.11.14-2"
PIPER_HOSTS = ("github.com", ".githubusercontent.com")  # GitHub hands release files out from its own download hosts
VOICE_HOSTS = ("huggingface.co", ".hf.co")  # and Hugging Face from its own
VOICES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/"


@dataclass(frozen=True)
class Piece:
    """One file to download: where from, its pinned SHA-256 and size, and the hosts it may come from."""
    name: str
    url: str
    sha256: str
    size: int
    hosts: tuple[str, ...]

    @property
    def mib(self) -> float:
        return self.size / 2**20


PIPER = Piece(f"piper-{PIPER_RELEASE}", f"https://github.com/rhasspy/piper/releases/download/{PIPER_RELEASE}/piper_windows_amd64.zip",
              "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea", 22477236, PIPER_HOSTS)


@dataclass(frozen=True)
class Voice:
    key: str
    name: str  # the voice's file name, without .onnx
    path: str  # where it sits in the collection
    label: str
    onnx: Piece
    config: Piece  # its .onnx.json
    speaker: int | None = None  # for a voice with many speakers: which one


def _voice(key, path, label, onnx_sha, onnx_size, json_sha, json_size, speaker=None) -> Voice:
    name = path.rsplit("/", 1)[-1]
    return Voice(key, name, path, label,
                 Piece(f"{name}.onnx", f"{VOICES_BASE}{path}.onnx", onnx_sha, onnx_size, VOICE_HOSTS),
                 Piece(f"{name}.onnx.json", f"{VOICES_BASE}{path}.onnx.json", json_sha, json_size, VOICE_HOSTS), speaker)


L2ARCTIC = ("en_US/l2arctic/medium/en_US-l2arctic-medium", "d89f6f124bf1e7735b2179d2141b8001c3e19169d5e743ed6e35624f4c76f044",
            76778673, "a97e2ba653e9efcdc1bdcec64a398c8beb19ae5e8dfdbfe4ad6841983e56c07c", 5252)  # one file, 24 speakers
LIBRITTS_R = ("en_US/libritts_r/medium/en_US-libritts_r-medium", "10bb85e071d616fcf4071f369f1799d0491492ab3c5d552ec19fb548fac13195",
              78580914, "b471dc60d2d8335e819c393d196d6fbf792817f40051257b269878505bc9afb3", 20123)  # one file, 904 speakers


def _speaker(key, label, file, speaker) -> Voice:
    path, onnx_sha, onnx_size, json_sha, json_size = file
    return _voice(key, path, label, onnx_sha, onnx_size, json_sha, json_size, speaker=speaker)


def _single(key, path, label, onnx_sha, json_sha, json_size, onnx_size=63201294) -> Voice:
    return _voice(key, path, label, onnx_sha, onnx_size, json_sha, json_size)


# All medium quality, from piper-voices v1.0.0; each one's licence is in VOICE.md. The first three were the gate's first
# choice (7 Nov 2026); the rest the owner asked for after hearing them (8 Nov 2026). Dropped for their licence: amy (no
# licence found for its recordings), lessac (a research licence, granted only to named people), alan (its recordings are
# "All Rights Reserved").
VOICES = {
    "indian-svbi": _speaker("indian-svbi", "Indian English, female (speaker SVBI of L2-ARCTIC)", L2ARCTIC, 2),
    "uk-jenny": _voice("uk-jenny", "en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium", "British English, female (Jenny (Dioco))",
                       "469c630d209e139dd392a66bf4abde4ab86390a0269c1e47b4e5d7ce81526b01", 63201294,
                       "a9a7a93a317c9a3cb6563e37eb057df9ef09c06188a8a4341b0fcb58cba54dd4", 4895),
    "us-hfc-female": _voice("us-hfc-female", "en_US/hfc_female/medium/en_US-hfc_female-medium", "US English, female (HFC)",
                            "914c473788fc1fa8b63ace1cdcdb44588f4ae523d3ab37df1536616835a140b7", 63201294,
                            "03f1fa0622b80463283592d97aca9f6e89aec345a5c56b7257723e0093c58b6c", 5033),
    "indian-tni": _speaker("indian-tni", "Indian English, female (speaker TNI of L2-ARCTIC)", L2ARCTIC, 9),
    "indian-asi": _speaker("indian-asi", "Indian English, male (speaker ASI of L2-ARCTIC)", L2ARCTIC, 10),
    "indian-rrbi": _speaker("indian-rrbi", "Indian English, male (speaker RRBI of L2-ARCTIC)", L2ARCTIC, 19),
    "us-kristin": _single("us-kristin", "en_US/kristin/medium/en_US-kristin-medium", "US English, female (Kristin)",
                          "5849957f929cbf720c258f8458692d6103fff2f0e3d3b19c8259474bb06a18d4",
                          "5681426d4aead22195de70531eeeeddb46493cfaffc5764b2ea3db73428b651c", 4968, onnx_size=63531379),
    "us-ryan": _single("us-ryan", "en_US/ryan/medium/en_US-ryan-medium", "US English, male (Ryan)",
                       "abf4c274862564ed647ba0d2c47f8ee7c9b717d27bdad9219100eb310db4047a",
                       "44034c056cb15681b2ad494307c7f3f2e4499d1253c700c711fa0a4607ffe78d", 4883),
    "us-joe": _single("us-joe", "en_US/joe/medium/en_US-joe-medium", "US English, male (Joe)",
                      "58afce0321b8d9c46d7cdf9c16500cc55a793b4220212dba6b70fb788b3baf06",
                      "3d6d5410b3795cb1950595247ef8f06190719e6fdbfa3a2356d8ec368e1aad33", 4794),
    "uk-alba": _single("uk-alba", "en_GB/alba/medium/en_GB-alba-medium", "Scottish English, female (Alba)",
                       "401369c4a81d09fdd86c32c5c864440811dbdcc66466cde2d64f7133a66ad03b",
                       "aa965a2f02ecced632c2694e1fc72bbff6d65f265fab567ca945918c73dd89f4", 4888),
    "uk-cori": _single("uk-cori", "en_GB/cori/medium/en_GB-cori-medium", "British English, female (Cori)",
                       "1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d",
                       "e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36", 4966, onnx_size=63531379),
    "uk-northern-male": _single("uk-northern-male", "en_GB/northern_english_male/medium/en_GB-northern_english_male-medium",
                                "Northern English, male", "57a219ae8e638873db7d18893304be5069c42868f392bb95c3ff17f0690d0689",
                                "69557ed3d974463453e9b0c09dd99a7ed0e52b8b87b64b357dbeeb2540a97d47", 4847),
    # LibriTTS-R's four warmest by measure (8 Nov 2026): darkest tone, steadiest pace, of every 15th of its 904 speakers
    "us-libritts-1093": _speaker("us-libritts-1093", "US English, female (LibriTTS-R speaker 1093)", LIBRITTS_R, 120),
    "us-libritts-3905": _speaker("us-libritts-3905", "US English, female (LibriTTS-R speaker 3905)", LIBRITTS_R, 450),
    "us-libritts-6694": _speaker("us-libritts-6694", "US English, male (LibriTTS-R speaker 6694)", LIBRITTS_R, 90),
    "us-libritts-3490": _speaker("us-libritts-3490", "US English, male (LibriTTS-R speaker 3490)", LIBRITTS_R, 435),
}
DEFAULT_VOICE = "uk-jenny"  # config.VOICE_VOICES lists the same keys, this one first (indian-svbi until 14 Nov 2026)
PIPER_MARK, VOICE_FOLDER = "kairu-piper.json", "piper-voices"


# --- Kokoro, the human-sounding voice (VOICE.md "Kokoro", 15 Nov 2026) ----------------------------------------------
#
# Kokoro-82M (Apache-2.0 weights) as the int8 ONNX model and its 54 voices, from the official release of kokoro-onnx (MIT)
# on GitHub, model-files-v1.0, each file SHA-256 pinned. It runs in its own program, kairu/voice/kokoro_worker.py, which
# needs `pip install -e .[kokoro]` (kokoro-onnx, with phonemizer and espeak-ng, both GPL-3.0, kept in that program only).

KOKORO_RELEASE = "model-files-v1.0"
KOKORO_BASE = f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/{KOKORO_RELEASE}/"
KOKORO_MODEL = Piece("kokoro-v1.0.int8.onnx", f"{KOKORO_BASE}kokoro-v1.0.int8.onnx",
                     "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb", 92361271, PIPER_HOSTS)
KOKORO_VOICES = Piece("voices-v1.0.bin", f"{KOKORO_BASE}voices-v1.0.bin",
                      "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28214398, PIPER_HOSTS)
KOKORO_FOLDER, KOKORO_MARK = "kokoro-v1.0", "kairu-kokoro.json"
# The English voices in voices-v1.0.bin: key -> (label, Kokoro's language). The first is the default.
KOKORO_SPEAKERS = {
    "af_heart": ("US English, female (Heart): warm", "en-us"), "af_bella": ("US English, female (Bella)", "en-us"),
    "af_nicole": ("US English, female (Nicole): soft", "en-us"), "af_sarah": ("US English, female (Sarah)", "en-us"),
    "af_aoede": ("US English, female (Aoede)", "en-us"), "af_kore": ("US English, female (Kore)", "en-us"),
    "af_nova": ("US English, female (Nova)", "en-us"), "af_sky": ("US English, female (Sky)", "en-us"),
    "af_alloy": ("US English, female (Alloy)", "en-us"), "af_jessica": ("US English, female (Jessica)", "en-us"),
    "af_river": ("US English, female (River)", "en-us"),
    "am_michael": ("US English, male (Michael)", "en-us"), "am_fenrir": ("US English, male (Fenrir)", "en-us"),
    "am_puck": ("US English, male (Puck)", "en-us"), "am_adam": ("US English, male (Adam)", "en-us"),
    "am_eric": ("US English, male (Eric)", "en-us"), "am_liam": ("US English, male (Liam)", "en-us"),
    "am_onyx": ("US English, male (Onyx)", "en-us"), "am_echo": ("US English, male (Echo)", "en-us"),
    "bf_emma": ("British English, female (Emma)", "en-gb"), "bf_isabella": ("British English, female (Isabella)", "en-gb"),
    "bf_alice": ("British English, female (Alice)", "en-gb"), "bf_lily": ("British English, female (Lily)", "en-gb"),
    "bm_george": ("British English, male (George)", "en-gb"), "bm_fable": ("British English, male (Fable)", "en-gb"),
    "bm_lewis": ("British English, male (Lewis)", "en-gb"), "bm_daniel": ("British English, male (Daniel)", "en-gb"),
}
DEFAULT_KOKORO = "af_heart"


def kokoro_ready(data_dir) -> tuple[Path, Path]:
    """(the model, the voices file), if `kairu voice setup` put them there and checked them. Raises NotSetUp otherwise."""
    place = Path(data_dir) / FOLDER / KOKORO_FOLDER
    try:
        mark = json.loads((place / KOKORO_MARK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mark = None
    files = (place / KOKORO_MODEL.name, place / KOKORO_VOICES.name)
    if (not isinstance(mark, dict) or mark.get("sha256") != [KOKORO_MODEL.sha256, KOKORO_VOICES.sha256]
            or not all(file.is_file() for file in files)):
        raise NotSetUp("Kokoro is not set up: run `kairu voice setup` (VOICE.md \"Kokoro\")")
    return files


def setup_kokoro(data_dir, say=print, opener=None) -> Path:
    try:
        return kokoro_ready(data_dir)[0].parent
    except NotSetUp:
        pass
    place = Path(data_dir) / FOLDER / KOKORO_FOLDER
    place.mkdir(parents=True, exist_ok=True)
    say(f"Downloading Kokoro ({KOKORO_MODEL.mib + KOKORO_VOICES.mib:.0f} MiB) from github.com/thewh1teagle/kokoro-onnx ...")
    for piece in (KOKORO_MODEL, KOKORO_VOICES):
        part = place / f"{piece.name}.part"
        try:
            _fetch(piece.url, piece.sha256, piece.size, piece.name, part, opener, say, piece.hosts)
            os.replace(part, place / piece.name)
        finally:
            part.unlink(missing_ok=True)
    (place / KOKORO_MARK).write_text(json.dumps({"name": KOKORO_RELEASE, "sha256": [KOKORO_MODEL.sha256, KOKORO_VOICES.sha256]}),
                                     encoding="utf-8")
    say("SHA-256 checked.")
    return kokoro_ready(data_dir)[0].parent


def kokoro_installed() -> bool:
    """Whether kokoro-onnx is installed (`pip install -e .[kokoro]`), without loading it into this program."""
    import importlib.util
    return importlib.util.find_spec("kokoro_onnx") is not None


def piper_folder(data_dir) -> Path:
    return Path(data_dir) / FOLDER / PIPER.name


def piper_ready(data_dir) -> Path:
    """piper.exe, if `kairu voice setup` put it there and checked it. Raises NotSetUp otherwise."""
    place = piper_folder(data_dir)
    try:
        mark = json.loads((place / PIPER_MARK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mark = None
    if not isinstance(mark, dict) or mark.get("sha256") != PIPER.sha256 or not (place / "piper.exe").is_file():
        raise NotSetUp(f"Piper ({PIPER.name}) is not set up: run `kairu voice setup` (VOICE.md)")
    return place / "piper.exe"


def voice_ready(data_dir, key: str) -> tuple[Path, Path, int | None]:
    """(the voice's .onnx, its .onnx.json, its speaker), if set up and checked. Raises NotSetUp otherwise."""
    voice = VOICES[key]
    place = Path(data_dir) / FOLDER / VOICE_FOLDER
    try:
        mark = json.loads((place / f"{voice.name}.kairu.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mark = None
    files = (place / voice.onnx.name, place / voice.config.name)
    if (not isinstance(mark, dict) or mark.get("sha256") != [voice.onnx.sha256, voice.config.sha256]
            or not all(file.is_file() for file in files)):
        raise NotSetUp(f"the voice {key} ({voice.name}) is not set up: run `kairu voice setup` (VOICE.md)")
    return files[0], files[1], voice.speaker


def setup_piper(data_dir, say=print, opener=None) -> Path:
    try:
        return piper_ready(data_dir)
    except NotSetUp:
        pass
    target = piper_folder(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    download = target.parent / f"{PIPER.name}.zip.part"
    try:
        say(f"Downloading Piper {PIPER_RELEASE} for Windows ({PIPER.mib:.1f} MiB) from github.com/rhasspy/piper ...")
        _fetch(PIPER.url, PIPER.sha256, PIPER.size, PIPER.name, download, opener, say, PIPER.hosts)
        say("SHA-256 checked. Unpacking ...")
        _unpack("piper", download, target)
        (target / PIPER_MARK).write_text(json.dumps({"name": PIPER.name, "sha256": PIPER.sha256}), encoding="utf-8")
    finally:
        download.unlink(missing_ok=True)
    return piper_ready(data_dir)


def setup_voice(data_dir, key: str, say=print, opener=None) -> Path:
    try:
        return voice_ready(data_dir, key)[0]
    except NotSetUp:
        pass
    voice = VOICES[key]
    place = Path(data_dir) / FOLDER / VOICE_FOLDER
    place.mkdir(parents=True, exist_ok=True)
    say(f"Downloading the voice {key}: {voice.label} ({voice.onnx.mib:.1f} MiB) from huggingface.co/rhasspy/piper-voices ...")
    for piece in (voice.onnx, voice.config):
        part = place / f"{piece.name}.part"
        try:
            _fetch(piece.url, piece.sha256, piece.size, piece.name, part, opener, say, piece.hosts)
            os.replace(part, place / piece.name)
        finally:
            part.unlink(missing_ok=True)
    mark = {"name": voice.name, "sha256": [voice.onnx.sha256, voice.config.sha256]}
    (place / f"{voice.name}.kairu.json").write_text(json.dumps(mark), encoding="utf-8")
    say("SHA-256 checked.")
    return voice_ready(data_dir, key)[0]


# --- the download and the unpacking, for every piece ------------------------------------------------------------------

def _host_allowed(host: str | None, hosts: tuple[str, ...]) -> bool:
    return bool(host) and any(host == allowed or (allowed.startswith(".") and host.endswith(allowed)) for allowed in hosts)


def _fetch(url: str, sha256: str, size: int, name: str, path: Path, opener, say, hosts: tuple[str, ...]) -> None:
    """Download url to path, checking where it really came from, its size and its SHA-256. SetupError, path deleted, if not.

    The download code is loaded only here, so voice.listen and voice.speak, which only read the files, stay small."""
    import hashlib
    import urllib.parse
    import urllib.request
    opener = opener or urllib.request.urlopen
    digest, got = hashlib.sha256(), 0
    try:
        response = opener(url, timeout=60)
    except OSError as error:
        raise SetupError(f"{url} could not be reached ({error})") from None
    try:
        with response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or not _host_allowed(final.hostname, hosts):
                raise SetupError(f"the download was sent elsewhere ({final.scheme}://{final.hostname}); nothing was kept")
            with open(path, "wb") as out:
                while chunk := response.read(READ):
                    got += len(chunk)
                    if got > size:
                        raise SetupError(f"the download is larger than {name} ({size} bytes); it was deleted")
                    digest.update(chunk)
                    out.write(chunk)
                    if got // (8 * 2**20) != (got - len(chunk)) // (8 * 2**20):
                        say(f"  {got / 2**20:.0f} of {size / 2**20:.0f} MiB")
        if digest.hexdigest() != sha256:
            raise SetupError(f"the download's SHA-256 is {digest.hexdigest()}, not the pinned {sha256}: it was deleted, and "
                             "nothing was unpacked")
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _unpack(top: str, archive: Path, target: Path) -> None:
    """Every file must sit inside the archive's own top folder: no absolute names, no "..", no links, a size limit."""
    import shutil
    import zipfile
    staging = target.with_name(target.name + ".unpacking")
    shutil.rmtree(staging, ignore_errors=True)
    total = 0
    try:
        with zipfile.ZipFile(archive) as packed:
            for member in packed.infolist():
                parts = PurePosixPath(member.filename.replace("\\", "/")).parts
                if (not parts or parts[0] != top or any(part in ("", ".", "..") or ":" in part for part in parts)
                        or member.filename.startswith(("/", "\\"))):
                    raise SetupError(f"the archive holds a file outside {top}/ ({member.filename[:80]!r}); nothing was kept")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise SetupError(f"the archive holds a link ({member.filename[:80]!r}); nothing was kept")
                total += member.file_size
                if total > MOST_UNPACKED:
                    raise SetupError("the archive unpacks to more than it should; nothing was kept")
                inside = staging.joinpath(*parts[1:]) if len(parts) > 1 else staging
                if member.is_dir():
                    inside.mkdir(parents=True, exist_ok=True)
                    continue
                inside.parent.mkdir(parents=True, exist_ok=True)
                with packed.open(member) as source, open(inside, "wb") as out:
                    shutil.copyfileobj(source, out, READ)
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    except zipfile.BadZipFile as error:
        raise SetupError(f"the download is not a usable archive ({error}); nothing was kept") from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
