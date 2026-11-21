"""The workspace program: the server (kairu/workspace/server.py) and its window.

    python -m kairu.workspace.app --config config.yaml [--open]     (`kairu workspace` starts it for you, in the background)

Its own program, like the bar: if it ends, Guardian and running actions carry on. Only one runs under your account. It
writes workspace.json in Guardian's data folder (its port and this start's key, readable by you only) so `kairu workspace`
can open one more window, and removes it when it ends. `kairu workspace quit` (the file workspace.quit) ends it.

The window is the installed Chrome or Edge as an app window (no address bar, no tabs), with a profile folder of its own,
workspace-profile in Guardian's data folder: never your own browser profile, and not Kairu's browser profile that web.open
uses. The browser is found the way web.open finds it (App Paths and the usual folders, kairu/tasks/pc.py), and is started
with its path and arguments as a list: no shell, nothing typed. With no Chrome or Edge, your default browser opens the page.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from kairu import config as kairu_config
from kairu.workspace.server import Server, Workspace

STATE_FILE, QUIT_FILE, LOG_FILE, PROFILE = "workspace.json", "workspace.quit", "workspace.log", "workspace-profile"
ALREADY_RUNNING = 3
WINDOW_SIZE = "1280,820"


def browser() -> str | None:
    """Chrome, then Edge, as web.open finds them. None elsewhere (Linux, or neither installed)."""
    from kairu.tasks import pc
    try:
        found = pc.backend().browsers()
    except Exception:
        return None
    return found.get("chrome") or found.get("edge")


def window_arguments(data_dir, url: str) -> list[str]:
    profile = Path(data_dir).resolve() / PROFILE
    profile.mkdir(parents=True, exist_ok=True)
    # The page keeps asking the server while the window is minimized or covered, so the mic goes off only when the last
    # window has really closed (W2): Chrome would otherwise slow a hidden page's timers to once a minute.
    return [f"--app={url}", f"--user-data-dir={profile}", f"--window-size={WINDOW_SIZE}", "--no-first-run",
            "--no-default-browser-check", "--disable-sync", "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows"]


def open_window(data_dir, url: str) -> str:
    """One more workspace window. What opened it: chrome/edge's path, or "default browser"."""
    found = browser()
    if found is None or os.environ.get("KAIRU_TEST_PC"):
        if os.environ.get("KAIRU_TEST_PC"):  # tests never open a window
            return "none (test)"
        webbrowser.open(url)
        return "default browser"
    flags = {}
    if sys.platform == "win32":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([found, *window_arguments(data_dir, url)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, **flags)
    return found


OPEN_WORKSPACE = re.compile(r"(?:(?:hey )?kairu[,.!]? )?(?:please )?(?:open|show|start|launch|bring up)(?: up)? (?:the |my )?(?:kairu )?"
                            r"(?:workspace|work space|kairu app)(?: window)?(?: please)?[.!]?", re.IGNORECASE)


def open_or_start(cfg, config_file=None) -> tuple[bool, str]:
    """`kairu workspace`, and "open the workspace" in the bar (W2, ADR-036): one more window if it runs, else start it.

    It starts Kairu's own window and nothing else: the same program, the same way, as `kairu workspace`."""
    from kairu import client, config as kairu_config
    data_dir = Path(cfg.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    state = read_state(data_dir)
    if state is not None and call(state, "/api/ping") is not None:
        call(state, "/api/open", {})
        return True, "The workspace is already running: one more window is opening."
    python, environment = client.guardian_python()
    config_file = Path(config_file or kairu_config.config_path()).resolve()
    argv = [python, "-m", "kairu.workspace.app", "--config", str(config_file), "--open"]
    with open(data_dir / LOG_FILE, "ab") as log:
        process = client._spawn(argv, log, environment)
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline and process.poll() is None:
        state = read_state(data_dir)
        if state and state.get("pid") == process.pid:
            return True, "The workspace is open."
        time.sleep(0.1)
    if process.returncode == ALREADY_RUNNING:
        return False, "The workspace is already running, but didn't answer; try `kairu workspace quit`, then `kairu workspace`."
    if process.returncode is not None:
        return False, f"The workspace did not start; {data_dir / LOG_FILE} says why."
    return True, "The workspace is starting; its window opens in a moment."


def write_state(data_dir, port: int, key: str) -> Path:
    path = Path(data_dir) / STATE_FILE
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump({"port": port, "key": key, "pid": os.getpid()}, file)
    os.replace(temporary, path)
    return path


def read_state(data_dir) -> dict | None:
    try:
        state = json.loads((Path(data_dir) / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(state, dict) and type(state.get("port")) is int and isinstance(state.get("key"), str)):
        return None
    return state


def call(state: dict, path: str, body: dict | None = None, seconds: float = 2.0) -> dict | None:
    """Ask the running workspace (from `kairu workspace`). None if it doesn't answer."""
    import urllib.request
    request = urllib.request.Request(f"http://127.0.0.1:{state['port']}{path}", method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode("utf-8") if body is not None else None,
                                     headers={"X-Kairu-Key": state["key"], "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 127.0.0.1 never goes through a proxy
    try:
        with opener.open(request, timeout=seconds) as reply:
            return json.loads(reply.read() or b"{}")
    except Exception:
        return None


class OneWorkspace:
    """Only one workspace program under your account at a time."""

    def __init__(self, data_dir):
        if sys.platform == "win32":
            from kairu import winpipe
            self.held = winpipe.claim_mutex(f"Local\\KairuWorkspace-{winpipe.current_user_sid()}")
        else:
            import fcntl
            self.held = os.open(Path(data_dir) / "workspace.lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(self.held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(self.held)
                self.held = None

    def release(self) -> None:
        if self.held is None:
            return
        if sys.platform == "win32":
            from kairu import winpipe
            winpipe.close(self.held)
        else:
            os.close(self.held)
        self.held = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kairu.workspace.app", description="The Kairu workspace.")
    parser.add_argument("--config", help="config.yaml to use")
    parser.add_argument("--open", action="store_true", help="open a window at once")
    parser.add_argument("--port", type=int, default=0, help="a fixed port on 127.0.0.1 (default: any free one)")
    args = parser.parse_args(argv)
    cfg = kairu_config.load(args.config)
    data_dir = Path(cfg.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / QUIT_FILE).unlink(missing_ok=True)
    one = OneWorkspace(data_dir)
    if one.held is None:
        return ALREADY_RUNNING
    workspace = Workspace(cfg)
    workspace.start_voice()
    server = Server(workspace, args.port)
    workspace.open_window = lambda: open_window(data_dir, server.url())
    write_state(data_dir, server.port, server.key)
    serving = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    serving.start()
    print(f"kairu workspace: on 127.0.0.1:{server.port}", flush=True)
    try:
        if args.open:
            workspace.open_window()
        while not (data_dir / QUIT_FILE).exists():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        workspace.close_voice()
        server.shutdown()
        server.server_close()
        workspace.wait(2)
        (data_dir / STATE_FILE).unlink(missing_ok=True)
        (data_dir / QUIT_FILE).unlink(missing_ok=True)
        one.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
