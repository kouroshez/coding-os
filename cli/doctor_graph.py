"""graph-os doctor checks (Phase I.14).

Implements C16-C22 (plan §18.3 / §19 I.14):

  C16 — graph index freshness           < 3600 s old
  C17 — parse error rate                < 5 %
  C18 — graph backend reachable
  C19 — group manifests healthy (all members resolvable)
  C20 — embedding migration status      (BGE-M3 progress)
  C21 — embedding dim distribution       (no split > 7 days)
  C22 — cascade overflow count           < 10 per 24 h

Callable from cli/doctor.py::run_doctor so the existing `cos doctor`
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


def add_check_c16(report: "DoctorReport", conn: sqlite3.Connection | None) -> None:
    """C16 — graph freshness."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    age = _graph_last_index_seconds(conn)
    if age is None:
        report.checks.append(
            CheckResult(
                "C17", "graph_freshness", SEV_WARN,
                "graph_nodes is empty — run `cos graph-reindex`",
            )
        )
        return
    if age > FRESHNESS_SECONDS:
        report.checks.append(
            CheckResult(
                "C17", "graph_freshness", SEV_WARN,
                f"graph index is stale: {age}s > {FRESHNESS_SECONDS}s",
                {"age_seconds": age, "threshold": FRESHNESS_SECONDS},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "C17", "graph_freshness", SEV_PASS,
            f"graph index fresh ({age}s old)",
            {"age_seconds": age},
        )
    )


def add_check_c17(report: "DoctorReport", state_dir: Path) -> None:
    """C17 — parse error rate on the last auto-reindex log."""
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
                "C18", "graph_parse_error_rate", SEV_WARN,
                f"parse error rate {rate:.1%} > {PARSE_ERROR_RATE_LIMIT:.1%}",
                {"rate": rate, "errors": errors, "total": total},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "C18", "graph_parse_error_rate", SEV_PASS,
            f"parse error rate {rate:.1%}",
            {"rate": rate, "errors": errors, "total": total},
        )
    )


def add_check_c18(report: "DoctorReport", state_dir: Path) -> None:
    """C18 — graph backend reachable."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    probe = _read_backend_probe(state_dir)
    if not probe:
        report.checks.append(
            CheckResult(
                "C19", "graph_backend_probe", SEV_WARN,
                "no backend probe yet — run any `cos graph-*` command once",
            )
        )
        return
    last_ok = probe.get("last_ok_at")
    age = int(time.time()) - int(last_ok) if last_ok else None
    if age is None or age > 6 * 3600:
        report.checks.append(
            CheckResult(
                "C19", "graph_backend_probe", SEV_WARN,
                f"backend probe stale (age={age}s)",
                probe,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "C19", "graph_backend_probe", SEV_PASS,
            f"backend {probe.get('backend', '?')} ok ({age}s ago)",
            probe,
        )
    )


def add_check_c19(report: "DoctorReport") -> None:
    """C19 — group manifests healthy."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    groups_root = Path.home() / ".coding-os" / "groups"
    if not groups_root.exists():
        report.checks.append(
            CheckResult("C20", "graph_groups", SEV_PASS, "no groups configured")
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
                "C20", "graph_groups", SEV_WARN,
                f"group members missing on disk: {', '.join(missing[:5])}"
                + ("..." if len(missing) > 5 else ""),
                {"missing": missing, "healthy": healthy_count},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "C20", "graph_groups", SEV_PASS,
            f"{healthy_count} group(s) healthy",
            {"healthy": healthy_count},
        )
    )


def add_check_c20(report: "DoctorReport", state_dir: Path) -> None:
    """C20 — embedding migration status."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    checkpoint = state_dir / ".embedding-migration.json"
    if not checkpoint.exists():
        report.checks.append(
            CheckResult(
                "C21", "embedding_migration", SEV_PASS,
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
                "C21", "embedding_migration", SEV_WARN,
                "migration checkpoint unreadable",
            )
        )
        return
    done = int(data.get("done", 0))
    total = int(data.get("total", 0))
    if total == 0 or done >= total:
        report.checks.append(
            CheckResult(
                "C21", "embedding_migration", SEV_PASS,
                f"migration complete ({done}/{total or done})",
                data,
            )
        )
        return
    pct = (done / total) * 100 if total else 0
    eta = data.get("eta_seconds")
    report.checks.append(
        CheckResult(
            "C21", "embedding_migration", SEV_WARN,
            f"migration in progress: {done}/{total} ({pct:.1f}%; ETA {eta}s)",
            data,
        )
    )


def add_check_c21(
    report: "DoctorReport",
    conn: sqlite3.Connection | None,
    state_dir: Path,
) -> None:
    """C21 — embedding dim distribution."""
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
                "C22", "embedding_dim_distribution", SEV_PASS,
                "embedding_dim column absent (pre-v12 DB)",
            )
        )
        return
    distribution = {int(r[0] or 0): int(r[1]) for r in rows}
    if not distribution:
        report.checks.append(
            CheckResult(
                "C22", "embedding_dim_distribution", SEV_PASS, "no embeddings yet"
            )
        )
        return
    if len(distribution) == 1:
        dim, count = next(iter(distribution.items()))
        report.checks.append(
            CheckResult(
                "C22", "embedding_dim_distribution", SEV_PASS,
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
            "C22", "embedding_dim_distribution", SEV_WARN,
            f"mixed dims: {distribution}"
            + (f" (split for ~{split_for_days:.1f}d)" if split_for_days else ""),
            {"distribution": distribution, "split_days": split_for_days},
        )
    )


def add_check_c22(report: "DoctorReport", state_dir: Path) -> None:
    """C22 — cascade overflow count in the last 24h."""
    from cli.doctor import CheckResult, SEV_PASS, SEV_WARN

    log = state_dir / ".graph-cascade-overflow.log"
    if not log.exists():
        report.checks.append(
            CheckResult("C23", "graph_cascade_overflow", SEV_PASS, "no overflow records")
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
                "C23", "graph_cascade_overflow", SEV_WARN,
                f"{count} overflows in 24h (limit {CASCADE_OVERFLOW_LIMIT})",
                {"count": count},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "C23", "graph_cascade_overflow", SEV_PASS,
            f"{count} overflows in 24h",
            {"count": count},
        )
    )


def run_graph_checks(
    report: "DoctorReport",
    state_dir: Path,
    conn: sqlite3.Connection | None,
) -> None:
    """Run C16-C22. Called from cli/doctor.py::run_doctor."""
    add_check_c16(report, conn)
    add_check_c17(report, state_dir)
    add_check_c18(report, state_dir)
    add_check_c19(report)
    add_check_c20(report, state_dir)
    add_check_c21(report, conn, state_dir)
    add_check_c22(report, state_dir)


__all__ = ["run_graph_checks"]
