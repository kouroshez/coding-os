"""board↔git coherence core detector (TASK-436).

The shared detector behind the cos doctor board.git_tracked check, the nightly
task-filer, and the CI gate. Fast + hermetic: a throwaway git repo, no DB.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from board_os.git_coherence import detect_board_git_drift


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    (repo / "docs" / "tasks").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "T")
    _git(repo, "commit", "--allow-empty", "-q", "-m", "init")  # born HEAD so untracked shows
    return repo


def test_untracked_task_file_is_drift(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/tasks/TASK-200-new.md").write_text("# TASK-200\n")  # never git-added
    d = detect_board_git_drift(repo, [("TASK-200", "docs/tasks/TASK-200-new.md")])
    assert d.is_git_root and d.has_drift
    assert d.untracked == ["TASK-200"]
    assert d.missing == [] and d.modified == []


def test_missing_md_for_db_row_is_drift(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    d = detect_board_git_drift(repo, [("TASK-300", "docs/tasks/TASK-300-gone.md")])
    assert d.has_drift and d.missing == ["TASK-300"]


def test_committed_is_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/tasks/TASK-100-done.md").write_text("# TASK-100\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "t")
    d = detect_board_git_drift(repo, [("TASK-100", "docs/tasks/TASK-100-done.md")])
    assert d.is_git_root and not d.has_drift and d.checked == 1


def test_no_rows_is_clean(tmp_path: Path) -> None:
    d = detect_board_git_drift(_repo(tmp_path), [])
    assert d.is_git_root and not d.has_drift and d.checked == 0


def test_non_git_dir_skipped_not_errored(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    (plain / "docs" / "tasks").mkdir(parents=True)
    d = detect_board_git_drift(plain, [("TASK-100", "docs/tasks/TASK-100.md")])
    assert not d.is_git_root and not d.git_unavailable
    assert "not a git" in (d.skip_reason or "")
