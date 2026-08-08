"""Shared helpers for the test_cli part modules (fixtures stay in the aggregator)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import cli.main as main_module
from cli.main import cli

__all__ = ["_class_scaffold_cli", "_claude_entrypoint_name", "cli", "main_module"]


def _claude_entrypoint_name() -> str:
    """The root entrypoint filename the claude adapter declares (Rule 11 — the
    literal lives in adapter.yaml, not in CLI code or in this test)."""
    from cli.adapter_registry import load_adapter_registry

    name = load_adapter_registry(main_module.ADAPTERS_DIR)["claude"].entrypoint_file
    assert name, "claude adapter must declare an entrypoint_file"
    return name


def _class_scaffold_cli(tmp_path_factory: pytest.TempPathFactory, name: str) -> Path:
    """Scaffold one `cos init` claude project shared across a class of read-only
    tests (TASK-670). Class-scoped fixtures run before the function-scoped
    _stub_initial_indexing autouse, so this re-applies the index stubs + registry
    isolation itself — otherwise init would load the embedding model and write the
    real ~/.coding-os registry."""
    base = tmp_path_factory.mktemp(name)
    project = base / "test-project"
    project.mkdir()
    mp = pytest.MonkeyPatch()
    mp.setenv("COS_REGISTRY_PATH", str(base / "registry.json"))
    mp.setattr(main_module, "_initial_doc_index", lambda *a, **k: None)
    mp.setattr(main_module, "_initial_graph_index", lambda *a, **k: None)
    try:
        result = CliRunner().invoke(cli, ["init", "--agent", "claude", "-d", str(project)])
        assert result.exit_code == 0, f"init failed: {result.output}"
    finally:
        mp.undo()
    return project
