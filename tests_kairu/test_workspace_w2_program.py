"""W2's file skills through the real Guardian program and the real task core, in the workspace, on a pretend PC.

A file made by a mission shows in its Files panel; Open and Show are orders that Guardian decides; a program is never opened;
the file's words never reach the audit log.
"""

from tests_kairu.helpers import wait_for
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_tasks_program import (calls, config_path, desk, logged, providers, run_rows,  # noqa: F401 (fixtures)
                                            work)
from tests_kairu.test_workspace import call
from tests_kairu.test_workspace_program import finished, serve


def test_a_made_file_shows_in_the_panel_and_opens_and_shows_through_guardian(program_with_pin, desk, work):
    workspace, running = serve(program_with_pin)
    try:
        mission = call(running, "/api/order", {"text": "make a file called gate.txt saying a private hello"})[1]["mission"]
        wait_for(lambda: finished(running), timeout=30)
        assert (work / "gate.txt").read_text(encoding="utf-8") == "a private hello\n"
        assert [(f["name"], f["how"]) for f in call(running, f"/api/missions/{mission}")[1]["files"]] == [("gate.txt", "made")]

        for text in ('open the file "gate.txt"', 'show "gate.txt" in its folder'):  # what the panel's buttons send
            call(running, "/api/order", {"mission": mission, "text": text})
            wait_for(lambda: finished(running), timeout=30)
        assert calls(desk) == ["open file gate.txt", "show file gate.txt"]
        assert [f["how"] for f in call(running, f"/api/missions/{mission}")[1]["files"]] == ["shown"]
        assert [row["action"] for row in run_rows(program_with_pin.data_dir)][-3:] == ["files.write", "files.open", "files.show"]
        assert "private hello" not in logged(program_with_pin.data_dir) and "gate.txt" not in logged(program_with_pin.data_dir)
    finally:
        running.shutdown()
        running.server_close()
        workspace.wait(5)


def test_a_program_is_never_opened_and_undo_puts_a_made_file_in_the_bin(program_with_pin, desk, work):
    work.mkdir(parents=True, exist_ok=True)
    (work / "tool.bat").write_text("echo hi")
    workspace, running = serve(program_with_pin)
    try:
        mission = call(running, "/api/order", {"text": "open file tool.bat"})[1]["mission"]
        wait_for(lambda: finished(running), timeout=30)
        assert "never opens programs" in call(running, f"/api/missions/{mission}")[1]["messages"][-1]["text"]
        assert calls(desk) == [] and call(running, f"/api/missions/{mission}")[1]["files"] == []

        for text in ("make a file called note.md saying hi", "undo"):
            call(running, "/api/order", {"mission": mission, "text": text})
            wait_for(lambda: finished(running), timeout=30)
        assert not (work / "note.md").exists()
        assert call(running, f"/api/missions/{mission}")[1]["messages"][-1]["text"] == "Undone: note.md is in the Recycle Bin."
    finally:
        running.shutdown()
        running.server_close()
        workspace.wait(5)
