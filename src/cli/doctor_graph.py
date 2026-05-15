"""graph_os doctor checks (Phase I.14).

Implements the graph-category checks (plan §18.3 / §19 I.14):

  graph.freshness                graph index freshness   < 3600 s old
  graph.parse_error_rate         parse error rate        < 5 %
  graph.backend_responsive       graph backend reachable
  graph.groups_configured        group manifests healthy (all members resolvable)
  graph.embedding_migration      embedding migration status (BGE-M3 progress)
  graph.embedding_dimensions     embedding dim distribution (no split > 7 days)
  graph.cascade_overflow         cascade overflow count  < 10 per 24 h
  graph.kuzu_state               kuzu directory state
  graph.evidence_table           graph_evidence_v12 table present
  graph.orphan_symbols           orphan symbols within budget
  graph.legacy_kinds             pre-v16 colon-prefixed kinds cleaned

Callable from src/cli/doctor.py::run_doctor so the existing `cos doctor`
CLI picks everything up — no new command.
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

FRESHNESS_SECONDS = 3600
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


def add_check_freshness(report: "DoctorReport", conn: sqlite3.Connection | None) -> None:
    """docs.agents_md_present — graph freshness."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    age = _graph_last_index_seconds(conn)
    if age is None:
        report.checks.append(
            CheckResult(
                "graph.freshness", SEV_WARN,
                "graph_nodes is empty — run `cos graph-reindex`",
            )
        )
        return
    if age > FRESHNESS_SECONDS:
        report.checks.append(
            CheckResult(
                "graph.freshness", SEV_WARN,
                f"graph index is stale: {age}s > {FRESHNESS_SECONDS}s",
                {"age_seconds": age, "threshold": FRESHNESS_SECONDS},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.freshness", SEV_PASS,
            f"graph index fresh ({age}s old)",
            {"age_seconds": age},
        )
    )


def add_check_parse_error_rate(report: "DoctorReport", state_dir: Path) -> None:
    """graph.freshness — parse error rate on the last auto-reindex log."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

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
                "graph.parse_error_rate", SEV_WARN,
                f"parse error rate {rate:.1%} > {PARSE_ERROR_RATE_LIMIT:.1%}",
                {"rate": rate, "errors": errors, "total": total},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.parse_error_rate", SEV_PASS,
            f"parse error rate {rate:.1%}",
            {"rate": rate, "errors": errors, "total": total},
        )
    )


def add_check_backend_responsive(report: "DoctorReport", state_dir: Path) -> None:
    """graph.parse_error_rate — graph backend reachable."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    probe = _read_backend_probe(state_dir)
    if not probe:
        report.checks.append(
            CheckResult(
                "graph.backend_responsive", SEV_WARN,
                "no backend probe yet — run any `cos graph-*` command once",
            )
        )
        return
    last_ok = probe.get("last_ok_at")
    age = int(time.time()) - int(last_ok) if last_ok else None
    if age is None or age > 6 * 3600:
        report.checks.append(
            CheckResult(
                "graph.backend_responsive", SEV_WARN,
                f"backend probe stale (age={age}s) — run: cos graph-reindex",
                probe,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.backend_responsive", SEV_PASS,
            f"backend {probe.get('backend', '?')} ok ({age}s ago)",
            probe,
        )
    )


def add_check_groups_configured(report: "DoctorReport") -> None:
    """graph.backend_responsive — group manifests healthy."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

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
                "graph.groups_configured", SEV_WARN,
                f"group members missing on disk: {', '.join(missing[:5])}"
                + ("..." if len(missing) > 5 else ""),
                {"missing": missing, "healthy": healthy_count},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.groups_configured", SEV_PASS,
            f"{healthy_count} group(s) healthy",
            {"healthy": healthy_count},
        )
    )


def add_check_embedding_migration(report: "DoctorReport", state_dir: Path) -> None:
    """graph.groups_configured — embedding migration status."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    checkpoint = state_dir / ".embedding-migration.json"
    if not checkpoint.exists():
        report.checks.append(
            CheckResult(
                "graph.embedding_migration", SEV_PASS,
                "no migration in progress",
            )
        )
        return
    try:
        data = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("embedding checkpoint unreadable: %s", exc)
        report.checks.append(
            CheckResult(
                "graph.embedding_migration", SEV_WARN,
                "migration checkpoint unreadable",
            )
        )
        return
    done = int(data.get("done", 0))
    total = int(data.get("total", 0))
    if total == 0 or done >= total:
        report.checks.append(
            CheckResult(
                "graph.embedding_migration", SEV_PASS,
                f"migration complete ({done}/{total or done})",
                data,
            )
        )
        return
    pct = (done / total) * 100 if total else 0
    eta = data.get("eta_seconds")
    report.checks.append(
        CheckResult(
            "graph.embedding_migration", SEV_WARN,
            f"migration in progress: {done}/{total} ({pct:.1f}%; ETA {eta}s)",
            data,
        )
    )


def add_check_embedding_dimensions(
    report: "DoctorReport",
    conn: sqlite3.Connection | None,
    state_dir: Path,
) -> None:
    """graph.embedding_migration — embedding dim distribution."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    if conn is None:
        return
    try:
        rows = conn.execute(
            "SELECT embedding_dim, COUNT(*) FROM embeddings "
            "WHERE embedding_dim IS NOT NULL GROUP BY embedding_dim"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("embeddings.embedding_dim absent (pre-v12): %s", exc)
        report.checks.append(
            CheckResult(
                "graph.embedding_dimensions", SEV_PASS,
                "embedding_dim column absent (pre-v12 DB)",
            )
        )
        return
    distribution = {int(r[0] or 0): int(r[1]) for r in rows}
    if not distribution:
        report.checks.append(
            CheckResult(
                "graph.embedding_dimensions", SEV_PASS, "no embeddings yet"
            )
        )
        return
    if len(distribution) == 1:
        dim, count = next(iter(distribution.items()))
        report.checks.append(
            CheckResult(
                "graph.embedding_dimensions", SEV_PASS,
                f"all {count} rows at dim={dim}",
                {"distribution": distribution},
            )
        )
        return
    checkpoint = state_dir / ".embedding-migration.json"
    split_for_days: float | None = None
    if checkpoint.exists():
        try:
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            started = float(data.get("started_at") or time.time())
            split_for_days = (time.time() - started) / 86400
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug("checkpoint split detection failed: %s", exc)
    report.checks.append(
        CheckResult(
            "graph.embedding_dimensions", SEV_WARN,
            f"mixed dims: {distribution}"
            + (f" (split for ~{split_for_days:.1f}d)" if split_for_days else ""),
            {"distribution": distribution, "split_days": split_for_days},
        )
    )


def add_check_cascade_overflow(report: "DoctorReport", state_dir: Path) -> None:
    """graph.embedding_dimensions — cascade overflow count in the last 24h."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    log = state_dir / ".graph-cascade-overflow.log"
    if not log.exists():
        report.checks.append(
            CheckResult("graph.cascade_overflow", SEV_PASS, "no overflow records")
        )
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
                "graph.cascade_overflow", SEV_WARN,
                f"{count} overflows in 24h (limit {CASCADE_OVERFLOW_LIMIT})",
                {"count": count},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.cascade_overflow", SEV_PASS,
            f"{count} overflows in 24h",
            {"count": count},
        )
    )


def add_check_kuzu_state(report: "DoctorReport", state_dir: Path) -> None:
    """Surface the kuzu-backend state so users aren't surprised by the
    auto-fallback. Three states: missing (kuzu not in use), populated,
    or empty (auto falls back to SQLite — fine but worth knowing)."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    kuzu_dir = state_dir / "graph_os.kuzu"
    if not kuzu_dir.exists():
        report.checks.append(
            CheckResult(
                "graph.kuzu_state", SEV_PASS,
                "kuzu not in use (sqlite only)",
                {"present": False},
            )
        )
        return
    data_file = kuzu_dir / "data.kz"
    size = data_file.stat().st_size if data_file.exists() else 0
    if size == 0:
        report.checks.append(
            CheckResult(
                "graph.kuzu_state", SEV_WARN,
                "kuzu directory exists but is empty — auto backend "
                "falls back to SQLite. Consider `rm -rf "
                f"{kuzu_dir}` or wire a kuzu reindexer.",
                {"present": True, "data_bytes": 0},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.kuzu_state", SEV_PASS,
            f"kuzu populated ({size} bytes)",
            {"present": True, "data_bytes": size},
        )
    )


def add_check_evidence_table(
    report: "DoctorReport", conn: sqlite3.Connection | None
) -> None:
    """graph.evidence_table: graph_evidence_v12 table is required by sqlite_backend's
    schema verifier; without it the backend constructor raises and
    every cos_graph_* tool returns `unavailable`."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN, SEV_FAIL

    if conn is None:
        report.checks.append(
            CheckResult(
                "graph.evidence_table", SEV_WARN,
                "no graph DB connection — skipped",
            )
        )
        return
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='graph_evidence_v12'"
        ).fetchone()
    except sqlite3.Error as exc:
        report.checks.append(
            CheckResult(
                "graph.evidence_table", SEV_FAIL,
                f"check failed: {exc}",
            )
        )
        return
    if row is None:
        report.checks.append(
            CheckResult(
                "graph.evidence_table", SEV_FAIL,
                "graph_evidence_v12 missing — run init_db",
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.evidence_table", SEV_PASS,
            "graph_evidence_v12 present",
        )
    )


def add_check_orphan_symbols(
    report: "DoctorReport", conn: sqlite3.Connection | None
) -> None:
    """graph.orphan_symbols: count code symbols with no contains-parent. Warn when the
    ratio crosses 5 % so the orphan rate doesn't silently regress."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    if conn is None:
        report.checks.append(
            CheckResult(
                "graph.orphan_symbols", SEV_WARN,
                "no graph DB connection — skipped",
            )
        )
        return
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes "
            "WHERE kind IN ('class','method','function')"
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
                "graph.orphan_symbols", SEV_WARN,
                f"check failed: {exc}",
            )
        )
        return
    rate = (orphans / total) if total else 0.0
    detail = {"orphans": orphans, "total": total, "rate": round(rate, 4)}
    if total == 0:
        report.checks.append(
            CheckResult("graph.orphan_symbols", SEV_PASS,
                        "no symbols indexed yet", detail))
        return
    if rate > 0.05:
        report.checks.append(
            CheckResult(
                "graph.orphan_symbols", SEV_WARN,
                f"{orphans}/{total} ({rate:.1%}) symbols are orphans",
                detail,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.orphan_symbols", SEV_PASS,
            f"{orphans}/{total} ({rate:.1%}) orphans — within budget",
            detail,
        )
    )


def add_check_legacy_kinds(
    report: "DoctorReport", conn: sqlite3.Connection | None
) -> None:
    """graph.legacy_kinds: every stored kind should be a canonical NodeKind short
    form. Legacy colon-prefixed kinds (`code:function`, `doc:heading`)
    indicate the storage-time normalizer is bypassed somewhere."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    if conn is None:
        report.checks.append(
            CheckResult(
                "graph.legacy_kinds", SEV_WARN,
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
                "graph.legacy_kinds", SEV_WARN,
                f"check failed: {exc}",
            )
        )
        return
    if bad > 0:
        report.checks.append(
            CheckResult(
                "graph.legacy_kinds", SEV_WARN,
                f"{bad} nodes carry legacy colon-prefixed kinds — "
                "run `cos graph-reindex --rebuild-kinds`",
                {"count": bad},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "graph.legacy_kinds", SEV_PASS,
            "all kinds canonical",
        )
    )


def run_graph_checks(
    report: "DoctorReport",
    state_dir: Path,
    conn: sqlite3.Connection | None,
) -> None:
    """Run docs.agents_md_present-graph.legacy_kinds. Called from src/cli/doctor.py::run_doctor."""
    add_check_freshness(report, conn)
    add_check_parse_error_rate(report, state_dir)
    add_check_backend_responsive(report, state_dir)
    add_check_groups_configured(report)
    add_check_embedding_migration(report, state_dir)
    add_check_embedding_dimensions(report, conn, state_dir)
    add_check_cascade_overflow(report, state_dir)
    add_check_kuzu_state(report, state_dir)
    add_check_evidence_table(report, conn)
    add_check_orphan_symbols(report, conn)
    add_check_legacy_kinds(report, conn)


__all__ = ["run_graph_checks"]
