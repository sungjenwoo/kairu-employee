"""research.location: "where am I?" answered with the area and city, from Windows' own location (the owner's choice,
19 Nov 2026: "when I say where am I, then it should locate my location, it is very useful").

    asked(text)   whether this question asks where you are ("where am I", "what's my location", "which area am I in")
    main(...)     the Guardian action (Medium, private, like the weather): Windows' location service gives this PC's
                  position (Settings > Privacy & security > Location must be on); it is rounded to 2 decimals (about
                  1 km) and only that goes to OpenStreetMap's reverse lookup, at its fixed address, to name the area and
                  city. What it found goes into data/research.db under the job's id, as names only, never instructions;
                  the exact position is never stored, sent or shown
    answer(found) the short spoken answer and one follow-up question (Tenmin), from those names only
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse

from kairu.research.store import ResearchStore

REVERSE = "https://nominatim.openstreetmap.org/reverse"
HOSTS = ("nominatim.openstreetmap.org",)
WAIT_SECONDS = 6
FIND_SECONDS = 12  # Windows' location service: usually 1-3 s from Wi-Fi
MOST_BYTES = 64 * 1024
ROUND = 2  # decimals: about 1.1 km, so no house or street is ever looked up
JOB = re.compile(r"[0-9a-f]{16}")
TEST_LOCATION = "KAIRU_TEST_LOCATION"  # the tests' pretend PC: a JSON file {"position": [lat, lon] or "denied", "address": {...}}
AGENT = "Kairu/1.0 (personal assistant on the owner's PC; https://github.com/sungjenwoo/Kairuu)"

ASK = re.compile(
    r"(?:(?:hey|ok|okay)\s+)?(?:kairu[\s,:!.-]*)?(?:please\s+)?(?:can you\s+|could you\s+)?(?:"
    r"where\s+am\s+i(?:\s+(?:now|right now|at the moment|currently))?"
    r"|(?:what(?:'s| is)?|whats|tell me|show me|say|find|check|get)\s+(?:is\s+)?(?:my|this pc'?s|the pc'?s)\s+"
    r"(?:current\s+|exact\s+|present\s+)?(?:location|area|place|city|locality)(?:\s+(?:now|right now))?"
    r"|(?:which|what)\s+(?:area|city|place|locality|town)\s+am\s+i\s+in(?:\s+(?:now|right now))?"
    r"|locate\s+me|find\s+me|my\s+(?:current\s+)?location)",
    re.IGNORECASE)

# Windows PowerShell's own .NET location service (System.Device, part of Windows): no package, no window
WINDOWS_SCRIPT = r"""
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::Default)
$null = $w.TryStart($false, [TimeSpan]::FromSeconds(8))
$t = 0
while (($w.Status -ne 'Ready') -and ($w.Permission -ne 'Denied') -and ($t -lt 90)) { Start-Sleep -Milliseconds 100; $t++ }
if ($w.Permission -eq 'Denied') { 'DENIED' } else {
  $l = $w.Position.Location
  if ($l.IsUnknown) { 'UNKNOWN' } else {
    [string]::Format([Globalization.CultureInfo]::InvariantCulture, '{0:F5},{1:F5}', $l.Latitude, $l.Longitude) }
}
$w.Stop()
"""
NO_LOCATION = ("Windows' location is off, so I can't tell where you are. Turn it on in Settings, Privacy & security, "
               "Location, with 'Let desktop apps access your location' on, then ask again.")


def asked(text: str) -> bool:
    said = " ".join((text or "").split()).strip(" ?.!,")
    return ASK.fullmatch(said) is not None


# --- the action ------------------------------------------------------------------------------------------------------

def main(data_dir: str, job: str) -> None:
    if not JOB.fullmatch(job):
        print("research.location: not a job id", file=sys.stderr)
        raise SystemExit(1)
    store = ResearchStore(data_dir)
    try:
        position = _pretend_position() if os.environ.get(TEST_LOCATION) else _windows_position()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"research.location: no position ({type(error).__name__})", file=sys.stderr, flush=True)
        position = None
    if position is None:
        store.put(job, "location", {"problem": NO_LOCATION})
        return
    lat, lon = (round(value, ROUND) for value in position)
    try:
        address = _pretend_address() if os.environ.get(TEST_LOCATION) else _reverse(lat, lon)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"research.location: OpenStreetMap did not answer ({type(error).__name__})", file=sys.stderr, flush=True)
        store.put(job, "location", {"problem": f"the map service did not answer ({type(error).__name__})"})
        return
    store.put(job, "location", _tidy(address))


def reverse_address(lat: float, lon: float) -> str:
    """The one address that is asked: the rounded position only (tests read it)."""
    query = {"format": "jsonv2", "lat": f"{round(lat, ROUND):.{ROUND}f}", "lon": f"{round(lon, ROUND):.{ROUND}f}",
             "zoom": 14, "addressdetails": 1, "accept-language": "en"}
    return f"{REVERSE}?{urllib.parse.urlencode(query)}"


def _windows_position() -> tuple[float, float] | None:
    if sys.platform != "win32":
        return None
    shell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", WINDOWS_SCRIPT], capture_output=True,
                          text=True, timeout=FIND_SECONDS, creationflags=0x08000000)  # CREATE_NO_WINDOW
    return _position_of(done.stdout)


def _position_of(said: str) -> tuple[float, float] | None:
    found = re.search(r"(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)", said or "")
    if not found:
        return None
    lat, lon = float(found[1]), float(found[2])
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _reverse(lat: float, lon: float) -> dict:
    import urllib.request  # only here: the action's own process, never the brain or Guardian
    address = reverse_address(lat, lon)
    if urllib.parse.urlsplit(address).hostname not in HOSTS:
        raise ValueError("not OpenStreetMap")
    request = urllib.request.Request(address, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=WAIT_SECONDS) as response:
        if urllib.parse.urlsplit(response.geturl()).hostname not in HOSTS:
            raise ValueError("sent elsewhere")
        return json.loads(response.read(MOST_BYTES)).get("address") or {}


def _pretend() -> dict:
    with open(os.environ[TEST_LOCATION], encoding="utf-8") as file:
        return json.load(file)


def _pretend_position() -> tuple[float, float] | None:
    position = _pretend().get("position")
    return tuple(position) if isinstance(position, list) and len(position) == 2 else None


def _pretend_address() -> dict:
    return _pretend().get("address") or {}


def _name(value) -> str:
    text = " ".join(str(value or "").split())
    return text[:60] if re.fullmatch(r"[\w .,'()-]{1,60}", text) else ""


def _tidy(address: dict) -> dict:
    """Only the area, the city and the state go into research.db: never a road, a house number or a postcode."""
    area = next((_name(address.get(key)) for key in ("suburb", "neighbourhood", "city_district", "quarter", "village",
                                                     "hamlet") if _name(address.get(key))), "")
    city = next((_name(address.get(key)) for key in ("city", "town", "municipality", "county", "state_district")
                 if _name(address.get(key))), "")
    state = _name(address.get("state"))
    if not (area or city or state):
        return {"problem": "the map service didn't name this place"}
    if area == city:
        area = ""
    return {"area": area, "city": city, "state": state}


def answer(found: dict) -> str:
    """Tenmin's way: the answer first and short, then exactly one follow-up question."""
    if not found:
        return ""
    if found.get("problem"):
        return f"{found['problem']}\nWant to try again after that?" if found["problem"] == NO_LOCATION else ""
    place = ", ".join(part for part in (found.get("area"), found.get("city"), found.get("state")) if part)
    return f"You're in {place}.\nWant me to find something nearby?"
