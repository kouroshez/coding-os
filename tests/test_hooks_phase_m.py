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
        # .ambiguity-cache + .thinking_os-gate are panel-scoped —
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

    def test_recent_db_violation_blocks(self, tmp_path):
        # The hook reads unresolved violations from the ambiguity_violations DB
        # table (the old .ambiguity-cache file mechanism is gone) — a recent row
        # for the current session blocks with exit 2.
        import sqlite3

        db = tmp_path / "coding-os.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE ambiguity_violations (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id TEXT NOT NULL, formula_id TEXT NOT NULL, step_id TEXT, "
            "criterion TEXT NOT NULL, detail TEXT, "
            "ts TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute(
            "INSERT INTO ambiguity_violations (session_id, formula_id, criterion, ts) "
            "VALUES ('aa-sid', 'f1', 'scoped', datetime('now'))"
        )
        conn.commit()
        conn.close()
        panel = tmp_path / "panels" / "aa-panel"
        panel.mkdir(parents=True)
        (panel / "session-id").write_text("aa-sid\n")
        result = _run_hook(
            "enforce-anti-ambiguity.sh",
            {"tool_name": "Write", "file_path": str(tmp_path / "src.py")},
            tmp_path,
            env={
                "COS_AGENT_DIR": str(tmp_path),
                "COS_PANEL_ID": "aa-panel",
                "COS_DB_PATH": str(db),
            },
        )
        assert result.returncode == 2
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
