"""Gemini writes a meeting recording down (Meeting in, HACKATHON.md stage 1, ADR-055 proposed).

    media_part(data_dir, data, mime)   the recording as Gemini's own part: inline (base64) when it is small, else uploaded
                                       once to Gemini's Files API (generativelanguage.googleapis.com only, with the sealed key
                                       from `kairu provider add gemini`), waited for until Google has it ready
    forget_upload(data_dir, part)      delete that upload from Google again, right after the transcript came back
    wav(sound)                         16 kHz 16-bit mono sound from the mic, as a WAV in memory (meeting.record)

Only ever the one recording you approved with "yes" and your PIN, and only to Gemini. Nothing is written to disk here: the
recording goes from memory to Google and the upload is deleted when the transcript is back (Google deletes uploads after 48
hours anyway). Standard library only. For the tests, KAIRU_TEST_PROVIDERS points every address at a stand-in on this PC.
"""

import base64
import http.client
import io
import json
import os
import ssl
import time
import wave
from urllib.parse import urlsplit

from kairu.brain import keys
from kairu.brain.providers import PROVIDERS, TEST_PROVIDERS, USER_AGENT

INLINE_BYTES = 14 * 1024 * 1024  # base64 grows it by a third; Gemini takes a request of up to 20 MB
READY_SECONDS = 180  # a long video may take Google a while to get ready
POLL_SECONDS = 2.0
RATE = 16000


class HearingProblem(Exception):
    pass


def _base() -> str:
    test = os.environ.get(TEST_PROVIDERS, "")
    if test:
        parts = urlsplit(test)
        if parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1"):
            return test.rstrip("/") + "/gemini"
    return f"https://{PROVIDERS['gemini'].host}"


def _ours(url: str) -> bool:
    """Only Google's own Gemini address (or the tests' stand-in on this PC) is ever sent the recording or the key."""
    base = urlsplit(_base())
    parts = urlsplit(url)
    return parts.scheme == base.scheme and parts.hostname == base.hostname and parts.port == base.port


def _request(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple[int, dict, bytes]:
    parts = urlsplit(url)
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout,
                                                 context=ssl.create_default_context())
    else:
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.request(method, parts.path + (f"?{parts.query}" if parts.query else ""), body=body, headers=headers)
        response = connection.getresponse()
        return response.status, {name.lower(): value for name, value in response.getheaders()}, response.read(1 << 20)
    finally:
        connection.close()


def _key(data_dir) -> str:
    found = keys.load(data_dir, "gemini")
    if not found:
        raise HearingProblem("Gemini isn't set up yet: `kairu provider add gemini`")
    return found[0]


def media_part(data_dir, data: bytes, mime: str, request=None, sleep=time.sleep, clock=time.monotonic) -> dict:
    if not data:
        raise HearingProblem("the recording is empty")
    if len(data) <= INLINE_BYTES:
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}}
    request = request or _request
    key = _key(data_dir)
    base = _base()
    try:
        status, headers, raw = request("POST", f"{base}/upload/v1beta/files", {
            "x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(data)), "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json", "User-Agent": USER_AGENT},
            json.dumps({"file": {"display_name": "kairu-meeting"}}).encode(), 60)
        upload = headers.get("x-goog-upload-url", "")
        if status != 200 or not upload:
            raise HearingProblem(f"Gemini didn't take the upload (HTTP {status})")
        if not _ours(upload):
            raise HearingProblem("Gemini named an upload address that isn't Google's own")
        status, headers, raw = request("POST", upload, {
            "x-goog-api-key": key, "Content-Length": str(len(data)), "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize", "User-Agent": USER_AGENT}, data, 600)
        if status != 200:
            raise HearingProblem(f"the upload to Gemini failed (HTTP {status})")
        found = json.loads(raw).get("file") or {}
        name, uri = str(found.get("name", "")), str(found.get("uri", ""))
        if not name.startswith("files/") or not _ours(uri):
            raise HearingProblem("Gemini's answer to the upload could not be read")
        deadline = clock() + READY_SECONDS
        state = found.get("state", "")
        while state == "PROCESSING":
            if clock() > deadline:
                raise HearingProblem("Google took too long to get the recording ready")
            sleep(POLL_SECONDS)
            status, headers, raw = request("GET", f"{base}/v1beta/{name}", {"x-goog-api-key": key, "User-Agent": USER_AGENT},
                                           None, 30)
            state = (json.loads(raw) if status == 200 else {}).get("state", "FAILED")
        if state not in ("ACTIVE", ""):
            raise HearingProblem(f"Google couldn't read the recording ({str(state)[:20].lower()})")
    except (OSError, http.client.HTTPException) as error:
        raise HearingProblem(f"Gemini could not be reached ({type(error).__name__})") from None
    except ValueError:
        raise HearingProblem("Gemini's answer to the upload could not be read") from None
    return {"file_data": {"mime_type": mime, "file_uri": uri}}


def forget_upload(data_dir, part: dict, request=None) -> None:
    """Delete an upload from Google right away (only one media_part made; an inline part has nothing to delete)."""
    uri = str((part.get("file_data") or {}).get("file_uri", ""))
    if not uri or not _ours(uri) or "/files/" not in uri:
        return
    name = "files/" + uri.rsplit("/files/", 1)[1].split("?")[0]
    try:
        (request or _request)("DELETE", f"{_base()}/v1beta/{name}", {"x-goog-api-key": _key(data_dir), "User-Agent": USER_AGENT},
                              None, 30)
    except (OSError, http.client.HTTPException, HearingProblem):
        pass  # Google deletes it after 48 hours anyway


def wav(sound: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(sound)
    return out.getvalue()


def minutes_of(name: str, data: bytes) -> float | None:
    """How long a recording is, when that's easy to know (a WAV); else None."""
    if not name.lower().endswith(".wav"):
        return None
    try:
        with wave.open(io.BytesIO(data)) as file:
            return round(file.getnframes() / float(file.getframerate()) / 60, 1)
    except (wave.Error, EOFError, ZeroDivisionError):
        return None
