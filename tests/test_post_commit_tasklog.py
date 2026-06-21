"""Tests for the post-commit task-log write-back (TASK-175).

The hook detects the task from the committed TASK-NNN-*.md, logs the committed
CODE files + short sha (idempotent per sha), skips when there is no task file or
no code, and never errors. The real work_log_append helper is stubbed so the
test stays hermetic.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
BODY = _REPO_ROOT / "src" / "scripts" / "_post_commit_body.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "T")
    return repo


def _stub(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "called.txt"
    stub = tmp_path / "stub.py"
    stub.write_text(
        "import os, sys\nopen(os.environ['STUB_OUT'], 'a').write(repr(sys.argv[1:]) + '\\n')\n"
    )
    return stub, out


def _run(repo: Path, stub: Path, out: Path) -> None:
    env = {**os.environ, "COS_WORKLOG_HELPER": str(stub), "STUB_OUT": str(out)}
    subprocess.run(
        ["bash", str(BODY)], cwd=repo, env=env, capture_output=True, text=True, check=True
    )


def test_logs_code_files_for_a_task_commit(tmp_path):
    repo = _new_repo(tmp_path)
    stub, out = _stub(tmp_path)
    (repo / "docs" / "tasks").mkdir(parents=True)
    (repo / "docs" / "tasks" / "TASK-901-demo.md").write_text("# TASK-901\n\n## Work Log\n")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")
    _run(repo, stub, out)
    recorded = out.read_text()
    assert "TASK-901" in recorded
    # Count-first summary, not the enumerated file list (recoverable via git).
    assert "1 file" in recorded
    assert "src/a.py" not in recorded


def test_idempotent_when_sha_already_logged(tmp_path):
    repo = _new_repo(tmp_path)
    stub, out = _stub(tmp_path)
    (repo / "docs" / "tasks").mkdir(parents=True)
    task = repo / "docs" / "tasks" / "TASK-902-demo.md"
    task.write_text("# TASK-902\n\n## Work Log\n")
    (repo / "a.py").write_text("y = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    task.write_text(task.read_text() + f"- 2026-06-06 [claude]: committed {sha}: a.py\n")
    _run(repo, stub, out)
    assert not out.exists(), "should skip when the sha is already logged"


def test_skips_when_no_task_file(tmp_path):
    repo = _new_repo(tmp_path)
    stub, out = _stub(tmp_path)
    (repo / "a.py").write_text("z = 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "no task")
    _run(repo, stub, out)
    assert not out.exists()


def test_skips_when_only_task_file_committed(tmp_path):
    repo = _new_repo(tmp_path)
    stub, out = _stub(tmp_path)
    (repo / "docs" / "tasks").mkdir(parents=True)
    (repo / "docs" / "tasks" / "TASK-903-demo.md").write_text("# TASK-903\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "task only")
    _run(repo, stub, out)
    assert not out.exists(), "no code files → nothing to log (loop guard)"
