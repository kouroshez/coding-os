#!/usr/bin/env python3
"""Thinking OS — garbage collection for dangling memory rows."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
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
            for source in ("observations", "document_chunks"):
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
            n = conn.execute(
                f"SELECT COUNT(*) FROM concept_graph WHERE {stale_where}"
            ).fetchone()[0]
            stats["stale_co_edit_edges"] = int(n)
            if n and not dry_run:
                conn.execute(f"DELETE FROM concept_graph WHERE {stale_where}")

        # ---- 3. Trash observations (captured during local experiments) ----
        if _table_exists(conn, "observations"):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Thinking OS memory GC")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--db", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = args.db or str(Path(args.project_root) / ".coding-os" / "coding-os.db")
    stats = gc_memory(db, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
