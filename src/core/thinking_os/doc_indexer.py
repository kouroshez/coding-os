"""
Coding OS — Document indexer for RAG retrieval.

Walks the project's `docs/` tree, chunks markdown by H2/H3 headings, and
stores chunks in the `document_chunks` table with embeddings in the
`embeddings` table. Designed for incremental updates: only files whose
mtime changed since the last index are re-chunked.

Configuration lives in `.coding-os/rag-config.yaml`. The indexer reads
the source list, walks each path, applies excludes, chunks each markdown
file, and writes chunks + embeddings.

Module layout:
    _doc_chunking   markdown → chunk dicts (front matter, headings, windowing)
    _doc_sources    rag-config loading, source walking, exclusion matching
    _doc_store      chunk row lifecycle (mtime, deletion, embedding write)
    this module     the index runs that drive them, plus the CLI entry point

Public API:
    chunk_markdown(content, max_chars, overlap_chars) -> list[dict]
    load_rag_config(path) -> dict
    walk_sources(sources, project_root, global_excludes) -> list[(Path, source_config)]
    index_docs(conn, config_path, project_root, force) -> dict

CLI entry point:
    python -m doc_indexer --config .coding-os/rag-config.yaml [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

try:  # package import
    from ._doc_chunking import (
        DEFAULT_MAX_CHARS as DEFAULT_MAX_CHARS,
        DEFAULT_OVERLAP_CHARS as DEFAULT_OVERLAP_CHARS,
        _build_heading_path as _build_heading_path,
        _extract_h1 as _extract_h1,
        _parse_front_matter,
        _strip_front_matter as _strip_front_matter,
        chunk_markdown,
    )
    from ._doc_sources import (
        _is_excluded as _is_excluded,
        _match_source_config,
        load_rag_config,
        walk_sources,
    )
    from ._doc_store import (
        _delete_chunks_for_path,
        _delete_orphaned_chunks,
        _embed_chunk_safe,
        _get_max_mtime,
    )
except ImportError:  # flat import (script / sys.path identity)
    from _doc_chunking import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        DEFAULT_MAX_CHARS,
        DEFAULT_OVERLAP_CHARS,
        _build_heading_path,
        _extract_h1,
        _parse_front_matter,
        _strip_front_matter,
        chunk_markdown,
    )
    from _doc_sources import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _is_excluded,
        _match_source_config,
        load_rag_config,
        walk_sources,
    )
    from _doc_store import (  # type: ignore[no-redef,import-not-found]
        _delete_chunks_for_path,
        _delete_orphaned_chunks,
        _embed_chunk_safe,
        _get_max_mtime,
    )

logger = logging.getLogger("coding_os.doc_indexer")


def index_docs(
    conn: sqlite3.Connection,
    config_path: Path,
    project_root: Path,
    force: bool = False,
) -> dict:
    """Index every markdown file in `docs/` per the RAG config.

    For each file:
      1. Compare mtime with the max stored mtime for that source_path.
      2. If unchanged and not force → skip.
      3. Otherwise: delete existing chunks for that path, re-chunk, insert,
         and embed each new chunk.

    Args:
        conn: Migrated SQLite connection (must include v5).
        config_path: Path to rag-config.yaml.
        project_root: Project root (for resolving relative source paths).
        force: When True, re-index every file regardless of mtime.

    Returns:
        Stats dict: {processed, skipped, new_chunks, updated_files, deleted_files, errors}.
    """
    config = load_rag_config(config_path)
    # Resolve project_root to match the resolved paths returned by walk_sources.
    # On macOS /tmp → /private/tmp symlink, so the raw argument and the walked
    # paths can differ even though they point at the same directory. Always
    # compare resolved-to-resolved to avoid ValueError in relative_to().
    project_root_resolved = project_root.resolve()
    files = walk_sources(config["sources"], project_root_resolved, config["exclude"])

    stats = {
        "processed": 0,
        "skipped": 0,
        "new_chunks": 0,
        "updated_files": 0,
        "deleted_files": 0,
        "errors": 0,
        "missing_frontmatter": 0,
    }

    seen_paths: set[str] = set()

    for file_path, source_config in files:
        rel_path = str(file_path.resolve().relative_to(project_root_resolved))
        seen_paths.add(rel_path)
        stats["processed"] += 1

        try:
            file_mtime = int(file_path.stat().st_mtime)
        except OSError as exc:
            logger.warning("Cannot stat %s: %s", rel_path, exc)
            stats["errors"] += 1
            continue

        if not force:
            existing_mtime = _get_max_mtime(conn, rel_path)
            if existing_mtime is not None and existing_mtime >= file_mtime:
                stats["skipped"] += 1
                continue

        # File is new or modified — replace its chunks
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", rel_path, exc)
            stats["errors"] += 1
            continue

        max_chars = int(source_config.get("chunk_size", DEFAULT_MAX_CHARS))
        overlap = int(source_config.get("chunk_overlap", DEFAULT_OVERLAP_CHARS))
        chunks = chunk_markdown(content, max_chars=max_chars, overlap_chars=overlap)

        # Stage-1 RAG metadata — frontmatter parsed BEFORE the chunker
        # strips it. Written to columns added in migration v22 so
        # cos_doc_search can pre-filter by domain/layer/updated.
        fm = _parse_front_matter(content)
        # D3-F7 (TASK-124): surface files with a body but no parseable
        # frontmatter — previously a silent logger.debug, invisible in the
        # index summary. A leading `<!--` that simply didn't match is a
        # malformed header, not a missing one; both count as a Stage-1 gap.
        if not fm:
            _stripped = content.lstrip()
            if _stripped:
                stats["missing_frontmatter"] += 1

        # Delete previous chunks (and their embeddings)
        _delete_chunks_for_path(conn, rel_path)

        if not chunks:
            stats["updated_files"] += 1
            continue

        source_type = source_config.get("type", "doc")
        priority = float(source_config.get("priority", 0.5))
        # D7-F9 (TASK-138): a doc that declares superseded_by in its header is a
        # past era — index it inactive so cos_doc_search hides it by default.
        doc_is_active = 0 if fm.get("superseded_by") else 1

        for chunk in chunks:
            cursor = conn.execute(
                "INSERT INTO document_chunks "
                "(source_path, source_type, chunk_index, heading_path, content, content_hash, priority, mtime, "
                " domain, layer, ssot, updated_iso, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rel_path,
                    source_type,
                    chunk["chunk_index"],
                    chunk["heading_path"],
                    chunk["content"],
                    chunk["content_hash"],
                    priority,
                    file_mtime,
                    fm.get("domain"),
                    fm.get("layer"),
                    fm.get("ssot"),
                    fm.get("updated_iso"),
                    doc_is_active,
                ),
            )
            stats["new_chunks"] += 1
            chunk_db_id = cursor.lastrowid
            _embed_chunk_safe(conn, chunk_db_id, chunk["heading_path"], chunk["content"])

        conn.commit()
        stats["updated_files"] += 1

    # Cleanup chunks for files no longer present
    stats["deleted_files"] = _delete_orphaned_chunks(conn, seen_paths)
    conn.commit()

    return stats


def index_single_file(
    conn: sqlite3.Connection,
    file_path: Path | str,
    *,
    project_root: Path | str,
    config_path: Path | str = ".coding-os/rag-config.yaml",
    force: bool = False,
) -> dict:
    """Incrementally re-index a single markdown file."""
    file_path = Path(file_path)
    project_root = Path(project_root)
    config_path = Path(config_path)

    config = load_rag_config(config_path)
    project_root_resolved = project_root.resolve()

    if file_path.is_absolute():
        abs_path = file_path
    else:
        abs_path = (project_root_resolved / file_path).resolve()
    try:
        rel_path = str(abs_path.resolve().relative_to(project_root_resolved))
    except ValueError:
        return {
            "status": "unscoped",
            "file": str(file_path),
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    # Missing on disk → treat as delete signal (cleanup ghost chunks).
    if not abs_path.exists():
        existed = (
            conn.execute(
                "SELECT 1 FROM document_chunks WHERE source_path = ? LIMIT 1",
                (rel_path,),
            ).fetchone()
            is not None
        )
        if existed:
            _delete_chunks_for_path(conn, rel_path)
            conn.commit()
            return {
                "status": "deleted",
                "file": rel_path,
                "new_chunks": 0,
                "deleted_chunks": 1,
                "source_type": None,
            }
        return {
            "status": "missing",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    source_config = _match_source_config(
        abs_path,
        config["sources"],
        project_root_resolved,
        config["exclude"],
    )
    if source_config is None:
        return {
            "status": "unscoped",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    if abs_path.suffix != ".md":
        return {
            "status": "unscoped",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    try:
        current_mtime = int(abs_path.stat().st_mtime)
    except OSError as exc:
        logger.debug("index_single_file stat failed for %s: %s", rel_path, exc)
        return {
            "status": "error",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    if not force:
        stored = _get_max_mtime(conn, rel_path)
        if stored is not None and stored >= current_mtime:
            return {
                "status": "unchanged",
                "file": rel_path,
                "new_chunks": 0,
                "deleted_chunks": 0,
                "source_type": source_config.get("type", "doc"),
            }

    try:
        content = abs_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("index_single_file read failed for %s: %s", rel_path, exc)
        return {
            "status": "error",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    max_chars = int(source_config.get("chunk_size", DEFAULT_MAX_CHARS))
    overlap = int(source_config.get("chunk_overlap", DEFAULT_OVERLAP_CHARS))
    chunks = chunk_markdown(content, max_chars=max_chars, overlap_chars=overlap)
    fm = _parse_front_matter(content)

    existing_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM document_chunks WHERE source_path = ?",
            (rel_path,),
        ).fetchall()
    ]
    _delete_chunks_for_path(conn, rel_path)

    if not chunks:
        conn.commit()
        return {
            "status": "reindexed",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": len(existing_ids),
            "source_type": source_config.get("type", "doc"),
        }

    source_type = source_config.get("type", "doc")
    priority = float(source_config.get("priority", 0.5))
    new_chunk_count = 0
    # D7-F9 (TASK-138): superseded docs index inactive (hidden by default).
    doc_is_active = 0 if fm.get("superseded_by") else 1

    for chunk in chunks:
        cursor = conn.execute(
            "INSERT INTO document_chunks "
            "(source_path, source_type, chunk_index, heading_path, content, "
            " content_hash, priority, mtime, "
            " domain, layer, ssot, updated_iso, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rel_path,
                source_type,
                chunk["chunk_index"],
                chunk["heading_path"],
                chunk["content"],
                chunk["content_hash"],
                priority,
                current_mtime,
                fm.get("domain"),
                fm.get("layer"),
                fm.get("ssot"),
                fm.get("updated_iso"),
                doc_is_active,
            ),
        )
        new_chunk_count += 1
        chunk_db_id = cursor.lastrowid
        _embed_chunk_safe(conn, chunk_db_id, chunk["heading_path"], chunk["content"])

    conn.commit()
    return {
        "status": "reindexed",
        "file": rel_path,
        "new_chunks": new_chunk_count,
        "deleted_chunks": len(existing_ids),
        "source_type": source_type,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(description="Index docs/ for RAG retrieval")
    parser.add_argument(
        "--config",
        type=str,
        default=".coding-os/rag-config.yaml",
        help="Path to rag-config.yaml (default: .coding-os/rag-config.yaml)",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index every file regardless of mtime",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Override DB path (defaults to COS_DB_PATH)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from database import init_db

    config_path = Path(args.config).resolve()
    project_root = Path(args.project_root).resolve()

    conn = init_db(args.db)
    try:
        stats = index_docs(conn, config_path, project_root, force=args.force)
    finally:
        conn.close()

    print(json.dumps({"status": "ok", "stats": stats}, indent=2))


if __name__ == "__main__":
    _main()
