"""Tests for link-commit-to-task.sh (TASK-273).

The Claude PostToolUse Bash hook links a real `git commit` to the panel's
active .task-current by appending `commit <sha> — <subject>` to the task's Work
Log, so cos_task_history surfaces code commits that never touched the task .md.
The append helper is stubbed via COS_WORKLOG_HELPER so the test stays hermetic;
the hook's synchronous systemMessage is the assertion surface.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = _REPO_ROOT / "src" / "core" / "hooks" / "link-commit-to-task.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo_with_task(tmp_path: Path, task_id: str) -> Path:
    repo = tmp_path / "proj"
    (repo / "docs" / "tasks").mkdir(parents=True)
    (repo / "docs" / "tasks" / f"{task_id}-demo.md").write_text(
        f"# {task_id}\n\n## Work Log\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "T")
    (repo / "a.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")
    panel = repo / "panel"
    panel.mkdir()
    (panel / ".task-current").write_text(task_id)
    return repo


def _run(repo: Path, command: str, *, helper: Path | None = None) -> tuple[int, str]:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {
        **os.environ,
        "COS_PROJECT_ROOT": str(repo),
        "COS_PANEL_DIR": str(repo / "panel"),
        "COS_AGENT_DIR": str(repo / "panel"),
    }
    if helper is not None:
        env["COS_WORKLOG_HELPER"] = str(helper)
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, env=env, capture_output=True, text=True, timeout=10
    )
    return proc.returncode, proc.stdout


def test_links_commit_for_active_task(tmp_path):
    repo = _repo_with_task(tmp_path, "TASK-555")
    sha = subprocess.run(
        ["git", "rev-parse", "--short=10", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    code, out = _run(repo, 'git commit -m "work"')
    assert code == 0
    assert "[worklog] commit" in out
    assert sha in out
    assert "TASK-555" in out


def test_dedup_when_sha_already_logged(tmp_path):
    repo = _repo_with_task(tmp_path, "TASK-556")
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    md = repo / "docs" / "tasks" / "TASK-556-demo.md"
    md.write_text(md.read_text() + f"- 2026 [claude]: committed {sha}: a.py\n")
    code, out = _run(repo, 'git commit -m "work"')
    assert code == 0
    assert out.strip() == "", "a 7-char prefix match should dedup the git-hook entry"


def test_noop_on_non_commit_bash(tmp_path):
    repo = _repo_with_task(tmp_path, "TASK-557")
    code, out = _run(repo, "ls -la")
    assert code == 0
    assert out.strip() == ""


def test_noop_when_no_active_task(tmp_path):
    repo = _repo_with_task(tmp_path, "TASK-558")
    (repo / "panel" / ".task-current").unlink()
    code, out = _run(repo, 'git commit -m "work"')
    assert code == 0
    assert out.strip() == ""
