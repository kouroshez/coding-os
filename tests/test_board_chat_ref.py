"""Coverage for the task->chat resolver endpoint (TASK-185):
/api/board/task/{id}/chat-ref.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.board_os import mcp_tools
from core.thinking_os.database import init_db
from core.web.server import create_app


@pytest.fixture
def proj(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "wip_limits": {"in_progress": 2, "testing": 3, "emergency": 2},
            }
        )
    )
    (root / "docs" / "tasks").mkdir(parents=True)
    db_path = root / ".coding-os" / "coding-os.db"
    monkeypatch.setenv("COS_PROJECT_ROOT", str(root))
    monkeypatch.setenv("COS_DB_PATH", str(db_path))
    monkeypatch.setenv("COS_STATE_DIR", str(root / ".coding-os"))
    monkeypatch.chdir(root)
    conn = init_db(db_path)
    created = json.loads(
        mcp_tools.cos_task_create(conn, title="x", swimlane="core", kind="feature", outcome="demo")
    )
    tid = created["data"]["task_id"]
    conn.execute("UPDATE tasks SET agent_session=? WHERE task_id=?", ("ses-claude-test-xyz", tid))
    conn.commit()
    conn.close()
    return root, tid


def test_resolves_sdk_uuid_and_snapshot(proj):
    root, tid = proj
    sess = root / ".coding-os" / "claude" / "sessions"
    sess.mkdir(parents=True)
    (sess / "ses-claude-test-xyz.json").write_text(
        json.dumps({"agent": "claude", "session_id": "ses-claude-test-xyz", "sdk_uuid": "SDK-123"})
    )
    (sess / "transcripts").mkdir()
    (sess / "transcripts" / "ses-claude-test-xyz.jsonl").write_text("{}\n")
    with TestClient(create_app()) as c:
        r = c.get(f"/api/board/task/{tid}/chat-ref")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["agent_session"] == "ses-claude-test-xyz"
    assert d["sdk_uuid"] == "SDK-123"
    assert d["has_snapshot"] is True


def test_none_for_human_attributed_task(proj):
    root, tid = proj
    conn = sqlite3.connect(str(root / ".coding-os" / "coding-os.db"))
    conn.execute("UPDATE tasks SET agent_session='human' WHERE task_id=?", (tid,))
    conn.commit()
    conn.close()
    with TestClient(create_app()) as c:
        r = c.get(f"/api/board/task/{tid}/chat-ref")
    d = r.json()["data"]
    assert d["sdk_uuid"] is None
    assert d["has_snapshot"] is False


def test_invalid_task_id_rejected(proj):
    with TestClient(create_app()) as c:
        assert c.get("/api/board/task/NOTATASK/chat-ref").status_code == 400
