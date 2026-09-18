"""Nightly index-maintenance legs — doc chunk reconcile and graph reindex.

The edit hooks keep both indexes fresh while someone is working; these legs
cover the gap a quiet project opens — deletions the hook never sweeps, and a
graph that silently drifts past its freshness window.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger("codingos.scheduled.nightly")

_GRAPH_REINDEX_THRESHOLD_S = 86400  # 24h — match doctor_graph.FRESHNESS_SECONDS


def _run_doc_reconcile(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """doc_reconcile — prune document_chunks for docs deleted on disk (the edit
    hook re-chunks single files but never sweeps deletions); reuses index_docs."""
    config_path = project_root / ".coding-os" / "rag-config.yaml"
    if not config_path.exists():
        return {"status": "skipped", "reason": "no rag-config.yaml"}
    if dry_run:
        return {"status": "skipped", "reason": "dry_run"}
    from thinking_os.doc_indexer import index_docs

    with sqlite3.connect(str(db_path), timeout=30) as conn:
        stats = index_docs(conn, config_path, project_root, force=False)
    return {
        "status": "ok",
        "pruned": stats.get("deleted_files", 0),
        "updated": stats.get("updated_files", 0),
    }


def _graph_index_age_seconds(db_path: Path) -> int | None:
    # The same number cos doctor grades graph.freshness on
    # (_doctor_graph_pipeline._graph_last_index_seconds): how old the newest
    # indexed NODE is. Not .graph-backend.json::last_ok_at — that is a backend
    # liveness probe, refreshed every time the backend answers a query, so on
    # any project someone is working in it is never 24h old and this leg never
    # fired. Observed 2026-09-15: nightly recorded
    # `skipped, fresh (38050s < 86400s)` while cos doctor reported the index
    # stale at 121176s six hours later. The self-healing leg could not fire in
    # exactly the case it exists for.
    import time as _t

    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10) as conn:
            row = conn.execute("SELECT MAX(updated_at) FROM graph_nodes").fetchone()
    except sqlite3.Error as exc:
        logger.debug("graph index age unavailable: %s", exc)
        return None
    if row is None or row[0] is None:
        return None
    return int(_t.time()) - int(row[0])


def _run_graph_reindex_if_stale(project_root: Path, *, dry_run: bool) -> dict:
    """Trigger a full graph reindex when the INDEX is older than 24h.

    The PostToolUse auto-reindex hook keeps the graph fresh on every Edit /
    Write, but a project that hasn't been touched for >24h drifts out of
    freshness silently. Nightly fills that gap so `cos doctor` keeps
    `graph.freshness` PASS without manual intervention.
    """
    db_path = project_root / ".coding-os" / "coding-os.db"
    age = _graph_index_age_seconds(db_path)
    if age is None:
        return {"status": "skipped", "reason": "no_graph_index_yet"}
    if age < _GRAPH_REINDEX_THRESHOLD_S:
        return {
            "status": "skipped",
            "reason": f"fresh ({age}s < {_GRAPH_REINDEX_THRESHOLD_S}s)",
            "age_seconds": age,
        }

    if dry_run:
        return {"status": "dry_run", "would_reindex": True, "age_seconds": age}

    import subprocess

    # Invoke via `sys.executable -m cli.main graph-reindex` so launchd's
    # stripped PATH (typically /usr/bin:/bin) cannot lose the binary —
    # the interpreter we are already running with always resolves.
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "cli.main", "graph-reindex"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}

    if completed.returncode != 0:
        return {
            "status": "error",
            "error": f"cos graph-reindex rc={completed.returncode}",
            "stderr_tail": completed.stderr[-500:],
        }
    summary_line = ""
    for line in reversed(completed.stdout.splitlines()):
        if "processed=" in line:
            summary_line = line.strip()
            break
    return {"status": "ok", "summary": summary_line or "completed", "age_seconds": age}
