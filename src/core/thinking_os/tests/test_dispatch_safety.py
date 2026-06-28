"""TASK-639 dispatch safety: per-chain budget ceiling, EvidenceBundle flock, max_turns hop-cap."""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import budget  # noqa: E402
from database import init_db  # noqa: E402
from dispatcher import DispatchRequest  # noqa: E402
from tools import cognition  # noqa: E402


def _dispatch(conn: sqlite3.Connection, task_marker: str, cost: float) -> None:
    conn.execute(
        "INSERT INTO formula_dispatches "
        "(session_id, task_marker, persona_id, formula_id, input_hash, status, ts, cost_usd) "
        "VALUES ('s', ?, 'p', 'f', 'h', 'ok', datetime('now'), ?)",
        (task_marker, cost),
    )


@pytest.fixture
def db(tmp_path: Path):
    p = tmp_path / "coding-os.db"
    conn = init_db(p)
    yield p, conn
    conn.close()


class TestChainBudget:
    def test_unset_allows_even_huge_spend(self, db, monkeypatch) -> None:
        path, conn = db
        monkeypatch.delenv("COS_CHAIN_BUDGET_USD", raising=False)
        _dispatch(conn, "TASK-1", 999.0)
        conn.commit()
        assert budget.chain_check(path, "TASK-1").allowed

    def test_sums_only_the_given_chain(self, db, monkeypatch) -> None:
        path, conn = db
        monkeypatch.setenv("COS_CHAIN_BUDGET_USD", "1.0")
        _dispatch(conn, "TASK-1", 0.6)
        _dispatch(conn, "TASK-1", 0.6)
        _dispatch(conn, "TASK-2", 50.0)  # a different chain must not count
        conn.commit()
        gate = budget.chain_check(path, "TASK-1")
        assert not gate.allowed and "TASK-1" in gate.reason
        assert budget.chain_check(path, "TASK-3").allowed  # untouched chain

    def test_under_cap_allows(self, db, monkeypatch) -> None:
        path, conn = db
        monkeypatch.setenv("COS_CHAIN_BUDGET_USD", "10.0")
        _dispatch(conn, "TASK-1", 2.0)
        conn.commit()
        gate = budget.chain_check(path, "TASK-1")
        assert gate.allowed and gate.spent_usd == pytest.approx(2.0)


class TestDispatchRequestMaxTurns:
    def test_field_defaults_none_and_accepts_value(self) -> None:
        r = DispatchRequest(formula_id="implementer", agent_file="/x.md", prompt="p")
        assert r.max_turns is None
        r2 = DispatchRequest(formula_id="implementer", agent_file="/x.md", prompt="p", max_turns=7)
        assert r2.max_turns == 7


class TestEvidenceBundleFlock:
    def test_concurrent_writes_stay_valid_json(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(cognition, "_bundle_path", lambda sid: tmp_path / f"b_{sid}.json")

        class _Bundle:
            def __init__(self, size: int) -> None:
                self._size = size

            def model_dump_json(self, indent: int = 2) -> str:
                return json.dumps({"pad": "x" * self._size})

        errors: list[Exception] = []

        def writer(size: int) -> None:
            try:
                for _ in range(25):
                    cognition._save_bundle("ses-1", _Bundle(size))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(s,)) for s in (200, 4000, 200, 4000)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        # flock guarantees every reader sees a complete, parseable bundle.
        data = json.loads((tmp_path / "b_ses-1.json").read_text())
        assert "pad" in data
