"""The Model Gateway (Phase B): free providers with switching, the privacy filter and the backstop, usage, keys.

Everything here talks to a stand-in transport: nothing leaves the PC.
"""

import json
import os
import time

import pytest

from kairu.brain import keys, providers, usage
from kairu.brain.actions import pause
from kairu.brain.gateway import ANSWERED, DATED_NOTE, NEEDS_APPROVAL, NOT_SENT, REFUSED, Gateway, tidy
from kairu.brain.store import BrainStore

SETTINGS = {"public_to_cloud": True, "providers": ["groq", "cloudflare", "openrouter"], "daily_cap": 0, "models": {}}
ACCOUNT = "0123456789abcdef0123456789abcdef"


class Transport:
    """Stands in for the providers: answers, or a status, per provider; remembers every request."""

    def __init__(self):
        self.sent, self.answers, self.status = [], {}, {}

    def __call__(self, url, headers, body, timeout):
        name = next(name for name, known in providers.PROVIDERS.items() if known.host in url)
        self.sent.append({"provider": name, "url": url, "headers": headers, "body": json.loads(body)})
        if name in self.status:
            return self.status[name]
        reply = {"choices": [{"message": {"content": self.answers.get(name, f"An answer from {name}.")}}],
                 "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        extra = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
                 "x-ratelimit-reset-requests": "1m"} if name == "groq" else {}
        return 200, extra, json.dumps(reply).encode()

    def to(self, name):
        return [request for request in self.sent if request["provider"] == name]

    def limited(self, name, retry_after="600"):
        self.status[name] = (429, {"Retry-After": retry_after}, b'{"error": {"message": "requests per day"}}')


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv(providers.TEST_PROVIDERS, raising=False)
    keys.save(tmp_path, "groq", "gsk_" + "a" * 40)
    keys.save(tmp_path, "cloudflare", "cf" + "b" * 38, ACCOUNT)
    return tmp_path


@pytest.fixture
def transport():
    return Transport()


def gateway(data_dir, transport, guardian=None, **settings):
    asked = guardian or (lambda message: {"verdict": "ok", "mode": "normal", "running": []})
    return Gateway(data_dir, {**SETTINGS, **settings}, transport, asked, sleep=lambda seconds: None)


# --- L3: public questions --------------------------------------------------------------------------

def test_a_public_question_goes_to_the_first_provider_and_the_answer_is_short_and_warm(data_dir, transport):
    transport.answers["groq"] = "**Narendra Modi** is the Prime Minister of India.\nWant to know more about him?"
    result = gateway(data_dir, transport).ask("who is the prime minister of India", "pc")
    assert (result.status, result.level, result.provider) == (ANSWERED, "L3", "groq")
    assert result.text.startswith("Narendra Modi is the Prime Minister") and result.text.endswith(DATED_NOTE)
    [request] = transport.sent
    assert request["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer gsk_" + "a" * 40
    assert request["body"]["model"] == "openai/gpt-oss-120b" and request["body"]["reasoning_effort"] == "low"
    assert "gsk_" not in json.dumps(request["body"])  # the key goes only in its header
    assert [message["role"] for message in request["body"]["messages"]] == ["system", "user"]


def test_at_a_free_limit_kairu_switches_to_the_next_provider_and_usage_shows_it(data_dir, transport):
    transport.limited("groq")
    result = gateway(data_dir, transport).ask("what is photosynthesis", "pc")
    assert (result.status, result.provider) == (ANSWERED, "cloudflare")
    assert "Groq at its free limit -> switched to Cloudflare" in result.note
    assert len(transport.to("groq")) == 1 and len(transport.to("cloudflare")) == 1  # one try each: no retry storm
    assert ACCOUNT in transport.to("cloudflare")[0]["url"]
    again = gateway(data_dir, transport).ask("what is gravity", "pc")
    assert again.provider == "cloudflare" and len(transport.to("groq")) == 1  # left alone until it is free again
    lines = "\n".join(usage.report(data_dir, SETTINGS))
    assert "at its free limit until" in lines and "switched to Cloudflare" in lines


def test_when_one_frees_up_within_seconds_kairu_waits_once_otherwise_it_says_when(data_dir, transport):
    transport.limited("groq", retry_after="1")
    transport.limited("cloudflare", retry_after="1")
    waited = []

    def sleep(seconds):
        waited.append(seconds)
        time.sleep(seconds)

    first = Gateway(data_dir, SETTINGS, transport, None, sleep=sleep).ask("what is photosynthesis", "pc")
    assert len(waited) == 1 and first.status == NOT_SENT  # still limited after the one wait: no loop
    assert len(transport.sent) == 4
    transport.limited("groq", retry_after="3600")
    transport.limited("cloudflare", retry_after="3600")
    BrainStore(data_dir).free_again("groq"), BrainStore(data_dir).free_again("cloudflare")
    later = gateway(data_dir, transport).ask("what is gravity", "pc")
    assert later.status == NOT_SENT and "Ask again after" in later.text


def test_a_refused_key_or_an_unreachable_provider_is_skipped(data_dir, transport):
    transport.status["groq"] = (401, {}, b'{"error": {"message": "Invalid API Key"}}')
    result = gateway(data_dir, transport).ask("what is photosynthesis", "pc")
    assert result.provider == "cloudflare" and "refused its key" in result.note
    assert "until you add its key again" in usage.state(data_dir, "groq", BrainStore(data_dir))[1]


def test_nothing_set_up_says_how(tmp_path, transport, monkeypatch):
    monkeypatch.delenv(providers.TEST_PROVIDERS, raising=False)
    result = gateway(tmp_path, transport).ask("what is photosynthesis", "pc")
    assert result.status == NOT_SENT and "kairu provider add groq" in result.text and not transport.sent
    personal = gateway(tmp_path, transport).ask("call me on 9876543210", "pc")
    assert (personal.status, personal.provider) == (NEEDS_APPROVAL, "")  # nowhere to approve it for, so it says so


def test_a_cap_is_there_only_if_you_set_one(data_dir, transport):
    for _ in range(3):
        assert gateway(data_dir, transport).ask("what is photosynthesis", "pc").status == ANSWERED
    capped = gateway(data_dir, transport, daily_cap=3).ask("what is gravity", "pc")
    assert capped.status == NOT_SENT and "brain.daily_cap" in capped.text and len(transport.sent) == 3


# --- the privacy filter and the backstop ------------------------------------------------------------

def test_a_personal_question_is_not_sent_it_waits_for_approval(data_dir, transport):
    result = gateway(data_dir, transport).ask("my friend Ravi's number is 9876543210, what should I tell him", "pc")
    assert (result.status, result.provider) == (NEEDS_APPROVAL, "groq") and "a phone number" in result.reasons
    assert transport.sent == []


def test_option_b_every_cloud_send_waits(data_dir, transport):
    result = gateway(data_dir, transport, public_to_cloud=False).ask("what is photosynthesis", "pc")
    assert result.status == NEEDS_APPROVAL and "public_to_cloud" in result.reasons[0] and transport.sent == []


def test_a_secret_is_never_sent_not_even_with_approval(data_dir, transport):
    gate = gateway(data_dir, transport)
    asked = gate.ask("my password is Tiger@123, is it strong?", "pc")
    assert asked.status == REFUSED and "Tiger@123" not in asked.text
    approved = gate.send_private("my password is Tiger@123, is it strong?", "groq", "pc")
    assert approved.status == REFUSED and transport.sent == []


def test_the_backstop_refuses_text_with_a_secret_whatever_let_it_through(data_dir, transport):
    with pytest.raises(providers.Backstopped):
        providers.chat(providers.PROVIDERS["groq"], "gsk_" + "a" * 40,
                       [{"role": "user", "content": "here is my key sk-proj-abcdefghijklmnopqrstuvwx"}], transport=transport)
    assert transport.sent == []


def test_an_approved_send_goes_only_to_the_approved_provider(data_dir, transport):
    transport.limited("groq")
    result = gateway(data_dir, transport).send_private("my friend Ravi's number is 9876543210, what should I tell him", "groq", "pc")
    assert result.status == NOT_SENT and "only to the provider you approved" in result.text
    assert len(transport.to("groq")) == 1 and transport.to("cloudflare") == []
    BrainStore(data_dir).free_again("groq")
    transport.status.clear()
    sent = gateway(data_dir, transport).send_private("my friend Ravi's number is 9876543210, what should I tell him", "groq", "pc")
    assert sent.status == ANSWERED and transport.to("groq")[-1]["body"]["messages"][-1]["content"].endswith("my friend Ravi's number is 9876543210, what should I tell him")


def test_a_follow_up_sends_the_last_public_exchange_but_never_a_personal_one(data_dir, transport):
    gate = gateway(data_dir, transport)
    gate.ask("who is the prime minister of India", "pc")
    gate.ask("yes, tell me more", "pc")
    assert [message["role"] for message in transport.sent[-1]["body"]["messages"]] == ["system", "user", "assistant", "user"]
    gate.ask("my friend Ravi's number is 9876543210, what should I tell him", "pc")  # personal: not kept
    gate.ask("tell me more", "pc")
    assert [message["role"] for message in transport.sent[-1]["body"]["messages"]] == ["system", "user"]
    assert gate.ask("tell me more", "dev-0123456789abcdef").status == ANSWERED  # each place has its own


# --- L0 and L4 --------------------------------------------------------------------------------------

def test_l0_answers_here_and_sends_nothing(data_dir, transport):
    gate = gateway(data_dir, transport)
    for question in ("what time is it", "what's the date today", "hello", "thanks", "help", "usage", "status"):
        result = gate.ask(question, "pc")
        assert (result.status, result.level) == (ANSWERED, "L0") and result.text
    assert transport.sent == []


def test_a_request_to_do_something_goes_to_guardian_and_nothing_runs(data_dir, transport):
    asked = []

    def guardian(message):
        asked.append(message)
        return {"verdict": "deny", "tier": "Critical", "reason": "Critical tier: always refused"}

    result = gateway(data_dir, transport, guardian).ask("pay my electricity bill", "pc")
    assert asked == [{"op": "check", "action": "money.spend", "details": {}}]
    assert "Guardian refused it" in result.text and "Nothing ran" in result.text and transport.sent == []


def test_team_mode_comes_with_phase_g(data_dir, transport):
    result = gateway(data_dir, transport).ask("build me a website for my shop", "pc")
    assert result.level == "L4" and "Phase G" in result.text and transport.sent == []


# --- providers, keys and the answer -----------------------------------------------------------------

def test_openrouter_is_asked_never_to_send_to_a_provider_that_collects_data(data_dir, transport):
    keys.save(data_dir, "openrouter", "sk-or-v1-" + "c" * 40)
    result = gateway(data_dir, transport, providers=["openrouter"]).ask("what is photosynthesis", "pc")
    assert result.provider == "openrouter"
    body = transport.to("openrouter")[0]["body"]
    assert body["provider"] == {"data_collection": "deny"} and [m["role"] for m in body["messages"]] == ["user"]
    transport.status["openrouter"] = (404, {}, b'{"error": {"message": "No endpoints found matching your data policy"}}')
    BrainStore(data_dir).free_again("openrouter")
    refused = gateway(data_dir, transport, providers=["openrouter"]).ask("what is gravity", "pc")
    assert refused.status == NOT_SENT and "promises not to collect" in refused.text


def test_pausing_a_provider_simulates_its_free_limit(data_dir, transport):
    pause(str(data_dir), "groq", 10)
    assert gateway(data_dir, transport).ask("what is photosynthesis", "pc").provider == "cloudflare"
    assert "paused by you until" in usage.state(data_dir, "groq", BrainStore(data_dir))[1]
    pause(str(data_dir), "groq", 0)
    assert gateway(data_dir, transport).ask("what is gravity", "pc").provider == "groq"
    notes = [note for _, _, _, note in BrainStore(data_dir).events(0)]
    assert any("switched to Cloudflare" in note for note in notes) and "back to Groq" in notes


def test_keys_are_sealed_and_only_ever_read_back_by_kairu(data_dir):
    raw = keys.key_path(data_dir, "groq").read_bytes()
    if os.name != "nt":
        assert keys.key_path(data_dir, "groq").stat().st_mode & 0o077 == 0
    else:
        assert b"gsk_" not in raw  # sealed with DPAPI
    assert keys.load(data_dir, "groq") == ("gsk_" + "a" * 40, "")
    keys.leave_pending(data_dir, "openrouter", "sk-or-v1-" + "d" * 40)
    assert keys.take_pending(data_dir, "openrouter")["key"].startswith("sk-or-v1-")
    assert not keys.pending_path(data_dir, "openrouter").exists()


def test_the_test_providers_address_is_honoured_only_on_this_pc(monkeypatch):
    groq = providers.PROVIDERS["groq"]
    monkeypatch.setenv(providers.TEST_PROVIDERS, "http://127.0.0.1:9999")
    assert providers.url_of(groq).startswith("http://127.0.0.1:9999/groq/")
    monkeypatch.setenv(providers.TEST_PROVIDERS, "http://attacker.example:80")
    assert providers.url_of(groq) == "https://api.groq.com/openai/v1/chat/completions"


def test_an_answer_is_read_once():
    from kairu.brain.store import Answer
    import tempfile
    store = BrainStore(tempfile.mkdtemp())
    store.put_answer(Answer("0" * 16, time.time(), "pc", ANSWERED, "L3", "groq", "text", "", (), 0.5))
    assert store.take_answer("0" * 16).text == "text" and store.take_answer("0" * 16) is None


@pytest.mark.parametrize("source", ["pc", "dev-0123456789abcdef"])
def test_a_call_request_gets_a_plain_answer_with_no_approval_and_nothing_sent(data_dir, transport, source):
    result = gateway(data_dir, transport).ask("call my friend Ravi on 9876543210", source)
    assert (result.status, result.level, result.provider) == (ANSWERED, "L0", "")
    assert result.text == "I can't make calls yet; that comes with the phone app."
    assert transport.sent == []


def test_one_space_before_a_follow_up_offer():
    assert tidy("It is how plants make food.\nWant to know more?") == "It is how plants make food. Want to know more?"
    assert tidy("Narendra Modi is the PM.  \n\nWould you like more?") == "Narendra Modi is the PM. Would you like more?"
    assert tidy("Paris.Want to learn more?") == "Paris. Want to learn more?"
    assert tidy("First line.\nSecond line.") == "First line.\nSecond line."  # other lines stay as they are
    assert tidy("Want to know?") == "Want to know?"


def test_tidy_and_durations():
    assert tidy("<think>secret plan</think>**Paris** is the capital.") == "Paris is the capital."
    assert len(tidy("Word. " * 400)) < 1300
    assert providers.seconds_of("2m59.56s") == pytest.approx(179.56) and providers.seconds_of("120") == 120
    assert providers.seconds_of("1h2m3s") == 3723 and providers.seconds_of("500ms") == 0.5
    assert providers.seconds_of("soon") is None
