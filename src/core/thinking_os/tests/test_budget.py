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


def _dispatch(conn: sqlite3.Connection, session_id: str, cost_usd: float, *, ts_expr: str = "datetime('now')") -> None:
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
