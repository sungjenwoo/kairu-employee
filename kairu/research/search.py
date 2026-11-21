"""research.web_search: one web search, as a Guardian action in its own process, so a stop ends it within a second.

The search goes to DuckDuckGo and nowhere else, through the ddgs package (free, no key). Kairu uses ddgs's DuckDuckGo
engine directly, because its front door may also ask Google, Bing and others, and falls back to all of them when it
does not know the engine it was told. The words leave this PC, so the privacy filter reads them here as well as in the
brain: a secret is never searched, whoever asks, and a personal search runs only with the mark your "yes" and PIN left
(kairu/research/store.py); so does every search when you set brain.public_to_cloud: false.

When DuckDuckGo answers anything but 200 (it says 202 when it thinks searches come too fast), Kairu does not try again
and tries no other way round: it leaves DuckDuckGo alone for REST_SECONDS and says when it will search again.

What it finds goes to data/research.db for the question that asked. Exit code 0 whenever there is something to read,
even "nothing found" or "refused". Guardian's log gets only a label, never the words: the audit log keeps their hash
(policy.yaml: private).

For the tests, KAIRU_TEST_SEARCH points the search at a stand-in on this PC (http://127.0.0.1:PORT); it is honoured
only for an address on this PC, and ddgs is then never loaded.
"""

import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime

from kairu.brain import privacy
from kairu.research.store import ResearchStore

REGION = "in-en"
SEARCH_SECONDS = 8
MOST_RESULTS = 8  # the pages to read are chosen from these (kairu/research/quarantine.py: rank)
MOST_URL = 2000
REST_SECONDS = 300
TEST_SEARCH = "KAIRU_TEST_SEARCH"
JOB = re.compile(r"[0-9a-f]{16}")
WEB_LINK = re.compile(r"https?://[^\s\x00-\x1f\x7f]+", re.IGNORECASE)  # it is also shown to you by "sources?"
RECENT = ("", "d", "w", "m", "y")  # the last day, week, month, year, or any time


class SearchFailed(Exception):
    """The search gave nothing back. Its text is a label, never the words searched for."""


class TooFast(SearchFailed):
    """DuckDuckGo wants a rest."""


def main(data_dir: str, query: str, job: str, recent: str = "", brain: dict | None = None) -> None:
    if not JOB.fullmatch(job) or recent not in RECENT or not query.strip() or len(query) > 600:
        print("research.web_search: not a search it can do", file=sys.stderr)
        raise SystemExit(1)
    store = ResearchStore(data_dir)
    problem = refusal(store, query, brain or {})
    if problem:
        store.put(job, "search", {"results": [], "problem": problem})
        return
    try:
        results = tidy(stand_in_search(query, recent) if stand_in() else duckduckgo(query, recent))
    except SearchFailed as error:
        problem = str(error)
        if isinstance(error, TooFast):
            until = time.time() + REST_SECONDS
            store.rest_until(until)
            problem += f"; Kairu searches again after {datetime.fromtimestamp(until).strftime('%H:%M')}"
        print(f"research.web_search: {problem}", file=sys.stderr, flush=True)
        store.put(job, "search", {"results": [], "problem": problem})
        return
    store.put(job, "search", {"results": results})


def refusal(store: ResearchStore, query: str, brain: dict) -> str:
    """Why these words may not leave this PC now ("" if they may). Only labels, never the words."""
    verdict = privacy.classify(query)
    if verdict.secret:
        return f"it has {verdict.why()}, and secrets are never searched"
    if (verdict.personal or not brain.get("public_to_cloud")) and not store.spend(query):
        return "a personal search needs your \"yes\" and PIN first"
    resting = store.resting_until()
    if resting and not stand_in():
        return f"DuckDuckGo asked Kairu to slow down, so it searches again after {datetime.fromtimestamp(resting).strftime('%H:%M')}"
    return ""


def duckduckgo(query: str, recent: str) -> list[dict]:
    """One request to DuckDuckGo's own page, and nothing else: no second engine, no second try."""
    try:
        from ddgs.engines.duckduckgo import Duckduckgo
    except ImportError as error:
        raise SearchFailed(f"the ddgs package could not be loaded ({type(error).__name__})") from None
    try:
        engine = Duckduckgo(timeout=SEARCH_SECONDS)
        payload = engine.build_payload(query=query, region=REGION, safesearch="moderate", timelimit=recent or None)
        response = engine.http_client.post(engine.search_url, data=payload)
        if response.status_code == 200:
            return [{"title": item.title, "href": item.href, "body": item.body}
                    for item in engine.post_extract_results(engine.extract_results(response.text))]
    except Exception as error:  # the library raises its own kinds, and its messages can hold the words: never repeat them
        raise SearchFailed(f"DuckDuckGo did not answer ({type(error).__name__})") from None
    if response.status_code in (202, 403, 429):
        raise TooFast(f"DuckDuckGo asked Kairu to slow down (HTTP {response.status_code})")
    raise SearchFailed(f"DuckDuckGo did not answer (HTTP {response.status_code})")


def tidy(found: list) -> list[dict]:
    """Search results as plain short text: web links only, each once. All of it is data from strangers."""
    results, seen = [], set()
    for item in found:
        if not isinstance(item, dict):
            continue
        url = item.get("href")
        if not isinstance(url, str) or not WEB_LINK.fullmatch(url) or len(url) > MOST_URL or url in seen:
            continue
        seen.add(url)
        results.append({"title": _short(item.get("title"), 200), "url": url, "snippet": _short(item.get("body"), 500)})
    return results[:MOST_RESULTS]


def _short(value, most: int) -> str:
    return " ".join(value.split())[:most] if isinstance(value, str) else ""


def stand_in() -> str:
    """The stand-in search of a test, only if it is on this PC; "" otherwise."""
    address = os.environ.get(TEST_SEARCH, "")
    parts = urllib.parse.urlsplit(address)
    return address.rstrip("/") if parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1") else ""


def stand_in_search(query: str, recent: str) -> list:
    import urllib.request  # only here: it brings ssl and http.client, which a real search has no use for (memory)
    words = urllib.parse.urlencode({"q": query, "recent": recent})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{stand_in()}/search?{words}", timeout=120) as response:
            return json.loads(response.read())
    except (OSError, ValueError) as error:
        raise SearchFailed(f"the stand-in search did not answer ({type(error).__name__})") from None
