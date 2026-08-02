"""Tests for the dispatch budget gate + cost analytics over formula_dispatches.

Covers the daily-cap gate (incl. the date(ts) fix), the utilization-ladder
gauge, and the median+MAD cost-anomaly + burn-rate analytics.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import budget  # noqa: E402
from database import init_db  # noqa: E402


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "coding-os.db"
    conn = init_db(path)
    yield path, conn
    conn.close()


def _dispatch(
    conn: sqlite3.Connection, session_id: str, cost_usd: float, *, ts_expr: str = "datetime('now')"
) -> None:
    conn.execute(
        "INSERT INTO formula_dispatches "
        "(session_id, task_marker, persona_id, formula_id, input_hash, status, ts, cost_usd) "
        f"VALUES (?, 't', 'p', 'f', 'h', 'ok', {ts_expr}, ?)",
        (session_id, cost_usd),
    )


class TestUtilizationLadder:
    @pytest.mark.parametrize(
        "spent,cap,level",
        [
            (0.0, 10.0, "ok"),
            (4.9, 10.0, "ok"),
            (5.0, 10.0, "info"),
            (7.5, 10.0, "warning"),
            (9.0, 10.0, "critical"),
            (10.0, 10.0, "hard_stop"),
            (12.0, 10.0, "hard_stop"),
            (5.0, None, "ok"),
        ],
    )
    def test_ladder_thresholds(self, spent: float, cap: float | None, level: str) -> None:
        assert budget._budget_utilization_level(spent, cap) == level


class TestSpentTodayTsFix:
    def test_spent_today_reads_ts_column(self, db, monkeypatch) -> None:
        path, conn = db
        _dispatch(conn, "ses-a", 1.50)  # ts defaults to now
        conn.commit()
        # the bug: a date(created_at) query returns 0 because the column is `ts`.
        monkeypatch.setenv("COS_DAILY_BUDGET_USD", "100")
        gate = budget.check(path)
        assert gate.spent_usd == pytest.approx(1.50)
        assert gate.level == "ok"


class TestCostAnomaly:
    def test_flags_a_lone_spike(self, db) -> None:
        path, conn = db
        for i in range(5):
            _dispatch(conn, f"ses-low-{i}", 0.10)
        _dispatch(conn, "ses-spike", 5.00)
        conn.commit()
        result = budget.cost_anomaly(path)
        assert not result["ok"]
        ids = [o["session_id"] for o in result["outliers"]]
        assert "ses-spike" in ids
        assert all("low" not in i for i in ids)

    def test_n_below_three_guard(self, db) -> None:
        path, conn = db
        _dispatch(conn, "ses-1", 0.10)
        _dispatch(conn, "ses-2", 9.99)
        conn.commit()
        result = budget.cost_anomaly(path)
        assert result["ok"] and result["outliers"] == [] and result["reason"] == "n<3"

    def test_uniform_costs_have_no_outlier(self, db) -> None:
        path, conn = db
        for i in range(5):
            _dispatch(conn, f"ses-{i}", 0.42)
        conn.commit()
        result = budget.cost_anomaly(path)
        assert result["ok"] and result["outliers"] == []

    def test_missing_db_fails_open(self, tmp_path: Path) -> None:
        result = budget.cost_anomaly(tmp_path / "nope.db")
        assert result["ok"] and result["outliers"] == []


class TestCostBurnRate:
    def test_accelerating_latest_day(self, db) -> None:
        path, conn = db
        for d in range(3, 6):  # prior days: low spend
            _dispatch(conn, f"ses-prior-{d}", 0.20, ts_expr=f"datetime('now', '-{d} days')")
        _dispatch(conn, "ses-today", 5.00)  # today: spike
        conn.commit()
        result = budget.cost_burn_rate(path)
        assert result["days"] >= 2
        assert result["accelerating"] is True
        assert result["delta_pct"] > 0
        assert result["partial_today"] is True

    def test_insufficient_history(self, db) -> None:
        path, conn = db
        _dispatch(conn, "ses-only", 1.0)
        conn.commit()
        result = budget.cost_burn_rate(path)
        assert result["days"] < 2 and result["reason"] == "insufficient"


class TestEstimateDispatchCost:
    def test_no_history_estimates_zero(self, db) -> None:
        path, _ = db
        assert budget.estimate_dispatch_cost(path, 3) == 0.0

    def test_median_times_count(self, db) -> None:
        path, conn = db
        for cost in (0.10, 0.20, 0.30):
            _dispatch(conn, "ses", cost)
        conn.commit()
        assert budget.estimate_dispatch_cost(path, 3) == pytest.approx(0.60)

    def test_median_resists_a_lone_outlier(self, db) -> None:
        path, conn = db
        for i in range(5):
            _dispatch(conn, f"ses-{i}", 0.10)
        _dispatch(conn, "ses-spike", 50.0)  # a mean would read ~8.4 per dispatch
        conn.commit()
        assert budget.estimate_dispatch_cost(path, 2) == pytest.approx(0.20)

    def test_non_positive_count_is_zero(self, db) -> None:
        path, conn = db
        _dispatch(conn, "ses", 1.0)
        conn.commit()
        assert budget.estimate_dispatch_cost(path, 0) == 0.0
        assert budget.estimate_dispatch_cost(path, -2) == 0.0

    def test_missing_db_fails_open(self, tmp_path: Path) -> None:
        assert budget.estimate_dispatch_cost(tmp_path / "nope.db", 5) == 0.0

    def test_null_and_zero_costs_are_ignored(self, db) -> None:
        path, conn = db
        _dispatch(conn, "ses-null", None)
        _dispatch(conn, "ses-zero", 0.0)
        _dispatch(conn, "ses-real", 0.40)
        conn.commit()
        assert budget.estimate_dispatch_cost(path, 1) == pytest.approx(0.40)

    def test_only_uncosted_rows_fails_open(self, db) -> None:
        path, conn = db
        _dispatch(conn, "ses-null", None)
        conn.commit()
        assert budget.estimate_dispatch_cost(path, 4) == 0.0

    def test_sample_is_bounded_to_the_recent_window(self, db) -> None:
        path, conn = db
        for i in range(budget.ESTIMATE_WINDOW + 5):
            _dispatch(conn, f"ses-old-{i}", 1.0)
        for i in range(budget.ESTIMATE_WINDOW):
            _dispatch(conn, f"ses-new-{i}", 0.10)
        conn.commit()
        # over the whole table the median would be 1.0; the window sees only the new rows
        assert budget.estimate_dispatch_cost(path, 1) == pytest.approx(0.10)


class TestProjectedGate:
    def test_daily_gate_blocks_on_projection_not_spend(self, db, monkeypatch) -> None:
        path, conn = db
        _dispatch(conn, "ses", 0.80)
        conn.commit()
        monkeypatch.setenv("COS_DAILY_BUDGET_USD", "1.0")
        assert budget.check(path).allowed  # spend alone still has headroom
        gate = budget.check(path, additional_estimate_usd=0.40)
        assert not gate.allowed
        assert "projected" in gate.reason and gate.level == "hard_stop"

    def test_estimate_within_headroom_still_allows(self, db, monkeypatch) -> None:
        path, conn = db
        _dispatch(conn, "ses", 0.20)
        conn.commit()
        monkeypatch.setenv("COS_DAILY_BUDGET_USD", "1.0")
        gate = budget.check(path, additional_estimate_usd=0.10)
        assert gate.allowed and gate.spent_usd == pytest.approx(0.20)

    def test_no_cap_ignores_the_estimate(self, db, monkeypatch, tmp_path: Path) -> None:
        path, conn = db
        _dispatch(conn, "ses", 5.0)
        conn.commit()
        monkeypatch.delenv("COS_DAILY_BUDGET_USD", raising=False)
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))  # no hub-settings fallback
        assert budget.check(path, additional_estimate_usd=999.0).allowed

    def test_chain_gate_blocks_on_projection(self, db, monkeypatch) -> None:
        path, conn = db
        _dispatch(conn, "ses", 0.80)  # helper writes task_marker 't'
        conn.commit()
        monkeypatch.setenv("COS_CHAIN_BUDGET_USD", "1.0")
        assert budget.chain_check(path, "t").allowed
        gate = budget.chain_check(path, "t", additional_estimate_usd=0.40)
        assert not gate.allowed and "projected" in gate.reason
