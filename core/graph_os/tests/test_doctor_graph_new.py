"""C24-C27 doctor checks added in the review pass."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cli.doctor import DoctorReport
from cli.doctor_graph import (
    add_check_c24_kuzu_state,
    add_check_c25_evidence_table,
    add_check_c26_orphan_symbols,
    add_check_c27_legacy_kinds,
)


def _migrated_conn() -> sqlite3.Connection:
    import database as thinking_os_db
    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def _new_report() -> DoctorReport:
    return DoctorReport(project_dir=".", agent="claude", templates=[])


def test_c24_passes_when_kuzu_dir_missing(tmp_path: Path):
    report = _new_report()
    add_check_c24_kuzu_state(report, tmp_path)
    [c] = [c for c in report.checks if c.id == "C24"]
    assert c.severity == "PASS"


def test_c24_warns_when_kuzu_dir_empty(tmp_path: Path):
    kuzu = tmp_path / "graph_os.kuzu"
    kuzu.mkdir()
    (kuzu / "data.kz").write_bytes(b"")
    report = _new_report()
    add_check_c24_kuzu_state(report, tmp_path)
    [c] = [c for c in report.checks if c.id == "C24"]
    assert c.severity == "WARN"


def test_c24_passes_when_kuzu_populated(tmp_path: Path):
    kuzu = tmp_path / "graph_os.kuzu"
    kuzu.mkdir()
    (kuzu / "data.kz").write_bytes(b"x" * 100)
    report = _new_report()
    add_check_c24_kuzu_state(report, tmp_path)
    [c] = [c for c in report.checks if c.id == "C24"]
    assert c.severity == "PASS"


def test_c25_passes_with_migrated_db():
    report = _new_report()
    add_check_c25_evidence_table(report, _migrated_conn())
    [c] = [c for c in report.checks if c.id == "C25"]
    assert c.severity == "PASS"


def test_c25_fails_when_table_missing():
    conn = sqlite3.connect(":memory:")
    report = _new_report()
    add_check_c25_evidence_table(report, conn)
    [c] = [c for c in report.checks if c.id == "C25"]
    assert c.severity == "FAIL"


def test_c26_passes_with_no_symbols():
    conn = _migrated_conn()
    report = _new_report()
    add_check_c26_orphan_symbols(report, conn)
    [c] = [c for c in report.checks if c.id == "C26"]
    assert c.severity == "PASS"


def test_c27_passes_when_kinds_canonical():
    conn = _migrated_conn()
    report = _new_report()
    add_check_c27_legacy_kinds(report, conn)
    [c] = [c for c in report.checks if c.id == "C27"]
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
    add_check_c27_legacy_kinds(report, conn)
    [c] = [c for c in report.checks if c.id == "C27"]
    assert c.severity == "WARN"
