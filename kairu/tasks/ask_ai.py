"""Kairu's browser eyes, and asking an AI website (ASK.md): "read this page", "ask Claude what is photosynthesis".

    web.read_page   Low, read-only   the words of the web page in the browser in front: shown to you, never an order
    web.ask            Medium           open one of the AI websites below in Kairu's own browser, type your question there,
                                        press Enter, wait, and show what the page answers. Public words only
    web.ask_private    High             the same after your "yes" and PIN, for a question the privacy filter calls personal

It uses Kairu's hands (kairu/tasks/screen.py, kairu/hands.py) and keeps every rule they have, and these of its own:

  - only the sites in SITES, at their fixed addresses: no other page is ever typed into by this skill;
  - only in Kairu's own browser profile (data/browser-profile): the window must belong to a browser started with that
    profile, so nothing is ever typed into your own Chrome window or your own sign-ins;
  - you sign in to a site yourself, once, in Kairu's browser. If the page shows a sign-in box, Kairu types nothing and
    says so: it never types a password, an OTP or a CAPTCHA;
  - a secret is never typed, not even with your PIN; personal words need web.ask_private (High);
  - one question at a time, and no faster than one every ASK_GAP_SECONDS: a person's pace, never a script's;
  - the page's answer is quoted data: lines that give orders or hold a secret are left out, and nothing in it can become
    an order (kairu/research/quarantine.py). It is shown to you; it never goes to another AI or anywhere else.
"""

import re
import time
from dataclasses import dataclass
from pathlib import Path

from kairu.brain import privacy
from kairu.research import quarantine
from kairu.tasks import pc, screen, web
from kairu.tasks.actions import Refusal, _guarded, _open_page

ACTIONS = ("web.ask", "web.ask_private")
STEP_SECONDS = 100  # the task core gives these steps this long: the page loads, then the AI writes
PERSONAL_ASK = "Not asked yet: "  # the core asks for your approval (web.ask_private) when a reply starts with this
ASK_GAP_SECONDS = 15
WINDOW_SECONDS = 15  # for Kairu's browser window to come up
LOAD_SECONDS = 4  # for the page to load before the question box is looked for
BOX_SECONDS = 12
ANSWER_SECONDS = 60
POLL_SECONDS = 2
LONGEST_ANSWER = 1500
LONGEST_PAGE = 1500


@dataclass(frozen=True)
class Site:
    label: str
    url: str


SITES = {  # the only pages this skill types into; the owner adds one here, in a pull request
    "claude": Site("Claude", "https://claude.ai/new"),
    "chatgpt": Site("ChatGPT", "https://chatgpt.com/"),
    "gemini": Site("Gemini", "https://gemini.google.com/app"),
    "perplexity": Site("Perplexity", "https://www.perplexity.ai/"),
}
NAMES = {"claude": "claude", "claude ai": "claude", "chatgpt": "chatgpt", "chat gpt": "chatgpt", "gpt": "chatgpt",
         "gemini": "gemini", "google gemini": "gemini", "perplexity": "perplexity", "perplexity ai": "perplexity"}
SITE_WORDS = "|".join(re.escape(name) for name in sorted(NAMES, key=len, reverse=True))


def site_of(name: str) -> Site:
    known = NAMES.get(" ".join((name or "").lower().split()))
    if not known:
        raise Refusal(f"I ask only {', '.join(site.label for site in SITES.values())}.")
    return SITES[known]


def question_problem(words: str) -> str:
    """Why this question can't be typed at all ("" if it can): the hands' own rule, so a secret is never typed."""
    return screen.text_problem(words).replace("Not typed:", "Not asked:").replace("I type ", "A question is ")


def is_personal(question: str) -> bool:
    return privacy.classify(" ".join(question.split())).personal


# --- Kairu's own browser window ------------------------------------------------------------------------------

def _kairus_browser(system, data_dir: str):
    """The browser window that was started with Kairu's own profile, waiting a little for it. Never any other window."""
    marker = web.PROFILE.lower()
    deadline = time.monotonic() + WINDOW_SECONDS
    while True:
        for window in system.windows():
            if window.app in screen.BROWSERS and screen._usable(system, window):
                try:
                    line = system.command_line(window).lower()
                except (pc.PcProblem, OSError):
                    line = ""
                if marker in line:
                    screen._check_window(system, window)
                    system.bring_to_front(window)
                    return window
        if time.monotonic() >= deadline:
            raise Refusal("Kairu's own browser didn't come up, so I asked nothing. Nothing was typed anywhere.")
        time.sleep(0.2)


def _pace(data_dir: str) -> None:
    mark = Path(data_dir) / "ask-ai.last"
    try:
        last = float(mark.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = 0.0
    wait = ASK_GAP_SECONDS - (time.time() - last)
    if 0 < wait <= ASK_GAP_SECONDS:
        raise Refusal(f"One question at a time: ask again in {int(wait) + 1} seconds.")
    mark.write_text(str(time.time()), encoding="utf-8")


def _question_box(system, window, site: Site) -> str:
    deadline = time.monotonic() + BOX_SECONDS
    while True:
        box = system.ask_box(window)
        if box == pc.SIGN_IN:
            raise Refusal(f"{site.label} wants you to sign in. Sign in yourself, once, in Kairu's browser (it is open now), "
                          "then ask again. I typed nothing.")
        if box:
            return box
        if time.monotonic() >= deadline:
            raise Refusal(f"I can't find {site.label}'s question box, so I typed nothing. The page is open in Kairu's browser.")
        time.sleep(1)


def _after(lines: list[str], question: str, before: list[str]) -> list[str]:
    """The page's lines after your question (its last showing); if the page doesn't show it, the lines that are new."""
    start = question.lower()[:40]
    places = [number for number, line in enumerate(lines) if start in line.lower()]
    if places:
        return lines[places[-1] + 1:]
    old = set(before)
    return [line for line in lines if line not in old]


def _answer(system, window, question: str, before: list[str]) -> list[str]:
    """Wait until the page's answer stops growing (two readings the same), or the time is up."""
    deadline, last = time.monotonic() + ANSWER_SECONDS, None
    while True:
        time.sleep(POLL_SECONDS)
        now = _after(system.read_page(window), question, before)
        if now and now == last:
            return now
        last = now
        if time.monotonic() >= deadline:
            return now


def quoted(lines: list[str], most: int) -> tuple[str, int]:
    """Page lines as text Kairu may show: orders and secrets left out, short. (the text, how many lines were left out)"""
    safe, removed = quarantine.safe_lines("\n".join(lines))
    text = "\n".join(line for line in safe if len(line) > 1)
    if len(text) > most:
        text = text[:most].rsplit(" ", 1)[0] + " …"
    return text, removed


def _ask(system, data_dir: str, site_name: str, question: str, approved: bool) -> str:
    site = site_of(site_name)
    words = " ".join((question or "").split())
    problem = question_problem(words)
    if problem:
        raise Refusal(problem)
    if not approved and is_personal(words):
        raise Refusal(f"{PERSONAL_ASK}it looks personal ({privacy.classify(words).why()}), so it needs your yes and PIN first.")
    _pace(data_dir)
    _open_page(system, data_dir, site.url)
    window = _kairus_browser(system, data_dir)
    time.sleep(LOAD_SECONDS)
    before = system.read_page(window)
    _question_box(system, window, site)
    system.type_text(window, words)
    system.press(window, "enter")
    text, removed = quoted(_answer(system, window, words, before), LONGEST_ANSWER)
    if not text:
        raise Refusal(f"I asked {site.label}, but I can't read an answer yet. It is open in Kairu's browser.")
    note = f"\n(I left out {removed} line{'s' if removed != 1 else ''} giving orders or holding a secret.)" if removed else ""
    return f"{site.label} says: {text}{note}"


def ask(data_dir: str, job: str, site: str, question: str) -> None:
    return _guarded(data_dir, job, lambda system: _ask(system, data_dir, site, question, approved=False))


def ask_private(data_dir: str, job: str, site: str, question: str) -> None:
    """You approved these words ("yes" and your PIN) for this site: asked, as long as they hold no secret."""
    return _guarded(data_dir, job, lambda system: _ask(system, data_dir, site, question, approved=True))


def read_page(data_dir: str, job: str, app: str = "") -> None:
    """The words of the page in the browser in front, as data: shown to you, never an order, sent nowhere."""
    def work(system) -> str:
        wanted = screen.program_of(app)
        target = screen.find(system, wanted if wanted else screen.BROWSER)
        if target.app not in screen.BROWSERS:
            raise Refusal("I read pages only in a browser.")
        screen._check_window(system, target.window)
        text, removed = quoted(system.read_page(target.window), LONGEST_PAGE)
        if not text:
            return f"{screen._name(target)} shows no page text I can read."
        note = f"\n(I left out {removed} line{'s' if removed != 1 else ''} giving orders or holding a secret.)" if removed else ""
        return f"This page says: {text}{note}"
    return _guarded(data_dir, job, work)
