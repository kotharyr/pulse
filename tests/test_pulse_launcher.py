"""Launcher tests never connect to Jira or download dependencies."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/start_pulse.py"
spec = importlib.util.spec_from_file_location("pulse_launcher", MODULE_PATH)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_launcher_forces_loopback_and_recommend_only(monkeypatch, tmp_path):
    monkeypatch.setenv("MODE", "approved_destructive")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "9000")
    environment = launcher.server_environment(tmp_path, 8080)
    assert environment["MODE"] == "recommend_only"
    assert environment["MCP_HOST"] == "127.0.0.1"
    assert environment["MCP_PORT"] == "8080"
    assert environment["PYTHONPATH"] == str(tmp_path / "src")


def test_reuse_existing_readonly_server_does_not_start_second_server(monkeypatch):
    monkeypatch.setattr(launcher, "pulse_health", lambda _: {"mode": "recommend_only"})
    opened = Mock()
    monkeypatch.setattr(launcher, "open_console", opened)
    assert launcher.reuse_existing(8080, True)
    opened.assert_called_once_with(8080, True)


def test_never_reuse_server_with_writes_enabled(monkeypatch):
    monkeypatch.setattr(launcher, "pulse_health", lambda _: {"mode": "safe_apply"})
    with pytest.raises(launcher.StartupError, match="writes enabled"):
        launcher.reuse_existing(8080, False)


@pytest.mark.parametrize("payload", [b"not-json", b"[]", b'{"product":"Other","status":"ok"}'])
def test_health_does_not_mistake_another_service_for_pulse(monkeypatch, payload):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return payload
    monkeypatch.setattr(launcher, "build_opener", lambda *args: SimpleNamespace(open=lambda *a, **kw: Response()))
    assert launcher.pulse_health(8080) is None


def test_existing_source_is_used_without_snapshot_or_configuration_changes(tmp_path):
    (tmp_path / "src/engineering_ops").mkdir(parents=True)
    (tmp_path / "src/engineering_ops/server.py").write_text("# source")
    (tmp_path / "pyproject.toml").write_text("# project")
    assert launcher.prepare_source(tmp_path, tmp_path / "cache") == tmp_path
    assert not (tmp_path / "cache").exists()


def test_recovery_source_uses_git_archive_and_preserves_current_checkout(monkeypatch, tmp_path):
    project = tmp_path / "Pulse project with spaces"
    project.mkdir()
    git = ["git", "-C", str(project)]
    subprocess.run([*git, "init", "-q"], check=True)
    (project / "src/engineering_ops").mkdir(parents=True)
    (project / "src/engineering_ops/server.py").write_text("# tested server")
    (project / "pyproject.toml").write_text("# tested project")
    (project / "config").mkdir()
    (project / "config/example.json").write_text("{}")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Saved source"], check=True)
    saved = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(launcher, "RECOVERY_COMMIT", saved)
    (project / "src/engineering_ops/server.py").unlink()
    (project / "config/local.json").write_text('{"local":true}')
    (project / ".env.local").write_text("LOCAL_SETTING=private-test-value")
    before = subprocess.check_output([*git, "status", "--porcelain"])
    runtime = project / "runtime"
    runtime.mkdir()
    source = launcher.prepare_source(project, runtime)
    assert source != project
    assert (source / "src/engineering_ops/server.py").read_text() == "# tested server"
    assert (source / "config").resolve() == project / "config"
    assert (source / ".env.local").resolve() == project / ".env.local"
    assert not (project / "src/engineering_ops/server.py").exists()
    assert subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() == saved
    # Ignore the cache itself when comparing the source checkout status.
    after = subprocess.check_output([*git, "status", "--porcelain", "--", ":!runtime"])
    assert after == before
    assert not (runtime / "source.tar").exists()
    # Cache reuse refreshes configuration links, rather than copying secrets.
    assert launcher.prepare_source(project, runtime) == source
    assert (source / ".env.local").is_symlink()


def test_config_link_exists_when_local_override_is_added_later(tmp_path):
    project, source = tmp_path / "project", tmp_path / "source"
    project.mkdir()
    source.mkdir()
    launcher.link_configuration(project, source)
    assert (source / ".env.local").is_symlink()
    assert not (source / ".env.local").exists()
    (project / ".env.local").write_text("MODE=recommend_only")
    assert (source / ".env.local").read_text() == "MODE=recommend_only"


def test_cached_environment_skips_installation(monkeypatch, tmp_path):
    source, runtime = tmp_path / "source", tmp_path / "runtime"
    source.mkdir()
    runtime.mkdir()
    (source / "pyproject.toml").write_text("# project")
    signature = launcher.hashlib.sha256(source.as_posix().encode() + b"# project").hexdigest()
    (runtime / "installed-version").write_text(signature)
    monkeypatch.setattr(launcher, "dependencies_available", lambda _: True)
    calls = Mock(side_effect=AssertionError("No setup command expected"))
    monkeypatch.setattr(launcher.subprocess, "run", calls)
    assert launcher.ensure_environment(source, runtime) == runtime / "venv/bin/python"
    calls.assert_not_called()


def test_setup_failure_gives_log_path_and_does_not_mark_installed(monkeypatch, tmp_path):
    source, runtime = tmp_path / "source", tmp_path / "runtime"
    source.mkdir()
    runtime.mkdir()
    (source / "pyproject.toml").write_text("# project")
    monkeypatch.setattr(launcher, "dependencies_available", lambda _: False)
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(launcher.StartupError, match="setup.log"):
        launcher.ensure_environment(source, runtime)
    assert not (runtime / "installed-version").exists()
    assert (runtime / "setup.log").stat().st_mode & 0o777 == 0o600


def test_shutdown_terminates_only_owned_server(monkeypatch):
    process = Mock(pid=12345)
    process.poll.return_value = None
    kill = Mock()
    monkeypatch.setattr(launcher.os, "killpg", kill)
    launcher.stop_server(process)
    kill.assert_called_once_with(12345, launcher.signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=10)


def test_early_server_failure_is_reported_and_cleanup_runs(monkeypatch, tmp_path):
    process = Mock()
    process.poll.return_value = 1
    monkeypatch.setattr(launcher, "require_free_port", lambda _: None)
    monkeypatch.setattr(launcher, "prepare_source", lambda *args: tmp_path)
    monkeypatch.setattr(launcher, "ensure_environment", lambda *args: Path("/test/python"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: process)
    cleanup = Mock()
    monkeypatch.setattr(launcher, "stop_server", cleanup)
    with pytest.raises(launcher.StartupError, match=".env.local"):
        launcher.run_server(tmp_path, tmp_path, 8080, False)
    cleanup.assert_called_once_with(process)
