"""Tests for `cos list-stacks` and `cos list-adapters`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from cli.list_adapters import list_adapters
from cli.list_stacks import list_stacks


def test_list_stacks_text_contains_live_stacks() -> None:
    runner = CliRunner()
    result = runner.invoke(list_stacks, [])
    assert result.exit_code == 0
    assert "django" in result.output
    assert "nextjs" in result.output
    assert "LABEL" in result.output  # header present


def test_list_stacks_json_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(list_stacks, ["--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "stacks" in payload
    assert "warnings" in payload
    ids = {s["id"] for s in payload["stacks"]}
    assert {"django", "nextjs"}.issubset(ids)
    # Shape check — each stack has these keys
    for stack in payload["stacks"]:
        assert {"id", "label", "category", "primary_skill", "skills"}.issubset(stack)


def test_list_adapters_text_contains_both() -> None:
    runner = CliRunner()
    result = runner.invoke(list_adapters, [])
    assert result.exit_code == 0
    assert "claude" in result.output
    assert "codex" in result.output


def test_list_adapters_json_shape() -> None:
    runner = CliRunner()
    result = runner.invoke(list_adapters, ["--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "adapters" in payload
    ids = {a["id"] for a in payload["adapters"]}
    assert {"claude", "codex"}.issubset(ids)
    for adapter in payload["adapters"]:
        assert {
            "id",
            "label",
            "settings_file",
            "hooks_dir",
            "rules_dir",
            "skills_dir",
            "supports_rules",
            "supports_settings_json",
            "sourced_hooks",
        }.issubset(adapter)
