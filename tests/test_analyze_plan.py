"""Tests for the sql-authoring analyze_plan.py EXPLAIN-plan summarizer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "sql-authoring" / "scripts"))

import analyze_plan as ap  # noqa: E402


def _plan(node: dict) -> list:
    return [{"Plan": node}]


def test_clean_index_scan_has_no_findings() -> None:
    plan = _plan({"Node Type": "Index Scan", "Relation Name": "users",
                  "Plan Rows": 1, "Actual Rows": 1})
    assert ap.analyze(plan, 1000, 10.0) == []


def test_big_seq_scan_flagged() -> None:
    plan = _plan({"Node Type": "Seq Scan", "Relation Name": "events",
                  "Plan Rows": 50000, "Actual Rows": 50000})
    found = ap.analyze(plan, 1000, 10.0)
    assert len(found) == 1 and "seq scan on events" in found[0]


def test_small_seq_scan_ok() -> None:
    plan = _plan({"Node Type": "Seq Scan", "Relation Name": "tiny",
                  "Plan Rows": 5, "Actual Rows": 5})
    assert ap.analyze(plan, 1000, 10.0) == []


def test_estimate_miss_flagged() -> None:
    plan = _plan({"Node Type": "Index Scan", "Relation Name": "orders",
                  "Plan Rows": 10, "Actual Rows": 5000})
    found = ap.analyze(plan, 1000, 10.0)
    assert any("estimate off on orders" in f for f in found)


def test_nested_loop_large_inner_flagged() -> None:
    plan = _plan({
        "Node Type": "Nested Loop",
        "Plans": [
            {"Node Type": "Seq Scan", "Relation Name": "a", "Plan Rows": 1, "Actual Rows": 1},
            {"Node Type": "Index Scan", "Relation Name": "b", "Plan Rows": 9000, "Actual Rows": 9000},
        ],
    })
    found = ap.analyze(plan, 1000, 10.0)
    assert any("nested loop" in f for f in found)


def test_recurses_into_children() -> None:
    plan = _plan({
        "Node Type": "Aggregate", "Plan Rows": 1, "Actual Rows": 1,
        "Plans": [{"Node Type": "Seq Scan", "Relation Name": "deep",
                   "Plan Rows": 20000, "Actual Rows": 20000}],
    })
    assert any("seq scan on deep" in f for f in ap.analyze(plan, 1000, 10.0))


def test_rejects_non_plan() -> None:
    with pytest.raises(ValueError):
        ap.analyze({"not": "a plan"}, 1000, 10.0)
