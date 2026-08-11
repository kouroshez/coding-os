"""Embedding checks — migration progress and dimension distribution.

Both read the BGE-M3 migration checkpoint and answer the same question: is the
embedding store mid-flight, and has it been split across dimensions long enough
to worry. They change together when the embedding model does, and with nothing
else in the graph doctor.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.doctor import DoctorReport


logger = logging.getLogger("coding_os.doctor.graph")


def add_check_embedding_migration(report: DoctorReport, state_dir: Path) -> None:
    """graph.groups_configured — embedding migration status."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

    checkpoint = state_dir / ".embedding-migration.json"
    if not checkpoint.exists():
        report.checks.append(
            CheckResult(
                "graph.embedding_migration",
                SEV_PASS,
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
                "graph.embedding_migration",
                SEV_WARN,
                "migration checkpoint unreadable",
            )
        )
        return
    done = int(data.get("done", 0))
    total = int(data.get("total", 0))
    if total == 0 or done >= total:
        report.checks.append(
            CheckResult(
                "graph.embedding_migration",
                SEV_PASS,
                f"migration complete ({done}/{total or done})",
                data,
            )
        )
        return
    pct = (done / total) * 100 if total else 0
    eta = data.get("eta_seconds")
    report.checks.append(
        CheckResult(
            "graph.embedding_migration",
            SEV_WARN,
            f"migration in progress: {done}/{total} ({pct:.1f}%; ETA {eta}s)",
            data,
        )
    )


def add_check_embedding_dimensions(
    report: DoctorReport,
    conn: sqlite3.Connection | None,
    state_dir: Path,
) -> None:
    """graph.embedding_migration — embedding dim distribution."""
    from cli.doctor import SEV_PASS, SEV_WARN, CheckResult

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
                "graph.embedding_dimensions",
                SEV_PASS,
                "embedding_dim column absent (pre-v12 DB)",
            )
        )
        return
    distribution = {int(r[0] or 0): int(r[1]) for r in rows}
    if not distribution:
        report.checks.append(
            CheckResult("graph.embedding_dimensions", SEV_PASS, "no embeddings yet")
        )
        return
    if len(distribution) == 1:
        dim, count = next(iter(distribution.items()))
        report.checks.append(
            CheckResult(
                "graph.embedding_dimensions",
                SEV_PASS,
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
            "graph.embedding_dimensions",
            SEV_WARN,
            f"mixed dims: {distribution}"
            + (f" (split for ~{split_for_days:.1f}d)" if split_for_days else ""),
            {"distribution": distribution, "split_days": split_for_days},
        )
    )
