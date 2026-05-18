"""Doctor checks: graph.evidence_table, graph.orphan_symbols, graph.legacy_kinds.

Kuzu state checks retired 2026-05-18 together with the Kuzu backend
(see commit removing src/core/graph_os/backends/kuzu_backend.py).
"""
from __future__ import annotations

import sqlite3

import pytest

from cli.doctor import DoctorReport
from cli.doctor_graph import (
    add_check_evidence_table,
    add_check_orphan_symbols,
    add_check_legacy_kinds,
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
