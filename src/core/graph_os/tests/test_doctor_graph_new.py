"""Doctor checks: graph.evidence_table, graph.orphan_symbols, graph.legacy_kinds.

Kuzu state checks retired 2026-05-18 together with the Kuzu backend
(see commit removing src/core/graph_os/backends/kuzu_backend.py).
"""

from __future__ import annotations

import sqlite3

from cli.doctor import DoctorReport
from cli.doctor_graph import (
    add_check_evidence_table,
    add_check_legacy_kinds,
    add_check_orphan_symbols,
)


def _migrated_conn() -> sqlite3.Connection:
    import database as thinking_os_db

    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def _new_report() -> DoctorReport:
    return DoctorReport(project_dir=".", agent="claude", templates=[])


def test_c25_passes_with_migrated_db():
    report = _new_report()
    add_check_evidence_table(report, _migrated_conn())
    [c] = [c for c in report.checks if c.id == "graph.evidence_table"]
    assert c.severity == "PASS"


def test_c25_fails_when_table_missing():
    conn = sqlite3.connect(":memory:")
    report = _new_report()
    add_check_evidence_table(report, conn)
    [c] = [c for c in report.checks if c.id == "graph.evidence_table"]
    assert c.severity == "FAIL"


def test_c26_passes_with_no_symbols():
    conn = _migrated_conn()
    report = _new_report()
    add_check_orphan_symbols(report, conn)
    [c] = [c for c in report.checks if c.id == "graph.orphan_symbols"]
    assert c.severity == "PASS"


def test_c27_passes_when_kinds_canonical():
    conn = _migrated_conn()
    report = _new_report()
    add_check_legacy_kinds(report, conn)
    [c] = [c for c in report.checks if c.id == "graph.legacy_kinds"]
    assert c.severity == "PASS"


def test_c27_warns_when_legacy_kind_present():
    conn = _migrated_conn()
    now = 0
    conn.execute(
        "INSERT INTO graph_nodes "
        "(kind, label, uid, file_path, metadata_json, created_at, updated_at) "
        "VALUES ('code:function', 'foo', 'code:external:foo', 'foo.py', '{}', ?, ?)",
        (now, now),
    )
    conn.commit()
    report = _new_report()
    add_check_legacy_kinds(report, conn)
    [c] = [c for c in report.checks if c.id == "graph.legacy_kinds"]
    assert c.severity == "WARN"


def test_backend_health_reports_doctor_verdict(monkeypatch):
    # cos doctor must surface the cos_graph_doctor verdict.
    import json as _json

    from cli import doctor_graph as dg

    def _fake_doctor(**_kw):
        return _json.dumps(
            {
                "ok": True,
                "data": {
                    "healthy": False,
                    "stats": {"node_count": 10, "edge_count": 20},
                    "issues": [
                        {"category": "stale_paths", "count": 3},
                        {"category": "slowest_extractions", "count": 10, "severity": "info"},
                    ],
                    "meta": {"informational_categories": ["slowest_extractions"]},
                },
            }
        )

    import graph_os.tools.graph as graph_tools

    monkeypatch.setattr(graph_tools, "cos_graph_doctor", _fake_doctor)
    report = _new_report()
    dg.add_check_backend_health(report)
    [c] = [c for c in report.checks if c.id == "graph.backend_health"]
    assert c.severity == "WARN"
    assert "stale_paths=3" in c.message
    assert "slowest_extractions" not in c.message


def test_backend_health_pass_on_healthy(monkeypatch):
    import json as _json

    import graph_os.tools.graph as graph_tools
    from cli import doctor_graph as dg

    monkeypatch.setattr(
        graph_tools,
        "cos_graph_doctor",
        lambda **_kw: _json.dumps(
            {
                "ok": True,
                "data": {
                    "healthy": True,
                    "stats": {"node_count": 5, "edge_count": 9},
                    "issues": [],
                    "meta": {"informational_categories": []},
                },
            }
        ),
    )
    report = _new_report()
    dg.add_check_backend_health(report)
    [c] = [c for c in report.checks if c.id == "graph.backend_health"]
    assert c.severity == "PASS"
