"""write-state.sh writes one-line markers under the agent dir only: agents run it without a prompt.

Spec: docs/engineering/state-files.md § State file format.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "write-state.sh"


def _write(state: Path, target: str, value: str = "v") -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "COS_STATE_DIR": str(state), "COS_AGENT_DIR": str(state / "claude")}
    env.pop("COS_PANEL_DIR", None)
    return subprocess.run(
        ["bash", str(HOOK), target, value], capture_output=True, text=True, env=env, timeout=20
    )


@pytest.fixture()
def state(tmp_path: Path) -> Path:
    root = tmp_path / "project" / ".coding-os"
    root.mkdir(parents=True)
    for name in ("coding-os.db", "hub-settings.json", "disabled-hook-scripts", ".last-verify.json"):
        (root / name).write_text("keep\n", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "target",
    [
        "{tmp}/outside.md",
        "../../x",
        "claude/../../x",
        "{state}/coding-os.db",
        "{state}/hub-settings.json",
        "{state}/disabled-hook-scripts",
        "{state}/.last-verify.json",
    ],
)
def test_anything_but_an_agent_marker_is_refused(state: Path, tmp_path: Path, target: str) -> None:
    result = _write(state, target.format(tmp=tmp_path, state=state))

    assert result.returncode == 2, result.stderr
    assert not (tmp_path / "outside.md").exists()
    for name in ("coding-os.db", "hub-settings.json", "disabled-hook-scripts", ".last-verify.json"):
        assert (state / name).read_text(encoding="utf-8") == "keep\n"


def test_a_multi_line_value_is_refused(state: Path) -> None:
    assert _write(state, ".model", "x\nblock-secrets.sh").returncode == 2
    assert not (state / "claude" / ".model").exists()


def test_a_marker_is_written(state: Path) -> None:
    assert _write(state, ".model").returncode == 0
    assert (state / "claude" / ".model").read_text().endswith(" v\n")
