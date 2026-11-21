"""Shared fixtures: a Guardian with its own temporary data folder and the real policy.yaml."""

import gc
import sys
import threading

import pytest
import yaml

from kairu import config as kairu_config, pin
from kairu.guardian import Guardian
from kairu.runner import Runner
from tests_kairu.helpers import PIN, POLICY


def free_closed_windows_here() -> None:
    """A closed Kairu bar is still held in reference cycles (its queued callbacks point back at it), so Python frees it at
    some later garbage collection, on whichever thread happens to run one. Tcl ends the whole program (Windows code
    0x80000003) when its interpreter is freed on a thread other than its own: PR #16's Windows CI, 7 Nov 2026, in
    test_brain_program. So the tests free them here, on the main thread, where every bar was made."""
    if "tkinter" in sys.modules and threading.current_thread() is threading.main_thread():
        gc.collect()


@pytest.fixture(autouse=True)
def windows_freed_on_the_main_thread():
    yield
    free_closed_windows_here()


@pytest.fixture
def write_config(tmp_path):
    """Write a config.yaml in tmp_path and return its path."""

    def write(voice=False, research=False, policy=POLICY):
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump({"voice": {"enabled": voice}, "research": {"enabled": research},
                                        "guardian": {"policy": str(policy), "data_dir": "data"}}))
        return path

    return write


@pytest.fixture
def config_path(write_config, monkeypatch):
    path = write_config()
    monkeypatch.setenv("KAIRU_CONFIG", str(path))  # for `python -m kairu ...` started by a test
    return path


@pytest.fixture
def config(config_path):
    return kairu_config.load(config_path)


@pytest.fixture
def guardian(config):
    return Guardian(config)


@pytest.fixture
def with_pin(guardian):
    pin.set_pin(guardian.store, PIN)
    return PIN


@pytest.fixture
def runner(guardian):
    runner = Runner(guardian)
    yield runner
    runner.close()
