"""The workspace through the real Guardian program and the real task core, on a pretend PC (KAIRU_TEST_PC).

An order typed in the workspace is decided and run by Guardian exactly as from the bar: each step shows, a High step waits
for the card, a refusal does nothing, and the order's words never reach the audit log.
"""

import threading

from kairu.workspace.server import Server, Workspace
from tests_kairu.helpers import PIN, wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_tasks_program import (calls, config_path, desk, logged, providers, run_rows,  # noqa: F401 (fixtures)
                                            work)
from tests_kairu.test_workspace import call


def serve(program_with_pin):
    workspace = Workspace(program_with_pin.config, client=program_with_pin.client)
    running = Server(workspace)
    threading.Thread(target=running.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return workspace, running


def finished(running):
    return call(running, "/api/state")[1]["run"] is None


def test_an_order_runs_through_guardian_and_each_step_is_shown_and_kept(program_with_pin, desk):
    workspace, running = serve(program_with_pin)
    try:
        project = call(running, "/api/projects", {"name": "Gate test"})[1]["project"]["id"]
        mission = call(running, "/api/order", {"text": "open Notepad and set volume to 20", "project": project})[1]["mission"]
        wait_for(lambda: finished(running), timeout=30)
        messages = call(running, f"/api/missions/{mission}")[1]["messages"]
        assert [(m["who"], m["text"], m["state"]) for m in messages] == [
            ("you", "open Notepad and set volume to 20", ""), ("step", "open Notepad", "done"), ("step", "volume 20", "done"),
            ("kairu", "Opened Notepad. Volume 20.", "")]
        assert calls(desk) == ["launch C:/Windows/notepad.exe", "volume 20 None"]
        assert [row["action"] for row in run_rows(program_with_pin.data_dir)][-2:] == ["apps.open", "system.volume"]
        assert "Notepad" not in logged(program_with_pin.data_dir)
    finally:
        running.shutdown()
        running.server_close()
        workspace.wait(5)


def test_restart_waits_for_the_card_and_a_refusal_does_nothing(program_with_pin, desk):
    workspace, running = serve(program_with_pin)
    try:
        mission = call(running, "/api/order", {"text": "restart"})[1]["mission"]
        wait_for(lambda: call(running, "/api/state")[1]["card"] is not None, timeout=30)
        card = call(running, "/api/state")[1]["card"]
        assert "system.restart" in "\n".join(card["lines"]) and card["with_pin"]
        call(running, "/api/answer", {"card": card["id"], "go_on": False})
        wait_for(lambda: finished(running), timeout=30)
        assert call(running, f"/api/missions/{mission}")[1]["messages"][-1]["text"] == "Not done: you refused it."
        assert not any("restart" in line for line in calls(desk))
    finally:
        running.shutdown()
        running.server_close()
        workspace.wait(5)


def test_restart_runs_after_yes_and_the_pin_typed_in_the_card(program_with_pin, desk):
    workspace, running = serve(program_with_pin)
    try:
        call(running, "/api/order", {"text": "restart"})
        wait_for(lambda: call(running, "/api/state")[1]["card"] is not None, timeout=30)
        card = call(running, "/api/state")[1]["card"]
        call(running, "/api/answer", {"card": card["id"], "go_on": True, "yes": "yes", "pin": PIN})
        wait_for(lambda: finished(running), timeout=30)
        wait_for(lambda: any("restart" in line for line in calls(desk)), timeout=15)
        assert PIN not in logged(program_with_pin.data_dir)
    finally:
        running.shutdown()
        running.server_close()
        workspace.wait(5)
