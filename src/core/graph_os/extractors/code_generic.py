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

Module layout:
  _generic_spec          extension routing + per-language node-type tables
  _generic_nodes         uid/name primitives and the baseline symbol walk
  _generic_edges_native  the hand-written rust and ruby edge hooks
  _generic_edges_table   the shared walker + handlers for the other 7 languages
  this module            the language->hook table and the extract() entry point
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath

from ..types import GraphNode
from ._generic_edges_native import _ruby_edges, _rust_edges
from ._generic_edges_table import _SPEC_HANDLERS as _SPEC_HANDLERS, _make_spec_edges
from ._generic_nodes import (
    _edge as _edge,
    _ext_uid as _ext_uid,
    _ext_unresolved_uid as _ext_unresolved_uid,
    _node_name as _node_name,
    _node_text as _node_text,
    _unique_uid as _unique_uid,
    _walk,
    file_uid,
)
from ._generic_spec import (
    _DECLARATOR_NAME_TYPES as _DECLARATOR_NAME_TYPES,
    _LANG_SPEC,
    _NAME_NODE_TYPES as _NAME_NODE_TYPES,
    EXT_TO_LANG,
    EXTRACTOR_ID,
)
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

try:
    from .. import tree_sitter_overlay as _ts_overlay

    _TS_AVAILABLE = _ts_overlay.is_available()
except ImportError:  # pragma: no cover - tree-sitter core absent
    _ts_overlay = None  # type: ignore[assignment]
    _TS_AVAILABLE = False

logger = logging.getLogger("graph_os.extractors.code_generic")


_LANG_EDGES = {
    "rust": _rust_edges,
    "ruby": _ruby_edges,
    **{lang: _make_spec_edges(lang) for lang in _SPEC_HANDLERS},
}


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

    # Per-language relationship edges (calls / imports / inherits) on top of
    # the baseline node walk. func/class indexes let same-file calls resolve
    # to real uids; everything else points at a code:external stub that the
    # post-walk link pass resolves cross-file (TASK-305).
    edge_hook = _LANG_EDGES.get(lang)
    if edge_hook is not None:
        func_index = {n.label: n.uid for n in result.nodes if n.kind == "code:function"}
        class_index = {n.label: n.uid for n in result.nodes if n.kind == "code:class"}
        try:
            edge_hook(parsed.root, content_bytes, file_uid_str, func_index, class_index, result)
        except Exception as exc:  # fail-open — baseline nodes already emitted
            logger.debug("edge hook failed for %s: %s", normalised, exc)
        _promote_stubs(result)

    err_count = sum(1 for _ in _ts_overlay.iter_nodes(parsed.root, {"ERROR"}))
    if err_count:
        result.parse_errors.append(
            ParseError(kind="tree_sitter_error", detail=f"{err_count} ERROR node(s)")
        )
    return result


__all__ = ["EXTRACTOR_ID", "EXT_TO_LANG", "extract", "file_uid"]
