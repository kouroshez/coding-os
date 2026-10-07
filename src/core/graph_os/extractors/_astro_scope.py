"""graph_os — an `.astro` client script is its own module.

Astro bundles each processed `<script>` apart from the frontmatter, so what it
imports and declares is not the frontmatter's: a script's symbol takes a
`script.` (then `script2.`, …) qualname, an edge drawn from inside a script
reaches the script's own symbol, and an edge drawn outside every script never
reaches a name only a script declares. `<script src="./x.ts">` imports x.ts.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..types import EvidenceSignal, GraphEdge
from ._astro_split import astro_scripts
from ._ts_regex_imports import _resolve_module_uid
from .md_links import ExtractionResult

SRC_CONFIDENCE = 0.85


def scope_scripts(
    result: ExtractionResult, text: str, *, path: str, module_uid: str, extractor: str
) -> None:
    """Give each processed client script of `text` its own symbol scope."""
    scripts = astro_scripts(text)
    ranges = [
        (text.count("\n", 0, script.body_start) + 1, text.count("\n", 0, script.body_end) + 1)
        for script in scripts
        if script.src is None
    ]
    renamed: list[dict[str, str]] = [{} for _ in ranges]
    outside: set[str] = set()
    for index, node in enumerate(result.nodes):
        scope = _scope(node.start_line, ranges) if node.file_path == path else None
        if "::" not in node.uid:
            continue
        if scope is None:
            outside.add(node.uid)
            continue
        prefix = "script" if scope == 0 else f"script{scope + 1}"
        head, _, qualname = node.uid.partition("::")
        renamed[scope][node.uid] = f"{head}::{prefix}.{qualname}"
        metadata = dict(node.metadata)
        if "qualname" in metadata:
            metadata["qualname"] = f"{prefix}.{metadata['qualname']}"
        result.nodes[index] = replace(node, uid=renamed[scope][node.uid], metadata=metadata)
    if any(renamed):
        result.edges[:] = _dedupe(
            variant
            for edge in result.edges
            for variant in _scoped(edge, renamed, outside, ranges, path)
        )
    for script in scripts:
        if script.src and script.src.startswith("."):
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid,
                    target_uid=_resolve_module_uid(path, script.src),
                    edge_type="imports",
                    extractor=extractor,
                    confidence=SRC_CONFIDENCE,
                    source_span=f"{path}:{script.line}",
                    evidence=(EvidenceSignal("astro_script_src", SRC_CONFIDENCE),),
                )
            )


def _scope(line: int | None, ranges: list[tuple[int, int]]) -> int | None:
    if line is None:
        return None
    return next(
        (index for index, (first, last) in enumerate(ranges) if first <= line <= last), None
    )


def _scoped(
    edge: GraphEdge,
    renamed: list[dict[str, str]],
    outside: set[str],
    ranges: list[tuple[int, int]],
    path: str,
) -> list[GraphEdge]:
    def local(uid: str) -> bool:
        return uid not in outside and any(uid in mapping for mapping in renamed)

    span_path, _, span_line = str(edge.source_span or "").rpartition(":")
    if span_path == path and span_line.isdigit():
        scope = _scope(int(span_line), ranges)
        if scope is not None:
            return [_through(edge, renamed[scope])]
        return [] if local(edge.target_uid) else [edge]
    # No span (`contains`): one copy for each scope that holds an endpoint.
    variants = [] if local(edge.source_uid) or local(edge.target_uid) else [edge]
    variants += [
        _through(edge, mapping)
        for mapping in renamed
        if edge.source_uid in mapping or edge.target_uid in mapping
    ]
    return variants


def _through(edge: GraphEdge, mapping: dict[str, str]) -> GraphEdge:
    return replace(
        edge,
        source_uid=mapping.get(edge.source_uid, edge.source_uid),
        target_uid=mapping.get(edge.target_uid, edge.target_uid),
    )


def _dedupe(edges: Any) -> list[GraphEdge]:
    seen: set[tuple[str, str, str, str | None]] = set()
    kept = []
    for edge in edges:
        key = (edge.source_uid, edge.target_uid, edge.edge_type, edge.source_span)
        if key not in seen:
            seen.add(key)
            kept.append(edge)
    return kept
