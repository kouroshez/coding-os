"""graph_os doctor checks.

Implements the graph-category checks (plan §18.3 / §19 I.14):

  graph.freshness                graph index freshness   < 3600 s old
  graph.parse_error_rate         parse error rate        < 5 %
  graph.backend_responsive       graph backend reachable
  graph.groups_configured        group manifests healthy (all members resolvable)
  graph.embedding_migration      embedding migration status (BGE-M3 progress)
  graph.embedding_dimensions     embedding dim distribution (no split > 7 days)
  graph.cascade_overflow         cascade overflow count  < 10 per 24 h
  graph.evidence_table           graph_evidence_v12 table present
  graph.orphan_symbols           orphan symbols within budget
  graph.legacy_kinds             pre-v16 colon-prefixed kinds cleaned

Callable from src/cli/doctor.py::run_doctor so the existing `cos doctor`
CLI picks everything up — no new command.

The individual checks live in three leaves — pipeline liveness, storage
integrity, and embeddings — and are re-exported here, so this module keeps the
run order in one readable place and every existing import keeps resolving.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from cli._doctor_graph_embeddings import (
    add_check_embedding_dimensions as add_check_embedding_dimensions,
    add_check_embedding_migration as add_check_embedding_migration,
)
from cli._doctor_graph_pipeline import (
    CASCADE_OVERFLOW_LIMIT as CASCADE_OVERFLOW_LIMIT,
    FRESHNESS_SECONDS as FRESHNESS_SECONDS,
    PARSE_ERROR_RATE_LIMIT as PARSE_ERROR_RATE_LIMIT,
    _backend_probe_path as _backend_probe_path,
    _graph_last_index_seconds as _graph_last_index_seconds,
    _read_backend_probe as _read_backend_probe,
    add_check_backend_health as add_check_backend_health,
    add_check_backend_responsive as add_check_backend_responsive,
    add_check_cascade_overflow as add_check_cascade_overflow,
    add_check_freshness as add_check_freshness,
    add_check_parse_error_rate as add_check_parse_error_rate,
)
from cli._doctor_graph_storage import (
    add_check_evidence_table as add_check_evidence_table,
    add_check_legacy_kinds as add_check_legacy_kinds,
    add_check_orphan_symbols as add_check_orphan_symbols,
)

if TYPE_CHECKING:
    from cli.doctor import DoctorReport


logger = logging.getLogger("coding_os.doctor.graph")


def add_check_groups_configured(report: DoctorReport) -> None:
    """graph.backend_responsive — group manifests healthy."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    groups_root = Path.home() / ".coding-os" / "groups"
    if not groups_root.exists():
        report.checks.append(
            CheckResult("graph.groups_configured", SEV_PASS, "no groups configured")
        )
        return
    missing: list[str] = []
    healthy_count = 0
    for folder in groups_root.iterdir():
        manifest = folder / "group.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("group manifest unreadable: %s", exc)
            missing.append(folder.name)
            continue
        for member in data.get("members", []):
            path = member.get("path")
            if not path or not Path(path).exists():
                missing.append(f"{data.get('name')}:{member.get('alias')}")
        healthy_count += 1
    if missing:
        report.checks.append(
            CheckResult(
                "graph.groups_configured",
                SEV_WARN,
                f"group members missing on disk: {', '.join(missing[:5])}"
                + ("..." if len(missing) > 5 else ""),
                {"missing": missing, "healthy": healthy_count},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.groups_configured",
            SEV_PASS,
            f"{healthy_count} group(s) healthy",
            {"healthy": healthy_count},
        )
    )


def run_graph_checks(
    report: DoctorReport,
    state_dir: Path,
    conn: sqlite3.Connection | None,
) -> None:
    """Run docs.agents_md_present-graph.legacy_kinds. Called from src/cli/doctor.py::run_doctor."""
    add_check_freshness(report, conn)
    add_check_parse_error_rate(report, state_dir)
    add_check_backend_responsive(report, state_dir)
    add_check_backend_health(report)
    add_check_groups_configured(report)
    add_check_embedding_migration(report, state_dir)
    add_check_embedding_dimensions(report, conn, state_dir)
    add_check_cascade_overflow(report, state_dir)
    add_check_evidence_table(report, conn)
    add_check_orphan_symbols(report, conn)
    add_check_legacy_kinds(report, conn)


__all__ = ["run_graph_checks"]
