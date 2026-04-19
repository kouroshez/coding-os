"""indexer:graph-os role — run extractors on a file batch (I.9)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ...extractors import (
    code_python,
    code_shell,
    code_ts,
    code_yaml,
    contracts,
    md_links,
    task_deps,
)
from ..registry import Role, RoleContext, RoleResult

logger = logging.getLogger("graph_os.orchestrator.roles.indexer_graph_os")

ROLE_NAME = "indexer:graph-os"


def _pick_extractor(path: str):
    if path.endswith(".py"):
        return [code_python.extract, contracts.extract]
    if path.endswith(".ts") or path.endswith(".tsx"):
        return [code_ts.extract, contracts.extract]
    if path.endswith(".sh"):
        return [code_shell.extract]
    if path.endswith((".yaml", ".yml")):
        return [code_yaml.extract]
    if path.endswith(".md"):
        if "tasks/" in path:
            return [task_deps.extract, md_links.extract]
        return [md_links.extract]
    if path.endswith(".go"):
        return [contracts.extract]
    return []


def _handler(ctx: RoleContext) -> RoleResult:
    args = ctx.args
    backend = ctx.shared.get("backend")
    if backend is None:
        return RoleResult(status="error", error="shared.backend missing")

    file_path = args.get("path")
    content = args.get("content")
    if file_path is None or content is None:
        return RoleResult(status="error", error="args.path and args.content required")

    extractors = _pick_extractor(file_path)
    if not extractors:
        return RoleResult(
            status="skipped",
            payload={"reason": "no extractor for suffix", "path": file_path},
        )

    started = time.monotonic()
    nodes_written = 0
    edges_written = 0
    parse_errors: list[dict] = []
    for extractor in extractors:
        result = extractor(file_path, content)
        parse_errors.extend(
            {"kind": p.kind, "detail": p.detail, "line": p.line}
            for p in result.parse_errors
        )
        n, e = backend.bulk_upsert(result.nodes, result.edges)
        nodes_written += n
        edges_written += e
    duration_ms = int((time.monotonic() - started) * 1000)
    return RoleResult(
        status="ok",
        payload={
            "path": file_path,
            "nodes_written": nodes_written,
            "edges_written": edges_written,
            "parse_errors": parse_errors,
        },
        duration_ms=duration_ms,
    )


def build_role() -> Role:
    return Role(
        name=ROLE_NAME,
        handler=_handler,
        description="Fan-in extractor pipeline — pure per-file work.",
        max_concurrency=8,
    )


__all__ = ["ROLE_NAME", "build_role"]
