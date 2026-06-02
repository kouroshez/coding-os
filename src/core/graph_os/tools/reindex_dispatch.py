"""graph_os + docs unified auto-reindex dispatcher (Phase I.14, V1 cache).

DEPENDS:  thinking_os/doc_indexer (for md), graph_os.extractors.*,
          graph_os.backends.sqlite_backend.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("graph_os.reindex_dispatch")

_EXT_MAP = {
    ".py": ("python", ["code_python", "contracts"]),
    ".ts": ("ts", ["code_ts", "contracts"]),
    ".tsx": ("tsx", ["code_ts", "contracts"]),
    ".sh": ("shell", ["code_shell"]),
    ".yaml": ("yaml", ["code_yaml"]),
    ".yml": ("yaml", ["code_yaml"]),
    ".go": ("go", ["code_go", "contracts"]),
    ".json": ("json", ["code_json"]),
    ".toml": ("toml", ["code_toml"]),
    # Plain JavaScript routes through the TS extractor (JS is a syntactic
    # subset; the regex/tree-sitter passes degrade cleanly on .js).
    ".js": ("js", ["code_ts", "contracts"]),
    ".jsx": ("jsx", ["code_ts", "contracts"]),
    ".mjs": ("js", ["code_ts", "contracts"]),
    ".cjs": ("js", ["code_ts", "contracts"]),
}

# Sentinel chain key stored on file_index_state for docs-only rows
# (markdown files that pass through the RAG indexer). Keeping it
# namespaced (``docs:md``) avoids collisions with any real extractor
# chain name.
_DOCS_CHAIN_KEY = "docs:md"


def _is_retryable_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


# Task-file path matcher. Comma-separated path fragments, env-overridable
# so projects that keep tickets under e.g. `docs/tickets/` or `tasks/`
# can opt into task_deps without forking the dispatcher. Each fragment
# is a substring match against the forward-slash-normalised repo-
# relative path.
_DEFAULT_TASK_PATH_FRAGMENTS = ("/tasks/", "docs/tasks/")


def _is_task_path(rel: str) -> bool:
    needle = rel.replace("\\", "/")
    # docs/tasks/audits/ holds audit artifacts, not tasks — keep them off task_deps.
    if "/tasks/audits/" in needle:
        return False
    raw = os.environ.get("COS_TASK_PATH_FRAGMENTS", "").strip()
    fragments: tuple[str, ...]
    if raw:
        fragments = tuple(p.strip() for p in raw.split(",") if p.strip())
    else:
        fragments = _DEFAULT_TASK_PATH_FRAGMENTS
    return any(frag in needle for frag in fragments)


def dispatch(
    file_path: str | Path,
    *,
    project_root: str | Path,
    db_path: str | None = None,
    include_docs: bool = True,
    force: bool = False,
    link_stubs: bool = True,
) -> dict[str, Any]:
    """Re-index `file_path` in both the docs layer and the graph layer."""
    started = time.monotonic()
    file_path = Path(file_path).resolve()
    project_root = Path(project_root).resolve()
    try:
        rel = str(file_path.relative_to(project_root))
    except ValueError:
        # File lives outside project root — typically a /tmp scratch
        # the agent edited. The PostToolUse hook fires for every Edit,
        # but those throwaway paths must never enter the project graph
        # or doc index. Skip fast so the background worker doesn't pile
        # up phantom-path inserts.
        return {
            "status": "skipped",
            "path": str(file_path),
            "layers": {},
            "duration_ms": int((time.monotonic() - started) * 1000),
            "reason": "out-of-repo",
        }
    suffix = file_path.suffix.lower()

    result: dict[str, Any] = {
        "status": "ok",
        "path": rel,
        "layers": {},
        "duration_ms": 0,
    }

    # Determine which chains are in play BEFORE touching the backend —
    # the cache lookup uses these as its composite key.
    graph_chain: tuple[str, list[str]] | None = None
    if suffix in _EXT_MAP:
        graph_chain = _EXT_MAP[suffix]
    elif suffix == ".md":
        graph_chain = ("markdown", ["md_links"])
        if _is_task_path(rel):
            graph_chain = ("markdown-task", ["task_deps", "md_links"])

    docs_in_scope = include_docs and suffix == ".md"

    # Read file content once so we can hash it + hand it to extractors.
    file_content: str | None = None
    read_error: str | None = None
    try:
        file_content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        read_error = str(exc)

    content_hash: str | None = None
    if file_content is not None:
        content_hash = hashlib.sha256(file_content.encode("utf-8", errors="replace")).hexdigest()

    cache_hits: dict[str, dict[str, Any]] = {}
    if content_hash is not None and not force:
        cache_hits = _lookup_cache(
            rel,
            content_hash=content_hash,
            graph_chain_key=graph_chain[0] if graph_chain else None,
            graph_chain_list=graph_chain[1] if graph_chain else None,
            docs_in_scope=docs_in_scope,
            project_root=project_root,
            db_path=db_path,
        )

    # ── docs layer ───────────────────────────────────────────────────
    if docs_in_scope:
        if "docs" in cache_hits:
            result["layers"]["docs"] = cache_hits["docs"]
        else:
            try:
                docs_layer = _reindex_docs(file_path, project_root=project_root, db_path=db_path)
                result["layers"]["docs"] = docs_layer
                if content_hash is not None:
                    _record_state_safe(
                        rel,
                        content_hash=content_hash,
                        chain_key=_DOCS_CHAIN_KEY,
                        nodes_written=0,
                        edges_written=0,
                        parse_errors_count=0,
                        last_error=None
                        if docs_layer.get("status") in {"ok", "unscoped"}
                        else str(docs_layer.get("reason") or docs_layer.get("status")),
                        project_root=project_root,
                        db_path=db_path,
                        advance_hash=docs_layer.get("status") in {"ok", "unscoped"},
                    )
            except Exception as exc:
                logger.debug("docs reindex failed for %s: %s", rel, exc)
                result["layers"]["docs"] = {"status": "error", "reason": str(exc)}
                if content_hash is not None:
                    _record_state_safe(
                        rel,
                        content_hash=content_hash,
                        chain_key=_DOCS_CHAIN_KEY,
                        nodes_written=0,
                        edges_written=0,
                        parse_errors_count=0,
                        last_error=str(exc),
                        project_root=project_root,
                        db_path=db_path,
                        advance_hash=False,
                    )

    # ── graph layer ──────────────────────────────────────────────────
    if graph_chain is not None:
        if "graph" in cache_hits:
            result["layers"]["graph"] = cache_hits["graph"]
        elif read_error is not None:
            result["layers"]["graph"] = {
                "status": "error",
                "reason": f"read_failed: {read_error}",
            }
        else:
            graph_result: dict[str, Any] | None = None
            last_error: Exception | None = None
            # Lock-retry loop: a busy SQLite under many parallel
            # writers can return "database is locked" even with
            # busy_timeout (because BEGIN IMMEDIATE on a fresh
            # connection isn't covered). Retry a few times with
            # exponential backoff so the dispatcher doesn't drop
            # writes the application would otherwise lose.
            graph_started = time.monotonic()
            for attempt in range(3):
                try:
                    graph_result = _reindex_graph(
                        rel,
                        file_content=file_content or "",
                        chain=graph_chain[1],
                        db_path=db_path,
                        project_root=project_root,
                        link_stubs=link_stubs,
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if not _is_retryable_lock_error(exc):
                        break
                    time.sleep(0.05 * (2**attempt))
            graph_duration_ms = int((time.monotonic() - graph_started) * 1000)
            if last_error is not None:
                logger.debug(
                    "graph reindex failed for %s after retries: %s",
                    rel,
                    last_error,
                )
                result["layers"]["graph"] = {
                    "status": "error",
                    "reason": str(last_error),
                }
            elif graph_result is not None:
                graph_result["chain"] = graph_chain[0]
                graph_result["duration_ms"] = graph_duration_ms
                result["layers"]["graph"] = graph_result
                if content_hash is not None:
                    _record_state_safe(
                        rel,
                        content_hash=content_hash,
                        chain_key=",".join(graph_chain[1]),
                        nodes_written=int(graph_result.get("nodes_written") or 0),
                        edges_written=int(graph_result.get("edges_written") or 0),
                        parse_errors_count=len(graph_result.get("parse_errors") or []),
                        last_error=None,
                        project_root=project_root,
                        db_path=db_path,
                        advance_hash=graph_result.get("status") == "ok",
                        duration_ms=graph_duration_ms,
                    )

            if last_error is not None and content_hash is not None:
                _record_state_safe(
                    rel,
                    content_hash=content_hash,
                    chain_key=",".join(graph_chain[1]),
                    nodes_written=0,
                    edges_written=0,
                    parse_errors_count=0,
                    last_error=str(last_error),
                    project_root=project_root,
                    db_path=db_path,
                    advance_hash=False,
                )

    if not result["layers"]:
        result["status"] = "skipped"
        result["reason"] = "no layer matched"

    # Cache marker: "hit" only when *every* layer we executed came from
    # cache. "bypass" when force=True. "miss" otherwise.
    if force:
        result["cache"] = "bypass"
    elif result["layers"] and all(
        isinstance(layer, dict) and layer.get("cache") == "hit"
        for layer in result["layers"].values()
    ):
        result["cache"] = "hit"
    elif any(
        isinstance(layer, dict) and layer.get("cache") == "hit"
        for layer in result["layers"].values()
    ):
        result["cache"] = "partial"
    else:
        result["cache"] = "miss"

    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    return result


# ---------------------------------------------------------------------------
# file_index_state helpers
# ---------------------------------------------------------------------------


def _lookup_cache(
    rel_path: str,
    *,
    content_hash: str,
    graph_chain_key: str | None,
    graph_chain_list: list[str] | None,
    docs_in_scope: bool,
    project_root: Path,
    db_path: str | None,
) -> dict[str, dict[str, Any]]:
    """Probe ``file_index_state`` for layers whose hash+chain still match.

    Returns a dict keyed by layer name (``docs`` / ``graph``) carrying a
    pre-shaped skip envelope so the caller can slot it straight into the
    result.  Never raises — a missing DB / table just yields no hits.
    """
    hits: dict[str, dict[str, Any]] = {}
    try:
        conn = _open_conn(project_root=project_root, db_path=db_path)
    except Exception as exc:
        logger.debug("cache lookup: conn open failed: %s", exc)
        return hits
    try:
        if not _has_state_table(conn):
            return hits
        # Graph chain lookup — chain join must match exactly.
        if graph_chain_list:
            chain_key = ",".join(graph_chain_list)
            row = conn.execute(
                "SELECT content_hash, nodes_written, edges_written, "
                "parse_errors_count, last_indexed_at, last_error "
                "FROM file_index_state "
                "WHERE file_path = ? AND extractor_chain = ?",
                (rel_path, chain_key),
            ).fetchone()
            if row and row[0] == content_hash and row[5] is None:
                hits["graph"] = {
                    "status": "skipped",
                    "reason": "unchanged",
                    "cache": "hit",
                    "chain": graph_chain_key or "",
                    "nodes_written": int(row[1]),
                    "edges_written": int(row[2]),
                    "parse_errors_count": int(row[3]),
                    "last_indexed_at": int(row[4]),
                }
        # Docs layer lookup.
        if docs_in_scope:
            row = conn.execute(
                "SELECT content_hash, last_indexed_at, last_error "
                "FROM file_index_state "
                "WHERE file_path = ? AND extractor_chain = ?",
                (rel_path, _DOCS_CHAIN_KEY),
            ).fetchone()
            if row and row[0] == content_hash and row[2] is None:
                hits["docs"] = {
                    "status": "skipped",
                    "reason": "unchanged",
                    "cache": "hit",
                    "last_indexed_at": int(row[1]),
                }
    except Exception as exc:
        logger.debug("cache lookup failed: %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return hits


def _record_state_safe(
    rel_path: str,
    *,
    content_hash: str,
    chain_key: str,
    nodes_written: int,
    edges_written: int,
    parse_errors_count: int,
    last_error: str | None,
    project_root: Path,
    db_path: str | None,
    advance_hash: bool,
    duration_ms: int | None = None,
) -> None:
    """Upsert file_index_state; on failure keep previous hash (retry on next call).

    ``advance_hash=False`` preserves the prior content_hash (when a row
    exists) so a failing extractor doesn't claim the file is cached —
    the next dispatch will retry until it succeeds.
    """
    try:
        conn = _open_conn(project_root=project_root, db_path=db_path)
    except Exception as exc:
        logger.debug("state record: conn open failed: %s", exc)
        return
    try:
        if not _has_state_table(conn):
            return
        effective_hash = content_hash
        if not advance_hash:
            prev = conn.execute(
                "SELECT content_hash FROM file_index_state "
                "WHERE file_path = ? AND extractor_chain = ?",
                (rel_path, chain_key),
            ).fetchone()
            if prev is not None:
                effective_hash = prev[0]
        conn.execute(
            "INSERT OR REPLACE INTO file_index_state "
            "(file_path, content_hash, extractor_chain, nodes_written, "
            " edges_written, parse_errors_count, last_indexed_at, last_error, "
            " duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rel_path,
                effective_hash,
                chain_key,
                int(nodes_written),
                int(edges_written),
                int(parse_errors_count),
                int(time.time()),
                last_error,
                int(duration_ms) if duration_ms is not None else None,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.debug("state record failed for %s: %s", rel_path, exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _open_conn(*, project_root: Path, db_path: str | None):
    from thinking_os.database import init_db, resolve_db_path  # type: ignore

    effective_db = db_path or str(resolve_db_path(project_root))
    return init_db(effective_db)


def _has_state_table(conn) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_index_state'"
        ).fetchone()
    except Exception:
        return False
    return row is not None


# ---------------------------------------------------------------------------
# Layer implementations
# ---------------------------------------------------------------------------


def _reindex_docs(
    file_path: Path,
    *,
    project_root: Path,
    db_path: str | None,
) -> dict[str, Any]:
    from thinking_os.database import init_db, resolve_db_path  # type: ignore
    from thinking_os.doc_indexer import index_single_file  # type: ignore

    config_path = project_root / ".coding-os" / "rag-config.yaml"
    effective_db = db_path or str(resolve_db_path(project_root))
    conn = init_db(effective_db)
    try:
        return index_single_file(
            conn,
            file_path,
            project_root=project_root,
            config_path=config_path,
        )
    finally:
        conn.close()


def _reindex_graph(
    rel_path: str,
    *,
    file_content: str,
    chain: list[str],
    db_path: str | None,
    project_root: Path,
    link_stubs: bool = True,
) -> dict[str, Any]:
    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.extractors import (  # type: ignore
        code_go,
        code_json,
        code_python,
        code_shell,
        code_toml,
        code_ts,
        code_yaml,
        contracts,
        md_links,
        task_deps,
    )
    from thinking_os.database import init_db, resolve_db_path  # type: ignore

    extractor_map = {
        "code_go": code_go.extract,
        "code_json": code_json.extract,
        "code_python": code_python.extract,
        "code_ts": code_ts.extract,
        "code_shell": code_shell.extract,
        "code_toml": code_toml.extract,
        "code_yaml": code_yaml.extract,
        "contracts": contracts.extract,
        "md_links": md_links.extract,
        "task_deps": task_deps.extract,
    }

    effective_db = db_path or str(resolve_db_path(project_root))
    conn = init_db(effective_db)
    nodes_written = edges_written = nodes_pruned = 0
    parse_errors: list[dict[str, Any]] = []
    try:
        backend = SqliteBackend(conn=conn)
        # Prune stale rows from the file's previous run BEFORE re-
        # extracting so renamed / deleted symbols don't linger as
        # zombies (the rename-survives-as-extra-node bug). Scope the
        # delete to *this run's* extractor IDs so cross-file stubs
        # other extractors created for the same path stay intact.
        chain_extractor_ids: list[str] = []
        for name in chain:
            extractor = extractor_map.get(name)
            if extractor is None:
                continue
            module = sys.modules.get(extractor.__module__)
            extractor_id = getattr(module, "EXTRACTOR_ID", None) if module else None
            if isinstance(extractor_id, str):
                chain_extractor_ids.append(extractor_id)
        if chain_extractor_ids:
            try:
                nodes_pruned = backend.delete_nodes_for_file(
                    rel_path, extractors=chain_extractor_ids
                )
            except Exception as exc:
                logger.debug("prune-before-reindex skipped for %s: %s", rel_path, exc)

        for extractor_name in chain:
            extractor = extractor_map.get(extractor_name)
            if extractor is None:
                continue
            result = extractor(rel_path, file_content)
            parse_errors.extend(
                {"kind": p.kind, "detail": p.detail, "line": p.line} for p in result.parse_errors
            )
            n, e = backend.bulk_upsert(result.nodes, result.edges)
            nodes_written += n
            edges_written += e

        # TASK-043: a full `cos graph-reindex` passes link_stubs=False and runs
        # ONE global link_external_stubs() after the whole walk — per-file
        # linking mid-walk resolves a stub→real edge that a LATER file's
        # prune-before-reindex then orphans (cross-file edge into a not-yet-
        # stable node). Single-file auto-reindex keeps link_stubs=True so an
        # edit resolves immediately without waiting for a global pass.
        if link_stubs:
            try:
                backend.link_external_stubs(file_path=rel_path)
            except Exception as exc:
                logger.debug("stub linking suppressed for %s: %s", rel_path, exc)
    finally:
        conn.close()
    return {
        "status": "ok",
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "nodes_pruned": nodes_pruned,
        "parse_errors": parse_errors,
    }


def _main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--db", default=None)
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = dispatch(
        args.path,
        project_root=args.project_root,
        db_path=args.db,
        include_docs=not args.skip_docs,
        force=args.force,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        layers = report.get("layers", {})
        layer_summary = (
            ", ".join(f"{name}={info.get('status', 'unknown')}" for name, info in layers.items())
            or "no-op"
        )
        print(
            f"[reindex] {report.get('status', 'ok')}: {report['path']} "
            f"({layer_summary}) cache={report.get('cache')} "
            f"in {report['duration_ms']}ms"
        )
    return 0 if report.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["dispatch"]
