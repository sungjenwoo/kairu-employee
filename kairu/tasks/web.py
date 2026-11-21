"""Kairu's own browser, light version (Sprint Day 4): web.open and web.search open pages in your installed Chrome or Edge,
with Kairu's own profile folder, so your personal browser profile is never touched. Kairu doesn't read the page.

    address(text)    what you said as an address: only http and https; a short site name such as "youtube" is a known
                     address; file:, javascript:, data: and anything else are refused, and so is an address with spaces,
                     quotes, a user name or a password in it. The result is always one argument for the browser.
    search_address   a Google search for these words (after the privacy filter, in kairu/tasks/actions.py)
    profile(data)    Kairu's own profile folder: browser-profile in Guardian's data folder

The browser is found by the PC layer (kairu/tasks/pc.py): Chrome, then Edge, only from App Paths and their usual folders.
It is started through a shortcut that Explorer opens, as apps.open starts apps: the browser's path, Kairu's profile and the
address as separate arguments, never a shell or a typed command line. Through Explorer, so the browser stays open when the
action ends (Guardian ends everything an action itself started).
"""

import re
from pathlib import Path
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

PROFILE = "browser-profile"
LONGEST = 2000
SITES = {
    "youtube": "https://www.youtube.com/", "google": "https://www.google.com/", "gmail": "https://mail.google.com/",
    "github": "https://github.com/", "wikipedia": "https://www.wikipedia.org/", "google maps": "https://maps.google.com/",
    "maps": "https://maps.google.com/", "google drive": "https://drive.google.com/", "drive": "https://drive.google.com/",
    "google docs": "https://docs.google.com/", "linkedin": "https://www.linkedin.com/", "reddit": "https://www.reddit.com/",
    "stack overflow": "https://stackoverflow.com/", "stackoverflow": "https://stackoverflow.com/",
    "whatsapp web": "https://web.whatsapp.com/", "leetcode": "https://leetcode.com/", "google news": "https://news.google.com/",
    "instagram": "https://www.instagram.com/", "facebook": "https://www.facebook.com/", "twitter": "https://x.com/",
    "flipkart": "https://www.flipkart.com/", "amazon": "https://www.amazon.in/", "gemini": "https://gemini.google.com/",
}  # no name an installed app also has (Outlook, Claude, ChatGPT, News): "open Outlook" still opens the app
TOP_LEVEL = ("com|org|net|in|io|dev|co|edu|gov|ai|app|me|info|uk|us|ca|au|de|fr|jp|tv|gg|so|xyz|site|online|tech|blog|ac|"
             "res|nic|int|mil|biz|cloud|page|ly|to|fm|sh|ws|eu|nl|se|no|fi|it|es|ch|be|at|nz|sg|ae|lk|pk|bd|np|ru|br|mx")
DOMAIN = re.compile(rf"(?:[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?\.)+(?:{TOP_LEVEL})(?::\d{{1,5}})?(?:[/?#][^\s]*)?", re.IGNORECASE)
SCHEME = re.compile(r"([a-z][a-z0-9+.-]+):", re.IGNORECASE)
HOST = re.compile(r"[a-z0-9.-]+", re.IGNORECASE)


class NotAnAddress(Exception):
    """Refused: its text says why."""


def looks_like_an_address(text: str) -> bool:
    """For the skill's phrase: a known site, a domain such as github.com, or anything with a scheme (refused later, plainly)."""
    words = " ".join(text.lower().split())
    return words in SITES or DOMAIN.fullmatch(words) is not None or SCHEME.match(words) is not None


def address(text: str) -> str:
    """The address to open, as one argument; NotAnAddress otherwise."""
    words = " ".join(text.split())
    if words.lower() in SITES:
        return SITES[words.lower()]
    if len(words) > LONGEST:
        raise NotAnAddress("that address is too long")
    if re.search(r"[\s\"'<>\\^`{|}\x00-\x1f\x7f]", words):
        raise NotAnAddress("an address can't have spaces, quotes or the like in it")
    scheme = SCHEME.match(words)
    if scheme and scheme.group(1).lower() not in ("http", "https"):
        raise NotAnAddress(f"Kairu opens only http and https addresses, not {scheme.group(1).lower()}:")
    if not scheme:
        if DOMAIN.fullmatch(words) is None:
            raise NotAnAddress(f"'{words[:60]}' isn't a web address")
        words = "https://" + words
    parts = urlsplit(words)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise NotAnAddress("that isn't a whole web address")
    if parts.username or parts.password or "@" in parts.netloc:
        raise NotAnAddress("an address with a user name or password in it is refused")
    if not HOST.fullmatch(parts.hostname) or parts.hostname.startswith(("-", ".")):
        raise NotAnAddress("that address's site name isn't one Kairu can check")
    safe = "/:@!$&'()*+,;=-._~%"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), quote(parts.path, safe=safe), quote(parts.query, safe=safe + "?"),
                       quote(parts.fragment, safe=safe + "?")))


def search_address(words: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(" ".join(words.split()))


def profile(data_dir) -> Path:
    """Kairu's own browser profile, made on first use: never yours."""
    folder = Path(data_dir).resolve() / PROFILE
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def arguments(profile_folder: Path, url: str) -> list[str]:
    """What the browser is given: Kairu's profile, no first-run pages, the page's words open to Windows' UI Automation
    (Chrome and Edge otherwise often show it only their own bars, so "read this page" and "ask Claude" would read nothing),
    and the address last, as its own argument. Only Kairu's own browser gets this; yours is never started with it."""
    if not url.startswith(("https://", "http://")) or re.search(r"[\s\"]", url):
        raise NotAnAddress("only a checked http or https address goes to the browser")
    return [f"--user-data-dir={profile_folder}", "--no-first-run", "--no-default-browser-check", "--force-renderer-accessibility", url]
