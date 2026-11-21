"""research.weather: "what's the weather in Hyderabad" answered in about a second, with no search, no page and no AI.

Asking the web (research.web_search, then research.web_read of three pages, then the AI writing an answer) took 8-15 s
for the weather on the owner's laptop (15 Nov 2026), and the pages often had yesterday's numbers. Open-Meteo is free,
needs no key and no account, and gives the weather now and today's forecast for a place, from national weather services.

    place(text)   the place a weather question asks about ("whats the weather in hyd" -> "Hyderabad"), or "" if it is
                  not a weather question Kairu answers this way
    main(...)     the Guardian action (Medium, like a web search): two requests, both to Open-Meteo's fixed addresses,
                  each limited to WAIT_SECONDS; only the place name leaves this PC. What it found goes into
                  data/research.db under the job's id, as numbers and names, never instructions
    answer(found) the short spoken answer and one follow-up question (Tenmin), from those numbers only
"""

import json
import os
import re
import sys
import urllib.parse

from kairu.brain import privacy
from kairu.research.store import ResearchStore

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
HOSTS = ("geocoding-api.open-meteo.com", "api.open-meteo.com")
WAIT_SECONDS = 5
MOST_BYTES = 64 * 1024
JOB = re.compile(r"[0-9a-f]{16}")
TEST_WEATHER = "KAIRU_TEST_WEATHER"  # the tests' pretend Open-Meteo: a JSON file {"place": {...}, "forecast": {...}}

ALIASES = {"hyd": "Hyderabad", "hyderabad": "Hyderabad", "secunderabad": "Secunderabad", "blr": "Bengaluru",
           "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "vizag": "Visakhapatnam", "bombay": "Mumbai",
           "madras": "Chennai", "calcutta": "Kolkata", "delhi": "Delhi", "new delhi": "New Delhi", "ncr": "Delhi",
           "warangal": "Warangal", "vijayawada": "Vijayawada", "tirupati": "Tirupati", "pune": "Pune"}
WORD = r"[A-Za-z][A-Za-z .'-]{0,40}?"
WHEN = r"(?:\s+(?:today|now|right now|currently|at the moment|this (?:morning|afternoon|evening)|tonight))?"
ASKS = [re.compile(p, re.IGNORECASE) for p in (
    rf"(?:what(?:'s| is)?|whats|how(?:'s| is)?|hows|tell me|check|show me|give me)\s+(?:the\s+)?(?:weather|temperature|temp|climate|forecast)"
    rf"(?:\s+like)?\s+(?:in|at|of|for|around)\s+(?P<place>{WORD}){WHEN}",
    rf"(?:the\s+)?(?:weather|temperature|temp|forecast)\s+(?:in|at|of|for)\s+(?P<place>{WORD}){WHEN}",
    rf"(?P<place>{WORD})\s+(?:weather|temperature|forecast){WHEN}",
    rf"(?:is it|will it|is it going to)\s+(?:rain(?:ing)?|hot|cold|sunny)\s+(?:in|at)\s+(?P<place>{WORD}){WHEN}",
    rf"how\s+(?:hot|cold|warm)\s+is\s+(?:it\s+)?(?:in\s+)?(?P<place>{WORD}){WHEN}")]
NOT_A_PLACE = re.compile(r"\b(?:my|your|the|this|that|tomorrow|week|weekend|next|yesterday|last|forecast|what|whats|who|how|"
                         r"is|it|tell|show|check|give|me|good|bad|nice|app)\b", re.IGNORECASE)
CODES = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy", 51: "light drizzle",
         53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
         67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow", 80: "light showers",
         81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers", 95: "a thunderstorm",
         96: "a thunderstorm with hail", 99: "a thunderstorm with hail"}


def place(text: str) -> str:
    """The place this weather question is about, or "" (tomorrow, the week, "my area": the usual way answers those)."""
    said = " ".join(text.split()).strip(" ?.!,")
    said = re.sub(r"^(?:(?:hey|ok|okay)\s+)?(?:kairu[\s,:!.-]*)?(?:please\s+)?(?:can you\s+)?", "", said, flags=re.IGNORECASE)
    for pattern in ASKS:
        asked = pattern.fullmatch(said)
        if asked:
            where = asked["place"].strip(" .'-")
            if not where or NOT_A_PLACE.search(where) or len(where) < 2:
                return ""
            return ALIASES.get(where.lower(), where.title() if where.islower() else where)
    return ""


# --- the action ------------------------------------------------------------------------------------------------------

def main(data_dir: str, place: str, job: str) -> None:
    if not JOB.fullmatch(job) or not 2 <= len(place) <= 60 or not re.fullmatch(r"[A-Za-z .'-]+", place):
        print("research.weather: not a place it can look up", file=sys.stderr)
        raise SystemExit(1)
    store = ResearchStore(data_dir)
    verdict = privacy.classify(place)
    if verdict.secret or verdict.personal:
        store.put(job, "weather", {"problem": "that doesn't look like a place name"})
        return
    try:
        found = _pretend(place) if os.environ.get(TEST_WEATHER) else _open_meteo(place)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        print(f"research.weather: Open-Meteo did not answer ({type(error).__name__})", file=sys.stderr, flush=True)
        store.put(job, "weather", {"problem": f"the weather service did not answer ({type(error).__name__})"})
        return
    store.put(job, "weather", found)


def _get(url: str, query: dict) -> dict:
    import urllib.request  # only here: the action's own process, never the brain or Guardian
    address = f"{url}?{urllib.parse.urlencode(query)}"
    if urllib.parse.urlsplit(address).hostname not in HOSTS:
        raise ValueError("not Open-Meteo")
    with urllib.request.urlopen(address, timeout=WAIT_SECONDS) as response:
        if urllib.parse.urlsplit(response.geturl()).hostname not in HOSTS:
            raise ValueError("sent elsewhere")
        return json.loads(response.read(MOST_BYTES))


def _open_meteo(place: str) -> dict:
    places = _get(GEOCODE, {"name": place, "count": 1, "language": "en", "format": "json"}).get("results") or []
    if not places:
        return {"problem": f"I couldn't find a place called {place}"}
    where = places[0]
    forecast = _get(FORECAST, {
        "latitude": where["latitude"], "longitude": where["longitude"], "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
    return _tidy(where, forecast)


def _pretend(place: str) -> dict:
    with open(os.environ[TEST_WEATHER], encoding="utf-8") as file:
        pretend = json.load(file)
    if not pretend.get("place"):
        return {"problem": f"I couldn't find a place called {place}"}
    return _tidy(pretend["place"], pretend["forecast"])


def _tidy(where: dict, forecast: dict) -> dict:
    """Only numbers and names go into research.db: never any other text from the service."""
    now, day = forecast["current"], forecast["daily"]
    rain = (day.get("precipitation_probability_max") or [None])[0]
    return {"name": str(where.get("name", ""))[:60], "region": str(where.get("admin1") or where.get("country") or "")[:60],
            "temp": round(float(now["temperature_2m"])), "feels": round(float(now["apparent_temperature"])),
            "humidity": round(float(now["relative_humidity_2m"])), "wind": round(float(now["wind_speed_10m"])),
            "sky": CODES.get(int(now["weather_code"]), "mixed weather"),
            "high": round(float(day["temperature_2m_max"][0])), "low": round(float(day["temperature_2m_min"][0])),
            "rain": None if rain is None else round(float(rain))}


def answer(found: dict) -> str:
    """Tenmin's way: the answer first and short, then exactly one follow-up question."""
    if not found or found.get("problem"):
        return ""
    feels = f", feels like {found['feels']}" if abs(found["feels"] - found["temp"]) >= 2 else ""
    rain = f", {found['rain']}% chance of rain" if found.get("rain") is not None else ""
    return (f"It's {found['temp']}°C and {found['sky']} in {found['name']} right now{feels}. "
            f"Today: {found['low']} to {found['high']}°C{rain}.\nWant tomorrow's forecast too?")
