"""Hub stale-code guard (TASK-428).

The hub imports core in-process and Python never reloads a live module, so a
core *.py edit only reaches projects after `cos hub restart`. These tests pin
the SSOT predicate `hub_commands._hub_code_is_stale()` (reused by status,
doctor, update) and the `hub.code_fresh` doctor check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import cli.registry
import cli.sync_all
from cli import doctor, hub_commands
from cli.doctor import SEV_PASS, SEV_WARN, DoctorReport


def _set_hub(monkeypatch, tmp_path, *, running: bool, started_mtime: float) -> None:
    pid_file = tmp_path / "hub.pid"
    pid_file.write_text("999\n", encoding="utf-8")
    os.utime(pid_file, (started_mtime, started_mtime))
    monkeypatch.setattr(hub_commands, "_pid_file", lambda: pid_file)
    monkeypatch.setattr(hub_commands, "_read_pid", lambda: 999 if running else None)
    # Point the reload marker at a non-existent tmp path so a real ~/.coding-os
    # reload hub can't make these tests flaky; reload tests create it explicitly.
    monkeypatch.setattr(hub_commands, "_reload_flag_file", lambda: tmp_path / "hub.reload")


def test_not_stale_when_hub_not_running(monkeypatch, tmp_path):
    _set_hub(monkeypatch, tmp_path, running=False, started_mtime=1000.0)
    monkeypatch.setattr(hub_commands, "_core_newest_mtime", lambda: (5000.0, tmp_path / "x.py"))
    assert hub_commands._hub_code_is_stale() == (False, None)


def test_stale_when_core_newer_than_start(monkeypatch, tmp_path):
    _set_hub(monkeypatch, tmp_path, running=True, started_mtime=1000.0)
    newer = tmp_path / "graph.py"
    monkeypatch.setattr(hub_commands, "_core_newest_mtime", lambda: (2000.0, newer))
    stale, path = hub_commands._hub_code_is_stale()
    assert stale is True
    assert path == newer


def test_fresh_when_core_older_than_start(monkeypatch, tmp_path):
    _set_hub(monkeypatch, tmp_path, running=True, started_mtime=3000.0)
    monkeypatch.setattr(hub_commands, "_core_newest_mtime", lambda: (2000.0, tmp_path / "graph.py"))
    stale, _ = hub_commands._hub_code_is_stale()
    assert stale is False


def test_hub_listener_state_distinguishes_healthy_and_occupied(monkeypatch):
    monkeypatch.setattr(hub_commands, "_hub_health_ok", lambda port: True)
    monkeypatch.setattr(hub_commands, "_port_accepts_connections", lambda port: False)
    assert hub_commands._hub_listener_state(9188) == "healthy"

    monkeypatch.setattr(hub_commands, "_hub_health_ok", lambda port: False)
    monkeypatch.setattr(hub_commands, "_port_accepts_connections", lambda port: True)
    assert hub_commands._hub_listener_state(9188) == "occupied"

    monkeypatch.setattr(hub_commands, "_port_accepts_connections", lambda port: False)
    assert hub_commands._hub_listener_state(9188) == "down"


def test_hub_status_reports_unmanaged_listener(monkeypatch, tmp_path):
    monkeypatch.setattr(hub_commands, "_read_pid", lambda: None)
    monkeypatch.setattr(hub_commands, "_hub_listener_state", lambda port: "healthy")
    monkeypatch.setattr(hub_commands, "_hub_dir", lambda: tmp_path)
    monkeypatch.setattr(hub_commands, "_log_file", lambda: tmp_path / "hub.log")
    monkeypatch.setattr(cli.registry, "load_registry", lambda: SimpleNamespace(projects=[]))
    monkeypatch.setattr(cli.sync_all, "_each_registered_project", lambda: [])

    result = CliRunner().invoke(hub_commands.hub_status)

    assert result.exit_code == 1
    assert "unmanaged listener" in result.output
    assert "no hub.pid" in result.output
    assert "not running" not in result.output


def test_hub_start_blocks_unmanaged_listener(monkeypatch, tmp_path):
    monkeypatch.setattr(hub_commands, "_read_pid", lambda: None)
    monkeypatch.setattr(hub_commands, "_hub_listener_state", lambda port: "occupied")
    monkeypatch.setattr(hub_commands, "_pid_file", lambda: tmp_path / "hub.pid")

    result = CliRunner().invoke(hub_commands.hub_start, ["--port", "9188"])

    assert result.exit_code != 0
    assert "unmanaged listener" in result.output
    assert "lsof -nP -iTCP:9188" in result.output


def test_reload_mode_suppresses_stale(monkeypatch, tmp_path):
    # A --reload hub auto-reloads its worker, so it is never stale even when core
    # is far newer than the original start (TASK-429).
    _set_hub(monkeypatch, tmp_path, running=True, started_mtime=1000.0)
    reload_flag = tmp_path / "hub.reload"
    reload_flag.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(hub_commands, "_reload_flag_file", lambda: reload_flag)
    monkeypatch.setattr(hub_commands, "_core_newest_mtime", lambda: (9000.0, tmp_path / "graph.py"))
    assert hub_commands._hub_code_is_stale() == (False, None)


def test_core_newest_mtime_skips_tests_and_caches(monkeypatch, tmp_path):
    core = tmp_path / "core"
    (core / "graph_os").mkdir(parents=True)
    (core / "graph_os" / "tools.py").write_text("x = 1\n", encoding="utf-8")
    os.utime(core / "graph_os" / "tools.py", (1000.0, 1000.0))
    # A newer file under tests/ and __pycache__/ must be ignored.
    (core / "graph_os" / "tests").mkdir()
    (core / "graph_os" / "tests" / "test_x.py").write_text("x = 1\n", encoding="utf-8")
    os.utime(core / "graph_os" / "tests" / "test_x.py", (9000.0, 9000.0))
    (core / "graph_os" / "__pycache__").mkdir()
    (core / "graph_os" / "__pycache__" / "tools.pyc.py").write_text("x\n", encoding="utf-8")
    os.utime(core / "graph_os" / "__pycache__" / "tools.pyc.py", (9000.0, 9000.0))
    monkeypatch.setattr("cli._resources.core_dir", lambda *a: core)
    newest, path = hub_commands._core_newest_mtime()
    assert newest == 1000.0
    assert path is not None and path.name == "tools.py"


def test_doctor_warns_when_stale(monkeypatch):
    monkeypatch.setattr("cli.hub_commands._hub_code_is_stale", lambda: (True, Path("/x/graph.py")))
    report = DoctorReport(project_dir="/x", agent=None, templates=[])
    doctor._check_hub_code_fresh(report)
    check = next(c for c in report.checks if c.id == "hub.code_fresh")
    assert check.severity == SEV_WARN
    assert "cos hub restart" in check.message


def test_doctor_pass_when_fresh(monkeypatch):
    monkeypatch.setattr("cli.hub_commands._hub_code_is_stale", lambda: (False, None))
    report = DoctorReport(project_dir="/x", agent=None, templates=[])
    doctor._check_hub_code_fresh(report)
    check = next(c for c in report.checks if c.id == "hub.code_fresh")
    assert check.severity == SEV_PASS


def test_daemon_scope_covers_project_and_session_groups():
    from thinking_os.database import PROJECT_SCOPED_ENV_VARS, SESSION_SCOPED_ENV_VARS

    both = set(PROJECT_SCOPED_ENV_VARS) | set(SESSION_SCOPED_ENV_VARS)
    env = dict.fromkeys(both, "/leak")
    assert set(hub_commands._strip_daemon_scope(env)) == both
    assert env == {}
    # The groups name different axes; an overlap would mean one is mislabelled.
    assert not set(PROJECT_SCOPED_ENV_VARS) & set(SESSION_SCOPED_ENV_VARS)


def test_strip_daemon_scope_drops_a_var_set_to_empty_string():
    env = {"COS_STATE_DIR": ""}
    assert hub_commands._strip_daemon_scope(env) == ["COS_STATE_DIR"]
    assert env == {}


def test_strip_daemon_scope_drops_pinning_vars_and_keeps_machine_knobs():
    env = {
        "COS_STATE_DIR": "/leak/.coding-os",
        "COS_DB_PATH": "/leak/.coding-os/coding-os.db",
        "COS_PROJECT_ROOT": "/leak",
        "COS_AGENT_DIR": "/leak/.coding-os/claude",
        "COS_HOOK_LOG": "/leak/hooks.log",
        "COS_GRAPH_BACKEND": "sqlite",
        "PATH": "/usr/bin",
    }
    dropped = hub_commands._strip_daemon_scope(env)
    assert set(dropped) == {
        "COS_STATE_DIR",
        "COS_DB_PATH",
        "COS_PROJECT_ROOT",
        "COS_AGENT_DIR",
        "COS_HOOK_LOG",
    }
    # Machine-wide knobs say *how* the server runs, not *which* project.
    assert env == {"COS_GRAPH_BACKEND": "sqlite", "PATH": "/usr/bin"}


def test_strip_daemon_scope_is_a_noop_on_a_clean_env():
    env = {"PATH": "/usr/bin"}
    assert hub_commands._strip_daemon_scope(env) == []
    assert env == {"PATH": "/usr/bin"}


def test_foreground_start_scrubs_process_env_before_serving(monkeypatch):
    """The --foreground process IS the daemon (service unit + detached path both land here)."""
    monkeypatch.setenv("COS_STATE_DIR", "/leak/.coding-os")
    monkeypatch.setenv("COS_PROJECT_ROOT", "/leak")
    monkeypatch.setenv("COS_GRAPH_BACKEND", "sqlite")
    seen: dict[str, str | None] = {}

    def _fake_run_server(**kwargs):
        seen["COS_STATE_DIR"] = os.environ.get("COS_STATE_DIR")
        seen["COS_PROJECT_ROOT"] = os.environ.get("COS_PROJECT_ROOT")
        seen["COS_GRAPH_BACKEND"] = os.environ.get("COS_GRAPH_BACKEND")

    monkeypatch.setitem(sys.modules, "web.server", SimpleNamespace(run_server=_fake_run_server))
    result = CliRunner().invoke(hub_commands.hub_start, ["--foreground", "--port", "9099"])

    assert result.exit_code == 0, result.output
    assert seen["COS_STATE_DIR"] is None
    assert seen["COS_PROJECT_ROOT"] is None
    assert seen["COS_GRAPH_BACKEND"] == "sqlite"
