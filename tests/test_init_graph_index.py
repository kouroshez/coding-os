"""Module-aware auto-build of the graph during `cos init` (_initial_graph_index, TASK-423).

`cos init` seeds the knowledge graph so the Hub Graph tab works with no manual
`cos graph-reindex`. It must respect the modular system: when the graph module
is disabled for the project, no build is attempted. These tests mock the heavy
subprocess and assert the gating decision only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli.main as main_module


def _project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "proj"
    state = project / ".coding-os"
    state.mkdir(parents=True)
    return project, state


def _set_disabled(state: Path, disabled: list[str]) -> None:
    (state / "subsystems-state.json").write_text(
        json.dumps({"version": 1, "disabled": disabled}), encoding="utf-8"
    )


def test_graph_index_skipped_when_graph_module_disabled(tmp_path, monkeypatch):
    project, state = _project(tmp_path)
    _set_disabled(state, ["graph"])
    calls: list = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: calls.append(a) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    main_module._initial_graph_index(project, state)
    assert calls == [], "graph build must NOT run when the graph module is disabled"


def test_graph_index_runs_when_graph_module_enabled(tmp_path, monkeypatch):
    project, state = _project(tmp_path)
    # No state file → every module enabled (backward-compatible default).
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        captured["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(
            returncode=0, stdout="  Built knowledge graph: 5/5 file(s) indexed", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    main_module._initial_graph_index(project, state)
    assert captured, "graph build must run when the graph module is enabled"
    # Runs the in-process python (not the global `cos`) so an extras-less env
    # fails fast instead of doing heavy work.
    assert captured["cmd"][0] == sys.executable
    assert captured["env"].get("COS_DB_PATH", "").endswith("coding-os.db")
    # Bounded so a huge repo can't blow the init budget (TASK-429).
    assert isinstance(captured["timeout"], int) and captured["timeout"] > 0


def test_graph_index_degrades_gracefully_on_timeout(tmp_path, monkeypatch):
    project, state = _project(tmp_path)

    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", boom)
    # Must swallow the timeout — init continues, graph left empty (valid).
    main_module._initial_graph_index(project, state)


def test_composer_init_argv_builds_graph_under_no_index():
    # The Hub Composer create path must pass BOTH --no-index (skip slow doc-RAG)
    # and --graph-index (still build the graph) so a new project's Graph tab is
    # never empty (TASK-429).
    core = Path(__file__).resolve().parent.parent / "src" / "core"
    sys.path.insert(0, str(core))
    from web.routes.hub import _build_cos_init_cmd

    cmd = _build_cos_init_cmd("proj", "/tmp", [], ["claude"])
    assert "--no-index" in cmd
    assert "--graph-index" in cmd
