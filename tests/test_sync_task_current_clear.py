"""sync-task-current.sh clears .task-current when a task leaves active work.

Before TASK-292 the hook only SET the marker on in_progress and never cleared
it, so `cos task-done` left a fossil that mis-attributed later commits/banners.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = _REPO_ROOT / "src" / "core" / "hooks" / "sync-task-current.sh"


def _run(panel: Path, command: str) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        timeout=10,
        env={"COS_PANEL_DIR": str(panel), "COS_AGENT_DIR": str(panel), "PATH": _path()},
    )


def _path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")


def _marker(panel: Path) -> Path:
    return panel / ".task-current"


def test_clears_on_task_done(tmp_path):
    panel = tmp_path / "panel"
    panel.mkdir()
    _marker(panel).write_text("ses-x TASK-555")
    _run(panel, "cos task-done TASK-555")
    assert not _marker(panel).exists()


def test_clears_on_move_to_complete(tmp_path):
    panel = tmp_path / "panel"
    panel.mkdir()
    _marker(panel).write_text("ses-x TASK-556")
    _run(panel, "cos task-move TASK-556 --to complete")
    assert not _marker(panel).exists()


def test_does_not_clear_a_different_task(tmp_path):
    panel = tmp_path / "panel"
    panel.mkdir()
    _marker(panel).write_text("ses-x TASK-999")
    _run(panel, "cos task-done TASK-555")
    assert _marker(panel).read_text().strip() == "ses-x TASK-999"


def test_testing_keeps_the_marker(tmp_path):
    panel = tmp_path / "panel"
    panel.mkdir()
    _marker(panel).write_text("ses-x TASK-557")
    _run(panel, "cos task-move TASK-557 --to testing")
    assert _marker(panel).exists()
