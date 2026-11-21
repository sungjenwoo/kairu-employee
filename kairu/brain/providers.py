"""The free cloud AI providers (L3) and their one connector: an OpenAI-style chat request over HTTPS.

Checked on 29 Oct 2026 on each provider's own pages (BRAIN.md, "Free AI providers"):

    groq        Groq: free, no card; about 1,000 questions a day and 30 a minute on openai/gpt-oss-120b. Its
                Services Agreement (section 4.2) does not let Groq train on your inputs or outputs.
    cloudflare  Cloudflare Workers AI: free plan, 10,000 "neurons" a day (a few hundred short answers), reset at
                00:00 UTC (5:30 am in India). Cloudflare: "does not use Customer Content processed by Workers AI
                to train AI models". Needs your account ID as well as an API token.
    openrouter  OpenRouter free models: 50 a day, 20 a minute. Each request says data_collection: deny, so
                OpenRouter may send it only to providers that do not collect it; if a free model has none, it
                refuses, and Kairu skips OpenRouter.

Not used: Cerebras (no free tier since July 2026: its trial needs a payment method), GitHub Models (retired
30 July 2026), Google AI Studio and Mistral free tiers (they may train on free prompts).

Where each request goes is fixed here, never taken from a question or a message: the host, the path and
the model (a model can be replaced in config.yaml, brain.models, if a provider retires it). Your key goes
only to its own provider, in the Authorization header; it is never logged or shown.

Before anything is sent, the backstop scanner (privacy.secrets_in) reads the exact text that is about to
leave; if it finds a secret, nothing is sent (Backstopped), whatever let the question through.

Standard library only. For the tests, KAIRU_TEST_PROVIDERS points every provider at a stand-in on this PC
(http://127.0.0.1:PORT); it is honoured only for an address on this PC.
"""

import base64
import http.client
import json
import os
import re
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import urlsplit

from kairu.brain import privacy

USER_AGENT = "kairu-brain/1"
TIMEOUT_SECONDS = 30
MOST_ANSWER_BYTES = 1 << 20
TEST_PROVIDERS = "KAIRU_TEST_PROVIDERS"
ACCOUNT = re.compile(r"[0-9a-f]{32}")  # a Cloudflare account ID
MODEL = re.compile(r"[A-Za-z0-9@._:/-]{1,100}")


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    host: str
    path: str  # "{account}" is filled in with your account ID (Cloudflare)
    model: str
    signup: str  # where to make a free account and a key
    terms: str  # where the provider says it does not train on your prompts
    per_day: int | None  # free questions a day (None: counted in another unit, see day_note)
    per_minute: int
    day_note: str  # how the free day is counted, in words
    needs_account: bool = False
    system_role: bool = True  # False: the instructions go in front of the question instead
    key_start: str = ""  # how its keys usually start
    neurons: tuple[float, float] | None = None  # Cloudflare's neurons per million tokens in and out, for the model
    extra: Mapping = field(default_factory=lambda: MappingProxyType({}))
    token_field: str = "max_tokens"


PROVIDERS: Mapping[str, Provider] = MappingProxyType({
    "groq": Provider(
        "groq", "Groq", "api.groq.com", "/openai/v1/chat/completions", "openai/gpt-oss-120b",
        "https://console.groq.com/keys", "https://console.groq.com/docs/legal/services-agreement (section 4.2)",
        1000, 30, "1,000 questions a day on this model; Groq reports what is left with every answer",
        key_start="gsk_", extra=MappingProxyType({"reasoning_effort": "low", "include_reasoning": False}),
        token_field="max_completion_tokens"),
    "cloudflare": Provider(
        "cloudflare", "Cloudflare", "api.cloudflare.com", "/client/v4/accounts/{account}/ai/v1/chat/completions",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "https://dash.cloudflare.com/profile/api-tokens",
        "https://developers.cloudflare.com/workers-ai/platform/privacy/", None, 300,
        "10,000 free neurons a day (a few hundred short answers), new at 00:00 UTC (5:30 am in India)",
        needs_account=True, neurons=(26668, 204805)),
    "openrouter": Provider(
        "openrouter", "OpenRouter", "openrouter.ai", "/api/v1/chat/completions", "google/gemma-4-31b-it:free",
        "https://openrouter.ai/settings/keys", "https://openrouter.ai/docs/features/provider-routing (data_collection)",
        50, 20, "50 free questions a day, new at 00:00 UTC", system_role=False, key_start="sk-or-",
        extra=MappingProxyType({"provider": {"data_collection": "deny"}})),
    # Gemini (the owner's GO of 16 Nov 2026): its key is for Gemini hearing (VOICE.md); the brain uses it only if you put
    # gemini in brain.providers, and the Builder only if it is in brain.build_providers (BUILDER.md, ADR-050 proposed).
    # Google's free tier may use what is sent to improve its products (terms below).
    "gemini": Provider(
        "gemini", "Google Gemini", "generativelanguage.googleapis.com", "/v1beta/openai/chat/completions",
        "gemini-flash-latest", "https://aistudio.google.com/apikey", "https://ai.google.dev/gemini-api/terms (free tier: "
        "Google may use content to improve its products)", 250, 10, "the free tier's daily limit, new at midnight Pacific time",
        key_start="AIza"),
})


class ProviderError(Exception):
    """Nothing usable came back. `what` is the short reason, in words."""


class Limited(ProviderError):
    """At its free limit: try another provider, wait, or tell you. `until` is when it should be free again."""

    def __init__(self, why: str, until: float):
        super().__init__(why)
        self.until = until


class KeyRefused(ProviderError):
    pass


class Unreachable(ProviderError):
    pass


class Backstopped(ProviderError):
    """The backstop found a secret in the text about to leave: nothing was sent."""


@dataclass(frozen=True)
class Reply:
    text: str
    tokens_in: int
    tokens_out: int
    day_limit: int | None  # what the provider says about its free day, when it says it
    day_left: int | None
    day_reset: float | None  # when its count is full again (a time), when it says
    finish: str = ""  # why the provider stopped writing: "length" means it was cut off at the token limit


Transport = Callable[[str, dict, bytes, float], tuple[int, dict, bytes]]


def url_of(provider: Provider, account: str = "") -> str:
    if provider.needs_account and not ACCOUNT.fullmatch(account or ""):
        raise ProviderError(f"{provider.label} needs your account ID (32 letters and digits): add the key again")
    path = provider.path.format(account=account)
    test = os.environ.get(TEST_PROVIDERS, "")
    if test:
        parts = urlsplit(test)
        if parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1"):
            return f"{test.rstrip('/')}/{provider.name}{path}"
    return f"https://{provider.host}{path}"


def chat(provider: Provider, key: str, messages: list[dict], account: str = "", model: str | None = None,
         transport: Transport | None = None, max_tokens: int = 700, timeout: float = TIMEOUT_SECONDS) -> Reply:
    """One question to one provider. Raises Backstopped, Limited, KeyRefused, Unreachable or ProviderError."""
    leaving = "\n".join(message["content"] for message in messages)
    found = privacy.secrets_in(leaving)
    if found:
        raise Backstopped(f"the backstop found {', '.join(found)} in the text about to leave, so nothing was sent")
    if not provider.system_role and messages and messages[0]["role"] == "system":
        first, rest = messages[0]["content"], messages[1:]
        messages = [{"role": rest[0]["role"], "content": f"{first}\n\n{rest[0]['content']}"}, *rest[1:]]
    body = {"model": model or provider.model, "messages": messages, "temperature": 0.3,
            provider.token_field: max_tokens, **provider.extra}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
    url = url_of(provider, account)
    started = time.time()
    try:
        status, answer_headers, raw = (transport or _post)(url, headers, json.dumps(body).encode("utf-8"), timeout)
    except (OSError, http.client.HTTPException) as error:
        raise Unreachable(f"{provider.label} could not be reached ({type(error).__name__})") from None
    answer_headers = {name.lower(): value for name, value in answer_headers.items()}
    if status != 200:
        raise _refusal(provider, status, answer_headers, raw, started)
    try:
        data = json.loads(raw)
        text = data["choices"][0]["message"]["content"]
        finish = str(data["choices"][0].get("finish_reason") or "")[:20]
        usage = data.get("usage") or {}
    except (ValueError, KeyError, IndexError, TypeError):
        raise ProviderError(f"{provider.label}'s answer could not be read") from None
    if not isinstance(text, str) or not text.strip():
        raise ProviderError(f"{provider.label} gave an empty answer")
    day_limit, day_left, day_reset = _day(provider, answer_headers, started)
    return Reply(text, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                 day_limit, day_left, day_reset, finish)


# The Builder's Gemini (BUILDER.md, ADR-050 proposed): Google's own generateContent address, as Gemini hearing uses
# (kairu/voice/gemini.py), not the OpenAI-compatible one. Its models are tried in turn: a name Google no longer serves (404)
# or one too busy (503, after one short wait) moves on to the next. The same backstop reads everything first.
GEMINI_MODELS = ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite")
GEMINI_BUSY_WAIT = 3.0


def gemini_url(name: str) -> str:
    """Google's own generateContent address for this model (for the tests, the stand-in that KAIRU_TEST_PROVIDERS names)."""
    path = f"/v1beta/models/{name}:generateContent"
    test = os.environ.get(TEST_PROVIDERS, "")
    if test:
        parts = urlsplit(test)
        if parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1"):
            return f"{test.rstrip('/')}/gemini{path}"
    return f"https://{PROVIDERS['gemini'].host}{path}"


MEDIA_TYPES = ("audio/mp3", "audio/mpeg", "audio/wav", "audio/mp4", "audio/aac", "audio/ogg", "audio/flac", "audio/aiff",
               "video/mp4", "video/webm", "video/quicktime", "video/mpeg")


def media_ok(media) -> bool:
    """One recording part for Gemini: inline_data (base64) or file_data (a file uploaded to Gemini's own Files API), of a
    meeting's sound or video type, and nothing else."""
    if not isinstance(media, dict) or len(media) != 1:
        return False
    (kind, part), = media.items()
    if not isinstance(part, dict) or part.get("mime_type") not in MEDIA_TYPES:
        return False
    if kind == "inline_data":
        return set(part) == {"mime_type", "data"} and isinstance(part["data"], str) and bool(part["data"])
    if kind == "file_data":
        uri = str(part.get("file_uri", ""))
        test = os.environ.get(TEST_PROVIDERS, "")
        return set(part) == {"mime_type", "file_uri"} and (
            uri.startswith(f"https://{PROVIDERS['gemini'].host}/") or bool(test) and uri.startswith(test.rstrip("/") + "/"))
    return False


def gemini_build(key: str, messages: list[dict], model: str | None = None, transport: Transport | None = None,
                 max_tokens: int = 8192, timeout: float = TIMEOUT_SECONDS, sleep=time.sleep, picture: bytes | None = None,
                 json_answer: bool = False, media: dict | None = None) -> Reply:
    """One Builder request to Google Gemini. Raises Backstopped, Limited, KeyRefused, Unreachable or ProviderError.

    picture (Kairu's eyes, kairu/tasks/eyes.py, ADR-051 proposed): a PNG of one window, in memory, put after the last words
    you send; json_answer asks Gemini to answer with JSON only. The backstop reads every word first, as always.
    media (Meeting in, kairu/meeting/hear.py, ADR-055 proposed): one meeting recording you approved, as Gemini's own
    inline_data or file_data part (MEDIA_TYPES only), put after the last words you send."""
    provider = PROVIDERS["gemini"]
    leaving = "\n".join(message["content"] for message in messages)
    found = privacy.secrets_in(leaving)
    if found:
        raise Backstopped(f"the backstop found {', '.join(found)} in the text about to leave, so nothing was sent")
    system = "\n\n".join(message["content"] for message in messages if message["role"] == "system")
    contents = [{"role": "model" if message["role"] == "assistant" else "user", "parts": [{"text": message["content"]}]}
                for message in messages if message["role"] != "system"]
    if picture is not None:
        if not picture.startswith(b"\x89PNG\r\n\x1a\n") or not contents or contents[-1]["role"] != "user":
            raise ProviderError("that picture can't be sent")
        contents[-1]["parts"].append({"inline_data": {"mime_type": "image/png",
                                                      "data": base64.b64encode(picture).decode("ascii")}})
    if media is not None:
        if not media_ok(media) or not contents or contents[-1]["role"] != "user":
            raise ProviderError("that recording can't be sent")
        contents[-1]["parts"].append(media)
    body = {"contents": contents, "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens,
                                                       **({"responseMimeType": "application/json"} if json_answer else {})}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = json.dumps(body).encode("utf-8")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json", "User-Agent": USER_AGENT}
    problem: ProviderError = ProviderError(f"{provider.label}: none of its models answered")
    for name in dict.fromkeys(([model] if model else []) + list(GEMINI_MODELS)):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
            continue
        url = gemini_url(name)
        for attempt in (1, 2):
            started = time.time()
            try:
                status, answer_headers, raw = (transport or _post)(url, headers, data, timeout)
            except (OSError, http.client.HTTPException) as error:
                raise Unreachable(f"{provider.label} could not be reached ({type(error).__name__})") from None
            answer_headers = {header.lower(): value for header, value in answer_headers.items()}
            if status == 200:
                return _gemini_reply(provider, raw, answer_headers, started)
            problem = _refusal(provider, status, answer_headers, raw, started)
            if status == 503 and attempt == 1:
                sleep(GEMINI_BUSY_WAIT)  # busy: once more, a moment later
                continue
            break
        if status in (404, 500, 503):
            continue  # this model isn't served, or is too busy: the next one
        raise problem
    raise problem


def _gemini_reply(provider: Provider, raw: bytes, headers: dict, started: float) -> Reply:
    try:
        data = json.loads(raw)
        candidate = data["candidates"][0]
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
        finish = str(candidate.get("finishReason") or "")
        usage = data.get("usageMetadata") or {}
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ProviderError(f"{provider.label}'s answer could not be read") from None
    if not text.strip():
        raise ProviderError(f"{provider.label} gave an empty answer")
    day_limit, day_left, day_reset = _day(provider, headers, started)
    return Reply(text, int(usage.get("promptTokenCount") or 0), int(usage.get("candidatesTokenCount") or 0),
                 day_limit, day_left, day_reset, "length" if finish == "MAX_TOKENS" else finish.lower()[:20])


def _post(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict, bytes]:
    parts = urlsplit(url)
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout,
                                                 context=ssl.create_default_context())
    else:
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.request("POST", parts.path + (f"?{parts.query}" if parts.query else ""), body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read(MOST_ANSWER_BYTES)
    finally:
        connection.close()


def _refusal(provider: Provider, status: int, headers: dict, raw: bytes, started: float) -> ProviderError:
    said = _said(raw)
    if status == 429 or (provider.name == "cloudflare" and re.search(r"free allocation|neurons", said, re.I)):
        until = _retry_at(headers, started)
        if until is None:
            until = next_utc_midnight(started) if re.search(r"per day|daily|free allocation|neurons|per-day", said, re.I) \
                else started + 60
        return Limited(f"{provider.label} is at its free limit", until)
    if status in (401, 403):
        return KeyRefused(f"{provider.label} refused the key (HTTP {status}); add it again with "
                          f"`kairu provider add {provider.name}`")
    if status == 402:
        return ProviderError(f"{provider.label} asks for credit (HTTP 402); Kairu uses free models only")
    if status == 404 and re.search(r"data policy|data_collection|no endpoints", said, re.I):
        return ProviderError(f"{provider.label} has no free endpoint for this model that promises not to collect "
                             "your data, so nothing was sent there")
    if status >= 500:
        return Unreachable(f"{provider.label} had a problem of its own (HTTP {status})")
    return ProviderError(f"{provider.label} refused the request (HTTP {status}{': ' + said[:120] if said else ''})")


def _said(raw: bytes) -> str:
    """The provider's own error message, short; never the request."""
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return " ".join(error["message"].split())[:300]
    errors = data.get("errors") if isinstance(data, dict) else None
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return " ".join(str(errors[0].get("message", "")).split())[:300]
    return ""


DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?")


def seconds_of(text: str) -> float | None:
    """'7.66s', '2m59.56s', '1h2m3s', '120' -> seconds; None if it is not a duration."""
    text = (text or "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    match = DURATION.fullmatch(text)
    if not text or not match or not any(match.groups()):
        return None
    hours, minutes, seconds, millis = (float(part) if part else 0.0 for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _retry_at(headers: dict, started: float) -> float | None:
    wait = seconds_of(headers.get("retry-after", ""))
    if wait is not None:
        return started + wait
    reset = headers.get("x-ratelimit-reset") or ""  # OpenRouter: a time in milliseconds
    if reset.isdigit():
        moment = int(reset) / (1000 if int(reset) > 10**11 else 1)
        if moment > started:
            return moment
    return None


def _day(provider: Provider, headers: dict, started: float) -> tuple[int | None, int | None, float | None]:
    """The free day's count as the provider reports it: (limit, left, full again at), or Nones."""
    def number(name):
        value = headers.get(name, "")
        return int(value) if value.isdigit() else None

    if provider.name == "groq":
        wait = seconds_of(headers.get("x-ratelimit-reset-requests", ""))
        return (number("x-ratelimit-limit-requests"), number("x-ratelimit-remaining-requests"),
                None if wait is None else started + wait)
    if provider.name == "openrouter":
        return number("x-ratelimit-limit"), number("x-ratelimit-remaining"), _retry_at(headers, started)
    return None, None, None


def next_utc_midnight(moment: float) -> float:
    day = datetime.fromtimestamp(moment, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day.timestamp() + 86400


def valid_key(provider: Provider, key: str) -> str:
    """Why this cannot be a key ("" if it can be one). Only its shape: whether it works shows at the first question."""
    if not 16 <= len(key) <= 400:
        return "a key is 16 to 400 characters long"
    if any(c.isspace() or not c.isprintable() or not c.isascii() for c in key):
        return "a key has no spaces and only plain letters, digits and signs"
    return ""
