"""write-state.sh writes state files only: agents run it without a prompt.

Spec: docs/engineering/state-files.md § State file format.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "write-state.sh"


def _write(state: Path, target: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "COS_STATE_DIR": str(state), "COS_AGENT_DIR": str(state / "claude")}
    return subprocess.run(
        ["bash", str(HOOK), target, "v"], capture_output=True, text=True, env=env, timeout=20
    )


@pytest.mark.parametrize("escape", ["outside/x", "../../x", "claude/../../x"])
def test_a_path_outside_the_state_dir_is_refused(tmp_path: Path, escape: str) -> None:
    state = tmp_path / "project" / ".coding-os"
    state.mkdir(parents=True)
    target = str(tmp_path / escape) if escape == "outside/x" else escape

    result = _write(state, target)

    assert result.returncode == 2, result.stderr
    assert not (tmp_path / "x").exists() and not (tmp_path / "outside" / "x").exists()


def test_a_state_file_is_written(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    assert _write(state, ".model").returncode == 0
    assert (state / "claude" / ".model").read_text().endswith(" v\n")
