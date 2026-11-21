"""Talking only to the real Guardian: a fake on the channel gets nothing, and without Guardian everything is refused."""

import subprocess
import sys
import time
from dataclasses import replace

import pytest

from kairu import channel
from kairu.client import GuardianClient
from kairu.config import ROOT
from kairu.guardian import Action, Approval, Refused, Verdict
from tests_kairu.helpers import PIN, kairu, wait_for
from tests_kairu.program import end, start

DELETE = Action("files.delete", {"path": "Finance/2026/receipt.pdf"})


@pytest.fixture
def fake(config, tmp_path):
    """A program that takes Guardian's channel first and pretends to be Guardian; it records what it is sent."""
    received = tmp_path / "fake-received.bin"
    process = subprocess.Popen([sys.executable, "-m", "tests_kairu.fake_guardian", str(config.data_dir), str(received)],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for(lambda: received.with_name(received.name + ".ready").exists() or process.poll() is not None, timeout=20)
        assert process.poll() is None, "the fake could not take the channel"
        yield received
    finally:
        process.kill()
        process.wait()


def test_a_fake_that_takes_the_channel_first_is_refused_and_never_gets_the_pin(config, fake):
    guardian = GuardianClient(config)
    decision = guardian.check(DELETE)
    assert decision.verdict is Verdict.DENY and "is not Guardian" in decision.reason and "Nothing was sent" in decision.reason
    assert guardian.check("chat.reply").verdict is Verdict.DENY
    with pytest.raises(Refused, match="is not Guardian"):
        guardian.approve("0" * 16, "yes", PIN)
    with pytest.raises(Refused, match="is not Guardian"):
        guardian.resume("yes", PIN)
    with pytest.raises(Refused, match="is not Guardian"):
        guardian.set_pin(PIN)
    with pytest.raises(Refused, match="is not Guardian"):
        guardian.reanchor("yes", PIN)
    assert guardian.authorize(DELETE, Approval("0" * 32, DELETE.name, time.time() + 60)).verdict is Verdict.DENY
    with pytest.raises(channel.NotGuardian, match="it is not the Guardian program"):
        guardian.status()

    requested = kairu("request", "files.delete", "path=x", input_text=f"yes\n{PIN}\n")
    assert requested.returncode == 1 and "is not Guardian" in requested.stdout
    assert "Your Kairu PIN" not in requested.stdout  # it never even asked for the PIN
    assert "is not Guardian" in kairu("status").stdout
    assert kairu("resume").returncode == 1

    assert fake.read_bytes() == b""  # nothing at all reached the fake: no request, no PIN


def test_guardian_will_not_start_while_a_fake_holds_its_channel(config, fake):
    started = kairu("guardian", "run", timeout=60)
    assert started.returncode == 1 and "not started" in started.stdout and "is not Guardian" in started.stdout
    with pytest.raises(channel.NotGuardian):
        GuardianClient(config).status()
    assert fake.read_bytes() == b""


def test_the_real_guardian_will_not_start_beside_another_and_a_fake_cannot_start_beside_it(config, config_path, tmp_path):
    running = start(config)
    try:
        received = tmp_path / "late-fake.bin"
        late = subprocess.run([sys.executable, "-m", "tests_kairu.fake_guardian", str(config.data_dir), str(received)],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert late.returncode != 0 and "ChannelTaken" in late.stderr  # the name is Guardian's alone
        assert running.client.status()["pid"] == running.pid
    finally:
        end(running)


GOOD = channel.Peer(pid=4242, same_user=True, integrity_ok=True, program=sys.executable,
                    argv=(sys.executable, "-m", channel.GUARDIAN_MODULE, "--config", "config.yaml"))


def test_only_kairus_python_running_the_guardian_program_as_you_counts_as_guardian():
    assert channel.why_not_guardian(GOOD) == ""
    assert "another account" in channel.why_not_guardian(replace(GOOD, same_user=False))
    assert "low integrity" in channel.why_not_guardian(replace(GOOD, integrity_ok=False))
    assert "not Kairu's Python" in channel.why_not_guardian(replace(GOOD, program=str(ROOT / "fake.exe")))
    for argv in [(sys.executable, "-m", "tests_kairu.fake_guardian"), (sys.executable, "guardian_program.py"),
                 (sys.executable, "-c", "kairu.guardian_program"), (sys.executable,), ()]:
        assert "not the Guardian program" in channel.why_not_guardian(replace(GOOD, argv=argv)), argv


def test_a_greeting_must_name_the_same_process_and_data_folder(tmp_path):
    said = channel.greeting(tmp_path)
    pid = said["pid"]
    assert channel.greeting_problem(said, pid, tmp_path) == ""
    assert channel.greeting_problem(said, pid + 1, tmp_path)
    assert channel.greeting_problem(said, pid, tmp_path / "other")
    assert channel.greeting_problem({**said, "protocol": 2}, pid, tmp_path)
    assert channel.greeting_problem({**said, "guardian": "fake"}, pid, tmp_path)
    assert channel.greeting_problem(None, pid, tmp_path)


def test_without_guardian_every_request_is_refused(config, config_path):
    guardian = GuardianClient(config)
    for name in ("chat.reply", "files.read", "files.write", "files.delete", "credentials.reveal"):
        decision = guardian.check(name)
        assert decision.verdict is Verdict.DENY and "Guardian is not running" in decision.reason
        assert guardian.authorize(name).verdict is Verdict.DENY
    for attempt in (lambda: guardian.approve("0" * 16, "yes", PIN), lambda: guardian.resume("yes", PIN),
                    lambda: guardian.set_pin(PIN), lambda: guardian.reanchor("yes", PIN)):
        with pytest.raises(Refused, match="Guardian is not running"):
            attempt()

    requested = kairu("request", "chat.reply")
    assert requested.returncode == 1 and "Guardian is not running" in requested.stdout
    assert "Guardian is not running" in kairu("status").stdout
    for command in (("resume",), ("pin", "set")):
        result = kairu(*command)
        assert result.returncode == 1 and "Guardian is not running" in result.stdout


def test_after_guardian_quits_every_request_is_refused_again(config, config_path):
    running = start(config)
    assert running.client.check("chat.reply").verdict is Verdict.ALLOW
    quitting = kairu("guardian", "quit")
    assert quitting.returncode == 0 and "has quit" in quitting.stdout
    try:
        decision = GuardianClient(config).check("chat.reply")
        assert decision.verdict is Verdict.DENY and "Guardian is not running" in decision.reason
    finally:
        end(running)
