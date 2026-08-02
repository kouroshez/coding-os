#!/usr/bin/env python3
"""Thinking OS — garbage collection for dangling memory rows."""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection

from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
logger = logging.getLogger("thinking_os.gc")


# Path globs that should never own persistent memory. When a Write/Edit
# hits one of these, the observation still gets captured (intent is
# correct) but follow-up purges leave orphans behind.  We match path
# prefixes so `/tmp` and the macOS `/private/tmp` alias collapse to one
# rule.
TRASH_PATH_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return bool(row)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def gc_memory(
    db_path: str | Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove dangling embeddings + concept_graph edges + trash observations.

    Returns stats; never raises on missing tables (pre-migration DBs
    silently report zero).
    """
    path = Path(db_path or DEFAULT_DB_PATH)
    stats: dict[str, Any] = {
        "orphan_embeddings_observations": 0,
        "orphan_embeddings_document_chunks": 0,
        "orphan_embeddings_learned_patterns": 0,
        "orphan_pattern_validations": 0,
        "orphan_graph_evidence": 0,
        "orphan_concept_graph_edges": 0,
        "stale_co_edit_edges": 0,
        "trash_observations": 0,
        "status": "ok",
        "dry_run": dry_run,
    }
    if not path.exists():
        stats["status"] = "no_db"
        return stats

    conn = get_connection(path)
    try:
        # ---- 1. Orphan embeddings that reference deleted rows ----
        if _table_exists(conn, "embeddings"):
            for source in ("observations", "document_chunks", "learned_patterns"):
                if not _table_exists(conn, source):
                    continue
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM embeddings e "
                    f"WHERE e.source_table = ? "
                    f"  AND NOT EXISTS (SELECT 1 FROM {source} t WHERE t.id = e.source_id)",
                    (source,),
                )
                n = cur.fetchone()[0]
                stats[f"orphan_embeddings_{source}"] = int(n)
                if n and not dry_run:
                    conn.execute(
                        f"DELETE FROM embeddings "
                        f"WHERE source_table = ? "
                        f"  AND NOT EXISTS (SELECT 1 FROM {source} t WHERE t.id = source_id)",
                        (source,),
                    )

        # ---- 1b. Orphan pattern_validations (pattern_id deleted) ----
        if _table_exists(conn, "pattern_validations") and _table_exists(conn, "learned_patterns"):
            n = conn.execute(
                "SELECT COUNT(*) FROM pattern_validations v "
                "WHERE NOT EXISTS (SELECT 1 FROM learned_patterns p WHERE p.id = v.pattern_id)"
            ).fetchone()[0]
            stats["orphan_pattern_validations"] = int(n)
            if n and not dry_run:
                conn.execute(
                    "DELETE FROM pattern_validations WHERE NOT EXISTS "
                    "(SELECT 1 FROM learned_patterns p WHERE p.id = pattern_validations.pattern_id)"
                )

        # ---- 1c. Orphan graph_evidence_v12 (the ON DELETE CASCADE that didn't fire) ----
        if _table_exists(conn, "graph_evidence_v12") and _table_exists(conn, "graph_edges_v12"):
            n = conn.execute(
                "SELECT COUNT(*) FROM graph_evidence_v12 e "
                "WHERE NOT EXISTS (SELECT 1 FROM graph_edges_v12 g WHERE g.id = e.edge_id)"
            ).fetchone()[0]
            stats["orphan_graph_evidence"] = int(n)
            if n and not dry_run:
                conn.execute(
                    "DELETE FROM graph_evidence_v12 WHERE NOT EXISTS "
                    "(SELECT 1 FROM graph_edges_v12 g WHERE g.id = graph_evidence_v12.edge_id)"
                )

        # ---- 2. Concept graph edges whose endpoints are trash paths ----
        if _table_exists(conn, "concept_graph"):
            globs = ["source LIKE ?", "target LIKE ?"]
            params: list[Any] = []
            for prefix in TRASH_PATH_PREFIXES:
                params.extend([f"{prefix}%", f"{prefix}%"])
            where = " OR ".join(globs * len(TRASH_PATH_PREFIXES))
            cur = conn.execute(
                f"SELECT COUNT(*) FROM concept_graph WHERE {where}",
                params,
            )
            n = cur.fetchone()[0]
            stats["orphan_concept_graph_edges"] = int(n)
            if n and not dry_run:
                conn.execute(
                    f"DELETE FROM concept_graph WHERE {where}",
                    params,
                )

        # ---- 2b. Stale, unreinforced co_edit edges (density backstop) ----
        # A co_edit edge seen once (weight <= 1.0) and untouched for 30 days is
        # noise; without this prune the graph trends back toward a useless
        # complete graph (the 260 MB incident). Reinforced (weight > 1.0) or
        # recent edges survive. Contract: docs/engineering/concept-graph.md.
        if _table_exists(conn, "concept_graph"):
            stale_where = (
                "edge_type = 'co_edit' AND weight <= 1.0 "
                "AND updated_at < datetime('now', '-30 days')"
            )
            n = conn.execute(f"SELECT COUNT(*) FROM concept_graph WHERE {stale_where}").fetchone()[
                0
            ]
            stats["stale_co_edit_edges"] = int(n)
            if n and not dry_run:
                conn.execute(f"DELETE FROM concept_graph WHERE {stale_where}")

        # ---- 3. Trash observations (captured during local experiments) ----
        if _table_exists(conn, "observations") and _column_exists(
            conn, "observations", "files_modified"
        ):
            like_terms = " OR ".join("files_modified LIKE ?" for _ in TRASH_PATH_PREFIXES)
            like_params = [f"{p}%" for p in TRASH_PATH_PREFIXES]
            cur = conn.execute(
                f"SELECT COUNT(*) FROM observations WHERE {like_terms}",
                like_params,
            )
            n = cur.fetchone()[0]
            stats["trash_observations"] = int(n)
            if n and not dry_run:
                # observations FTS + concept_graph triggers fire on DELETE.
                conn.execute(
                    f"DELETE FROM observations WHERE {like_terms}",
                    like_params,
                )

        if not dry_run:
            conn.commit()

        return stats
    finally:
        conn.close()


# Legacy mechanical changelog rows (write/edit) that pre-date the expires_at TTL
# wiring carry NULL expiry, so decay's forward GC (expires_at IS NOT NULL) never
# reaches them. This predicate is disjoint from that GC and excludes the
# tool_failure/completion_gap rows the learning loop mines for lessons.
_CHANGELOG_SWEEP_PREDICATE = (
    "memory_type = 'changelog' AND expires_at IS NULL "
    "AND COALESCE(observation_type, '') NOT IN ('tool_failure', 'completion_gap')"
)


def sweep_changelog(
    db_path: str | Path | None = None,
    *,
    dry_run: bool = True,
    grace_days: int = 14,
    archive_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Retire legacy mechanical `changelog` observations (NULL expiry).

    Owner-invoked, dry-run by default: reports the matched count and writes
    nothing. With dry_run=False it archives the matched rows to a gzip JSONL
    under archive_dir (archive-first, so undo_sweep can restore) then deletes
    them. Rows newer than grace_days are protected.
    """
    path = Path(db_path or DEFAULT_DB_PATH)
    stats: dict[str, Any] = {
        "matched": 0,
        "archived": 0,
        "deleted": 0,
        "archive_path": None,
        "grace_days": grace_days,
        "dry_run": dry_run,
        "status": "ok",
    }
    if not path.exists():
        stats["status"] = "no_db"
        return stats

    conn = get_connection(path)
    conn.row_factory = sqlite3.Row
    try:
        if not (
            _table_exists(conn, "observations")
            and _column_exists(conn, "observations", "expires_at")
        ):
            stats["status"] = "no_target"
            return stats
        where = _CHANGELOG_SWEEP_PREDICATE + " AND created_at < datetime('now', ?)"
        grace = f"-{max(0, int(grace_days))} days"
        rows = conn.execute(f"SELECT * FROM observations WHERE {where}", (grace,)).fetchall()
        stats["matched"] = len(rows)
        if dry_run or not rows:
            return stats

        adir = Path(archive_dir or (path.parent / "archives"))
        adir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        apath = adir / f"changelog-sweep-{stamp}.jsonl.gz"
        cols = list(rows[0].keys())
        with gzip.open(apath, "wt", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({k: r[k] for k in cols}, ensure_ascii=False) + "\n")
        stats["archived"] = len(rows)
        stats["archive_path"] = str(apath)

        # observations FTS + concept_graph triggers fire on DELETE.
        conn.executemany("DELETE FROM observations WHERE id = ?", [(r["id"],) for r in rows])
        conn.commit()
        stats["deleted"] = len(rows)
        return stats
    finally:
        conn.close()


def undo_sweep(db_path: str | Path | None, archive_path: str | Path) -> dict[str, Any]:
    """Restore rows a prior sweep archived — re-insert from the gzip JSONL,
    skipping any id that still exists (idempotent)."""
    path = Path(db_path or DEFAULT_DB_PATH)
    apath = Path(archive_path)
    stats: dict[str, Any] = {
        "restored": 0,
        "skipped": 0,
        "archive_path": str(apath),
        "status": "ok",
    }
    if not path.exists():
        stats["status"] = "no_db"
        return stats
    if not apath.exists():
        stats["status"] = "no_archive"
        return stats

    conn = get_connection(path)
    try:
        with gzip.open(apath, "rt", encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        for rec in records:
            if conn.execute("SELECT 1 FROM observations WHERE id = ?", (rec.get("id"),)).fetchone():
                stats["skipped"] += 1
                continue
            cols = list(rec.keys())
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO observations ({', '.join(cols)}) VALUES ({placeholders})",
                [rec[c] for c in cols],
            )
            stats["restored"] += 1
        conn.commit()
        return stats
    finally:
        conn.close()


def vacuum_db(db_path: str | Path | None) -> dict[str, Any]:
    """Reclaim file bytes via VACUUM (exclusive lock — run at quiescence only)."""
    path = Path(db_path or DEFAULT_DB_PATH)
    stats: dict[str, Any] = {"status": "ok", "size_before": None, "size_after": None}
    if not path.exists():
        stats["status"] = "no_db"
        return stats
    stats["size_before"] = path.stat().st_size
    conn = get_connection(path)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    stats["size_after"] = path.stat().st_size
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Thinking OS memory GC")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--db", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--sweep-changelog",
        action="store_true",
        help="Retire legacy changelog rows (NULL expiry) instead of running GC",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="With --sweep-changelog: archive-first then delete (default is dry-run)",
    )
    parser.add_argument(
        "--undo", default=None, metavar="ARCHIVE", help="Restore rows from a sweep archive"
    )
    parser.add_argument("--vacuum", action="store_true", help="VACUUM the DB to reclaim bytes")
    parser.add_argument(
        "--grace-days",
        type=int,
        default=14,
        help="With --sweep-changelog: protect rows newer than N days (default 14)",
    )
    args = parser.parse_args()

    db = args.db or str(Path(args.project_root) / ".coding-os" / "coding-os.db")
    if args.undo:
        stats = undo_sweep(db, args.undo)
    elif args.vacuum:
        stats = vacuum_db(db)
    elif args.sweep_changelog:
        stats = sweep_changelog(db, dry_run=not args.confirm, grace_days=args.grace_days)
    else:
        stats = gc_memory(db, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
