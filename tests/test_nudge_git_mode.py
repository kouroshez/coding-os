"""Tests for nudge-git-mode.sh — pr-mode directive injector (TASK-615).

pr-mode must be surfaced PROACTIVELY (once per session) rather than learned by
being block-shared-tree-edit BLOCKed; trunk (the default) stays inert.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "nudge-git-mode.sh"


def _run(panel: Path, *, git_workflow: str | None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["COS_PANEL_DIR"] = str(panel)
    env["COS_AGENT_DIR"] = str(panel)
    if git_workflow is None:
        env.pop("COS_GIT_WORKFLOW", None)  # default resolves to trunk
    else:
        env["COS_GIT_WORKFLOW"] = git_workflow
    return subprocess.run(
        ["bash", str(HOOK)], input="", capture_output=True, text=True, env=env, timeout=10
    )


def test_pr_mode_injects_directive_once_per_session(tmp_path: Path) -> None:
    first = _run(tmp_path, git_workflow="pr")
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)
    out = payload["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    assert "pr-mode ON" in out["additionalContext"]
    assert "cos pr open" in out["additionalContext"]
    assert (tmp_path / ".git-mode-nudged").is_file()  # marker stamped
    # a second prompt in the same session injects nothing (marker present)
    second = _run(tmp_path, git_workflow="pr")
    assert second.returncode == 0
    assert second.stdout.strip() == ""


def test_trunk_mode_is_inert(tmp_path: Path) -> None:
    res = _run(tmp_path, git_workflow=None)  # default = trunk
    assert res.returncode == 0
    assert res.stdout.strip() == ""
    assert not (tmp_path / ".git-mode-nudged").exists()  # no marker, no work


def test_explicit_trunk_is_inert(tmp_path: Path) -> None:
    res = _run(tmp_path, git_workflow="trunk")
    assert res.returncode == 0
    assert res.stdout.strip() == ""
