"""graph_os — Python extractor (I.4).

DEPENDS:  Python's stdlib `ast`; no tree-sitter / LSP unless
`COS_EXTRACTOR_PREFERENCE=tree-sitter` opts the import + heritage paths into the
tree-sitter overlay.

Module layout
  - `_python_uids`        uid grammar + path-to-module resolution (leaf)
  - `_python_decls`       declaration records + ast-to-text helpers (leaf)
  - `_python_tree_sitter` opt-in overlay for imports, heritage, decorators
  - `_python_visitor`     the ast walk + same-file name resolution
  - `_python_emit`        result assembly from collected visitor state
  - this module           parse bootstrap, overlay selection, and `extract()`
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import PurePosixPath

from ..types import GraphEdge, GraphNode
from ._python_decls import _module_docstring
from ._python_emit import (
    _emit_annotations,
    _emit_calls,
    _emit_declarations,
    _emit_decorators,
    _emit_file_spine,
    _emit_imports,
    _emit_inheritance,
)
from ._python_tree_sitter import (
    _heritage_via_tree_sitter,
    _imports_via_tree_sitter,
    _tree_sitter_heritage_active,
    _tree_sitter_imports_active,
)
from ._python_uids import (
    EXTRACTOR_ID,
    EXTRACTOR_ID_TS_IMPORTS,
    _absolute_module_for,  # noqa: F401  — pre-split re-export
    _module_name_for_path,
    class_uid,
    file_uid,
    function_uid,
    method_uid,
    module_uid,
)
from ._python_visitor import _PythonVisitor
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a `.py` file into nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_header = _module_docstring(content)

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="py",
        doc_blob=file_header,
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    try:
        tree = ast.parse(content, filename=normalised)
    except SyntaxError as exc:
        result.parse_errors.append(
            ParseError(
                kind="syntax_error",
                detail=f"{exc.msg} at line {exc.lineno}",
                line=exc.lineno,
            )
        )
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result
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

    mod_name = _module_name_for_path(normalised)
    mod_node = GraphNode(
        uid=module_uid(mod_name),
        kind="code:module",
        label=mod_name,
        file_path=normalised,
        lang="py",
        doc_blob=ast.get_docstring(tree) or file_header,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(mod_node)
    result.edges.append(
        GraphEdge(
            source_uid=file_node.uid,
            target_uid=mod_node.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    visitor = _PythonVisitor(path=normalised, module_name=mod_name, content=content)
    visitor.visit(tree)

    # Module-level call statements (e.g. ``_db_conn = init_db()`` at
    # server.py:51) are not captured during ``visitor.visit`` because the
    # visitor only walks call-sites inside ``visit_FunctionDef`` /
    # ``visit_AsyncFunctionDef``. After the visit completes, the scope
    # stack is back at module scope, so walking top-level non-decl
    # statements attributes their calls correctly to the module uid.
    # FunctionDef / ClassDef are skipped because their bodies were
    # already walked. Import / ImportFrom were registered by
    # ``visit_Import`` / ``visit_ImportFrom`` during generic_visit.
    for stmt in tree.body:
        if isinstance(
            stmt,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Import,
                ast.ImportFrom,
            ),
        ):
            continue
        visitor._walk_calls(stmt)

    # tree-sitter primary path for imports, opt-in via the
    # `--extractor=tree-sitter` flag. When active and the
    # grammar parse succeeds, replace the ast-derived import list with
    # the tree-sitter one and tag the emitted edges with
    # `code_python_ts@v1` so `provenance_for(...)` returns
    # `"tree-sitter"`.  When inactive (default) the legacy ast path
    # runs unchanged — zero regression risk for existing graphs.
    import_extractor_id = EXTRACTOR_ID
    if _tree_sitter_imports_active():
        ts_imports = _imports_via_tree_sitter(content)
        if ts_imports is not None:
            visitor.imports = ts_imports
            visitor.imported_local_names = {
                d.local_name: d for d in ts_imports if d.local_name != "*"
            }
            import_extractor_id = EXTRACTOR_ID_TS_IMPORTS

    # tree-sitter primary path for class heritage + decorators.
    # Same activation gate as imports — flips both paths in lock-step.
    heritage_extractor_id = EXTRACTOR_ID
    if _tree_sitter_heritage_active():
        ts_heritage = _heritage_via_tree_sitter(normalised, content)
        if ts_heritage is not None:
            ts_inherits, ts_decorators = ts_heritage
            visitor.inherits = ts_inherits
            # G1/G28: tree-sitter overlay misses module-level decorators
            # for some files (board_os/mcp_tools.py: 0 of 16 @safe_tool
            # captured). MERGE rather than overwrite — keep the AST's
            # decorators when tree-sitter's set is a strict subset.
            ast_dec_set = set(visitor.decorators_edges)
            ts_dec_set = set(ts_decorators)
            if ast_dec_set - ts_dec_set:
                # AST sees more — union and prefer.
                visitor.decorators_edges = list(ast_dec_set | ts_dec_set)
            else:
                visitor.decorators_edges = ts_decorators
            heritage_extractor_id = EXTRACTOR_ID_TS_IMPORTS

    _emit_declarations(
        result=result,
        visitor=visitor,
        normalised=normalised,
        module_uid_str=mod_node.uid,
    )
    _emit_inheritance(
        result=result,
        visitor=visitor,
        normalised=normalised,
        heritage_extractor_id=heritage_extractor_id,
    )
    _emit_annotations(result=result, visitor=visitor, normalised=normalised)
    _emit_decorators(
        result=result,
        visitor=visitor,
        normalised=normalised,
        heritage_extractor_id=heritage_extractor_id,
    )
    _emit_imports(
        result=result,
        visitor=visitor,
        normalised=normalised,
        module_uid_str=mod_node.uid,
        import_extractor_id=import_extractor_id,
    )
    _emit_calls(result=result, visitor=visitor, normalised=normalised)

    # S3: Folder→...→File CONTAINS spine (idempotent via uid).
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    _emit_file_spine(result=result, visitor=visitor, file_uid_str=file_node.uid)

    _promote_stubs(result)
    return result


__all__ = [
    "EXTRACTOR_ID",
    "class_uid",
    "extract",
    "file_uid",
    "function_uid",
    "method_uid",
    "module_uid",
]
