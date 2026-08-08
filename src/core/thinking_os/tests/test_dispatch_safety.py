"""TASK-639 dispatch safety: per-chain budget ceiling, EvidenceBundle flock, max_turns hop-cap."""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import budget
from database import init_db
from dispatcher import DispatchRequest
from tools import cognition


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


class _FakeMcp:
    def __init__(self) -> None:
        self._tools: dict = {}

    def tool(self, name: str = "", description: str = "", annotations: dict | None = None):
        def decorator(fn):
            self._tools[name or fn.__name__] = fn
            return fn

        return decorator

    def call(self, name: str, **kwargs) -> dict:
        return json.loads(self._tools[name](**kwargs))


class TestParallelFanOutBudget:
    """One gate authorizes N spawns, so it must project the fan-out (TASK-853)."""

    @staticmethod
    def _tools(db_path: Path) -> _FakeMcp:
        fake = _FakeMcp()
        cognition.register_all(fake, str(db_path))
        return fake

    @staticmethod
    def _row_count(conn: sqlite3.Connection) -> int:
        return conn.execute("SELECT COUNT(*) FROM formula_dispatches").fetchone()[0]

    def test_blocks_the_fan_out_before_any_spawn(self, db, monkeypatch) -> None:
        path, conn = db
        _dispatch(conn, "TASK-1", 0.80)
        conn.commit()
        monkeypatch.setenv("COS_DAILY_BUDGET_USD", "1.0")  # $0.20 headroom
        before = self._row_count(conn)

        result = self._tools(path).call(
            "cos_dispatch_parallel_run",
            formula_ids=["reviewer", "security_auditor", "analyst"],
            session_id="ses-x",
            task_marker="TASK-1",
            persona_id="p",
        )

        assert result["ok"] is False
        assert result["error"]["category"] == "budget"
        assert "projected" in result["error"]["message"]
        assert self._row_count(conn) == before  # nothing was dispatched

    def test_single_role_gate_stays_spend_only(self, db, monkeypatch) -> None:
        path, conn = db
        _dispatch(conn, "TASK-1", 0.80)
        conn.commit()
        monkeypatch.setenv("COS_DAILY_BUDGET_USD", "1.0")
        # the same headroom that stops a 3-way fan-out must not stop one dispatch
        assert budget.check(path).allowed

    def test_no_history_does_not_block_the_fan_out(self, db, monkeypatch) -> None:
        path, conn = db
        conn.execute(
            "INSERT INTO formula_dispatches "
            "(session_id, task_marker, persona_id, formula_id, input_hash, status, ts, cost_usd) "
            "VALUES ('s', 'TASK-1', 'p', 'f', 'h', 'ok', datetime('now'), NULL)"
        )
        conn.commit()
        monkeypatch.setenv("COS_DAILY_BUDGET_USD", "1.0")
        assert budget.estimate_dispatch_cost(path, 3) == 0.0
        assert budget.check(path, additional_estimate_usd=0.0).allowed


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


class TestCostRoutedDispatch:
    def test_reviewer_downgrades_to_cheaper_tier_when_flagged(self, monkeypatch) -> None:
        monkeypatch.setenv("COS_ROUTER_REVIEWER_CHEAPER", "1")
        # explicit generator tier 'opus' on a review role -> one tier cheaper
        assert (
            cognition._resolve_dispatch_model("reviewer", "s", {}, "opus", "COMPLICATED", None)
            == "sonnet"
        )
        # a non-review role keeps the generator tier
        assert (
            cognition._resolve_dispatch_model("implementer", "s", {}, "opus", "COMPLICATED", None)
            == "opus"
        )

    def test_no_downgrade_when_flag_off(self, monkeypatch) -> None:
        monkeypatch.delenv("COS_ROUTER_REVIEWER_CHEAPER", raising=False)
        assert (
            cognition._resolve_dispatch_model("reviewer", "s", {}, "opus", "COMPLICATED", None)
            == "opus"
        )
