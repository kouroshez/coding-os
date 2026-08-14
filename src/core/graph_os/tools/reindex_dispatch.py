"""graph_os + docs unified auto-reindex dispatcher (V1 cache).

DEPENDS:  thinking_os/doc_indexer (for md), graph_os.extractors.*,
          graph_os.backends.sqlite_backend.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from graph_os.tools._reindex_layers import (
    _prune_graph_for_deleted_file as _prune_graph_for_deleted_file,
    _reindex_docs as _reindex_docs,
    _reindex_graph as _reindex_graph,
)
from graph_os.tools._reindex_routing import (
    _DEFAULT_TASK_PATH_FRAGMENTS as _DEFAULT_TASK_PATH_FRAGMENTS,
    _DOCS_CHAIN_KEY,
    _EXT_MAP,
    _is_retryable_lock_error as _is_retryable_lock_error,
    _is_task_path,
)
from graph_os.tools._reindex_state import (
    _has_state_table as _has_state_table,
    _lookup_cache,
    _open_conn as _open_conn,
    _record_state_safe,
)

logger = logging.getLogger("graph_os.reindex_dispatch")


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
    # Render-artifact / dependency dirs (.claude/.codex/.cursor, node_modules,
    # dist, .venv, …) are excluded by the bulk walker (DEFAULT_EXCLUDE). The
    # per-file auto-reindex path had no such guard, so a PostToolUse edit
    # inside a render dir indexed a phenotype COPY of a canonical src/ doc —
    # whose copied-in relative links resolve from the wrong depth and mint
    # broken file stubs (e.g. code:file:core/hooks/registry.yaml). Mirror the
    # walker's per-segment denylist so both paths agree.
    from graph_os.ingest.base import DEFAULT_EXCLUDE

    if any(part in DEFAULT_EXCLUDE for part in Path(rel).parts):
        return {
            "status": "skipped",
            "path": rel,
            "layers": {},
            "duration_ms": int((time.monotonic() - started) * 1000),
            "reason": "excluded-dir",
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
            # D7-F1: a read error on a path that no longer exists is
            # a DELETION, not a transient failure — still prune the file's graph
            # nodes so a deleted file doesn't leave orphans. A read error on a
            # path that DOES exist is transient (locked/encoding); keep the
            # error and leave its nodes intact.
            if not file_path.exists():
                try:
                    pruned = _prune_graph_for_deleted_file(
                        rel, db_path=db_path, project_root=project_root
                    )
                    result["layers"]["graph"] = {
                        "status": "pruned",
                        "reason": "deleted",
                        "nodes_pruned": pruned,
                    }
                except Exception as exc:
                    result["layers"]["graph"] = {
                        "status": "error",
                        "reason": f"prune_failed: {exc}",
                    }
            else:
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
