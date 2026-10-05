"""The edit-time reindex hooks index the last edit of a burst, and neither cancels the other."""

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


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".coding-os").mkdir()
    return tmp_path


def _fire(hook: str, project: Path, path: Path) -> None:
    subprocess.run(
        ["bash", str(HOOKS / hook)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(path)}}),
        env={
            **os.environ,
            "COS_STATE_DIR": str(project / ".coding-os"),
            "COS_PROJECT_ROOT": str(project),
            "COS_DB_PATH": str(project / ".coding-os" / "coding-os.db"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        cwd=project,
        check=True,
    )


def _labels_once_settled(project: Path, path: str, expected: set[str]) -> set[str]:
    labels: set[str] = set()
    deadline = time.monotonic() + WAIT_SECONDS
    while labels != expected and time.monotonic() < deadline:
        time.sleep(0.25)
        try:
            conn = sqlite3.connect(project / ".coding-os" / "coding-os.db")
            try:
                rows = conn.execute(
                    "SELECT label FROM graph_nodes WHERE file_path = ? AND kind = 'function'",
                    (path,),
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            continue
        labels = {row[0] for row in rows}
    return labels


def _nodes_once_settled(project: Path, path: str) -> int:
    count = 0
    deadline = time.monotonic() + WAIT_SECONDS
    while count == 0 and time.monotonic() < deadline:
        time.sleep(0.25)
        try:
            conn = sqlite3.connect(project / ".coding-os" / "coding-os.db")
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE file_path = ?", (path,)
                ).fetchone()[0]
            finally:
                conn.close()
        except sqlite3.OperationalError:
            continue
    return count


def test_a_second_edit_inside_the_old_debounce_window_reaches_the_graph(project: Path):
    module = project / "pkg" / "mod.py"
    module.parent.mkdir()
    module.write_text("def first():\n    return 1\n", encoding="utf-8")
    _fire("auto-reindex-graph.sh", project, module)
    time.sleep(1.5)
    module.write_text(
        "def first():\n    return 1\n\n\ndef added():\n    return 2\n", encoding="utf-8"
    )
    _fire("auto-reindex-graph.sh", project, module)

    assert _labels_once_settled(project, "pkg/mod.py", {"first", "added"}) == {"first", "added"}


def test_a_docs_hook_fire_does_not_cancel_the_graph_hooks_pending_reindex(project: Path):
    doc = project / "docs" / "guide.md"
    doc.parent.mkdir()
    doc.write_text("# Guide\n\nSee [setup](./setup.md).\n", encoding="utf-8")
    _fire("auto-reindex-graph.sh", project, doc)
    _fire("auto-reindex-docs.sh", project, doc)

    assert _nodes_once_settled(project, "docs/guide.md") > 0
