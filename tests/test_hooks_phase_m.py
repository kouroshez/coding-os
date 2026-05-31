"""Phase M hook tests: enforce-anti-ambiguity and track-backtrack."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_DIR = REPO_ROOT / "src" / "core" / "hooks"


def _run_hook(
    hook_name: str, tool_input: dict, state_dir: Path, env: dict | None = None
) -> subprocess.CompletedProcess:
    hook = HOOK_DIR / hook_name
    payload = json.dumps(
        {"tool_name": tool_input.pop("tool_name", "Write"), "tool_input": tool_input}
    )
    # state_dir is the test's tmp_path — never a shared /tmp path, so
    # concurrent runs (pytest -n) and stale state never collide.
    e = {**os.environ, "COS_AGENT": "claude", "COS_STATE_DIR": str(state_dir)}
    if env:
        e.update(env)
    return subprocess.run(
        ["bash", str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        env=e,
        timeout=10,
    )


class TestEnforceAntiAmbiguity:
    def test_non_code_file_passes(self, tmp_path):
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Write", "file_path": str(tmp_path / "README.md")},
            tmp_path,
        )
        assert result.returncode == 0

    def test_non_write_tool_passes(self, tmp_path):
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Read", "file_path": str(tmp_path / "src.py")},
            tmp_path,
        )
        assert result.returncode == 0

    def test_code_file_no_cache_passes(self, tmp_path):
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Write", "file_path": str(tmp_path / "src.py")},
            tmp_path,
            env={"COS_AGENT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_code_file_with_pass_cache_passes(self, tmp_path):
        # .ambiguity-cache + .thinking_os-gate are panel-scoped since TASK-035 —
        # the hook reads them from $COS_PANEL_DIR.
        panel = tmp_path / "panels" / "aa-panel"
        panel.mkdir(parents=True)
        (panel / ".ambiguity-cache").write_text("PASS")
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Write", "file_path": str(tmp_path / "src.py")},
            tmp_path,
            env={"COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "aa-panel"},
        )
        assert result.returncode == 0

    def test_code_file_with_fail_cache_blocks(self, tmp_path):
        panel = tmp_path / "panels" / "aa-panel"
        panel.mkdir(parents=True)
        (panel / ".ambiguity-cache").write_text("FAIL:scoped,owned")
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Write", "file_path": str(tmp_path / "src.py")},
            tmp_path,
            env={"COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "aa-panel"},
        )
        assert result.returncode == 1
        assert "BLOCKED" in result.stderr

    def test_clear_gate_bypasses_fail_cache(self, tmp_path):
        panel = tmp_path / "panels" / "aa-panel"
        panel.mkdir(parents=True)
        (panel / ".ambiguity-cache").write_text("FAIL:scoped")
        (panel / ".thinking_os-gate").write_text("CLEAR 1")
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Write", "file_path": str(tmp_path / "src.py")},
            tmp_path,
            env={"COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "aa-panel"},
        )
        assert result.returncode == 0


class TestHookRegistryPhaseM:
    def test_enforce_anti_ambiguity_in_registry(self):
        registry = REPO_ROOT / "src" / "core" / "hooks" / "registry.yaml"
        assert "enforce-anti-ambiguity" in registry.read_text()

    def test_track_backtrack_in_registry(self):
        registry = REPO_ROOT / "src" / "core" / "hooks" / "registry.yaml"
        assert "track-backtrack" in registry.read_text()

    def test_both_hooks_have_phase_m(self):
        registry = REPO_ROOT / "src" / "core" / "hooks" / "registry.yaml"
        content = registry.read_text()
        # Both hooks must declare phase: M
        assert content.count("phase: M") >= 2
