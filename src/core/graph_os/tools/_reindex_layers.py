"""Docs-layer, graph-layer and deletion-prune implementations behind the dispatcher."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from graph_os.tools._reindex_state import _open_conn

logger = logging.getLogger("graph_os.reindex_dispatch")


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


def _prune_graph_for_deleted_file(rel_path: str, *, db_path: str | None, project_root: Path) -> int:
    # D7-F1: prune ALL graph nodes for a path that was deleted on
    # disk (extractors=None deletes every node for the file, cascading to its
    # edges/evidence). Used by the read_error branch when the file is gone.
    from graph_os.backends.sqlite_backend import SqliteBackend
    from thinking_os.database import init_db, resolve_db_path  # type: ignore

    effective_db = db_path or str(resolve_db_path(project_root))
    conn = init_db(effective_db)
    backend = SqliteBackend(conn=conn)
    return backend.delete_nodes_for_file(rel_path)


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
        code_generic,
        code_go,
        code_json,
        code_php,
        code_python,
        code_shell,
        code_toml,
        code_ts,
        code_yaml,
        contracts,
        md_links,
        task_deps,
    )

    extractor_map = {
        "code_generic": code_generic.extract,
        "code_go": code_go.extract,
        "code_json": code_json.extract,
        "code_php": code_php.extract,
        "code_python": code_python.extract,
        "code_ts": code_ts.extract,
        "code_shell": code_shell.extract,
        "code_toml": code_toml.extract,
        "code_yaml": code_yaml.extract,
        "contracts": contracts.extract,
        "md_links": md_links.extract,
        "task_deps": task_deps.extract,
    }
    conn = _open_conn(project_root=project_root, db_path=db_path)
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

        # a full `cos graph-reindex` passes link_stubs=False and runs
        # ONE global link_external_stubs() after the whole walk — per-file
        # linking mid-walk resolves a stub→real edge that a LATER file's
        # prune-before-reindex then orphans (cross-file edge into a not-yet-
        # stable node). Single-file auto-reindex keeps link_stubs=True so an
        # edit resolves immediately without waiting for a global pass.
        if link_stubs:
            try:
                backend.link_external_stubs(file_path=rel_path)
                backend.link_import_bindings(file_path=rel_path)
                if rel_path.endswith(".php"):
                    backend.link_php_handlers()
            except Exception as exc:
                logger.debug("stub linking suppressed for %s: %s", rel_path, exc)
    finally:
        # Connection is the thread-cached one from _open_conn — never close.
        pass
    return {
        "status": "ok",
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "nodes_pruned": nodes_pruned,
        "parse_errors": parse_errors,
    }
