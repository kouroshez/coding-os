"""board_os test fixtures.

Adds the repo root to sys.path so tests using `from core.board_os …`
imports resolve when invoked via the matrix command (`pytest
core/board_os/tests/`). Mirrors core/thinking_os/tests/conftest.py.

Also adds src/core/thinking_os so the board_os conn fixture — which runs
the thinking_os DB migrations, including v37's bare `from sanitizer import`
(the thinking_os in-package convention) — resolves in isolation, not only
when a thinking_os test happened to prime sys.path first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_THINKING_OS = Path(__file__).resolve().parents[2] / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))


@pytest.fixture(autouse=True)
def _scrub_panel_env(monkeypatch):
    """Board writes resolve the calling session from $COS_PANEL_DIR /
    $COS_AGENT_DIR / $COS_SESSION_* (board_os._agent_runtime). Running the
    suite inside a live coding-os panel leaks the real session into
    attribution-sensitive tests; scrub it so a developer's in-panel run is
    deterministic and matches CI (where these are unset)."""
    for var in ("COS_PANEL_DIR", "COS_AGENT_DIR", "COS_SESSION_FILE", "COS_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)


# ── shared harness for the test_mcp_* part files ─────────────────────
import importlib.util as _importlib_util
import json as _json
import sqlite3
import time
from pathlib import Path as _Path

import yaml as _yaml


def _load_db_module():
    spec = _importlib_util.spec_from_file_location(
        "_db_under_test",
        _Path(__file__).resolve().parents[2] / "thinking_os" / "database.py",
    )
    mod = _importlib_util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


db = _load_db_module()


def _parse(envelope: str) -> dict:
    return _json.loads(envelope)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Minimal project with scrumban-config.yaml — shared by every test_mcp_* file."""
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        _yaml.safe_dump(
            {
                "swimlanes": [
                    {"id": "core", "label": "Core", "color": "#3b82f6"},
                    {"id": "docs", "label": "Docs", "color": "#a855f7"},
                ],
                "wip_limits": {"in_progress": 2, "testing": 3, "emergency": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def conn(tmp_path):
    return db.init_db(tmp_path / "coding-os.db")


def _backdate_task(conn: sqlite3.Connection, task_id: str, status: str, seconds_ago: int) -> None:
    old = int(time.time()) - seconds_ago
    conn.execute("UPDATE tasks SET status=?, started_at=? WHERE task_id=?", (status, old, task_id))
    conn.execute("UPDATE task_status_history SET transitioned_at=? WHERE task_id=?", (old, task_id))
    conn.commit()
