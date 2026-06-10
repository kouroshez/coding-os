"""_prepare_commit_msg_body.sh stamps the active task id into a commit subject.

This is the write-side of commit→task linking (TASK-297): with the id in the
subject, cos_task_history's `git log --all --grep` links the commit to its task
for every actor — terminal agent, human, or Hub.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = _REPO_ROOT / "src" / "scripts" / "_prepare_commit_msg_body.sh"


def _run(msg_file: Path, panel: Path, src: str = "") -> None:
    subprocess.run(
        ["bash", str(HOOK), str(msg_file), src],
        cwd=_REPO_ROOT,
        env={"COS_PANEL_DIR": str(panel), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True,
        timeout=10,
    )


def _panel(tmp_path: Path, task: str) -> Path:
    panel = tmp_path / "panel"
    panel.mkdir()
    (panel / ".task-current").write_text(f"ses {task}")
    return panel


def test_stamps_active_task_when_missing(tmp_path):
    panel = _panel(tmp_path, "TASK-297")
    msg = tmp_path / "msg"
    msg.write_text("feat(x): add a thing\n")
    _run(msg, panel)
    assert msg.read_text().splitlines()[0] == "feat(x): add a thing (TASK-297)"


def test_does_not_double_stamp(tmp_path):
    panel = _panel(tmp_path, "TASK-297")
    msg = tmp_path / "msg"
    msg.write_text("feat(x): already (TASK-297)\n")
    _run(msg, panel)
    assert msg.read_text().splitlines()[0] == "feat(x): already (TASK-297)"


def test_skips_when_subject_would_exceed_100(tmp_path):
    panel = _panel(tmp_path, "TASK-297")
    msg = tmp_path / "msg"
    long_subject = "feat(x): " + ("a" * 95)
    msg.write_text(long_subject + "\n")
    _run(msg, panel)
    assert "TASK-297" not in msg.read_text()


def test_noop_when_no_active_task(tmp_path):
    panel = tmp_path / "panel"
    panel.mkdir()  # no .task-current
    msg = tmp_path / "msg"
    msg.write_text("feat(x): add a thing\n")
    _run(msg, panel)
    assert msg.read_text().splitlines()[0] == "feat(x): add a thing"


def test_skips_merge_source(tmp_path):
    panel = _panel(tmp_path, "TASK-297")
    msg = tmp_path / "msg"
    msg.write_text("Merge branch 'x'\n")
    _run(msg, panel, src="merge")
    assert "TASK-297" not in msg.read_text()
