"""graph_os — TypeScript / TSX extractor (I.6).

DEPENDS:  stdlib regex only.

Module layout
  - `_ts_uids`          uid grammar + language constants (leaf; imports no sibling)
  - `_ts_nodes`         tree-sitter node/type primitives
  - `_ts_symbols`       AST-accurate declaration + call walk (parity path)
  - `_ts_regex_imports` regex import scan + module-specifier resolution
  - `_ts_regex_decls`   regex declaration scan
  - `_ts_regex_calls`   regex call-site + JSX scan
  - this module         parser bootstrap, path selection, and result assembly
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath

from ..types import GraphEdge, GraphNode
from ._ts_nodes import _count_ts_nodes
from ._ts_regex_calls import _extract_calls, _extract_jsx_components
from ._ts_regex_decls import (
    _extract_arrow_fns,
    _extract_classes,
    _extract_functions,
    _extract_interfaces,
)
from ._ts_regex_imports import (
    _apply_ts_path as _apply_ts_path,
    _extract_imports,
    _parse_clause as _parse_clause,
    _resolve_module_uid as _resolve_module_uid,
    _resolve_ts_alias as _resolve_ts_alias,
    _strip_comments,
    _strip_comments_and_strings,
)
from ._ts_symbols import _walk_ts_symbols
from ._ts_uids import (
    _TS_KEYWORDS as _TS_KEYWORDS,
    EXTRACTOR_ID,
    EXTRACTOR_ID_TS,
    _tree_sitter_ts_active,
    _ts_method_uid as _ts_method_uid,
    class_uid as class_uid,
    file_uid,
    function_uid as function_uid,
    interface_uid as interface_uid,
    module_uid,
)
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_ts")


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a TS / TSX file → nodes + edges."""
    # Tree-sitter overlay pass (I.6b) — runs first to enrich AST-level
    # metadata. Regex scan below continues unchanged so results stay
    # backwards-compatible when the grammar is absent.
    try:
        from ..tree_sitter_overlay import parse as _ts_parse

        lang_id = "tsx" if path.endswith((".tsx", ".jsx")) else "typescript"
        _ts_overlay = _ts_parse(lang_id, content)
    except ImportError:
        _ts_overlay = None
    result = ExtractionResult()
    normalised = _normalize_path(path)
    lang = "tsx" if normalised.endswith((".tsx", ".jsx")) else "ts"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang=lang,
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    try:
        import_scan = _strip_comments(content)
        decl_scan = _strip_comments_and_strings(content)
    except Exception as exc:
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    overlay_meta: dict[str, object] = {}
    if _ts_overlay is not None:
        overlay_meta["ts_ast_nodes"] = _count_ts_nodes(_ts_overlay.root)
        overlay_meta["ts_language"] = _ts_overlay.language_id
    module = GraphNode(
        uid=module_uid(path),
        kind="code:module",
        label=PurePosixPath(normalised).stem,
        file_path=normalised,
        lang=lang,
        metadata={"extractor": EXTRACTOR_ID, **overlay_meta},
    )
    result.nodes.append(module)
    result.edges.append(
        GraphEdge(
            source_uid=file_node.uid,
            target_uid=module.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    # tag imports as tree-sitter when the user opted in
    # AND the overlay parsed successfully (we already have a parsed
    # AST in `_ts_overlay`). The regex still extracts; the tag swap
    # signals "this came from grammar-validated TS" so the Hub UI
    # Inspector and provenance_for() consumers can distinguish.
    ts_override: str | None = None
    if _ts_overlay is not None and _tree_sitter_ts_active(lang_id):
        ts_override = EXTRACTOR_ID_TS

    imported_names = _extract_imports(
        path=normalised,
        module_uid_=module.uid,
        content=import_scan,
        result=result,
        extractor_override=ts_override,
    )
    local_names: dict[str, str] = {}
    if _ts_overlay is not None:
        # Parity path (default when grammar parsed): AST-accurate symbol/edge
        # extraction. Mirrors Python (ast) and Go (code_go@v2 tree-sitter).
        # Regex below is the fallback only when the grammar is unavailable.
        _walk_ts_symbols(
            _ts_overlay.root,
            path=normalised,
            module_uid_=module.uid,
            file_uid_=file_node.uid,
            lang=lang,
            imported_names=imported_names,
            local_names=local_names,
            result=result,
        )
    else:
        # Regex fallback (grammar absent) — backwards-compatible.
        _extract_classes(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_interfaces(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_functions(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_arrow_fns(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_calls(
            path=normalised,
            content=decl_scan,
            imported_names=imported_names,
            local_names=local_names,
            result=result,
        )
        if lang == "tsx":
            _extract_jsx_components(
                path=normalised,
                content=decl_scan,
                imported_names=imported_names,
                local_names=local_names,
                result=result,
            )

    # S3: Folder→...→File spine.
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    # S3: File→Class / File→Function / File→Interface direct ``contains``
    # edges (ts extractor already wires Module→decl; add File→decl for
    # the SPA tree-view spine). Uniqueness is enforced by the backend.
    for _name, decl_uid in local_names.items():
        if (
            decl_uid.startswith("code:class:")
            or decl_uid.startswith("code:function:")
            or decl_uid.startswith("code:interface:")
        ):
            result.edges.append(
                GraphEdge(
                    source_uid=file_node.uid,
                    target_uid=decl_uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )

    _promote_stubs(result)
    return result


__all__ = [
    "EXTRACTOR_ID",
    "class_uid",
    "extract",
    "file_uid",
    "function_uid",
    "interface_uid",
    "module_uid",
]
