"""First-session UX (TASK-372): a brand-new project's FIRST legitimate code edit
must clear the enforce-doc-anchor BLOCK via the one-shot `.fresh-init` grace that
`cos init` leaves, and the grace must be bounded — the next anchorless edit blocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cli.main import cli

HOOK = REPO_ROOT / "src" / "core" / "hooks" / "enforce-doc-anchor.sh"

pytestmark = pytest.mark.slow  # scaffolds a real project via `cos init`


def _run_hook(project: Path, state: Path, agent_dir: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "COS_STATE_DIR": str(state),
        "COS_AGENT_DIR": str(agent_dir),
        "COS_AGENT": "claude",
        "COS_PROJECT_ROOT": str(project),
    }
    env.pop("COS_PANEL_DIR", None)  # force the agent-dir anchor path
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(project / "src" / "app.py"),
            "old_string": "a",
            "new_string": "b",
        },
    }
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project),
        timeout=15,
    )


def test_fresh_project_first_edit_passes_then_grace_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_path / "registry.json"))
    result = CliRunner().invoke(
        cli,
        [
            "init",
            "--agent",
            "claude",
            "--name",
            "proj",
            "-d",
            str(tmp_path),
            "--no-git",
            "--no-index",
        ],
    )
    assert result.exit_code == 0, result.output

    project = tmp_path / "proj"
    state = project / ".coding-os"
    marker = state / ".fresh-init"
    assert marker.exists(), "init must leave a .fresh-init grace marker"

    agent_dir = state / "claude"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (project / "src").mkdir(parents=True, exist_ok=True)
    assert not (agent_dir / ".doc-anchor").exists()  # fresh — no anchor yet

    # First legitimate edit: grace allows it and consumes the marker.
    first = _run_hook(project, state, agent_dir)
    assert first.returncode == 0, f"fresh first edit blocked: {first.stderr}"
    assert not marker.exists(), "grace marker must be consumed after the first edit"

    # Bounded: a second anchorless edit blocks normally (no standing bypass).
    second = _run_hook(project, state, agent_dir)
    assert second.returncode == 2, "second anchorless edit must block — grace is one-shot"
    assert "BLOCKED" in second.stderr
