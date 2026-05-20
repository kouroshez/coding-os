"""Tests for I.14 hooks + skill + docs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"


def _run_hook(
    name: str, *, stdin: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess:
    hook = HOOKS_DIR / name
    assert hook.exists(), f"hook missing: {hook}"
    full_env = {**os.environ, **env}
    return subprocess.run(
        ["bash", str(hook)],
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=cwd,
    )


class TestEnforceGraphContext:
    def _write_config(self, tmp_path: Path, patterns: list[str]) -> None:
        cfg_dir = tmp_path / ".coding-os"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "rag-config.yaml").write_text(
            "graph:\n  enforce_context_on:\n" + "".join(f"    - '{p}'\n" for p in patterns),
            encoding="utf-8",
        )

    def test_disabled_by_default(self, tmp_path):
        self._write_config(tmp_path, ["core/**/*.py"])
        result = _run_hook(
            "enforce-graph-context.sh",
            stdin=json.dumps({"tool_input": {"file_path": "core/x.py"}}),
            env={},
            cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_warn_when_marker_missing(self, tmp_path):
        self._write_config(tmp_path, ["core/x.py"])
        result = _run_hook(
            "enforce-graph-context.sh",
            stdin=json.dumps({"tool_input": {"file_path": "core/x.py"}}),
            env={"COS_ENFORCE_GRAPH_CONTEXT": "1"},
            cwd=tmp_path,
        )
        assert result.returncode == 0  # warn, not block
        assert "graph-context missing" in result.stderr

    def test_strict_blocks_when_marker_missing(self, tmp_path):
        self._write_config(tmp_path, ["core/x.py"])
        result = _run_hook(
            "enforce-graph-context.sh",
            stdin=json.dumps({"tool_input": {"file_path": "core/x.py"}}),
            env={"COS_ENFORCE_GRAPH_CONTEXT": "strict"},
            cwd=tmp_path,
        )
        assert result.returncode == 2

    def test_skip_when_file_not_in_scope(self, tmp_path):
        self._write_config(tmp_path, ["core/x.py"])
        result = _run_hook(
            "enforce-graph-context.sh",
            stdin=json.dumps({"tool_input": {"file_path": "unrelated/y.py"}}),
            env={"COS_ENFORCE_GRAPH_CONTEXT": "strict"},
            cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_no_config_file(self, tmp_path):
        # .coding-os/ absent entirely → hook exits 0.
        result = _run_hook(
            "enforce-graph-context.sh",
            stdin=json.dumps({"tool_input": {"file_path": "core/x.py"}}),
            env={"COS_ENFORCE_GRAPH_CONTEXT": "strict"},
            cwd=tmp_path,
        )
        assert result.returncode == 0


class TestEnforceRenamePlan:
    def test_warn_when_rename_without_plan(self, tmp_path):
        result = _run_hook(
            "enforce-rename-plan.sh",
            stdin=json.dumps({"tool_input": {"old_string": "foo", "new_string": "bar"}}),
            env={"COS_ENFORCE_RENAME_PLAN": "1"},
            cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "rename-plan missing" in result.stderr

    def test_non_identifier_change_ignored(self, tmp_path):
        result = _run_hook(
            "enforce-rename-plan.sh",
            stdin=json.dumps(
                {"tool_input": {"old_string": "hello world", "new_string": "hi there"}}
            ),
            env={"COS_ENFORCE_RENAME_PLAN": "strict"},
            cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_strict_blocks_new_rename(self, tmp_path):
        result = _run_hook(
            "enforce-rename-plan.sh",
            stdin=json.dumps({"tool_input": {"old_string": "foo", "new_string": "bar"}}),
            env={"COS_ENFORCE_RENAME_PLAN": "strict"},
            cwd=tmp_path,
        )
        assert result.returncode == 2


class TestSkillPresent:
    def test_graph_explorer_skill_file(self):
        path = REPO_ROOT / "src" / "core" / "skills" / "graph-explorer" / "SKILL.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "cos_graph_context" in text

    def test_queries_guide(self):
        path = REPO_ROOT / "docs" / "engineering" / "graph_os-queries.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "cos_graph_impact" in text
        assert "cos_graph_rename_plan" in text
