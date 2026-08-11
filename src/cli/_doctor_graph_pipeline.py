"""Graph pipeline health — is the index current and the backend answering.

Freshness, parse errors, the backend probe, the cos_graph_doctor verdict, and
cascade overflow all report on the indexing pipeline as it runs; the checks that
inspect what the pipeline *stored* live next door. Their thresholds move with
the pipeline, so they live with it.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cli.doctor import DoctorReport


logger = logging.getLogger("coding_os.doctor.graph")

FRESHNESS_SECONDS = 86400  # 24h — dev workflow doesn't reindex hourly; nightly cron + on-edit auto-reindex keep it fresh
PARSE_ERROR_RATE_LIMIT = 0.05
CASCADE_OVERFLOW_LIMIT = 10


def _backend_probe_path(state_dir: Path) -> Path:
    return state_dir / ".graph-backend.json"


def _read_backend_probe(state_dir: Path) -> dict[str, Any]:
    path = _backend_probe_path(state_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("backend probe unreadable: %s", exc)
        return {}


def _graph_last_index_seconds(conn: sqlite3.Connection | None) -> int | None:
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT MAX(updated_at) FROM graph_nodes").fetchone()
    except sqlite3.OperationalError as exc:
        logger.debug("graph_nodes not available: %s", exc)
        return None
    if row is None or row[0] is None:
        return None
    return int(time.time()) - int(row[0])


def add_check_freshness(report: DoctorReport, conn: sqlite3.Connection | None) -> None:
    """docs.agents_md_present — graph freshness."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    age = _graph_last_index_seconds(conn)
    if age is None:
        report.checks.append(
            CheckResult(
                "graph.freshness",
                SEV_WARN,
                "graph_nodes is empty — run `cos graph-reindex`",
            )
        )
        return
    if age > FRESHNESS_SECONDS:
        report.checks.append(
            CheckResult(
                "graph.freshness",
                SEV_WARN,
                f"graph index is stale: {age}s > {FRESHNESS_SECONDS}s",
                {"age_seconds": age, "threshold": FRESHNESS_SECONDS},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.freshness",
            SEV_PASS,
            f"graph index fresh ({age}s old)",
            {"age_seconds": age},
        )
    )


def add_check_parse_error_rate(report: DoctorReport, state_dir: Path) -> None:
    """graph.freshness — parse error rate on the last auto-reindex log."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    log_path = state_dir / ".reindex-errors.log"
    total = errors = 0
    if log_path.exists():
        try:
            with log_path.open(encoding="utf-8") as fh:
                for line in fh:
                    total += 1
                    if "ERROR" in line or "error" in line:
                        errors += 1
        except OSError as exc:
            logger.debug("reindex-errors.log unreadable: %s", exc)
    if total == 0:
        total = 1
    rate = errors / total
    if rate > PARSE_ERROR_RATE_LIMIT:
        report.checks.append(
            CheckResult(
                "graph.parse_error_rate",
                SEV_WARN,
                f"parse error rate {rate:.1%} > {PARSE_ERROR_RATE_LIMIT:.1%}",
                {"rate": rate, "errors": errors, "total": total},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.parse_error_rate",
            SEV_PASS,
            f"parse error rate {rate:.1%}",
            {"rate": rate, "errors": errors, "total": total},
        )
    )


def add_check_backend_responsive(report: DoctorReport, state_dir: Path) -> None:
    """graph.parse_error_rate — graph backend reachable."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    probe = _read_backend_probe(state_dir)
    if not probe:
        report.checks.append(
            CheckResult(
                "graph.backend_responsive",
                SEV_WARN,
                "no backend probe yet — run any `cos graph-*` command once",
            )
        )
        return
    last_ok = probe.get("last_ok_at")
    age = int(time.time()) - int(last_ok) if last_ok else None
    if age is None or age > FRESHNESS_SECONDS:
        report.checks.append(
            CheckResult(
                "graph.backend_responsive",
                SEV_WARN,
                f"backend probe stale (age={age}s) — run: cos graph-reindex",
                probe,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.backend_responsive",
            SEV_PASS,
            f"backend {probe.get('backend', '?')} ok ({age}s ago)",
            probe,
        )
    )


def add_check_cascade_overflow(report: DoctorReport, state_dir: Path) -> None:
    """graph.embedding_dimensions — cascade overflow count in the last 24h."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    log = state_dir / ".graph-cascade-overflow.log"
    if not log.exists():
        report.checks.append(CheckResult("graph.cascade_overflow", SEV_PASS, "no overflow records"))
        return
    cutoff = time.time() - 86400
    count = 0
    try:
        with log.open(encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split("|", 1)
                if len(parts) != 2:
                    continue
                try:
                    ts = float(parts[0])
                except ValueError:
                    continue
                if ts >= cutoff:
                    count += 1
    except OSError as exc:
        logger.debug("cascade overflow log unreadable: %s", exc)
    if count >= CASCADE_OVERFLOW_LIMIT:
        report.checks.append(
            CheckResult(
                "graph.cascade_overflow",
                SEV_WARN,
                f"{count} overflows in 24h (limit {CASCADE_OVERFLOW_LIMIT})",
                {"count": count},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.cascade_overflow",
            SEV_PASS,
            f"{count} overflows in 24h",
            {"count": count},
        )
    )


def add_check_backend_health(report: DoctorReport) -> None:
    """graph.backend_health: the cos_graph_doctor verdict — the same healthy/
    issues view the Hub Backend tab renders. The system doctor is the
    whole-system probe, so backend findings (stale paths, phantoms,
    malformed uids) must surface here too, not only in the Hub (TASK-405)."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    try:
        from graph_os.tools.graph import cos_graph_doctor

        envelope = cos_graph_doctor()
        if isinstance(envelope, str):
            envelope = json.loads(envelope)
        data = envelope.get("data") or {}
        healthy = data.get("healthy")
        stats = data.get("stats") or {}
        informational = set((data.get("meta") or {}).get("informational_categories") or [])
        real_issues = {
            issue.get("category"): issue.get("count")
            for issue in data.get("issues") or []
            if issue.get("category") not in informational
        }
    except Exception as exc:
        report.checks.append(CheckResult("graph.backend_health", SEV_WARN, f"check failed: {exc}"))
        return
    if healthy:
        report.checks.append(
            CheckResult(
                "graph.backend_health",
                SEV_PASS,
                f"backend healthy — {stats.get('node_count', '?')} nodes / "
                f"{stats.get('edge_count', '?')} edges",
            )
        )
        return
    summary = ", ".join(f"{cat}={cnt}" for cat, cnt in real_issues.items()) or "unknown"
    report.checks.append(
        CheckResult(
            "graph.backend_health",
            SEV_WARN,
            f"backend issues: {summary} — run `cos graph-doctor --fix`",
            {"issues": real_issues},
        )
    )
