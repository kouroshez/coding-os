"""Tests for cli.adapter_registry."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cli.adapter_registry import AdapterManifestError, load_adapter_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ADAPTERS = REPO_ROOT / "src" / "adapters"


def _copy_adapter_as(src_id: str, dest_dir: Path, new_id: str) -> None:
    target = dest_dir / new_id
    shutil.copytree(_SRC_ADAPTERS / src_id, target)
    manifest = target / "adapter.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(f"id: {src_id}", f"id: {new_id}", 1),
        encoding="utf-8",
    )


def test_live_registry_has_claude_and_codex() -> None:
    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")
    assert "claude" in adapters
    assert "codex" in adapters
    # Both adapters now expose a rules directory (Codex
    # gets .codex/rules/ too so consumer projects can resolve path
    # references from AGENTS.md even though Codex CLI does not auto-load
    # them the way Claude Code auto-loads .claude/rules/).
    assert adapters["claude"].supports_rules is True
    assert adapters["codex"].supports_rules is True


def test_claude_declares_settings_and_hooks() -> None:
    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")
    claude = adapters["claude"]
    assert claude.settings_file == ".claude/settings.json"
    assert claude.hooks_dir == ".claude/hooks"
    assert "cos-env.sh" in claude.sourced_hooks


def test_codex_declares_symmetric_dirs() -> None:
    # Codex declares the same structural dirs as Claude.
    # Content source (core/) is shared; only the loading mechanism differs.
    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")
    codex = adapters["codex"]
    assert codex.rules_dir == ".codex/rules"
    assert codex.hooks_dir == ".codex/hooks"
    assert codex.skills_dir == ".codex/skills"
    assert codex.commands_dir == ".codex/commands"


def test_entrypoint_file_declared_per_runtime() -> None:
    # Claude Code reads CLAUDE.md; Codex reads AGENTS.md natively, so it
    # declares no entrypoint of its own.
    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")
    assert adapters["claude"].entrypoint_file == "CLAUDE.md"
    assert adapters["codex"].entrypoint_file is None


@pytest.mark.parametrize("bad", ["../escape.md", "nested/CLAUDE.md", ".."])
def test_entrypoint_file_rejects_path_traversal(tmp_path: Path, bad: str) -> None:
    # A community adapter must not be able to make the scaffolder link outside
    # the project root.
    _copy_adapter_as("claude", tmp_path, "rogue")
    manifest = tmp_path / "rogue" / "adapter.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'entrypoint_file: "CLAUDE.md"', f'entrypoint_file: "{bad}"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(AdapterManifestError, match="entrypoint_file"):
        load_adapter_registry(tmp_path)


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
    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")
    assert "claude" in adapters and "codex" in adapters


# ---------- out-of-tree community overlay (B-7) ----------


def test_overlay_discovers_community_adapter(tmp_path: Path) -> None:
    """A community adapter in an out-of-tree overlay loads alongside the bundled
    ones — a third party adds an adapter without forking ($COS_USER_ADAPTERS_DIR)."""
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    _copy_adapter_as("claude", overlay, "community-x")
    reg = load_adapter_registry(_SRC_ADAPTERS, overlay_dirs=(overlay,))
    assert "community-x" in reg and "claude" in reg


def test_overlay_may_not_shadow_bundled_adapter(tmp_path: Path) -> None:
    """A community adapter id colliding with a bundled one is rejected (bundled
    kept), never raising the way a bundled duplicate does."""
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    _copy_adapter_as("claude", overlay, "claude")  # same id as bundled
    reg = load_adapter_registry(_SRC_ADAPTERS, overlay_dirs=(overlay,))
    assert "claude" in reg  # bundled kept, no AdapterManifestError


def test_overlay_malformed_community_adapter_fails_soft(tmp_path: Path) -> None:
    """A malformed COMMUNITY adapter is skipped (fail-soft), never crashing the
    CLI — unlike a malformed bundled adapter which still fails hard."""
    overlay = tmp_path / "overlay"
    (overlay / "broken").mkdir(parents=True)
    (overlay / "broken" / "adapter.yaml").write_text("{a: [unclosed\n", encoding="utf-8")
    reg = load_adapter_registry(_SRC_ADAPTERS, overlay_dirs=(overlay,))
    assert "claude" in reg and "broken" not in reg
