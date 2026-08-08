"""Dedicated pytest coverage for /api/cognition trace endpoints."""

from __future__ import annotations

import json
import sys
import time
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
    # An ambient COS_DB_PATH would route cost/health at the real project DB
    # (fresh dispatch rows there flip the fail-open assertions).
    monkeypatch.delenv("COS_DB_PATH", raising=False)
    app = create_app()
    with TestClient(app) as c:
        yield c, state


def test_initial_trace_pos_bounds_replay(tmp_path):
    from core.web.routes.cognition import _initial_trace_pos

    log = tmp_path / "big.jsonl"
    # Many small lines well past the 256 KB window.
    lines = [json.dumps({"i": i, "pad": "x" * 200}) for i in range(4000)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    size = log.stat().st_size
    assert size > 256 * 1024  # sanity: the file exceeds the window

    pos = _initial_trace_pos(log)
    assert 0 < pos < size  # bounded: starts inside the tail, not at 0
    # The offset lands on a line boundary — the remaining tail parses cleanly.
    tail = log.read_bytes()[pos:].decode("utf-8")
    for line in tail.splitlines():
        json.loads(line)  # no partial leading line


def test_initial_trace_pos_small_file_starts_at_zero(tmp_path):
    from core.web.routes.cognition import _initial_trace_pos

    log = tmp_path / "small.jsonl"
    log.write_text('{"a": 1}\n', encoding="utf-8")
    assert _initial_trace_pos(log) == 0
    assert _initial_trace_pos(tmp_path / "missing.jsonl") == 0  # OSError → 0


def test_cognition_traces_lists_jsonl_sessions(client):
    c, state = client
    (state / "claude" / "traces" / "ses-a.jsonl").write_text("{}", encoding="utf-8")
    (state / "claude" / "sessions").mkdir(parents=True, exist_ok=True)
    (state / "claude" / "sessions" / "ses-claude-20260425-111111-aaaa.json").write_text(
        json.dumps(
            {"agent": "claude", "session_id": "ses-claude-20260425-111111-aaaa", "started_at": 1}
        ),
        encoding="utf-8",
    )

    resp = c.get("/api/cognition/traces")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 2
    assert data["trace_count"] == 1
    assert data["session_count"] == 1
    session_ids = {row["session_id"] for row in data["sessions"]}
    assert "ses-a" in session_ids
    assert "ses-claude-20260425-111111-aaaa" in session_ids


def test_cognition_traces_marks_session_only_without_trace(client):
    c, state = client
    (state / "claude" / "sessions").mkdir(parents=True, exist_ok=True)
    sid = "ses-claude-20260425-222222-bbbb"
    (state / "claude" / "sessions" / f"{sid}.json").write_text(
        json.dumps({"agent": "claude", "session_id": sid, "started_at": 2, "last_tool_at": 3}),
        encoding="utf-8",
    )

    resp = c.get("/api/cognition/traces")
    assert resp.status_code == 200
    rows = resp.json()["data"]["sessions"]
    row = next(r for r in rows if r["session_id"] == sid)
    assert row["has_trace"] is False
    assert row["source"] == "session-only"
    assert "display_name" in row


def test_cognition_traces_sorts_active_sessions_first(client):
    c, state = client
    sessions_dir = state / "claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    active_sid = "ses-claude-20260425-333333-cccc"
    idle_sid = "ses-claude-20260425-333334-dddd"
    now = time.time()
    (sessions_dir / f"{active_sid}.json").write_text(
        json.dumps(
            {
                "agent": "claude",
                "session_id": active_sid,
                "started_at": now - 30,
                "last_prompt_at": now - 20,
                "last_tool_at": now - 10,
                "last_stop_at": now - 40,
                "ended_at": None,
            }
        ),
        encoding="utf-8",
    )
    (sessions_dir / f"{idle_sid}.json").write_text(
        json.dumps(
            {
                "agent": "claude",
                "session_id": idle_sid,
                "started_at": now - 7200,
                "last_prompt_at": now - 7200,
                "last_tool_at": now - 7200,
                "last_stop_at": now - 7100,
                "ended_at": None,
            }
        ),
        encoding="utf-8",
    )

    resp = c.get("/api/cognition/traces")
    assert resp.status_code == 200
    rows = [r for r in resp.json()["data"]["sessions"] if r["session_id"] in {active_sid, idle_sid}]
    assert len(rows) == 2
    assert rows[0]["session_id"] == active_sid
    assert rows[0]["is_active"] is True
    assert rows[1]["is_active"] is False


def test_cognition_trace_parses_jsonl_lines(client):
    c, state = client
    trace = state / "claude" / "traces" / "ses-b.jsonl"
    trace.write_text(
        "\n".join(
            [
                json.dumps({"kind": "analyze_done", "ts": 1}),
                "not-json-line",
                json.dumps({"kind": "compose_done", "ts": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = c.get("/api/cognition/trace/ses-b", params={"agent": "claude"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == "ses-b"
    assert data["count"] == 3
    assert data["events"][0]["kind"] == "analyze_done"
    assert data["events"][1]["raw"] == "not-json-line"


def test_cognition_trace_returns_404_for_unknown_session(client):
    c, _ = client
    resp = c.get("/api/cognition/trace/missing-session")
    assert resp.status_code == 404


def test_cognition_traces_envelope_contract(client):
    """Web envelope contract — unwrap() translates the MCP ok envelope to
    HTTP 200 + {data, meta}; a failure becomes a 4xx/5xx + {error}.
    The raw `ok` boolean is intentionally NOT echoed in the HTTP body."""
    c, _ = client
    resp = c.get("/api/cognition/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body


def test_cognition_traces_sorted_newest_first(client):
    c, state = client
    old_file = state / "claude" / "traces" / "ses-old.jsonl"
    new_file = state / "claude" / "traces" / "ses-new.jsonl"
    old_file.write_text("{}", encoding="utf-8")
    new_file.write_text("{}", encoding="utf-8")
    now = time.time()
    old_ts = now - 3600
    new_ts = now - 10
    old_file.touch()
    new_file.touch()
    # force deterministic mtimes independent of filesystem ordering
    old_file.chmod(0o644)
    new_file.chmod(0o644)
    import os

    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    resp = c.get("/api/cognition/traces")
    assert resp.status_code == 200
    sessions = resp.json()["data"]["sessions"]
    ids = [s["session_id"] for s in sessions]
    assert ids.index("ses-new") < ids.index("ses-old")


# ---------------------------------------------------------------------------
# Chat priming from the onboarding intake — TASK-364
# ---------------------------------------------------------------------------


class TestChatPriming:
    def _module(self):
        import importlib

        return importlib.import_module("core.web.routes.cognition")

    def test_intake_appended_to_system_prompt(self, tmp_path):
        cog = self._module()
        meta = tmp_path / "docs" / "_meta"
        meta.mkdir(parents=True)
        (meta / "project-description.md").write_text(
            "# Project Description (onboarding intake)\n\nInvoice automation for agencies.\n",
            encoding="utf-8",
        )
        base = {"type": "preset", "preset": "claude_code", "append": "BASE"}
        primed = cog._prime_with_project_description(base, str(tmp_path))
        assert primed["append"].startswith("BASE")
        assert "Project context (onboarding intake)" in primed["append"]
        assert "Invoice automation for agencies." in primed["append"]
        assert base["append"] == "BASE"  # input not mutated

    def test_missing_intake_leaves_prompt_untouched(self, tmp_path):
        cog = self._module()
        base = {"type": "preset", "preset": "claude_code", "append": "BASE"}
        assert cog._prime_with_project_description(base, str(tmp_path)) is base

    def test_intake_is_bounded(self, tmp_path):
        cog = self._module()
        meta = tmp_path / "docs" / "_meta"
        meta.mkdir(parents=True)
        (meta / "project-description.md").write_text("x" * 10_000, encoding="utf-8")
        primed = cog._prime_with_project_description(
            {"type": "preset", "preset": "claude_code", "append": "BASE"}, str(tmp_path)
        )
        assert len(primed["append"]) < 2_200  # 2000-char intake cap + framing


def test_cost_health_fails_open_without_db(client):
    c, _ = client
    resp = c.get("/api/cognition/cost/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) >= {"anomaly", "burn", "budget", "overall_ok"}
    assert data["overall_ok"] is True
    assert data["budget"]["level"] == "ok"


def test_cost_health_flags_outlier_with_db(client):
    from thinking_os.database import init_db, resolve_db_path
    from web._project_context import current_project_root

    c, _ = client
    dbp = resolve_db_path(current_project_root())
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(dbp)
    for i in range(5):
        conn.execute(
            "INSERT INTO formula_dispatches "
            "(session_id,task_marker,persona_id,formula_id,input_hash,status,ts,cost_usd) "
            "VALUES (?,?,?,?,?,?,datetime('now'),?)",
            (f"s{i}", "t", "p", "f", "h", "ok", 0.1),
        )
    conn.execute(
        "INSERT INTO formula_dispatches "
        "(session_id,task_marker,persona_id,formula_id,input_hash,status,ts,cost_usd) "
        "VALUES (?,?,?,?,?,?,datetime('now'),?)",
        ("spike", "t", "p", "f", "h", "ok", 9.0),
    )
    conn.commit()
    conn.close()
    resp = c.get("/api/cognition/cost/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["anomaly"]["ok"] is False
    assert any(o["session_id"] == "spike" for o in data["anomaly"]["outliers"])
    assert data["overall_ok"] is False
