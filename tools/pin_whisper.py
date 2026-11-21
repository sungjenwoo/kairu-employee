r"""Pin the bigger Whisper hearing models (VOICE.md "The top hearing model"): you run this once, on a PC with internet.

    py -3.12 tools\pin_whisper.py            all four: large-v3-turbo, distil-large-v3, medium.en, small.en
    py -3.12 tools\pin_whisper.py large-v3-turbo

For each model it asks Hugging Face for the newest commit of its repository (kairu/voice/models.py BIG_REPOS, fixed in the
code), then for the file list at exactly that commit: every big file's SHA-256 is Hugging Face's own (Git LFS), and each
small file is downloaded once and hashed here. It writes kairu/voice/whisper_pins.json and downloads no model. Commit that
file in a pull request: from then on `kairu voice setup` downloads only those files, at that commit, each SHA-256 checked.
Only huggingface.co is asked; nothing about you or this PC is sent.
"""

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kairu.voice.models import BIG_FIRST, BIG_REPOS, PINS_FILE  # noqa: E402

API = "https://huggingface.co/api/models/"
SKIP = {".gitattributes", "README.md"}
MOST_SMALL = 20 * 2**20  # a file that is not in Git LFS is small; anything bigger than this is refused


def _get(url: str, opener=urllib.request.urlopen) -> bytes:
    with opener(url, timeout=60) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or not (final.hostname == "huggingface.co" or final.hostname.endswith(".hf.co")):
            raise SystemExit(f"pin_whisper: sent elsewhere ({final.hostname}); nothing written")
        return response.read(MOST_SMALL + 1)


def pin(key: str, opener=urllib.request.urlopen) -> dict:
    repo = BIG_REPOS[key]
    commit = json.loads(_get(f"{API}{repo}/revision/main", opener))["sha"]
    if len(commit) != 40:
        raise SystemExit(f"pin_whisper: {repo} gave no commit")
    tree = json.loads(_get(f"{API}{repo}/tree/{commit}", opener))
    files = []
    for entry in tree:
        name = entry.get("path", "")
        if entry.get("type") != "file" or name in SKIP or "/" in name:
            continue
        lfs = entry.get("lfs")
        if lfs:
            sha, size = lfs["oid"], int(lfs["size"])
        else:
            body = _get(f"https://huggingface.co/{repo}/resolve/{commit}/{name}", opener)
            if len(body) > MOST_SMALL:
                raise SystemExit(f"pin_whisper: {name} is too big for a file outside Git LFS")
            sha, size = hashlib.sha256(body).hexdigest(), len(body)
        files.append([name, sha, size])
    names = {name for name, *_ in files}
    if not {"config.json", "model.bin"} <= names:
        raise SystemExit(f"pin_whisper: {repo} at {commit} has no config.json and model.bin")
    return {"repo": repo, "commit": commit, "files": sorted(files)}


def main(argv=None) -> int:
    wanted = (argv if argv is not None else sys.argv[1:]) or list(BIG_FIRST)
    unknown = [key for key in wanted if key not in BIG_REPOS]
    if unknown:
        print(f"pin_whisper: no such model {', '.join(unknown)} (choose from {', '.join(BIG_FIRST)})")
        return 2
    try:
        pins = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pins = {}
    for key in wanted:
        print(f"Pinning Whisper {key} ({BIG_REPOS[key]}) ...", flush=True)
        pins[key] = pin(key)
        total = sum(size for _, _, size in pins[key]["files"]) / 2**20
        print(f"  commit {pins[key]['commit']}, {len(pins[key]['files'])} files, {total:.0f} MiB")
    PINS_FILE.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Written: {PINS_FILE}. Commit it, then set voice.engine in config.yaml and run `kairu voice setup`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
