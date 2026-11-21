"""Putting the Kairu phone app on the owner's phone with ADB (PHONE.md). Owner commands, never Kairu actions.

    kairu phone pair <ip:port> <code>    once: Wireless debugging's "Pair device with pairing code"
    kairu phone connect <ip:port>        Wireless debugging's own address (it changes when Wi-Fi changes)
    kairu phone install [file]           the app from GitHub (a kairu-phone*.apk, or the artifact's .zip)
    kairu phone status                   adb found? phone connected? which app file is newest?

The app is built on GitHub (.github/workflows/phone.yml); the PC only needs Google's platform-tools (adb), never Android
Studio. adb runs with its path and arguments as a list: no shell. These commands only move the app to the phone; they don't
start Guardian, Kairu or anything on the phone.
"""

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

LONGEST_APP = 200 * 1024 * 1024
APP_NAME = re.compile(r"kairu-phone[-.\w]*(?: \(\d{1,3}\))?\.(apk|zip)$", re.IGNORECASE)  # "kairu-phone (1).zip": a browser's second copy
ADDRESS = re.compile(r"^[A-Za-z0-9.\-:\[\]]+:\d{1,5}$")
PAIRING_CODE = re.compile(r"^\d{6}$")


class PhoneError(Exception):
    """Its text says what to do."""


def adb_places() -> list[Path]:
    places = [Path("C:/platform-tools/adb.exe")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        places.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    places.append(Path.home() / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb"))
    return places


def find_adb() -> str:
    for place in adb_places():
        if place.is_file():
            return str(place)
    found = shutil.which("adb")
    if found:
        return found
    raise PhoneError("adb isn't installed. Download Google's SDK Platform-Tools for Windows and unzip it to "
                     "C:\\platform-tools (PHONE.md, step 2).")


def run(adb: str, *arguments: str, seconds: float = 60) -> subprocess.CompletedProcess:
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        return subprocess.run([adb, *arguments], capture_output=True, text=True, timeout=seconds, **flags)
    except subprocess.TimeoutExpired:
        raise PhoneError(f"adb {arguments[0]} took longer than {int(seconds)} seconds. Is the phone on the same Wi-Fi?")


def devices(adb: str) -> list[str]:
    """Phones adb can use now (state "device"), by serial."""
    listed = run(adb, "devices", seconds=20).stdout
    found = []
    for line in listed.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            found.append(parts[0])
    return found


def downloads() -> Path:
    return Path.home() / "Downloads"


def newest_app(folder: Path | None = None) -> Path | None:
    folder = folder or downloads()
    try:
        found = [path for path in folder.iterdir() if path.is_file() and APP_NAME.search(path.name)]
    except OSError:
        return None
    return max(found, key=lambda path: path.stat().st_mtime) if found else None


def app_from(path: Path, data_dir: Path) -> Path:
    """The .apk to install: the file itself, or the one .apk inside GitHub's artifact .zip (copied to data/phone)."""
    path = Path(path)
    if not path.is_file():
        raise PhoneError(f"{path} isn't there.")
    if path.stat().st_size > LONGEST_APP:
        raise PhoneError(f"{path.name} is too big to be the Kairu app.")
    if path.suffix.lower() == ".apk":
        return path
    if path.suffix.lower() != ".zip":
        raise PhoneError(f"{path.name} is neither the app (.apk) nor GitHub's artifact (.zip).")
    try:
        with zipfile.ZipFile(path) as archive:
            inside = [item for item in archive.infolist() if item.filename.lower().endswith(".apk") and not item.is_dir()]
            if len(inside) != 1:
                raise PhoneError(f"{path.name} should hold exactly one .apk; it holds {len(inside)}.")
            item = inside[0]
            if item.file_size > LONGEST_APP:
                raise PhoneError(f"The app inside {path.name} is too big.")
            target_dir = Path(data_dir) / "phone"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / Path(item.filename).name  # the name only: nothing can be written outside data/phone
            with archive.open(item) as source, open(target, "wb") as copy:
                shutil.copyfileobj(source, copy)
            return target
    except zipfile.BadZipFile:
        raise PhoneError(f"{path.name} isn't a whole .zip; download it again.")


def one_phone(adb: str) -> str:
    found = devices(adb)
    if not found:
        raise PhoneError("No phone is connected. On the phone, open Wireless debugging and run "
                         "`kairu phone connect <the IP address and port it shows>` (PHONE.md, step 4).")
    if len(found) > 1:
        raise PhoneError(f"{len(found)} phones are connected ({', '.join(found)}); disconnect the others with `adb disconnect`.")
    return found[0]


def install(app: Path, adb: str | None = None) -> str:
    adb = adb or find_adb()
    phone = one_phone(adb)
    done = run(adb, "-s", phone, "install", "-r", str(app), seconds=180)
    said = (done.stdout + done.stderr).strip()
    if done.returncode != 0 or "Success" not in said:
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in said:
            raise PhoneError("This build is signed with a different key than the Kairu app on the phone. Uninstall Kairu "
                             "on the phone once (its pairing goes too), then install again (PHONE.md).")
        if "INSTALL_FAILED_VERSION_DOWNGRADE" in said:
            raise PhoneError("The phone has a newer Kairu app than this file. Download the newest build from GitHub.")
        raise PhoneError(f"The phone refused the app: {said.splitlines()[-1] if said else 'no reason given'}")
    return phone


def pair(address: str, code: str, adb: str | None = None) -> str:
    if not ADDRESS.match(address or ""):
        raise PhoneError("Give the address the phone shows under 'Pair device with pairing code', like 192.168.1.5:37145.")
    if not PAIRING_CODE.match(code or ""):
        raise PhoneError("The pairing code is the 6 digits the phone shows.")
    adb = adb or find_adb()
    done = run(adb, "pair", address, code, seconds=30)
    said = (done.stdout + done.stderr).strip()
    if done.returncode != 0 or "Successfully paired" not in said:
        raise PhoneError(f"Pairing didn't work: {said.splitlines()[-1] if said else 'no answer'}. The code changes each time; try again.")
    return said


def connect(address: str, adb: str | None = None) -> str:
    if not ADDRESS.match(address or ""):
        raise PhoneError("Give the address Wireless debugging shows at the top (not the pairing one), like 192.168.1.5:41823.")
    adb = adb or find_adb()
    done = run(adb, "connect", address, seconds=20)
    said = (done.stdout + done.stderr).strip()
    if "connected to" not in said or "failed" in said.lower() or "cannot" in said.lower():
        raise PhoneError(f"Couldn't connect: {said or 'no answer'}. Is Wireless debugging still on, on the same Wi-Fi?")
    return said
