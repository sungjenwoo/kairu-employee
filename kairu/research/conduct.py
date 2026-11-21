"""How a question gets what the web says: it asks Guardian for one search, then one read of the top pages.
Deep research (look_into) does that for up to three search queries, one after the other.

The brain (kairu/brain/) only thinks and answers, and never searches or fetches anything itself. When it says a
question needs fresh facts, this Orchestration part (ADR-011) runs in that same question's process and asks Guardian
to `run` research.web_search and research.web_read, follows them with `run_status`, and `end`s one that takes too
long. Those three are its only requests. Guardian decides each one by policy.yaml like any other action, and a stop
ends the question, the search and the page read together, within a second.

A search that fails is no failure of the question: Found says why, and the brain answers from what it knows, saying so.
"""

import re
import secrets
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from kairu import channel
from kairu.research import quarantine
from kairu.research.store import ResearchStore

MOST_PAGES = 3
MOST_QUERIES = 3  # deep research: the searches one question may ask for
DEEP_SECONDS = 70  # ... and no new search starts after this long, so the report is written within a question's time
DEEP_PAUSE_SECONDS = 1.5  # between two searches, so DuckDuckGo is not asked too fast
MOST_FROM_ONE_SITE = 2
SEARCH_WAIT_SECONDS = 14  # the action's own 8 s, and Python starting on a slow PC
READ_WAIT_SECONDS = 13
WEATHER_WAIT_SECONDS = 14  # the action's own two 5 s requests, and Python starting on a slow PC
LOCATION_WAIT_SECONDS = 24  # Windows' location (up to 12 s), one 6 s request, and Python starting
POLL_SECONDS = 0.1
JUST_NOW = re.compile(r"\b(?:today|tonight|yesterday|tomorrow|latest|news|headlines?|scores?|scorecard|right now|"
                      r"this (?:morning|afternoon|evening|week)|last night)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Found:
    results: list[dict] = field(default_factory=list)  # {"title", "url", "snippet"}
    pages: list[dict] = field(default_factory=list)  # {"url", "title", "text", "asked"}, or {"url", "problem"}
    problem: str = ""  # why there is nothing, as a label
    stopped: bool = False  # a stop or `end` ended the search: nothing more may go out


def log(text: str) -> None:
    print(f"research: {text}", file=sys.stderr, flush=True)


def _top_pages(results: list[dict], seen=frozenset()) -> list[str]:
    """The addresses to read: the first ones, at most two from one site, so one site cannot fill all three.

    seen: pages an earlier search of the same question already read; they are not read twice."""
    urls, sites = [], {}
    for item in results:
        site = urlsplit(item["url"]).hostname
        if item["url"] not in seen and sites.get(site, 0) < MOST_FROM_ONE_SITE and len(urls) < MOST_PAGES:
            urls.append(item["url"])
            sites[site] = sites.get(site, 0) + 1
    return urls


class Research:
    def __init__(self, data_dir, request=None, poll: float = POLL_SECONDS, pause: float = DEEP_PAUSE_SECONDS):
        self.data_dir, self.poll, self.pause = str(data_dir), poll, pause
        self.request = request or (lambda message: channel.request(self.data_dir, message, timeout=15))

    def look_into(self, queries: list[str]) -> list[Found]:
        """Deep research: one look_up for each of a few search queries, one after the other, each page read once.

        Every search and read is still its own Guardian action. A stop ends it at once: nothing more is asked for."""
        founds, seen, deadline = [], set(), time.monotonic() + DEEP_SECONDS
        for number, query in enumerate(queries[:MOST_QUERIES]):
            if number:
                if time.monotonic() > deadline:
                    log(f"deep research: out of time after {number} searches; going on with what they found")
                    break
                time.sleep(self.pause)
            found = self.look_up(query, frozenset(seen))
            founds.append(found)
            if found.stopped:
                break
            seen.update(page.get("asked") or page.get("url") for page in found.pages)
        return founds

    def look_up(self, query: str, seen=frozenset()) -> Found:
        job = secrets.token_hex(8)
        store = ResearchStore(self.data_dir)
        recent = "w" if JUST_NOW.search(query) else ""
        outcome, problem = self._run("research.web_search", {"query": query, "job": job, "recent": recent},
                                     SEARCH_WAIT_SECONDS)
        if outcome == "halted":
            return Found(stopped=True)
        if outcome != "finished":
            return Found(problem=problem or "the search did not finish")
        found = store.take(job, "search") or {}
        results = found.get("results") or []
        if not results:
            return Found(problem=found.get("problem") or "the search found nothing")
        results = quarantine.rank(results, query, quarantine.asked_day(query, time.time()))
        urls = _top_pages(results, seen)
        if not urls:  # deep research: an earlier search already read every page this one found
            return Found(results)
        details = {"job": job, **{f"url{number}": url for number, url in enumerate(urls, 1)}}
        outcome, problem = self._run("research.web_read", details, READ_WAIT_SECONDS)
        if outcome == "halted":
            return Found(results, stopped=True)
        if outcome != "finished":
            log(f"the pages were not read: {problem or 'the read did not finish'}; going on with the search's own snippets")
            return Found(results)
        pages = (store.take(job, "pages") or {}).get("pages") or []
        return Found(results, [{**page, "asked": url} for page, url in zip(pages, urls)])

    def weather(self, place: str) -> str:
        """research.weather (kairu/research/weather.py): the short answer, or "" when Open-Meteo could not give one."""
        from kairu.research import weather
        job = secrets.token_hex(8)
        outcome, problem = self._run("research.weather", {"place": place, "job": job}, WEATHER_WAIT_SECONDS)
        if outcome != "finished":
            log(f"the weather was not looked up: {problem or outcome}; asking the web instead")
            return ""
        return weather.answer(ResearchStore(self.data_dir).take(job, "weather") or {})

    def location(self) -> str:
        """research.location (kairu/research/where.py): "You're in <area>, <city>.", or "" when it could not be found."""
        from kairu.research import where
        job = secrets.token_hex(8)
        outcome, problem = self._run("research.location", {"job": job}, LOCATION_WAIT_SECONDS)
        if outcome != "finished":
            log(f"the location was not found: {problem or outcome}")
            return ""
        return where.answer(ResearchStore(self.data_dir).take(job, "location") or {})

    def _run(self, action: str, details: dict, limit: float) -> tuple[str, str]:
        """Guardian runs it, and this waits: (its outcome, or "" with why not)."""
        try:
            started = self.request({"op": "run", "action": action, "details": details})
        except channel.ChannelError as error:
            return "", f"Guardian could not be asked ({type(error).__name__})"
        if started.get("verdict") != "ok":
            return "", f"Guardian refused {action}: {started.get('reason')}"
        run, deadline = started["run"], time.monotonic() + limit
        while time.monotonic() < deadline:
            try:
                outcome = self.request({"op": "run_status", "run": run}).get("outcome")
            except channel.ChannelError:
                outcome = None
            if outcome is not None:
                return outcome, f"{action} {outcome}"
            time.sleep(self.poll)
        try:
            self.request({"op": "end", "run": run})
        except channel.ChannelError:
            pass
        return "", f"{action} took longer than {limit:g} s"
