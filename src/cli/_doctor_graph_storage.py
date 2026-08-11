"""Storage integrity — is what the graph holds well-formed.

The required evidence table, the orphan-symbol ratio, and legacy colon-prefixed
kinds all interrogate stored rows against the schema contract, so they move with
the schema and its normalizers rather than with the indexing pipeline.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.doctor import DoctorReport


logger = logging.getLogger("coding_os.doctor.graph")


def add_check_evidence_table(report: DoctorReport, conn: sqlite3.Connection | None) -> None:
    """graph.evidence_table: graph_evidence_v12 table is required by sqlite_backend's
    schema verifier; without it the backend constructor raises and
    every cos_graph_* tool returns `unavailable`."""
    from cli.doctor import SEV_FAIL, SEV_PASS, SEV_WARN, CheckResult

    if conn is None:
        report.checks.append(
            CheckResult(
                "graph.evidence_table",
                SEV_WARN,
                "no graph DB connection — skipped",
            )
        )
        return
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_evidence_v12'"
        ).fetchone()
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "graph.evidence_table",
                SEV_FAIL,
                f"check failed: {exc}",
            )
        )
        return
    if row is None:
        report.checks.append(
            CheckResult(
                "graph.evidence_table",
                SEV_FAIL,
                "graph_evidence_v12 missing — run init_db",
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.evidence_table",
            SEV_PASS,
            "graph_evidence_v12 present",
        )
    )


def add_check_orphan_symbols(report: DoctorReport, conn: sqlite3.Connection | None) -> None:
    """graph.orphan_symbols: count code symbols with no contains-parent. Warn when the
    ratio crosses 5 % so the orphan rate doesn't silently regress."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    if conn is None:
        report.checks.append(
            CheckResult(
                "graph.orphan_symbols",
                SEV_WARN,
                "no graph DB connection — skipped",
            )
        )
        return
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE kind IN ('class','method','function')"
        ).fetchone()[0]
        orphans = conn.execute(
            """
            SELECT COUNT(*) FROM graph_nodes m
            WHERE m.kind IN ('class','method','function')
              AND NOT EXISTS (
                SELECT 1 FROM graph_edges_v12 e
                JOIN graph_nodes p ON p.id = e.source_id
                WHERE e.target_id = m.id
                  AND e.edge_type = 'contains'
                  AND p.kind IN ('file','module','class','method')
              )
            """
        ).fetchone()[0]
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "graph.orphan_symbols",
                SEV_WARN,
                f"check failed: {exc}",
            )
        )
        return
    rate = (orphans / total) if total else 0.0
    detail = {"orphans": orphans, "total": total, "rate": round(rate, 4)}
    if total == 0:
        report.checks.append(
            CheckResult("graph.orphan_symbols", SEV_PASS, "no symbols indexed yet", detail)
        )
        return
    if rate > 0.05:
        report.checks.append(
            CheckResult(
                "graph.orphan_symbols",
                SEV_WARN,
                f"{orphans}/{total} ({rate:.1%}) symbols are orphans",
                detail,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.orphan_symbols",
            SEV_PASS,
            f"{orphans}/{total} ({rate:.1%}) orphans — within budget",
            detail,
        )
    )


def add_check_legacy_kinds(report: DoctorReport, conn: sqlite3.Connection | None) -> None:
    """graph.legacy_kinds: every stored kind should be a canonical NodeKind short
    form. Legacy colon-prefixed kinds (`code:function`, `doc:heading`)
    indicate the storage-time normalizer is bypassed somewhere."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    if conn is None:
        report.checks.append(
            CheckResult(
                "graph.legacy_kinds",
                SEV_WARN,
                "no graph DB connection — skipped",
            )
        )
        return
    try:
        bad = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes "
            "WHERE kind LIKE 'code:%' OR kind LIKE 'doc:%' "
            "OR kind LIKE 'cos:%' OR kind LIKE 'task:%'"
        ).fetchone()[0]
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "graph.legacy_kinds",
                SEV_WARN,
                f"check failed: {exc}",
            )
        )
        return
    if bad > 0:
        report.checks.append(
            CheckResult(
                "graph.legacy_kinds",
                SEV_WARN,
                f"{bad} nodes carry legacy colon-prefixed kinds — "
                "run `cos graph-reindex --rebuild-kinds`",
                {"count": bad},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.legacy_kinds",
            SEV_PASS,
            "all kinds canonical",
        )
    )
