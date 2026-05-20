"""Dedicated pytest coverage for /api/roles endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src" / "core") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src" / "core"))

from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = tmp_path / ".coding-os"
    (state / "claude" / "traces").mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    app = create_app()
    with TestClient(app) as c:
        yield c, state


def test_roles_list_contains_formula_metadata(client):
    c, _ = client
    resp = c.get("/api/roles")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert isinstance(body["data"]["roles"], list)
    assert body["data"]["count"] >= 11
    first = body["data"]["roles"][0]
    assert "formula_id" in first
    assert "output_schema" in first


def test_roles_chain_reads_state_files(client):
    c, state = client
    agent_dir = state / "claude"
    (agent_dir / ".roles").write_text(json.dumps(["F1", "F2", "F5"]), encoding="utf-8")
    (agent_dir / ".role").write_text("F2", encoding="utf-8")

    resp = c.get("/api/roles/chain", params={"agent": "claude"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["chain"] == ["F1", "F2", "F5"]
    assert data["active_formula"] == "F2"
    assert data["has_active_session"] is True


def test_roles_outputs_collects_trace_and_bundle(client):
    c, state = client
    trace = state / "claude" / "traces" / "ses-test-1.jsonl"
    trace.write_text(
        "\n".join(
            [
                json.dumps({"kind": "compose_done", "data": {"chain": ["F1", "F2"]}, "ts": 1}),
                json.dumps(
                    {
                        "kind": "role_output_recorded",
                        "data": {"formula_id": "F1", "status": "ok", "latency_ms": 32},
                        "ts": 2,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    bundle = state / "claude" / "evidence_bundle_ses-test-1.json"
    bundle.write_text(
        json.dumps(
            {
                "task_marker": "TASK-124",
                "persona_id": "builder",
                "F1_research": {
                    "summary": "done",
                    "sources": [],
                    "key_findings": [],
                    "open_questions": [],
                },
            }
        ),
        encoding="utf-8",
    )

    resp = c.get("/api/roles/F1/outputs", params={"agent": "claude", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["formula_id"] == "F1"
    assert data["count"] == 1
    row = data["outputs"][0]
    assert row["session_id"] == "ses-test-1"
    assert row["status"] == "ok"
    assert row["schema_ok"] is True
