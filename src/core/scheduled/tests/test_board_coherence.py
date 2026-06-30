"""nightly board_coherence task (TASK-436) — idempotent board↔git drift filing."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

try:
    from core.scheduled.nightly import _run_board_coherence
    from core.thinking_os.database import init_db
except ImportError:  # runner path differences
    from scheduled.nightly import _run_board_coherence
    from thinking_os.database import init_db


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo_with_db(tmp_path: Path):
    repo = tmp_path / "proj"
    (repo / "docs" / "tasks").mkdir(parents=True)
    (repo / ".coding-os").mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "T")
    _git(repo, "commit", "--allow-empty", "-q", "-m", "init")  # born HEAD so untracked shows
    db_path = repo / ".coding-os" / "coding-os.db"
    conn = init_db(db_path)
    return repo, db_path, conn


def _seed_drift(conn: sqlite3.Connection, title: str) -> None:
    # cos_task_create writes a real DB row (+ an uncommitted .md) → board↔git drift.
    import json

    from board_os.mcp_tools import cos_task_create

    env = cos_task_create(
        conn,
        title=title,
        swimlane="infra",
        kind="chore",
        status="icebox",
        ready=True,
        outcome="seed task to create board↔git drift for the coherence nightly test path",
    )
    assert json.loads(env).get("ok"), env


def test_no_drift_files_nothing(tmp_path: Path) -> None:
    repo, db_path, conn = _repo_with_db(tmp_path)
    conn.close()
    r = _run_board_coherence(db_path, repo, dry_run=False)
    assert r["status"] == "ok" and r.get("drift") is False


def test_files_once_idempotent(tmp_path: Path, monkeypatch) -> None:
    repo, db_path, conn = _repo_with_db(tmp_path)
    # cos_task_create resolves docs/tasks from $COS_PROJECT_ROOT/cwd — scope it to
    # the tmp repo so the test never writes task files into the real repo.
    monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))
    monkeypatch.delenv("COS_GIT_AUTONOMY", raising=False)  # default 'draft' → file, don't commit
    _seed_drift(conn, "drift seed A")
    conn.close()

    r1 = _run_board_coherence(db_path, repo, dry_run=False)
    assert r1.get("drift") is True and r1.get("filed") is True, r1
    assert r1.get("task_id"), r1  # filed must mint a real task_id, never filed:true / id:null
    r2 = _run_board_coherence(db_path, repo, dry_run=False)
    assert r2.get("filed") is False, r2  # idempotent — open auto-git-drift task already exists

    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('complete', 'archive') "
        "AND labels_json LIKE '%\"auto-git-drift\"%'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_dry_run_files_nothing(tmp_path: Path, monkeypatch) -> None:
    repo, db_path, conn = _repo_with_db(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))  # scope task writes to tmp repo
    monkeypatch.delenv("COS_GIT_AUTONOMY", raising=False)
    _seed_drift(conn, "drift seed B")
    conn.close()
    r = _run_board_coherence(db_path, repo, dry_run=True)
    assert r.get("drift") is True and r.get("filed") is False and r.get("dry_run") is True


def test_autonomous_autocommits_drift(tmp_path: Path, monkeypatch) -> None:
    repo, db_path, conn = _repo_with_db(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))
    monkeypatch.setenv("COS_GIT_AUTONOMY", "autonomous")
    _seed_drift(conn, "drift seed C")
    conn.close()

    r = _run_board_coherence(db_path, repo, dry_run=False)
    assert r.get("drift") is True and r.get("committed") is True and r.get("sha"), r
    # tasks-only commit converged the tree clean — no leftover docs/tasks drift.
    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--", "docs/tasks"],
        cwd=repo, capture_output=True, text=True,
    ).stdout.strip()
    assert porcelain == "", porcelain
    # the commit resolved the drift, so the nagger filed no task.
    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE labels_json LIKE '%\"auto-git-drift\"%'"
    ).fetchone()[0]
    conn.close()
    assert n == 0


def test_autocommit_converges_in_one_pass(tmp_path: Path, monkeypatch) -> None:
    repo, db_path, conn = _repo_with_db(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))
    monkeypatch.setenv("COS_GIT_AUTONOMY", "autonomous")
    _seed_drift(conn, "drift seed D")
    conn.close()

    first = _run_board_coherence(db_path, repo, dry_run=False)
    assert first.get("committed") is True, first
    second = _run_board_coherence(db_path, repo, dry_run=False)
    assert second.get("drift") is False, second  # one tasks-only pass cleaned it, no re-dirty


def test_local_autonomy_also_autocommits(tmp_path: Path, monkeypatch) -> None:
    # 'local' = "commits, never pushes" — the natural Hub choice — must also
    # trigger board-churn auto-commit (gate-expansion regression, the rung the
    # Hub dropdown actually offers for a no-remote trunk repo).
    repo, db_path, conn = _repo_with_db(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))
    monkeypatch.setenv("COS_GIT_AUTONOMY", "local")
    _seed_drift(conn, "drift seed E")
    conn.close()

    r = _run_board_coherence(db_path, repo, dry_run=False)
    assert r.get("committed") is True and r.get("sha"), r
