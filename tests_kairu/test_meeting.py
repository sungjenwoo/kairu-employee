"""Meeting in (HACKATHON.md stage 1, ADR-055 proposed): a meeting becomes decisions, owners, deadlines and open questions.

No test reaches Google or opens a microphone: Gemini is the stand-in on this PC (KAIRU_TEST_PROVIDERS), its Files API a
recorded request function, and the mic a list of sound chunks.
"""

import json
import os
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from kairu import executors, policy
from kairu.brain import keys
from kairu.brain.gateway import Gateway
from kairu.brain.providers import ProviderError, gemini_build, media_ok
from kairu.meeting import conduct, hear, orders, read
from kairu.meeting.store import MeetingStore
from kairu.policy import Tier
from kairu.tasks.core import TaskCore
from kairu.tasks.store import TaskStore
from tests_kairu.fake_provider import FakeProviders
from tests_kairu.helpers import POLICY
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_day4_program import Owner

GEMINI_KEY = "AIza" + "k" * 35
JOB = "b" * 16
DEMO = Path(__file__).resolve().parent.parent / "tools" / "demo_meetings"
KICKOFF = DEMO / "2026-11-12 Fresh Bakes kickoff.vtt"
HELD = date(2026, 11, 12)
RULES = policy.load(POLICY).rules

ANSWER = {
    "title": "Fresh Bakes kickoff", "summary": "The team set the scope of the Fresh Bakes website and gave out the first tasks.",
    "people": ["Saitej", "Anu", "Ravi", "Priya"],
    "decisions": [
        {"what": "Drop the mobile app; build a website that works well on phones.", "owner": "", "due": "", "due_said": "",
         "replaces": "", "quote": "Okay, decided: we drop the mobile app.", "at": "00:24", "sure": "high"},
        {"what": "Launch on 28 November.", "owner": "Saitej", "due": "2026-11-28", "due_said": "the 28th of November",
         "quote": "Launch is on the 28th of November.", "at": "02:10", "sure": "high"}],
    "actions": [
        {"what": "Design the homepage, first mockup.", "owner": "Priya", "due": "2026-11-17", "due_said": "by Monday",
         "quote": "I'll do the homepage design. I can have the first mockup by Monday.", "at": "00:36", "sure": "high"},
        {"what": "Set up hosting and the domain.", "owner": "", "due": "", "due_said": "",
         "quote": "Let's leave hosting open for now", "at": "", "sure": "medium"},
        {"what": "Build the menu page.", "owner": "Ravi", "due": "20 Nov", "due_said": "Friday the 20th",
         "quote": "words nobody ever said in this meeting", "at": "00:48", "sure": "low"}],
    "questions": [{"what": "Does the client want online payments or only pickup orders?", "owner": "Saitej",
                   "quote": "does the client want online payments or just pickup orders?", "at": "01:10", "sure": "high"}]}


def transcript() -> str:
    return "\n".join(read.transcript_of(KICKOFF.name, KICKOFF.read_bytes()))


# --- the policy and the executors ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, tier", [("meeting.read", Tier.HIGH), ("meeting.record", Tier.HIGH), ("meeting.stop", Tier.LOW),
                                        ("meeting.show", Tier.LOW), ("meeting.forget", Tier.MEDIUM)])
def test_each_meeting_action_has_its_tier_and_code(name, tier):
    assert RULES[name].tier is tier
    assert name in executors.EXECUTORS


def test_the_data_folder_brain_and_work_folder_come_from_guardian_never_a_request():
    read_it = executors.EXECUTORS["meeting.read"]
    assert set(read_it.supplied) == {"data_dir", "brain", "work_folder"}
    assert not {"data_dir", "brain", "work_folder"} & set(read_it.arguments)
    assert executors.EXECUTORS["meeting.record"].single
    assert "sha" in read_it.arguments  # the approval is for exactly that file


# --- transcript files ------------------------------------------------------------------------------------------------

def test_a_teams_vtt_becomes_one_line_per_turn_with_its_time_and_speaker():
    lines = read.transcript_of(KICKOFF.name, KICKOFF.read_bytes())
    assert lines[0].startswith("[00:00] Saitej: Okay everyone")
    assert lines[1] == "[00:14] Anu: Honestly I think a mobile app is too much for this budget and this timeline."
    assert not any("-->" in line or line.strip().isdigit() or "<v" in line for line in lines)


def test_an_srt_with_names_in_the_words_and_a_plain_text_are_read_too():
    srt = b"1\n00:00:01,000 --> 00:00:03,000\nRavi: I'll fix the login bug.\n\n2\n00:01:05,500 --> 00:01:07,000\nAnu: Thanks.\n"
    assert read.transcript_of("call.srt", srt) == ["[00:01] Ravi: I'll fix the login bug.", "[01:05] Anu: Thanks."]
    assert read.transcript_of("notes.txt", b"Ravi: hello\r\n\r\n  Anu:   hi  \n") == ["Ravi: hello", "Anu: hi"]
    with pytest.raises(read.NotAMeeting):
        read.transcript_of("empty.txt", b" \n\n")


def test_only_recordings_and_transcripts_are_meetings():
    assert read.kind_of("standup.MP3") == "audio" and read.kind_of("call.webm") == "audio" and read.kind_of("a.vtt") == "text"
    assert read.mime_of("x.m4a") == "audio/mp4" and read.mime_of("x.mp4") == "video/mp4"
    for name in ("setup.exe", "notes.docx", "photo.png", "script.py"):
        with pytest.raises(read.NotAMeeting):
            read.kind_of(name)


def test_a_line_with_a_secret_is_left_out_before_anything_is_kept_or_sent():
    lines, count = read.left_out(["Ravi: the wifi password is Tiger@1234", "Anu: launch on Friday"])
    assert count == 1 and lines == [read.SECRET_LINE, "Anu: launch on Friday"]


# --- Gemini's answer, read strictly ----------------------------------------------------------------------------------

def test_the_answer_becomes_decisions_actions_and_questions_with_owners_and_real_dates():
    reading = read.parse("```json\n" + json.dumps(ANSWER) + "\n```", transcript(), HELD)
    kinds = [item["kind"] for item in reading["items"]]
    assert kinds == ["decision", "decision", "action", "action", "action", "question"]
    homepage = reading["items"][2]
    assert homepage["owner"] == "Priya" and homepage["due"] == "2026-11-17" and homepage["due_said"] == "by Monday"
    assert homepage["heard"] and homepage["owner_heard"] and homepage["at"] == "00:36"
    assert reading["items"][3]["owner"] == ""  # nobody took hosting: never a guessed owner
    menu = reading["items"][4]
    assert menu["due"] == "" and menu["due_said"] == "Friday the 20th"  # "20 Nov" isn't a date: dropped, never guessed
    assert not menu["heard"]  # a quote that isn't in the transcript is never shown as evidence
    assert reading["people"] == ["Saitej", "Anu", "Ravi", "Priya"]


@pytest.mark.parametrize("bad", ["Sure! The team decided to drop the app.", '{"decisions": "drop the app"}',
                                 '{"actions": [{"owner": "Ravi"}]}', "[1, 2]"])
def test_an_answer_that_is_not_the_shape_asked_for_is_refused(bad):
    with pytest.raises(read.NoReading):
        read.parse(bad, transcript(), HELD)


def test_a_date_far_from_the_meeting_and_an_item_holding_a_secret_are_dropped():
    data = {"decisions": [{"what": "Ship it", "due": "2031-01-01", "quote": ""},
                          {"what": "Use the key sk-or-" + "a" * 40, "quote": ""}], "actions": [], "questions": []}
    reading = read.parse(json.dumps(data), "Ship it", HELD)
    assert len(reading["items"]) == 1 and reading["items"][0]["due"] == ""


def test_a_quote_may_differ_by_a_word_at_either_end_but_not_more():
    said = "Saitej: Okay, decided: we drop the mobile app. Website only."
    assert read.heard("decided: we drop the mobile app", said)
    assert read.heard("so decided we drop the mobile app", said)
    assert not read.heard("we keep the mobile app", said)
    assert not read.heard("", said)


def test_gemini_is_told_the_meeting_day_so_friday_becomes_a_date():
    told = read.instructions(HELD, "Kickoff")
    assert "Thursday 12 November 2026" in told and "2026-11-12" in told and "never guess an owner" in told


# --- the Gateway and the recording part ------------------------------------------------------------------------------

def gemini_said(text):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
                       "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}).encode()


def test_a_meeting_goes_to_gemini_only_and_needs_its_key(tmp_path):
    sent = []

    def transport(url, headers, body, timeout):
        sent.append((url, json.loads(body)))
        return 200, {}, gemini_said("[00:00] Ravi: hello")

    keys.save(tmp_path, "groq", "gsk_" + "g" * 52)
    gateway = Gateway(tmp_path, {"public_to_cloud": True, "providers": ["groq"]}, transport=transport, sleep=lambda s: None)
    part = {"inline_data": {"mime_type": "audio/wav", "data": "AAAA"}}
    missing = gateway.meeting(read.HEAR, "Transcribe this meeting recording.", media=part)
    assert missing.status == "not_sent" and "Gemini" in missing.text and sent == []
    keys.save(tmp_path, "gemini", GEMINI_KEY)
    result = gateway.meeting(read.HEAR, "Transcribe this meeting recording.", media=part)
    assert result.status == "answered" and result.provider == "gemini" and len(sent) == 1
    url, body = sent[0]
    assert ":generateContent" in url and body["contents"][-1]["parts"][-1] == part
    assert body["generationConfig"]["maxOutputTokens"] > 8192  # a whole meeting's transcript fits


def test_only_a_meeting_recording_part_may_ride_along():
    assert media_ok({"inline_data": {"mime_type": "audio/mp3", "data": "AAAA"}})
    assert media_ok({"file_data": {"mime_type": "video/mp4", "file_uri": "https://generativelanguage.googleapis.com/v1beta/files/x"}})
    for bad in ({"inline_data": {"mime_type": "image/png", "data": "AAAA"}},
                {"file_data": {"mime_type": "audio/mp3", "file_uri": "https://evil.example/files/x"}},
                {"inline_data": {"mime_type": "audio/mp3", "data": "AAAA"}, "text": "x"}, "audio", None):
        assert not media_ok(bad)
    with pytest.raises(ProviderError):
        gemini_build(GEMINI_KEY, [{"role": "user", "content": "x"}], media={"inline_data": {"mime_type": "text/html", "data": "x"}},
                     transport=lambda *a: (200, {}, gemini_said("x")), sleep=lambda s: None)


def test_a_small_recording_goes_inline_and_a_big_one_is_uploaded_then_deleted(tmp_path):
    assert hear.media_part(tmp_path, b"RIFF....", "audio/wav") == {"inline_data": {"mime_type": "audio/wav", "data": "UklGRi4uLi4="}}
    keys.save(tmp_path, "gemini", GEMINI_KEY)
    calls = []
    states = iter(["PROCESSING", "ACTIVE"])

    def request(method, url, headers, body, timeout):
        calls.append((method, url))
        if url.endswith("/upload/v1beta/files"):
            assert headers["X-Goog-Upload-Command"] == "start" and headers["x-goog-api-key"] == GEMINI_KEY
            return 200, {"x-goog-upload-url": "https://generativelanguage.googleapis.com/upload/v1beta/files?upload_id=1"}, b"{}"
        if "upload_id" in url:
            return 200, {}, json.dumps({"file": {"name": "files/abc", "state": "PROCESSING",
                                                 "uri": "https://generativelanguage.googleapis.com/v1beta/files/abc"}}).encode()
        if method == "GET":
            return 200, {}, json.dumps({"state": next(states)}).encode()
        return 200, {}, b"{}"

    big = b"\0" * (hear.INLINE_BYTES + 1)
    part = hear.media_part(tmp_path, big, "audio/mp3", request=request, sleep=lambda s: None)
    assert part == {"file_data": {"mime_type": "audio/mp3", "file_uri": "https://generativelanguage.googleapis.com/v1beta/files/abc"}}
    hear.forget_upload(tmp_path, part, request=request)
    assert [method for method, _ in calls] == ["POST", "POST", "GET", "GET", "DELETE"]
    assert calls[-1][1].endswith("/v1beta/files/abc")


def test_an_upload_address_that_is_not_googles_is_never_sent_the_recording(tmp_path):
    keys.save(tmp_path, "gemini", GEMINI_KEY)
    sent = []

    def request(method, url, headers, body, timeout):
        sent.append(url)
        return 200, {"x-goog-upload-url": "https://evil.example/upload"}, b"{}"

    with pytest.raises(hear.HearingProblem, match="isn't Google's"):
        hear.media_part(tmp_path, b"\0" * (hear.INLINE_BYTES + 1), "audio/mp3", request=request)
    assert len(sent) == 1


# --- meeting.read and meeting.record, with the stand-in Gemini --------------------------------------------------------

@pytest.fixture
def gemini(monkeypatch):
    fake = FakeProviders()
    monkeypatch.setenv("KAIRU_TEST_PROVIDERS", fake.url)
    yield fake
    fake.close()


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / "Kairu-files"
    (folder / "meetings").mkdir(parents=True)
    shutil.copy(KICKOFF, folder / "meetings" / "kickoff.vtt")
    return folder


BRAIN = {"public_to_cloud": True, "providers": ["groq"]}


def reply_of(data_dir):
    return TaskStore(data_dir).take_reply(JOB)


def test_a_transcript_file_becomes_a_meeting_with_its_items_kept_on_this_pc(tmp_path, gemini, work):
    data = tmp_path / "data"
    keys.save(data, "gemini", GEMINI_KEY)
    gemini.answers["gemini"] = json.dumps(ANSWER)
    sha = conduct.sha_of((work / "meetings" / "kickoff.vtt").read_bytes())
    assert conduct.read_meeting(str(data), JOB, "meetings/kickoff.vtt", sha, "", "2026-11-12", BRAIN, str(work)) is None
    said = reply_of(data)
    assert said.ok and said.text.startswith("Meeting 1 read: Fresh Bakes kickoff (12 Nov). 2 decisions, 3 actions, 1 open question.")
    assert "1 action has no owner yet." in said.text and "Design the homepage, first mockup → Priya by Tue 17 Nov" in said.text
    sent = gemini.heard("gemini")
    assert len(sent) == 1  # a transcript is only read, not heard
    words = sent[0]["body"]["contents"][-1]["parts"][0]["text"]
    assert words.startswith("Meeting transcript:\n[00:00] Saitej:") and sent[0]["body"]["generationConfig"]["responseMimeType"] == \
        "application/json"
    meeting = MeetingStore(data).meeting(1, transcript=True)
    assert meeting["held"] == "2026-11-12" and meeting["heard"] == "transcript" and meeting["file"] == "meetings/kickoff.vtt"
    assert len(meeting["items"]) == 6 and all(item["status"] == "open" for item in meeting["items"])
    assert meeting["transcript"][1].startswith("[00:14] Anu:")


def test_a_changed_file_a_file_outside_the_work_folder_and_no_file_are_refused(tmp_path, gemini, work):
    data = tmp_path / "data"
    keys.save(data, "gemini", GEMINI_KEY)
    outside = tmp_path / "secret.txt"
    outside.write_text("Ravi: private")
    cases = [("meetings/kickoff.vtt", "0" * 64, "changed after you approved it"),
             (str(outside), conduct.sha_of(outside.read_bytes()), "outside your work folder"),
             ("../secret.txt", conduct.sha_of(outside.read_bytes()), "outside your work folder"),
             ("nothing.vtt", "0" * 64, "there's no file")]
    for file, sha, why in cases:
        conduct.read_meeting(str(data), JOB, file, sha, "", "", BRAIN, str(work))
        said = reply_of(data)
        assert not said.ok and why in said.text, said.text
    assert gemini.heard("gemini") == []  # nothing left


def test_a_recording_is_heard_by_gemini_then_read(tmp_path, gemini, work):
    data = tmp_path / "data"
    keys.save(data, "gemini", GEMINI_KEY)
    (work / "standup.mp3").write_bytes(b"ID3" + b"\0" * 200)
    gemini.script["gemini"] = ["[00:00] Saitej: Okay, decided: we drop the mobile app.\n[00:05] Priya: I'll do the homepage design.",
                               json.dumps({"title": "Standup", "summary": "", "people": ["Saitej", "Priya"], "decisions": [
                                   {"what": "Drop the mobile app.", "quote": "we drop the mobile app", "sure": "high"}],
                                   "actions": [], "questions": []})]
    sha = conduct.sha_of((work / "standup.mp3").read_bytes())
    conduct.read_meeting(str(data), JOB, "standup.mp3", sha, "", "", BRAIN, str(work))
    assert reply_of(data).ok
    first, second = gemini.heard("gemini")
    audio = first["body"]["contents"][-1]["parts"][-1]["inline_data"]
    assert audio["mime_type"] == "audio/mp3" and "Transcribe this meeting" in first["body"]["contents"][-1]["parts"][0]["text"]
    assert "speaker" in first["body"]["systemInstruction"]["parts"][0]["text"].lower()
    assert "inline_data" not in json.dumps(second["body"])  # the recording is sent once
    meeting = MeetingStore(data).meeting(1)
    assert meeting["heard"] == "gemini" and meeting["items"][0]["heard"]


class Mic:
    def __init__(self, chunks, stop_after, data_dir):
        self.chunks, self.stop_after, self.data_dir, self.read_count, self.closed = chunks, stop_after, data_dir, 0, False

    def read(self):
        self.read_count += 1
        if self.read_count == self.stop_after:
            assert self.stop_after < 10 or conduct.live(self.data_dir)["seconds"] >= 0  # the page sees the recording
            (Path(self.data_dir) / conduct.STOP_FILE).write_text("stop")
        return self.chunks

    def close(self):
        self.closed = True


def test_a_recording_from_the_mic_stays_in_memory_until_end_and_then_becomes_a_meeting(tmp_path, gemini, work):
    data = tmp_path / "data"
    data.mkdir()
    keys.save(data, "gemini", GEMINI_KEY)
    chunk = (b"\x10\x27" * 1600)  # a tenth of a second, loud
    mic = Mic(chunk, stop_after=80, data_dir=str(data))
    now = iter(x * 0.1 for x in range(100000))
    gemini.script["gemini"] = ["[00:00] Anu: I'll set up hosting by Saturday.",
                               json.dumps({"title": "Quick call", "summary": "Hosting.", "people": ["Anu"], "decisions": [],
                                           "actions": [{"what": "Set up hosting.", "owner": "Anu", "due": "2026-11-21",
                                                        "quote": "I'll set up hosting by Saturday", "sure": "high"}],
                                           "questions": []})]
    before = set(os.listdir(tmp_path))
    conduct.record(str(data), JOB, "", 60, "2026-11-19", BRAIN, open_mic=lambda: mic, clock=lambda: next(now))
    said = reply_of(data)
    assert said.ok and "Set up hosting → Anu by Sat 21 Nov" in said.text
    assert mic.closed and conduct.live(str(data)) is None and not (data / conduct.STOP_FILE).exists()
    assert gemini.heard("gemini")[0]["body"]["contents"][-1]["parts"][-1]["inline_data"]["mime_type"] == "audio/wav"
    assert set(os.listdir(tmp_path)) == before  # no sound written anywhere
    assert not any(name.endswith((".wav", ".raw", ".pcm")) for name in os.listdir(data))
    assert MeetingStore(data).meeting(1)["heard"] == "mic"


def test_a_too_short_recording_sends_nothing(tmp_path, gemini):
    data = tmp_path / "data"
    data.mkdir()
    mic = Mic(b"\0" * 3200, stop_after=3, data_dir=str(data))
    now = iter(x * 0.1 for x in range(1000))
    conduct.record(str(data), JOB, "", 60, "", BRAIN, open_mic=lambda: mic, clock=lambda: next(now))
    said = reply_of(data)
    assert not said.ok and "only 0 seconds" in said.text and gemini.heard() == []


def test_show_and_forget(tmp_path):
    data = tmp_path / "data"
    conduct.show(str(data), JOB, 0)
    assert "No meetings yet" in reply_of(data).text
    reading = read.parse(json.dumps(ANSWER), transcript(), HELD)
    number = MeetingStore(data).add("Kickoff", "2026-11-12", "k.vtt", "x", "transcript", ["a"], reading)
    conduct.show(str(data), JOB, 0)
    assert reply_of(data).text.startswith("Meeting 1: Kickoff (12 Nov). 2 decisions")
    conduct.forget(str(data), JOB, number)
    assert reply_of(data).ok and MeetingStore(data).meeting(number) is None


# --- the orders ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("said, kind", [
    ("read the meeting kickoff.vtt", "read"), ("transcribe the meeting recording standup.mp3", "read"),
    ("pull out the decisions from the meeting kickoff", "read"), ("go through the call notes.txt", "read"),
    ("record the meeting", "record"), ("record the meeting called Sprint planning", "record"), ("start recording the call", "record"),
    ("end the meeting", "end"), ("stop the recording", "end"), ("finish the meeting", "end"),
    ("show the last meeting", "show"), ("what did we decide in the meeting", "show"), ("show meeting 2", "show"),
    ("open notepad", None), ("stop", None), ("read my email", None)])
def test_the_meeting_orders(said, kind):
    found = {"read": orders.READ.fullmatch(said), "record": orders.RECORD.fullmatch(said), "end": orders.END.fullmatch(said),
             "show": orders.SHOW.fullmatch(said)}
    assert [name for name, match in found.items() if match] == ([kind] if kind else [])


def test_a_meeting_is_found_by_its_name_in_the_work_folder_or_its_meetings_folder(work):
    assert orders.find(work, "meetings/kickoff.vtt") == "meetings/kickoff.vtt"
    assert orders.find(work, "kickoff.vtt") == "meetings/kickoff.vtt"
    assert orders.find(work, "Kickoff") == "meetings/kickoff.vtt"
    assert orders.find(work, "../../etc/passwd") == ""
    assert orders.find(work, "nothing") == ""


# --- through the real Guardian program: the card first, then Gemini ---------------------------------------------------

@pytest.fixture
def config_path(tmp_path, monkeypatch, work, gemini):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "brain": {"public_to_cloud": True, "providers": ["groq"]},
                                    "tasks": {"work_folder": str(work)},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


def test_read_the_meeting_shows_the_card_with_the_file_then_gemini_reads_it(program_with_pin, gemini):
    keys.save(program_with_pin.data_dir, "gemini", GEMINI_KEY)
    gemini.answers["gemini"] = json.dumps(ANSWER)
    owner = Owner(program_with_pin)
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=owner.approver, confirmer=owner.confirmer)
    said = core.handle("read the meeting kickoff")
    assert "Meeting 1 read: Fresh Bakes kickoff" in said, said
    assert len(owner.cards) == 1 and owner.cards[0].action.name == "meeting.read"
    details = owner.cards[0].action.details
    assert details["file"] == "meetings/kickoff.vtt" and len(details["sha"]) == 64
    assert "Meeting 1:" in core.handle("show the last meeting")


def test_a_refused_card_sends_nothing(program_with_pin, gemini):
    owner = Owner(program_with_pin, yes=False)
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=owner.approver, confirmer=owner.confirmer)
    assert core.handle("read the meeting kickoff.vtt") == "Not done: you refused it."
    assert gemini.heard() == []
