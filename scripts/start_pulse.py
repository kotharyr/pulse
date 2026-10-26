#!/usr/bin/env python3
"""One-click local Console startup, including first-run setup and safe recovery.

The launcher never changes Git history. If source files are temporarily absent,
use a verified local Git snapshot in an ignored runtime directory. Configuration
stays in the user's project and is linked, rather than copied, into that snapshot.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_COMMIT = "74e29c5b5a66515ba0c638f5a7657e78104bb9e6"
DEPENDENCY_CHECK = "import mcp, httpx, pydantic_settings, uvicorn, starlette, dotenv"


class StartupError(RuntimeError):
    """A startup problem that can be explained without displaying credentials."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_file(path: Path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    return os.fdopen(descriptor, "w")


def source_is_present(root: Path) -> bool:
    return (root / "pyproject.toml").is_file() and (
        root / "src/engineering_ops/server.py"
    ).is_file()


def link_configuration(project: Path, source: Path) -> None:
    for name in ("config", ".env", ".env.local"):
        destination = source / name
        if destination.is_symlink():
            destination.unlink()
        elif destination.is_dir():
            shutil.rmtree(destination)
        elif destination.exists():
            destination.unlink()
        # A dangling link permits .env.local to be added later without rebuilding.
        destination.symlink_to(project / name, target_is_directory=name == "config")


def prepare_source(project: Path, runtime: Path) -> Path:
    if source_is_present(project):
        return project
    source = runtime / ("source-" + RECOVERY_COMMIT[:12])
    if not source_is_present(source):
        print("Preparing the last tested Pulse version. Your Git checkout stays intact.", flush=True)
        if source.exists():
            shutil.rmtree(source)
        source.mkdir()
        archive = runtime / "source.tar"
        with archive.open("wb") as archive_file:
            result = subprocess.run(
                ["git", "-C", str(project), "archive", "--format=tar", RECOVERY_COMMIT],
                stdout=archive_file, stderr=subprocess.DEVNULL,
            )
        if result.returncode:
            archive.unlink(missing_ok=True)
            raise StartupError("Pulse source is missing and its saved version is unavailable.")
        try:
            # The archive is produced by local Git, not a downloaded archive.
            result = subprocess.run(
                ["tar", "-xf", str(archive), "-C", str(source)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if result.returncode or not source_is_present(source):
                raise StartupError("The saved Pulse version could not be prepared.")
        finally:
            archive.unlink(missing_ok=True)
    link_configuration(project, source)
    return source


def dependencies_available(python: Path) -> bool:
    try:
        return subprocess.run(
            [str(python), "-c", DEPENDENCY_CHECK],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
    except OSError:
        return False


def ensure_environment(source: Path, runtime: Path) -> Path:
    environment = runtime / "venv"
    python = environment / "bin/python"
    stamp = runtime / "installed-version"
    signature = hashlib.sha256(
        source.as_posix().encode() + (source / "pyproject.toml").read_bytes()
    ).hexdigest()
    if stamp.exists() and stamp.read_text() == signature and dependencies_available(python):
        return python
    print("Setting up Pulse. The first start may take a few minutes.", flush=True)
    log_path = runtime / "setup.log"
    with private_file(log_path) as log:
        if not dependencies_available(python):
            # This environment belongs only to the launcher; leave .venv untouched.
            result = subprocess.run(
                [sys.executable, "-m", "venv", "--clear", str(environment)],
                stdout=log, stderr=log,
            )
            if result.returncode:
                raise StartupError(f"Python setup failed. Details: {log_path}")
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-e", str(source)],
            stdout=log, stderr=log,
        )
        if result.returncode or not dependencies_available(python):
            raise StartupError(f"Dependency setup failed. Check your network. Details: {log_path}")
    stamp.write_text(signature)
    return python


def pulse_health(port: int) -> dict | None:
    opener = build_opener(ProxyHandler({}), NoRedirects())
    try:
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
            data = json.loads(response.read(16384))
        if isinstance(data, dict) and data.get("product") == "Pulse" and data.get("status") == "ok":
            return data
    except (OSError, URLError, ValueError):
        pass
    return None


def open_console(port: int, browser: bool) -> None:
    url = f"http://127.0.0.1:{port}/console"
    print(f"Pulse is ready: {url}", flush=True)
    if browser:
        webbrowser.open(url)


def reuse_existing(port: int, browser: bool) -> bool:
    health = pulse_health(port)
    if not health:
        return False
    if health.get("mode") != "recommend_only":
        raise StartupError(
            "Pulse is already running with writes enabled. Stop it before using this read-only launcher."
        )
    print("Pulse is already running. Opening its Console.", flush=True)
    open_console(port, browser)
    return True


def require_free_port(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise StartupError(
                f"Port {port} is being used by another service. Stop that service "
                "or launch Pulse with --port followed by a different port."
            ) from exc


def server_environment(source: Path, port: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update({
        "MODE": "recommend_only",
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(port),
        "PYTHONPATH": str(source / "src"),
        "PYTHONUNBUFFERED": "1",
    })
    return environment


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_server(project: Path, runtime: Path, port: int, browser: bool) -> None:
    require_free_port(port)
    source = prepare_source(project, runtime)
    python = ensure_environment(source, runtime)
    log_path = runtime / "pulse.log"
    print("Starting Pulse in read-only mode…", flush=True)
    with private_file(log_path) as log:
        process = subprocess.Popen(
            [str(python), "-m", "engineering_ops.server"],
            cwd=project, env=server_environment(source, port),
            stdout=log, stderr=log, start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise StartupError(
                        "Pulse could not start. Check .env.local and your Jira configuration. "
                        f"Details: {log_path}"
                    )
                health = pulse_health(port)
                if health and health.get("mode") == "recommend_only":
                    open_console(port, browser)
                    print("Keep this window open. Press Control+C to stop Pulse.", flush=True)
                    result = process.wait()
                    if result:
                        raise StartupError(f"Pulse stopped unexpectedly. Details: {log_path}")
                    return
                time.sleep(0.2)
            raise StartupError(f"Pulse took too long to start. Details: {log_path}")
        finally:
            stop_server(process)


def start(project: Path, port: int, browser: bool) -> None:
    if reuse_existing(port, browser):
        return
    runtime = project / ".pulse-local"
    runtime.mkdir(mode=0o700, exist_ok=True)
    os.chmod(runtime, 0o700)
    with (runtime / "launcher.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Pulse is already starting. Waiting for its Console…", flush=True)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if reuse_existing(port, browser):
                    return
                time.sleep(0.5)
            raise StartupError("Pulse is still setting up. Check its first Terminal window.")
        run_server(project, runtime, port, browser)


def interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the local Pulse Console in read-only mode.")
    parser.add_argument("--no-browser", action="store_true", help="Print the Console address without opening it.")
    parser.add_argument("--port", type=int, default=8080, help="Local port (default: 8080).")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        print("Pulse needs Python 3.11 or newer.", file=sys.stderr)
        return 1
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGHUP, interrupt)
    try:
        start(PROJECT_ROOT, args.port, not args.no_browser)
    except KeyboardInterrupt:
        print("\nPulse stopped.")
    except StartupError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    except OSError:
        print("Pulse could not access a required file or program. Check Python, Git and folder permissions.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
