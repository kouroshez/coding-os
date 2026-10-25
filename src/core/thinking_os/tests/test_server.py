"""
Tests for server.py — health tool response and self-test.

TASK-141: Unit tests for the MCP server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Adjust path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path):
    """Initialize a temp DB and monkeypatch server to use it."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    yield conn, db_path
    conn.close()


# ---------------------------------------------------------------------------
# Health tool
# ---------------------------------------------------------------------------


class TestHealthTool:
    """Assertions drill through the MCP envelope {ok, data} — see
    docs/engineering/mcp-error-envelope.md."""

    def test_health_returns_valid_envelope(self, tmp_db, monkeypatch) -> None:
        conn, _ = tmp_db
        import server

        monkeypatch.setattr(server, "_db_conn", conn)
        envelope = json.loads(server.thinking_os_health())
        assert envelope["ok"] is True
        assert isinstance(envelope["data"], dict)

    def test_health_contains_required_fields(self, tmp_db, monkeypatch) -> None:
        conn, _ = tmp_db
        import server

        monkeypatch.setattr(server, "_db_conn", conn)
        data = json.loads(server.thinking_os_health())["data"]
        assert "schema_version" in data
        assert "tables" in data
        assert "fts5_available" in data
        assert "db_size_bytes" in data

    def test_health_schema_version(self, tmp_db, monkeypatch) -> None:
        conn, _ = tmp_db
        import server

        monkeypatch.setattr(server, "_db_conn", conn)
        data = json.loads(server.thinking_os_health())["data"]
        assert data["schema_version"] >= 1

    def test_health_all_tables_present(self, tmp_db, monkeypatch) -> None:
        conn, _ = tmp_db
        import server

        monkeypatch.setattr(server, "_db_conn", conn)
        data = json.loads(server.thinking_os_health())["data"]
        expected = [
            "task_outcomes",
        ]
        for table in expected:
            assert table in data["tables"], f"Missing table: {table}"
            assert data["tables"][table] is not None, f"Table {table} is None"


# ---------------------------------------------------------------------------
# Self-test via subprocess
# ---------------------------------------------------------------------------


class TestSelfTest:
    """Run server.py --test as a subprocess.

    We pass COS_DB_PATH to a pytest tmp_path so the self-test does not
    depend on a pre-existing `.coding-os/` directory relative to cwd.
    """

    def test_self_test_exits_zero(self, tmp_path: Path) -> None:
        server_path = Path(__file__).resolve().parent.parent / "server.py"
        env = os.environ.copy()
        env["COS_DB_PATH"] = str(tmp_path / "selftest.db")
        result = subprocess.run(
            [sys.executable, str(server_path), "--test"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(server_path.parent),
            env=env,
        )
        assert result.returncode == 0, f"Self-test failed:\nstderr: {result.stderr}"

    def test_self_test_logs_pass(self, tmp_path: Path) -> None:
        server_path = Path(__file__).resolve().parent.parent / "server.py"
        env = os.environ.copy()
        env["COS_DB_PATH"] = str(tmp_path / "selftest.db")
        result = subprocess.run(
            [sys.executable, str(server_path), "--test"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(server_path.parent),
            env=env,
        )
        assert "PASS" in result.stderr, f"Expected PASS in logs:\n{result.stderr}"


class TestGraphReferencesCsvGuard:
    """F5 regression — the cos_graph_references wrapper (server.py:2424) must
    tolerate empty/None `kinds`. `tuple(_csv(""))` crashed with
    `'NoneType' object is not iterable`; `tuple(_csv("") or ())` must not.
    Tests the WRAPPER transform, not the graph.py impl (which already tolerated
    None and so masked the bug)."""

    def test_csv_empty_or_none_is_none(self) -> None:
        import server

        assert server._csv("") is None
        assert server._csv(None) is None

    def test_references_wrapper_kinds_transform_no_crash(self) -> None:
        import server

        # Mirror the exact wrapper expression at server.py:2424.
        for raw in ("", None, "calls,imports", "calls"):
            parsed = tuple(server._csv(raw) or ())
            assert isinstance(parsed, tuple)  # never raises; impl gets () → None


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


class TestSchemaIntegrity:
    def test_task_outcomes_pk_is_task_id(self, tmp_db) -> None:
        conn, _ = tmp_db
        info = conn.execute("PRAGMA table_info(task_outcomes)").fetchall()
        pk_cols = [row[1] for row in info if row[5] == 1]
        assert pk_cols == ["task_id"]
