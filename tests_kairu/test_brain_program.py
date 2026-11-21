"""Kairu's brain through the real Guardian program (Phase B): `kairu ask`, the phone's questions, approvals, the
switch at a free limit, the stop, and Mission Cards going on after a crash.

The providers are a stand-in on this PC (tests_kairu/fake_provider.py), the Gate a stand-in relay, the phone the
stand-in phone: nothing leaves the PC.
"""

import json
import os
import re
import signal
import time

import pytest
import yaml

from kairu import audit, safemode
from kairu.brain import keys
from kairu.config import ROOT
from kairu.guardian import Action, Refused, Verdict
from kairu.missions.store import MissionStore
from kairu.store import Store
from tests_kairu.fake_provider import FakeProviders
from tests_kairu.fake_relay import FakeRelay
from tests_kairu.helpers import PIN, POLICY, alive, kairu, wait_for
from tests_kairu.program import end, family_memory_mib, memory_mib, program, program_with_pin, start  # noqa: F401
from tests_kairu.test_link_program import pair_phone

LIMIT = 1.0
GROQ_KEY = "gsk_" + "k" * 40


@pytest.fixture
def providers(monkeypatch):
    fake = FakeProviders()
    fake.answers["groq"] = "Narendra Modi is the Prime Minister of India.\nWant to know more about him?"
    monkeypatch.setenv("KAIRU_TEST_PROVIDERS", fake.url)
    yield fake
    fake.close()


@pytest.fixture
def relay():
    fake = FakeRelay(keepalive=0.5)
    yield fake
    fake.close()


@pytest.fixture
def config_path(tmp_path, monkeypatch, relay, providers):
    """Like conftest's, with the brain on (option A) and Kairu Link on, through the stand-ins."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "link": {"enabled": True, "relay": relay.url},
                                    "brain": {"public_to_cloud": True, "providers": ["groq", "cloudflare"]},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


@pytest.fixture
def brain(program_with_pin):
    keys.save(program_with_pin.data_dir, "groq", GROQ_KEY)
    keys.save(program_with_pin.data_dir, "cloudflare", "cf" + "c" * 38, "0123456789abcdef0123456789abcdef")
    return program_with_pin


def kairu_typing(monkeypatch, capsys, *args, typed=()):
    """`kairu ...` run here, with what you would type. On Windows getpass reads the console, never a pipe, so a
    PIN cannot be typed into a `kairu` started as its own process; here it is read from `typed` instead."""
    from kairu import approval, cli
    answers = iter(typed)

    def read(prompt=""):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", read)
    monkeypatch.setattr("getpass.getpass", read)
    monkeypatch.setattr(approval.ask, "__defaults__", (read, read, print))
    capsys.readouterr()
    code = cli.main(list(args))
    return code, capsys.readouterr().out


def logged(data_dir) -> str:
    with Store(data_dir).connect() as db:
        return " ".join(str(row) for row in db.execute("SELECT * FROM audit"))


def rows(data_dir, kind=None):
    return audit.tail(Store(data_dir), 3000, kind=kind)


def running(program, action):
    return [run for run in program.client.status()["running"] if run["action"] == action]


# --- asking from the PC -----------------------------------------------------------------------------

def test_kairu_ask_answers_short_and_the_audit_log_keeps_no_words(brain, providers):
    asked = kairu("ask", "who is the prime minister of India", timeout=60)
    assert asked.returncode == 0, asked.stdout + asked.stderr
    assert asked.stdout.startswith("Narendra Modi is the Prime Minister of India.") and "(L3: Groq" in asked.stdout
    [request] = providers.heard("groq")
    assert request["authorization"] == f"Bearer {GROQ_KEY}"
    assert request["body"]["messages"][-1]["content"] == "who is the prime minister of India"
    everything = logged(brain.data_dir)
    assert "prime minister" not in everything and GROQ_KEY not in everything
    l0 = kairu("ask", "what time is it")
    assert re.match(r"It's \d{1,2}:\d\d [ap]m\.", l0.stdout) and len(providers.heard()) == 1


def test_adding_a_key_is_high_and_the_key_never_reaches_a_log(program_with_pin, providers, monkeypatch, capsys):
    data_dir = program_with_pin.data_dir
    with pytest.raises(Refused, match="not approved"):
        program_with_pin.client.run(Action("provider.add", {"provider": "groq"}))
    code, said = kairu_typing(monkeypatch, capsys, "provider", "add", "groq", typed=["yes", PIN, GROQ_KEY])
    assert code == 0 and "Saved" in said, said
    assert keys.load(data_dir, "groq") == (GROQ_KEY, "") and not keys.pending_path(data_dir, "groq").exists()
    assert kairu("ask", "what is photosynthesis", timeout=60).returncode == 0
    for text in (logged(data_dir), (data_dir / "guardian.log").read_text(errors="replace"), said):
        assert GROQ_KEY not in text and "kkkkkkkk" not in text
    refused = kairu("provider", "add", "groq", input_text="no\n", timeout=60)
    assert refused.returncode == 1 and keys.load(data_dir, "groq") == (GROQ_KEY, "")
    code, said = kairu_typing(monkeypatch, capsys, "provider", "add", "cloudflare",
                              typed=["0123456789abcdef0123456789abcdef", "yes", PIN, "cf" + "t" * 38])
    assert code == 0 and keys.load(data_dir, "cloudflare") == ("cf" + "t" * 38, "0123456789abcdef0123456789abcdef")


def test_a_personal_question_waits_for_yes_and_the_pin_and_is_sent_only_then(brain, providers, monkeypatch, capsys):
    question = "my friend Ravi's number is 9876543210, what should I tell him when I ask him"
    refused = kairu("ask", question, input_text="no\n", timeout=60)
    assert "a phone number" in refused.stdout and "Not sent" in refused.stdout and refused.returncode == 1
    assert providers.heard() == []
    code, said = kairu_typing(monkeypatch, capsys, "ask", question, typed=["yes", PIN])
    assert code == 0 and "to Groq (api.groq.com)" in said and "(L3: Groq" in said, said
    [request] = providers.heard()
    assert request["body"]["messages"][-1]["content"] == question
    checks = [row for row in rows(brain.data_dir, "check") if row["action"] == "brain.send_private"]
    assert checks and all("details_sha256" in row["details"] for row in checks) and "9876543210" not in logged(brain.data_dir)


def test_a_secret_is_never_sent_even_when_its_send_is_approved(brain, providers):
    question = "my password is Tiger@123, is it strong?"
    asked = kairu("ask", question, timeout=60)
    assert "Not sent" in asked.stdout and "Tiger@123" not in asked.stdout
    action = Action("brain.send_private", {"question": question, "provider": "groq", "ask": "a" * 16, "source": "pc"})
    decision = brain.client.check(action)
    assert decision.verdict is Verdict.NEEDS_APPROVAL
    run = brain.client.run(action, brain.client.approve(decision.request_id, "yes", PIN))
    wait_for(lambda: brain.client.run_status(run["run"])["outcome"] == "finished", timeout=30)
    from kairu.brain.store import BrainStore
    assert BrainStore(brain.data_dir).take_answer("a" * 16).status == "refused"
    assert providers.heard() == [] and "Tiger@123" not in logged(brain.data_dir)


def test_at_a_free_limit_kairu_switches_provider_and_kairu_usage_shows_it(brain, providers):
    providers.limited("groq")
    asked = kairu("ask", "what is photosynthesis", timeout=60)
    assert "(L3: Cloudflare" in asked.stdout and "switched to Cloudflare" in asked.stdout, asked.stdout + asked.stderr
    assert len(providers.heard("groq")) == 1 and len(providers.heard("cloudflare")) == 1
    shown = kairu("usage").stdout
    assert "Groq at its free limit -> switched to Cloudflare" in shown and "at its free limit until" in shown
    paused = kairu("provider", "resume", "groq")
    assert paused.returncode == 0  # resume works even after a real limit: you decide


def test_a_paused_provider_simulates_the_limit_for_the_gate_test(brain, providers):
    assert kairu("provider", "pause", "groq", "--minutes", "10").returncode == 0
    assert "(L3: Cloudflare" in kairu("ask", "what is gravity", timeout=60).stdout
    assert "paused by you until" in kairu("usage").stdout
    assert providers.heard("groq") == []


# --- asking from the phone --------------------------------------------------------------------------

def test_the_phone_asks_and_hears_a_short_answer(brain, tmp_path, providers):
    phone = pair_phone(brain, tmp_path)
    since = int(time.time()) - 1
    started = time.monotonic()
    phone.send("ask", "who is the prime minister of India")
    [answer] = phone.replies(since, 30, until=lambda got: got)
    print(f"\n  phone question: answer in {time.monotonic() - started:.2f} s (stand-in relay and provider on this PC)")
    assert answer["body"].startswith("Narendra Modi is the Prime Minister of India.")
    assert "prime minister" not in logged(brain.data_dir)


def test_a_personal_question_from_the_phone_waits_for_the_pin_at_the_pc(brain, tmp_path, providers):
    phone = pair_phone(brain, tmp_path)
    since = int(time.time()) - 1
    phone.send("ask", "what should I tell Priya about the party on 9876543210")
    [waiting] = phone.replies(since, 30, until=lambda got: got)
    assert "not sent" in waiting["body"] and "kairu link approve 1" in waiting["body"] and providers.heard() == []
    [entry] = brain.client.link_waiting()
    assert entry["action"] == "brain.send_private" and entry["details"]["question"].startswith("what should I tell Priya")
    since = int(time.time()) - 1
    brain.client.link_approve(1, "yes", PIN)
    got = phone.replies(since, 30, until=lambda messages: any("Narendra" in m["body"] for m in messages))
    assert any("goes to groq" in message["body"] for message in got) and len(providers.heard()) == 1


# --- the stop -----------------------------------------------------------------------------------------

def test_a_stop_ends_a_question_on_its_way_within_1_second(brain, providers):
    providers.delay = 20  # the provider is slow: the question is still on its way
    run = brain.client.run(Action("brain.ask", {"question": "what is photosynthesis", "ask": "b" * 16, "source": "pc"}))
    wait_for(lambda: providers.heard(), timeout=20)
    store = Store(brain.data_dir)
    safemode.emergency_stop(store, "test")
    wait_for(lambda: not alive(run["pid"]), timeout=5)

    def halted_rows():
        return [row for row in rows(brain.data_dir, "run") if row["decision"] == "halted" and row["action"] == "brain.ask"]

    wait_for(halted_rows, timeout=5)  # recorded just after it is gone
    [halted] = halted_rows()
    print(f"\n  stop with a question on its way: halted in {halted['details']['seconds_since_stop']:.3f} s")
    assert halted["details"]["seconds_since_stop"] < LIMIT
    refused = kairu("ask", "what is gravity", timeout=60)  # Safe Mode: Kairu answers nothing until you resume
    assert "Safe Mode" in refused.stdout and refused.returncode == 1


# --- Mission Cards ------------------------------------------------------------------------------------

def card_file(tmp_path, steps, report="pc"):
    path = tmp_path / "card.yaml"
    path.write_text(yaml.safe_dump({"goal": "Test mission", "done": ["all counted"], "steps": steps, "report": report}))
    return str(path)


def test_a_mission_cut_off_by_a_crash_goes_on_from_its_last_checkpoint(brain, tmp_path, config, providers):
    made = kairu("mission", "new", card_file(tmp_path, [{"wait": 1}, {"wait": 1}, {"wait": 6}, {"wait": 1},
                                                        {"ask": "What is the capital of India?"}]))
    assert made.returncode == 0, made.stdout + made.stderr
    store = MissionStore(brain.data_dir)
    wait_for(lambda: store.card(1).steps[2].status == "running", timeout=30)
    time.sleep(1)
    actions = [run for run in brain.client.status()["running"]]
    if hasattr(signal, "SIGKILL"):  # Linux: a crash takes the whole family (on Windows, Guardian's Job Object does)
        os.kill(brain.pid, signal.SIGKILL)
        for run in actions:
            os.kill(run["pid"], signal.SIGKILL)
    else:
        os.kill(brain.pid, signal.SIGTERM)  # Windows: ended at once, like a crash
    wait_for(lambda: not alive(brain.pid) and not any(alive(run["pid"]) for run in actions), timeout=10)
    assert [step.status for step in store.card(1).steps] == ["done", "done", "running", "todo", "todo"]
    again = start(config)
    try:
        assert again.client.status()["mode"] == "safe"  # an unclean end: nothing goes on until you resume
        time.sleep(2)
        assert store.card(1).steps[2].tries == 1
        again.client.resume("yes", PIN)
        wait_for(lambda: store.card(1).status == "done", timeout=60)
        finished = store.card(1)
        assert [step.tries for step in finished.steps] == [1, 1, 2, 1, 1]  # only the cut-off step ran again
        counted = [row for row in rows(config.data_dir, "run") if row["action"] == "demo.count" and row["decision"] == "started"]
        assert len(counted) == 5  # four counts, and the one that was cut off, once more
        assert finished.steps[4].status == "done" and "Narendra" in finished.steps[4].result  # the stand-in's answer
        wait_for(lambda: any(row["decision"] == "card done" for row in rows(config.data_dir, "mission")), timeout=10)
    finally:
        end(again)
        brain.pid = again.pid


def test_a_stop_ends_a_mission_within_1_second_and_it_keeps_its_checkpoint(brain, tmp_path):
    assert kairu("mission", "new", card_file(tmp_path, [{"wait": 1}, {"wait": 30}, {"wait": 1}])).returncode == 0
    store = MissionStore(brain.data_dir)
    wait_for(lambda: store.card(1).steps[1].status == "running" and running(brain, "demo.count"), timeout=30)
    pids = [run["pid"] for run in brain.client.status()["running"] if run["action"] in ("mission.run", "demo.count")]
    safemode.emergency_stop(Store(brain.data_dir), "test")
    wait_for(lambda: not any(alive(pid) for pid in pids), timeout=5)
    wait_for(lambda: store.card(1).status == "stopped", timeout=5)
    halted = [row for row in rows(brain.data_dir, "run") if row["decision"] == "halted"]
    slowest = max(row["details"]["seconds_since_stop"] for row in halted)
    print(f"\n  stop with a mission and its step running: halted in {slowest:.3f} s")
    assert slowest < LIMIT and "emergency stop" in store.card(1).reason
    brain.client.resume("yes", PIN)
    time.sleep(2)
    assert store.card(1).status == "stopped"  # a stop is yours: it waits for `kairu mission continue`
    assert kairu("mission", "continue", "1").returncode == 0
    wait_for(lambda: store.card(1).steps[1].tries == 2 and running(brain, "demo.count"), timeout=30)
    assert store.card(1).steps[0].tries == 1  # the finished step is not counted again
    assert kairu("mission", "stop", "1").returncode == 0
    wait_for(lambda: not running(brain, "demo.count") and store.card(1).steps[1].status == "todo", timeout=10)
    assert store.card(1).status == "stopped" and store.card(1).steps[1].tries == 1  # your own stop is not counted


def test_a_finished_mission_is_reported_on_the_phone(brain, tmp_path):
    phone = pair_phone(brain, tmp_path)
    since = int(time.time()) - 1
    assert kairu("mission", "new", card_file(tmp_path, [{"wait": 1}, {"ask": "What is the capital of India?"}],
                                             report="phone")).returncode == 0
    got = phone.replies(since, 40, until=lambda messages: any("Mission 1 done" in m["body"] for m in messages))
    report = next(message["body"] for message in got if "Mission 1 done" in message["body"])
    assert "What is the capital of India? -> Narendra" in report and "please tick it yourself" in report


# --- memory and authority -------------------------------------------------------------------------------

def test_brain_memory(brain, providers):
    providers.delay = 3
    run = brain.client.run(Action("brain.ask", {"question": "what is photosynthesis", "ask": "c" * 16, "source": "pc"}))
    wait_for(lambda: providers.heard(), timeout=20)
    asking_now, asking_peak = family_memory_mib(run["pid"])
    wait_for(lambda: brain.client.run_status(run["run"])["outcome"] == "finished", timeout=20)
    guardian_now, guardian_peak = memory_mib(brain.pid)
    print(f"\n  Guardian program memory with the brain and Mission Cards: {guardian_now:.0f} MiB "
          f"(peak {guardian_peak:.0f} MiB); a question's own process: {asking_now:.0f} MiB")
    assert guardian_now < 64 and asking_now < 80


BRAIN = sorted((ROOT / "kairu" / "brain").glob("*.py"))
MISSIONS = sorted((ROOT / "kairu" / "missions").glob("*.py"))
CORE = ("kairu.guardian", "kairu.pin", "kairu.safemode", "kairu.audit", "kairu.store", "kairu.client", "kairu.approval",
        "kairu.runner", "kairu.guardian_program", "kairu.executors", "kairu.anchor", "kairu.policy")


def source(path) -> str:
    return path.read_text(encoding="utf-8")  # Kairu's files are UTF-8, whatever Windows' own code page is


@pytest.mark.parametrize("path", BRAIN + MISSIONS, ids=[f"{path.parent.name}/{path.name}" for path in BRAIN + MISSIONS])
def test_the_brain_and_the_missions_hold_no_authority(path):
    text = path.read_text(encoding="utf-8")
    for module in CORE:
        assert not re.search(rf"^\s*(from|import)\s+{re.escape(module)}\b", text, re.MULTILINE), f"{path.name} imports {module}"
        assert not re.search(rf"^\s*from\s+kairu\s+import\s+.*\b{module.split('.')[1]}\b", text, re.MULTILINE)
    assert "GuardianClient" not in text and "approve" not in re.findall(r"[\"']op[\"']\s*:\s*[\"'](\w+)", text)


def test_the_brain_only_asks_guardian_for_decisions_and_the_missions_only_for_steps():
    """Two brains (ADR-011): the brain only thinks and answers; the missions only ask Guardian to run their steps."""
    def asked(paths):
        return {op for path in paths for op in re.findall(r"[\"']op[\"']\s*:\s*[\"'](\w+)[\"']", source(path))}

    assert asked(BRAIN) == {"check", "status"}
    assert asked(MISSIONS) == {"run", "run_status", "end"}
    for path in BRAIN:
        assert "kairu.missions.run" not in source(path)
    for path in MISSIONS:
        assert not re.search(r"^\s*from\s+kairu\.brain\.(gateway|providers|router|privacy)", source(path), re.MULTILINE)


def test_the_guardian_program_does_not_load_the_brains_network_code():
    import subprocess
    import sys
    loaded = subprocess.run([sys.executable, "-c", "import sys, kairu.guardian_program; "
                             "print(sorted(m for m in sys.modules if m.startswith('kairu.brain.') or m == 'kairu.missions.run'))"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert json.loads(loaded.stdout.replace("'", '"')) == ["kairu.brain.store"], loaded.stdout + loaded.stderr
