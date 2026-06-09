"""code_generic — table-driven baseline extractor for polyglot languages.

One extractor covers every language whose tree-sitter grammar is installed
AND whose function / class node-types appear in ``_LANG_SPEC``. It emits the
baseline that makes ``cos_graph_search`` / ``_similar`` / ``_context`` work
for a new language: the file node, the folder ``contains`` spine, and one
node per top-level/nested function- and class-like symbol with ``contains``
edges. Calls / imports / type edges are deliberately left to per-language
extractors — this is the floor, not the ceiling.

Coverage is the curated ``_LANG_SPEC`` set (rust + ruby ship with grammars;
java / c / cpp / c_sharp are code-ready, install the grammar to activate).
Adding a language = one ``_LANG_SPEC`` row + one overlay loader + the
``_EXT_MAP`` route, never a new extractor. Fail-open: a missing grammar or
unsupported extension records a parse error (surfaced by cos_graph_doctor,
TASK-293) and emits just the file node — never raises.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Any

from ..types import GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    emit_contains_spine,
)

try:
    from .. import tree_sitter_overlay as _ts_overlay

    _TS_AVAILABLE = _ts_overlay.is_available()
except ImportError:  # pragma: no cover - tree-sitter core absent
    _ts_overlay = None  # type: ignore[assignment]
    _TS_AVAILABLE = False

logger = logging.getLogger("graph_os.extractors.code_generic")
EXTRACTOR_ID = "code_generic@v1"

# Extension → overlay language id. Several extensions map to one grammar
# (.cc/.cpp/.hpp → cpp). The grammar must be registered in
# tree_sitter_overlay._LOADERS for the language to actually parse.
EXT_TO_LANG: dict[str, str] = {
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "c_sharp",
}

# Per-language tree-sitter node types that denote a function-like or
# class-like definition. Curated (not heuristic) so coverage is honest and
# reliable — ruby names methods `method`, rust uses `function_item`, etc.
_LANG_SPEC: dict[str, dict[str, frozenset[str]]] = {
    "rust": {
        # impl_item is intentionally excluded — it duplicates the struct/enum
        # name as a phantom class. Methods inside an impl are still captured
        # (they attach to the file); linking impl→type is per-language work.
        "func": frozenset({"function_item", "function_signature_item"}),
        "class": frozenset({"struct_item", "enum_item", "trait_item", "mod_item"}),
    },
    "ruby": {
        "func": frozenset({"method", "singleton_method"}),
        "class": frozenset({"class", "module"}),
    },
    "java": {
        "func": frozenset({"method_declaration", "constructor_declaration"}),
        "class": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
                "annotation_type_declaration",
            }
        ),
    },
    "c": {
        "func": frozenset({"function_definition"}),
        "class": frozenset({"struct_specifier", "union_specifier", "enum_specifier"}),
    },
    "cpp": {
        "func": frozenset({"function_definition"}),
        "class": frozenset(
            {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier"}
        ),
    },
    "c_sharp": {
        "func": frozenset(
            {"method_declaration", "constructor_declaration", "local_function_statement"}
        ),
        "class": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "struct_declaration",
                "enum_declaration",
                "record_declaration",
            }
        ),
    },
}

_NAME_NODE_TYPES = ("identifier", "type_identifier", "constant", "name", "field_identifier")


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def _node_text(node: Any, content_bytes: bytes) -> str:
    try:
        return content_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _node_name(node: Any, content_bytes: bytes) -> str:
    # Most grammars expose the symbol name as the "name" field; rust's
    # impl_item carries the type under "type" instead.
    for field in ("name", "type"):
        try:
            named = node.child_by_field_name(field)
        except Exception:
            named = None
        if named is not None:
            text = _node_text(named, content_bytes).strip()
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


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a polyglot source file → file + folder spine + symbol nodes."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    suffix = PurePosixPath(normalised).suffix.lower()
    lang = EXT_TO_LANG.get(suffix)
    file_uid_str = file_uid(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # File node + folder spine first, so the file is in the graph even when
    # the grammar is missing (its symbols just won't be).
    result.nodes.append(
        GraphNode(
            uid=file_uid_str,
            kind="code:file",
            label=PurePosixPath(normalised).name,
            file_path=normalised,
            lang=lang or "",
            content_hash=content_hash,
            metadata={"extractor": EXTRACTOR_ID},
        )
    )
    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid_str,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    spec = _LANG_SPEC.get(lang) if lang else None
    if spec is None:
        result.parse_errors.append(
            ParseError(kind="lang_unsupported", detail=f"no generic spec for {suffix or path}")
        )
        return result
    if not _TS_AVAILABLE or _ts_overlay is None:
        result.parse_errors.append(ParseError(kind="dep_missing", detail="tree-sitter core absent"))
        return result

    parsed = _ts_overlay.parse(lang, content)
    if parsed is None:
        result.parse_errors.append(
            ParseError(kind="dep_missing", detail=f"grammar '{lang}' not installed")
        )
        return result

    content_bytes = content.encode("utf-8")
    seen: set[str] = {file_uid_str}
    _walk(
        parsed.root,
        parent_uid=file_uid_str,
        spec=spec,
        normalised=normalised,
        lang=lang,
        content_bytes=content_bytes,
        result=result,
        seen=seen,
    )

    err_count = sum(1 for _ in _ts_overlay.iter_nodes(parsed.root, {"ERROR"}))
    if err_count:
        result.parse_errors.append(
            ParseError(kind="tree_sitter_error", detail=f"{err_count} ERROR node(s)")
        )
    return result


__all__ = ["EXTRACTOR_ID", "EXT_TO_LANG", "extract", "file_uid"]
