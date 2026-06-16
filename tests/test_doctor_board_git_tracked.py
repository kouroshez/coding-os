"""board.git_tracked doctor check — board↔git coherence (TASK-432).

Fast + hermetic: a tiny throwaway git repo + an in-memory tasks table, calling
the check directly. NOT slow-marked (unlike test_doctor.py) so it runs in the
normal suite and guards the drift detection on every change.
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

from cli import doctor_board
from cli.doctor import SEV_PASS, SEV_WARN


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    (repo / "docs" / "tasks").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "T")
    return repo


def _db(rows: list[tuple[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tasks (task_id TEXT, file_path TEXT)")
    conn.executemany("INSERT INTO tasks (task_id, file_path) VALUES (?, ?)", rows)
    return conn


def _run(conn: sqlite3.Connection, repo: Path):
    report = SimpleNamespace(checks=[])
    doctor_board._check_git_tracked(report, conn, repo)
    return report.checks[-1]


def test_untracked_task_file_warns(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/tasks/TASK-100-done.md").write_text("# TASK-100\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "task 100")
    (repo / "docs/tasks/TASK-200-new.md").write_text("# TASK-200\n")  # never git-added
    conn = _db(
        [
            ("TASK-100", "docs/tasks/TASK-100-done.md"),
            ("TASK-200", "docs/tasks/TASK-200-new.md"),
        ]
    )
    check = _run(conn, repo)
    assert check.severity == SEV_WARN
    assert "TASK-200" in check.details["untracked"]
    assert "TASK-100" not in check.details["untracked"]


def test_missing_md_for_db_row_warns(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    conn = _db([("TASK-300", "docs/tasks/TASK-300-gone.md")])  # row but no file on disk
    check = _run(conn, repo)
    assert check.severity == SEV_WARN
    assert "TASK-300" in check.details["missing_file"]


def test_all_committed_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/tasks/TASK-100-done.md").write_text("# TASK-100\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "task 100")
    conn = _db([("TASK-100", "docs/tasks/TASK-100-done.md")])
    check = _run(conn, repo)
    assert check.severity == SEV_PASS


def test_non_git_dir_is_skipped_not_errored(tmp_path: Path) -> None:
    # cwd is not a work-tree → fail-open, never crash, never report a parent repo.
    plain = tmp_path / "plain"
    (plain / "docs" / "tasks").mkdir(parents=True)
    conn = _db([("TASK-100", "docs/tasks/TASK-100-done.md")])
    check = _run(conn, plain)
    assert check.severity == SEV_PASS
    assert "not a git work-tree" in check.message
