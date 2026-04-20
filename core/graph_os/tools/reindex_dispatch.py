"""graph-os + docs unified auto-reindex dispatcher (Phase I.14).

PURPOSE:  Called from `auto-reindex-docs.sh` PostToolUse hook. Routes
          a single file path to the correct extractor(s) based on
          extension, updates both the docs RAG index and the graph-os
          backend in one pass.
INPUT:    repo-relative file path + project root.
OUTPUT:   status dict (always returns — never raises).
DEPENDS:  thinking-os/doc_indexer (for md), graph_os.extractors.*,
          graph_os.backends.sqlite_backend.
NOTES:    Single entry point so both Claude PostToolUse (shell hook)
          and Codex opt-in background indexer can route through the
          same code path — zero drift between adapters.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("graph_os.reindex_dispatch")

_EXT_MAP = {
    ".py":  ("python",  ["code_python", "contracts"]),
    ".ts":  ("ts",      ["code_ts", "contracts"]),
    ".tsx": ("tsx",     ["code_ts", "contracts"]),
    ".sh":  ("shell",   ["code_shell"]),
    ".yaml":("yaml",    ["code_yaml"]),
    ".yml": ("yaml",    ["code_yaml"]),
    ".go":  ("go",      ["contracts"]),
}


def dispatch(
    file_path: str | Path,
    *,
    project_root: str | Path,
    db_path: str | None = None,
    include_docs: bool = True,
) -> dict[str, Any]:
    """Re-index `file_path` in both the docs layer and the graph layer.

    PURPOSE:      One call, one DB, both layers updated.
    INPUT:        absolute or repo-relative file path + project_root.
    OUTPUT:       {status, path, layers: {docs, graph}, duration_ms}.
    NOTES:        Catches every exception so the shell hook's fire-
                  and-forget contract holds.
    """
    started = time.monotonic()
    file_path = Path(file_path).resolve()
    project_root = Path(project_root).resolve()
    try:
        rel = str(file_path.relative_to(project_root))
    except ValueError:
        rel = str(file_path)
    suffix = file_path.suffix.lower()

    result: dict[str, Any] = {
        "status": "ok",
        "path": rel,
        "layers": {},
        "duration_ms": 0,
    }

    if include_docs and suffix == ".md":
        try:
            result["layers"]["docs"] = _reindex_docs(
                file_path, project_root=project_root, db_path=db_path
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("docs reindex failed for %s: %s", rel, exc)
            result["layers"]["docs"] = {"status": "error", "reason": str(exc)}

    chain: tuple[str, list[str]] | None = None
    if suffix in _EXT_MAP:
        chain = _EXT_MAP[suffix]
    elif suffix == ".md":
        chain = ("markdown", ["md_links"])
        if "/tasks/" in rel.replace("\\", "/"):
            chain = ("markdown-task", ["task_deps", "md_links"])
    if chain is not None:
        try:
            graph_result = _reindex_graph(
                rel,
                file_path,
                chain=chain[1],
                db_path=db_path,
            )
            graph_result["chain"] = chain[0]
            result["layers"]["graph"] = graph_result
        except Exception as exc:  # noqa: BLE001
            logger.debug("graph reindex failed for %s: %s", rel, exc)
            result["layers"]["graph"] = {"status": "error", "reason": str(exc)}

    if not result["layers"]:
        result["status"] = "skipped"
        result["reason"] = "no layer matched"

    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _reindex_docs(
    file_path: Path,
    *,
    project_root: Path,
    db_path: str | None,
) -> dict[str, Any]:
    _ensure_thinking_os_on_path()
    from db import init_db  # type: ignore
    from doc_indexer import index_single_file  # type: ignore

    config_path = project_root / ".coding-os" / "rag-config.yaml"
    effective_db = db_path or os.environ.get(
        "COS_DB_PATH", str(project_root / ".coding-os" / "thinking-os.db")
    )
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
    file_path: Path,
    *,
    chain: list[str],
    db_path: str | None,
) -> dict[str, Any]:
    _ensure_core_on_path()
    _ensure_thinking_os_on_path()
    from db import init_db  # type: ignore
    from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore
    from graph_os.extractors import (  # type: ignore
        code_python,
        code_shell,
        code_ts,
        code_yaml,
        contracts,
        md_links,
        task_deps,
    )

    extractor_map = {
        "code_python": code_python.extract,
        "code_ts": code_ts.extract,
        "code_shell": code_shell.extract,
        "code_yaml": code_yaml.extract,
        "contracts": contracts.extract,
        "md_links": md_links.extract,
        "task_deps": task_deps.extract,
    }

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return {"status": "error", "reason": f"read_failed: {exc}"}

    effective_db = db_path or os.environ.get(
        "COS_DB_PATH", str(file_path.parents[0] / ".coding-os" / "thinking-os.db")
    )
    conn = init_db(effective_db)
    nodes_written = edges_written = 0
    parse_errors: list[dict[str, Any]] = []
    try:
        backend = SqliteBackend(conn=conn)
        for extractor_name in chain:
            extractor = extractor_map.get(extractor_name)
            if extractor is None:
                continue
            result = extractor(rel_path, content)
            parse_errors.extend(
                {"kind": p.kind, "detail": p.detail, "line": p.line}
                for p in result.parse_errors
            )
            n, e = backend.bulk_upsert(result.nodes, result.edges)
            nodes_written += n
            edges_written += e
    finally:
        conn.close()
    return {
        "status": "ok",
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "parse_errors": parse_errors,
    }


def _ensure_thinking_os_on_path() -> None:
    here = Path(__file__).resolve()
    target = here.parent.parent.parent / "thinking-os"
    if target.exists() and str(target) not in sys.path:
        sys.path.insert(0, str(target))


def _ensure_core_on_path() -> None:
    here = Path(__file__).resolve()
    target = here.parent.parent.parent
    if target.exists() and str(target) not in sys.path:
        sys.path.insert(0, str(target))


def _main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--db", default=None)
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = dispatch(
        args.path,
        project_root=args.project_root,
        db_path=args.db,
        include_docs=not args.skip_docs,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        layers = report.get("layers", {})
        layer_summary = ", ".join(
            f"{name}={info.get('status', 'unknown')}"
            for name, info in layers.items()
        ) or "no-op"
        print(
            f"[reindex] {report.get('status', 'ok')}: {report['path']} "
            f"({layer_summary}) in {report['duration_ms']}ms"
        )
    return 0 if report.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["dispatch"]
