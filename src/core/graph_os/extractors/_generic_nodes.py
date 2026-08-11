"""code_generic — node primitives and the baseline symbol walk.

The floor every supported language gets for free: uid minting, name recovery
across grammars that disagree on where a name lives, and the recursive walk
that emits one node per function/class-like symbol with its `contains` edge.
Edge hooks build on these; nothing here knows about a specific language beyond
the tables it is handed.
"""

from __future__ import annotations

from typing import Any

from ..types import GraphEdge, GraphNode
from ._generic_spec import _DECLARATOR_NAME_TYPES, _NAME_NODE_TYPES, EXTRACTOR_ID
from .md_links import ExtractionResult, _normalize_path


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def _node_text(node: Any, content_bytes: bytes) -> str:
    try:
        return content_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _name_via_declarator(node: Any, content_bytes: bytes) -> str:
    # C / C++ keep the function name inside a nested `declarator` chain
    # (function_definition → function_declarator → identifier), NOT a `name`
    # field. Descend the declarator field to the leaf identifier so we get
    # `main`, not the return type `int`.
    cur = node
    for _ in range(6):
        nxt = cur.child_by_field_name("declarator")
        if nxt is None:
            break
        cur = nxt
    if cur is not None and cur.type in _DECLARATOR_NAME_TYPES:
        return _node_text(cur, content_bytes).strip()
    return ""


def _node_name(node: Any, content_bytes: bytes) -> str:
    # Most grammars expose the symbol name as the "name" field.
    named = node.child_by_field_name("name")
    if named is not None:
        text = _node_text(named, content_bytes).strip()
        if text:
            return text
    # C / C++ : name lives inside the declarator subtree, not a field.
    via_decl = _name_via_declarator(node, content_bytes)
    if via_decl:
        return via_decl
    # Rust impl_item carries the type under "type" instead of a name.
    typ = node.child_by_field_name("type")
    if typ is not None:
        text = _node_text(typ, content_bytes).strip()
        if text:
            return text
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            text = _node_text(child, content_bytes).strip()
            if text:
                return text
    return ""


def _unique_uid(kind: str, normalised: str, name: str, seen: set[str]) -> str:
    base = f"{kind}:{normalised}::{name}"
    uid = base
    n = 2
    # Deterministic disambiguation for same-named siblings (traversal order
    # is stable for identical content, so the suffix is stable across runs).
    while uid in seen:
        uid = f"{base}#{n}"
        n += 1
    seen.add(uid)
    return uid


def _walk(
    node: Any,
    *,
    parent_uid: str,
    spec: dict[str, frozenset[str]],
    normalised: str,
    lang: str,
    content_bytes: bytes,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    for child in node.children:
        kind: str | None = None
        if child.type in spec["func"]:
            kind = "code:function"
        elif child.type in spec["class"]:
            kind = "code:class"

        if kind is not None:
            name = _node_name(child, content_bytes)
            if name:
                uid = _unique_uid(kind, normalised, name, seen)
                result.nodes.append(
                    GraphNode(
                        uid=uid,
                        kind=kind,
                        label=name,
                        file_path=normalised,
                        start_line=child.start_point[0] + 1,
                        lang=lang,
                        metadata={"extractor": EXTRACTOR_ID, "ts_type": child.type},
                    )
                )
                result.edges.append(
                    GraphEdge(
                        source_uid=parent_uid,
                        target_uid=uid,
                        edge_type="contains",
                        extractor=EXTRACTOR_ID,
                        confidence=1.0,
                    )
                )
                # Descend with this symbol as parent so methods nest under
                # their class (file → class → method).
                _walk(
                    child,
                    parent_uid=uid,
                    spec=spec,
                    normalised=normalised,
                    lang=lang,
                    content_bytes=content_bytes,
                    result=result,
                    seen=seen,
                )
                continue

        _walk(
            child,
            parent_uid=parent_uid,
            spec=spec,
            normalised=normalised,
            lang=lang,
            content_bytes=content_bytes,
            result=result,
            seen=seen,
        )


def _ext_uid(name: str) -> str:
    return f"code:external:{name}"


def _ext_unresolved_uid(name: str) -> str:
    return f"code:external:unresolved:{name}"


def _edge(result: ExtractionResult, src: str, tgt: str, kind: str, conf: float) -> None:
    result.edges.append(
        GraphEdge(
            source_uid=src,
            target_uid=tgt,
            edge_type=kind,
            extractor=EXTRACTOR_ID,
            confidence=conf,
        )
    )
