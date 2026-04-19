"""Tests for cli.adapter_registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.adapter_registry import AdapterManifestError, load_adapter_registry

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_live_registry_has_claude_and_codex() -> None:
    adapters = load_adapter_registry(REPO_ROOT / "adapters")
    assert "claude" in adapters
    assert "codex" in adapters
    # Both adapters now expose a rules directory (Phase G symmetry — Codex
    # gets .codex/rules/ too so consumer projects can resolve path
    # references from AGENTS.md even though Codex CLI does not auto-load
    # them the way Claude Code auto-loads .claude/rules/).
    assert adapters["claude"].supports_rules is True
    assert adapters["codex"].supports_rules is True


def test_claude_declares_settings_and_hooks() -> None:
    adapters = load_adapter_registry(REPO_ROOT / "adapters")
    claude = adapters["claude"]
    assert claude.settings_file == ".claude/settings.json"
    assert claude.hooks_dir == ".claude/hooks"
    assert "cos-env.sh" in claude.sourced_hooks


def test_codex_declares_symmetric_dirs() -> None:
    # Post-Phase G: Codex declares the same structural dirs as Claude.
    # Content source (core/) is shared; only the loading mechanism differs.
    adapters = load_adapter_registry(REPO_ROOT / "adapters")
    codex = adapters["codex"]
    assert codex.rules_dir == ".codex/rules"
    assert codex.hooks_dir == ".codex/hooks"
    assert codex.skills_dir == ".codex/skills"
    assert codex.commands_dir == ".codex/commands"


def test_missing_adapter_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(AdapterManifestError):
        load_adapter_registry(tmp_path / "missing")


def test_invalid_yaml_raises_hard(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "broken"
    adapter_dir.mkdir()
    # Unbalanced flow mapping — guaranteed YAML parse error.
    (adapter_dir / "adapter.yaml").write_text("{a: 1, b: [unclosed\n", encoding="utf-8")
    with pytest.raises(AdapterManifestError):
        load_adapter_registry(tmp_path)


def test_missing_required_field_raises_hard(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "incomplete"
    adapter_dir.mkdir()
    (adapter_dir / "adapter.yaml").write_text(
        "version: 1\nid: incomplete\n",  # no label
        encoding="utf-8",
    )
    with pytest.raises(AdapterManifestError, match="label"):
        load_adapter_registry(tmp_path)


def test_id_mismatch_raises(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "actualname"
    adapter_dir.mkdir()
    (adapter_dir / "adapter.yaml").write_text(
        "version: 1\nid: wrongname\nlabel: X\ninstall_script: install.sh\n",
        encoding="utf-8",
    )
    with pytest.raises(AdapterManifestError, match="directory"):
        load_adapter_registry(tmp_path)


def test_adapter_without_manifest_silently_skipped(tmp_path: Path) -> None:
    # adapter dir exists but no adapter.yaml → skipped without error
    (tmp_path / "stub_adapter").mkdir()
    adapters = load_adapter_registry(tmp_path)
    assert adapters == {}


# ---------- JSON schema validation ----------

def test_adapter_schema_rejects_unknown_field(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "typo"
    adapter_dir.mkdir()
    (adapter_dir / "adapter.yaml").write_text(
        "version: 1\n"
        "id: typo\n"
        "label: Typo\n"
        "install_script: install.sh\n"
        "support_rules: true\n",  # typo: should be 'supports_rules'
        encoding="utf-8",
    )
    with pytest.raises(AdapterManifestError, match="schema validation"):
        load_adapter_registry(tmp_path)


def test_adapter_schema_rejects_wrong_id_pattern(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "BadID"
    adapter_dir.mkdir()
    (adapter_dir / "adapter.yaml").write_text(
        "version: 1\n"
        "id: BadID\n"  # must match ^[a-z][a-z0-9_-]*$
        "label: Bad\n"
        "install_script: install.sh\n",
        encoding="utf-8",
    )
    with pytest.raises(AdapterManifestError):
        load_adapter_registry(tmp_path)


def test_adapter_schema_accepts_live_adapters() -> None:
    """Sanity: claude + codex must both pass schema validation."""
    adapters = load_adapter_registry(REPO_ROOT / "adapters")
    assert "claude" in adapters and "codex" in adapters
