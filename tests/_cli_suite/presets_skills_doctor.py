"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


class TestDoctorAgentSdk:
    def test_codex_optional_sdk_uses_data_driven_probe(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.metadata

        def missing_package(name: str):
            raise importlib.metadata.PackageNotFoundError(name)

        class FakeResult:
            stdout = "codex-cli 0.144.1"
            stderr = ""

        monkeypatch.setenv("COS_AGENT", "codex")
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(importlib.metadata, "version", missing_package)
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codex")
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

        result = runner.invoke(cli, ["doctor", "--agent-sdk"])

        assert result.exit_code == 0, result.output
        assert "OpenAI Codex CLI SDK compatibility report" in result.output
        assert "openai-codex not installed" in result.output
        assert "uv sync --extra codex-sdk" in result.output
        assert "CODEX_API_KEY, OPENAI_API_KEY" in result.output
        assert "CLI fallback remains available" in result.output

    def test_legacy_claude_sdk_flag_remains_an_alias(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.metadata

        monkeypatch.setenv("COS_AGENT", "codex")
        monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.1.0b3")
        monkeypatch.setattr(shutil, "which", lambda _: None)

        result = runner.invoke(cli, ["doctor", "--claude-sdk"])

        assert result.exit_code == 0, result.output
        assert "OpenAI Codex CLI SDK compatibility report" in result.output
        assert "openai-codex = 0.1.0b3" in result.output


class TestDoctorBootstrap:
    _ALL_CHECK_IDS = (
        "bootstrap.python_version",
        "bootstrap.bash_version",
        "bootstrap.git_present",
        "bootstrap.uv_present",
        "bootstrap.sed_flavor",
    )

    def test_all_checks_pass_on_dev_machine(self, runner: CliRunner) -> None:
        """Runs with NO project — a brand-new user's very first command."""
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 0, result.output
        for check_id in self._ALL_CHECK_IDS:
            assert check_id in result.output

    def test_old_bash_fails_with_brew_hint(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.doctor as doctor_module

        real_capture = doctor_module._capture_tool_version

        def _bash_32(executable: str):
            if executable == "bash":
                return "GNU bash, version 3.2.57(1)-release (arm64-apple-darwin24)"
            return real_capture(executable)

        monkeypatch.setattr(doctor_module, "_capture_tool_version", _bash_32)
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 1
        assert "brew install bash" in result.output

    def test_missing_git_fails_with_install_hint(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.doctor as doctor_module

        real_capture = doctor_module._capture_tool_version
        monkeypatch.setattr(
            doctor_module,
            "_capture_tool_version",
            lambda exe: None if exe == "git" else real_capture(exe),
        )
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 1
        assert "git not found" in result.output

    def test_missing_uv_warns_but_passes_unless_strict(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.doctor as doctor_module

        real_capture = doctor_module._capture_tool_version
        monkeypatch.setattr(
            doctor_module,
            "_capture_tool_version",
            lambda exe: None if exe == "uv" else real_capture(exe),
        )
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 0, result.output
        assert "uv not found" in result.output

        strict_result = runner.invoke(cli, ["doctor", "--bootstrap", "--strict"])
        assert strict_result.exit_code == 1

    def test_json_format_is_machine_readable(self, runner: CliRunner) -> None:
        import json

        result = runner.invoke(cli, ["doctor", "--bootstrap", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        reported_ids = {check["id"] for check in payload["checks"]}
        assert set(self._ALL_CHECK_IDS) <= reported_ids
