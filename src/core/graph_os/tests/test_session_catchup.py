"""SessionStart catches the graph up with files changed outside the agent.

Spec: docs/engineering/graph_os-queries.md § Session-start catch-up.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / "hooks"
WAIT_SECONDS = 20


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _env(project: Path, panel: str) -> dict[str, str]:
    state = project / ".coding-os"
    return {
        **os.environ,
        "COS_STATE_DIR": str(state),
        "COS_PROJECT_ROOT": str(project),
        "COS_DB_PATH": str(state / "coding-os.db"),
        "COS_PANEL_DIR": str(state / "panels" / panel),
        "COS_HOOK_LOG": str(state / ".hooks.log"),
    }


def _session_start(project: Path, panel: str) -> None:
    subprocess.run(
        ["bash", str(HOOKS / "warn-graph-empty.sh")],
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        env=_env(project, panel),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=project,
        check=True,
    )


def _nodes(project: Path, rel: str) -> int:
    try:
        conn = sqlite3.connect(project / ".coding-os" / "coding-os.db")
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE file_path = ?", (rel,)
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return 0


def _wait(predicate) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return False


def _marker(project: Path) -> str:
    path = project / ".coding-os" / ".graph-indexed-head"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".gitignore").write_text(".coding-os/\n", encoding="utf-8")
    (tmp_path / "seed.py").write_text("def seed():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "seed")
    # The catch-up only runs on a graph that has nodes, so index the seed the
    # way an edit hook does before the first session start records the marker.
    subprocess.run(
        ["bash", str(HOOKS / "auto-reindex-graph.sh")],
        input=json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "seed.py")}}
        ),
        env=_env(tmp_path, "seed"),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=tmp_path,
        check=True,
    )
    assert _wait(lambda: _nodes(tmp_path, "seed.py") > 0)
    _session_start(tmp_path, "first")
    assert _marker(tmp_path) == _git(tmp_path, "rev-parse", "HEAD")
    return tmp_path


def test_a_file_pulled_since_the_last_session_reaches_the_graph(project: Path):
    (project / "pulled.py").write_text("def pulled():\n    return 2\n", encoding="utf-8")
    _git(project, "add", "pulled.py")
    _git(project, "commit", "-qm", "pulled")

    _session_start(project, "second")

    assert _wait(lambda: _nodes(project, "pulled.py") > 0)
    assert _wait(lambda: _marker(project) == _git(project, "rev-parse", "HEAD"))


def test_a_file_deleted_outside_the_agent_is_pruned(project: Path):
    _git(project, "rm", "-q", "seed.py")
    _git(project, "commit", "-qm", "drop seed")

    _session_start(project, "second")

    assert _wait(lambda: _nodes(project, "seed.py") == 0)


def test_an_unchanged_tree_spawns_no_worker(project: Path):
    log = project / ".coding-os" / ".hooks.log"
    started = time.monotonic()

    _session_start(project, "second")

    assert time.monotonic() - started < 2
    assert "catchup-none" in log.read_text(encoding="utf-8")
    assert _marker(project) == _git(project, "rev-parse", "HEAD")
