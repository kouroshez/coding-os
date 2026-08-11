"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
    main_module,
)

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestAddAdapter:
    def test_adds_codex_to_claude_project(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert (initialized_project / ".codex" / "hooks.json").exists()

    def test_updates_config(self, runner: CliRunner, initialized_project: Path) -> None:
        runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        import yaml

        config = yaml.safe_load((initialized_project / ".coding-os.yaml").read_text())
        assert "claude" in config["agents"]
        assert "codex" in config["agents"]

    def test_duplicate_adapter_noop(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["add-adapter", "claude", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "already installed" in result.output

    def test_fails_without_init(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(tmp_path)])
        assert result.exit_code != 0

    def test_generates_agents_md_if_missing(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        # Simulate a partial install where AGENTS.md was never generated.
        agents_md = initialized_project / "AGENTS.md"
        if agents_md.exists():
            agents_md.unlink()

        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert agents_md.exists(), "add-adapter must generate missing AGENTS.md"
        assert "Generated AGENTS.md" in result.output

    def test_preserves_existing_agents_md(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        agents_md = initialized_project / "AGENTS.md"
        sentinel = "## CUSTOM SECTION — do not overwrite\n"
        agents_md.write_text(sentinel)

        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert agents_md.read_text() == sentinel, (
            "add-adapter must not overwrite existing AGENTS.md"
        )


class TestCodexMcpInstall:
    def test_default_writes_project_local_config(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["codex-mcp-install"])
        assert result.exit_code == 0
        target = tmp_path / ".codex" / "config.toml"
        assert target.exists()
        assert "[mcp_servers.coding-os]" in target.read_text(encoding="utf-8")

    def test_dry_run_prints_snippet(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "fake-codex-config.toml"
        result = runner.invoke(cli, ["codex-mcp-install", "--dry-run", "--config", str(target)])
        assert result.exit_code == 0
        assert "[mcp_servers.coding-os]" in result.output
        assert not target.exists(), "dry-run must not write"

    def test_writes_to_fresh_config(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "codex" / "config.toml"
        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        assert target.exists()
        content = target.read_text()
        assert "[mcp_servers.coding-os]" in content

    def test_preserves_existing_content(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        prior = '[mcp_servers.other]\ncommand = "other-tool"\n'
        target.write_text(prior)

        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        new = target.read_text()
        assert prior in new, "existing MCP entries must survive"
        assert "[mcp_servers.coding-os]" in new

    def test_idempotent(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        size_after_first = target.stat().st_size

        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        assert "Already registered" in result.output
        assert target.stat().st_size == size_after_first, (
            "second run must not append a duplicate section"
        )

    def test_repairs_existing_stale_entry(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text(
            "[mcp_servers.coding-os]\n"
            'command = "uv"\n'
            'args = ["run", "--directory", "/old/path", "python", "server.py"]\n',
            encoding="utf-8",
        )

        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        content = target.read_text(encoding="utf-8")
        assert content.count("[mcp_servers.coding-os]") == 1
        assert "/old/path" not in content
        assert 'command = "uv"' not in content

    def test_fallback_uses_python_not_uv(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "config.toml"

        def fake_which(name: str) -> str | None:
            return None if name == "cos" else shutil.which(name)

        monkeypatch.setattr(shutil, "which", fake_which)
        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        content = target.read_text(encoding="utf-8")
        assert 'command = "uv"' not in content
        assert sys.executable in content

    def test_rejects_config_and_global_together(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target), "--global"])
        assert result.exit_code != 0
        assert "either --config or --global" in result.output


class TestServerStart:
    def test_execs_current_python_directly(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_execvpe(file: str, args: list[str], env: dict[str, str]) -> None:
            captured["file"] = file
            captured["args"] = args
            captured["env"] = env
            raise SystemExit(0)

        monkeypatch.setattr(os, "execvpe", fake_execvpe)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(cli, ["server-start"])

        assert result.exit_code == 0, result.output
        assert captured["file"] == sys.executable
        assert captured["args"] == [
            sys.executable,
            str(main_module.CORE_DIR / "thinking_os" / "server.py"),
        ]
        env = captured["env"]
        assert isinstance(env, dict)
        assert env["COS_DB_PATH"] == str(tmp_path / ".coding-os" / "coding-os.db")
        assert env["COS_STATE_DIR"] == str(tmp_path / ".coding-os")


class TestHealth:
    def test_health_on_initialized_project(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_health_shows_agent(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "claude" in result.output

    def test_health_shows_database(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "Database" in result.output

    def test_health_shows_hooks(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "hooks" in result.output.lower()

    def test_health_missing_config(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert "MISSING" in result.output


class TestHooksDir:
    def test_prints_hooks_path(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["hooks-dir"])
        assert result.exit_code == 0
        assert "src/core/hooks" in result.output


class TestVersion:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        # Any semver string is fine; just confirm version line rendered.
        assert "version" in result.output.lower()
