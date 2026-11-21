"""A Shadow's whole trip through the real Guardian program (Phase H, SHADOW.md): Guardian decides every step.

The Gate is the stand-in relay, the owner's repository a folder on this PC, the friend's laptop another folder.
"""

import subprocess

import pytest
import yaml

from kairu import audit, policy
from kairu.guardian import Action, Refused, Verdict
from kairu.link import store as link_store
from kairu.policy import Tier
from kairu.shadow import agent, manager
from kairu.shadow.store import ShadowStore
from kairu.store import Store
from tests_kairu.fake_relay import FakeRelay
from tests_kairu.helpers import PIN, POLICY, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_shadow import build, git, repo  # noqa: F401 (repo is a fixture)

RULES = policy.load(POLICY).rules
MISSION = "Add up the expenses Sai says"


@pytest.fixture
def relay():
    fake = FakeRelay(keepalive=0.5)
    yield fake
    fake.close()


@pytest.fixture
def config_path(tmp_path, monkeypatch, relay):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"voice": {"enabled": False}, "research": {"enabled": False},
                                    "link": {"enabled": True, "relay": relay.url},
                                    "guardian": {"policy": str(POLICY), "data_dir": "data"}}))
    monkeypatch.setenv("KAIRU_CONFIG", str(path))
    return path


def approved(program, action: Action):
    decision = program.client.check(action)
    assert decision.verdict is Verdict.NEEDS_APPROVAL, decision.reason
    return program.client.approve(decision.request_id, "yes", PIN)


def finish(program, action: Action, approval=None, timeout=60) -> str:
    run = program.client.run(action, approval)
    wait_for(lambda: program.client.run_status(run["run"])["outcome"] is not None, timeout=timeout)
    return program.client.run_status(run["run"])["outcome"]


@pytest.mark.parametrize("name,tier", [
    ("shadow.create", Tier.HIGH), ("shadow.install", Tier.HIGH), ("pack.run", Tier.HIGH), ("shadow.sync", Tier.LOW),
    ("shadow.recall", Tier.LOW), ("shadow.lesson", Tier.LOW), ("pack.remove", Tier.LOW)])
def test_the_shadow_actions_have_their_tiers(name, tier):
    assert RULES[name].tier is tier and not RULES[name].read_only


def test_no_shadow_action_can_set_the_relay_or_the_data_folder():
    from kairu import executors
    for name in ("shadow.create", "shadow.sync", "shadow.recall", "shadow.lesson", "shadow.install", "pack.run", "pack.remove"):
        executor = executors.EXECUTORS[name]
        assert "data_dir" in executor.supplied and not {"data_dir", "relay"} & set(executor.arguments), name


def test_a_shadows_whole_trip_and_guardian_decides_every_step(program_with_pin, tmp_path, repo):
    program, friend = program_with_pin, tmp_path / "friend-laptop" / "Kairu-shadow"
    create = Action("shadow.create", {"friend": "Shruthi", "mission": MISSION, "pack": "expense-total", "hours": 3.0,
                                      "repo": str(repo)})
    with pytest.raises(Refused, match="not approved"):  # making a Shadow is High: "yes" and the PIN
        program.client.run(create)
    run = program.client.run(create, approved(program, create))
    wait_for(lambda: manager.read_offer(program.data_dir), timeout=30)
    offer = manager.read_offer(program.data_dir)
    shadow = agent.Shadow.join(offer["text"], offer["code"], friend, wait=30)
    wait_for(lambda: program.client.run_status(run["run"])["outcome"] == "finished", timeout=30)
    store = ShadowStore(program.data_dir)
    assert store.get(1)["state"] == "working" and link_store.paired(program.data_dir) == []

    build(shadow, ["Small functions were easier to test than one long one"])
    branch = shadow.state["branch"]
    shadow.progress(force=True)
    assert finish(program, Action("shadow.sync")) == "finished" and store.get(1)["progress"]["ready"] is True
    assert shadow.come_home("done")["done"] and not friend.exists()
    assert finish(program, Action("shadow.sync")) == "finished" and store.get(1)["state"] == "returned"

    checkout = tmp_path / "checkout"
    git("clone", "--quiet", "--branch", branch, str(repo), str(checkout))
    install = Action("shadow.install", {"shadow": 1.0, "folder": str(checkout / "packs" / "expense-total")})
    with pytest.raises(Refused, match="not approved"):  # a Shadow never installs anything: the owner does, with the PIN
        program.client.run(install)
    assert store.packs() == []
    assert finish(program, install, approved(program, install), timeout=120) == "finished"
    assert store.get(1)["state"] == "installed" and store.pack("expense-total")["made_by"] == "Rahul"

    words = "lunch 120 and bus 30"
    use = Action("pack.run", {"name": "expense-total", "text": words, "job": "job-1"})
    with pytest.raises(Refused, match="not approved"):
        program.client.run(use)
    assert finish(program, use, approved(program, use)) == "finished"
    assert store.run_result("job-1")["output"] == "The total is 150."
    assert finish(program, Action("shadow.lesson", {"lesson": 1.0, "keep": True})) == "finished"
    assert len(store.lessons("kept")) == 1

    logged = "\n".join(str(row) for row in audit.tail(Store(program.data_dir), 2000))
    assert MISSION not in logged and "Shruthi" not in logged and words not in logged  # your words: hashes only
    assert offer["code"] not in logged


def test_the_kairu_command_lists_shadows_and_packs(program_with_pin):
    from tests_kairu.helpers import kairu
    listed = kairu("shadow", "list")
    assert listed.returncode == 0 and "You have no Shadows" in listed.stdout
    assert "No pack is installed" in kairu("pack", "list").stdout
    refused = kairu("shadow", "create", "--for", "Shruthi", "--mission", MISSION, "--repo", "x", input_text="no\n")
    assert refused.returncode == 1 and "High tier" in refused.stdout and ShadowStore(program_with_pin.data_dir).all() == []
    assert subprocess.run(["git", "--version"], capture_output=True).returncode == 0


def test_a_cowork_shadow_is_made_through_guardian_with_yes_and_the_pin(program_with_pin, repo):
    program = program_with_pin
    create = Action("shadow.create", {"friend": "Omesh", "mission": "Make the task core open sites in Chrome",
                                      "pack": "task-core", "hours": 24.0, "repo": str(repo), "mode": "cowork",
                                      "base": "main"})
    with pytest.raises(Refused, match="not approved"):
        program.client.run(create)
    run = program.client.run(create, approved(program, create))
    wait_for(lambda: manager.read_offer(program.data_dir), timeout=30)
    from kairu.shadow import wire
    invite = wire.read_invite(manager.read_offer(program.data_dir)["text"])
    assert invite["mode"] == "cowork" and invite["base"] == "main" and invite["hours"] == 24.0
    program.client.end(run["run"])
