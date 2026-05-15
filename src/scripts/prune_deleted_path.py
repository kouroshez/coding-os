"""Prune graph + docs RAG state for a deleted path."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "core"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "thinking_os"))


def _resolve_db_path(project_root: Path) -> Path:
    return Path(
        os.environ.get("COS_DB_PATH", str(project_root / ".coding-os" / "coding-os.db"))
    )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _delete_where(conn: sqlite3.Connection, table: str, column: str, value: str) -> int:
    if not _table_exists(conn, table):
        return 0
    cursor = conn.execute(f"DELETE FROM {table} WHERE {column}=?", (value,))
    return int(cursor.rowcount or 0)


def _prune_one(rel_path: str, *, db_path: Path) -> dict:
    """Run all DELETEs for one path. Returns counts per layer."""
    counts = {"graph_nodes": 0, "document_chunks": 0, "file_index_state": 0}
    conn = sqlite3.connect(str(db_path))
    try:
        # graph_os layer — cascades to graph_edges_v12 + graph_evidence_v12
        # via FK ON DELETE CASCADE (migration v12).
        if _table_exists(conn, "graph_nodes"):
            cursor = conn.execute(
                "DELETE FROM graph_nodes WHERE file_path=?", (rel_path,)
            )
            counts["graph_nodes"] = int(cursor.rowcount or 0)
        # docs RAG layer
        counts["document_chunks"] = _delete_where(
            conn, "document_chunks", "source_path", rel_path
        )
        # reindex cache
        counts["file_index_state"] = _delete_where(
            conn, "file_index_state", "file_path", rel_path
        )
        conn.commit()
    finally:
        conn.close()
    return counts


def _to_rel(path: str, project_root: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(project_root.resolve()))
        except ValueError:
            return str(p.resolve())
    return str(p)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", help="Files to prune")
    parser.add_argument("--force", action="store_true",
                        help="Skip the 'still exists?' guard (pre-emptive prune)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-path OK/SKIP lines")
    args = parser.parse_args(argv)

    project_root = Path(os.environ.get("COS_PROJECT_ROOT", str(_REPO_ROOT))).resolve()
    db_path = _resolve_db_path(project_root)
    if not db_path.exists():
        print(f"SKIP: no DB at {db_path} (fresh install?)", file=sys.stderr)
        return 0

    pruned = skipped = 0
    for raw in args.paths:
        rel = _to_rel(raw, project_root)
        abs_path = (project_root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        if not args.force and abs_path.exists():
            if not args.quiet:
                print(f"SKIP: {rel} (still exists — agent re-created)")
            skipped += 1
            continue
        try:
            counts = _prune_one(rel, db_path=db_path)
        except sqlite3.Error as exc:
            print(f"ERROR: {rel}: {exc}", file=sys.stderr)
            continue
        total = counts["graph_nodes"] + counts["document_chunks"] + counts["file_index_state"]
        if total == 0:
            if not args.quiet:
                print(f"SKIP: {rel} (no rows — never indexed)")
            skipped += 1
            continue
        if not args.quiet:
            extras = []
            if counts["graph_nodes"]:
                extras.append(f"graph={counts['graph_nodes']}")
            if counts["document_chunks"]:
                extras.append(f"docs={counts['document_chunks']}")
            if counts["file_index_state"]:
                extras.append(f"cache={counts['file_index_state']}")
            print(f"OK: {rel} ({', '.join(extras)})")
        pruned += 1

    print(f"INFO: {pruned} pruned, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
