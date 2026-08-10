"""graph_os — result assembly for the Python extractor.

Each function turns one slice of collected `_PythonVisitor` state into nodes and
edges on the shared `ExtractionResult`. Imports the visitor module for name
resolution and the two leaves; never imports the facade.
"""

from __future__ import annotations

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._python_decls import _hash_decl
from ._python_uids import EXTRACTOR_ID, EXTRACTOR_ID_TS_IMPORTS, module_uid
from ._python_visitor import (
    _annotation_confidence,
    _decorator_confidence,
    _inherit_confidence,
    _PythonVisitor,
    _resolve_call,
    _resolve_symbol,
)
from .md_links import ExtractionResult


def _emit_declarations(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    normalised: str,
    module_uid_str: str,
) -> None:
    # Emit decls + containment.
    for decl in visitor.decls:
        result.nodes.append(
            GraphNode(
                uid=decl.uid,
                kind=decl.kind,
                label=decl.name,
                file_path=normalised,
                start_line=decl.line,
                end_line=decl.end_line,
                signature=decl.signature,
                lang="py",
                doc_blob=decl.docstring,
                ast_hash=_hash_decl(decl),
                metadata={
                    "qualname": decl.qualname,
                    "decorators": list(decl.decorators),
                    "is_method": decl.is_method,
                    "extractor": EXTRACTOR_ID,
                },
            )
        )
        parent = decl.parent_uid or module_uid_str
        result.edges.append(
            GraphEdge(
                source_uid=parent,
                target_uid=decl.uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{normalised}:{decl.line}",
            )
        )


def _emit_inheritance(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    normalised: str,
    heritage_extractor_id: str,
) -> None:
    # Inheritance.
    inherit_signal = (
        "tree_sitter_base_class"
        if heritage_extractor_id == EXTRACTOR_ID_TS_IMPORTS
        else "ast_base_class"
    )
    for subclass_uid, base_name in visitor.inherits:
        result.edges.append(
            GraphEdge(
                source_uid=subclass_uid,
                target_uid=_resolve_symbol(base_name, path=normalised, visitor=visitor),
                edge_type="inherits_from",
                extractor=heritage_extractor_id,
                confidence=_inherit_confidence(base_name, visitor),
                source_span=f"{normalised}",
                evidence=(EvidenceSignal(inherit_signal, 0.9),),
            )
        )


def _emit_annotations(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    normalised: str,
) -> None:
    # type annotations — has_param_type / returns_type / field_of_type.
    for fn_uid, type_name in visitor.param_types:
        result.edges.append(
            GraphEdge(
                source_uid=fn_uid,
                target_uid=_resolve_symbol(type_name, path=normalised, visitor=visitor),
                edge_type="has_param_type",
                extractor=EXTRACTOR_ID,
                confidence=_annotation_confidence(type_name, visitor),
                source_span=normalised,
                evidence=(EvidenceSignal("ast_annotation", 0.9),),
            )
        )
    for fn_uid, type_name in visitor.return_types:
        result.edges.append(
            GraphEdge(
                source_uid=fn_uid,
                target_uid=_resolve_symbol(type_name, path=normalised, visitor=visitor),
                edge_type="returns_type",
                extractor=EXTRACTOR_ID,
                confidence=_annotation_confidence(type_name, visitor),
                source_span=normalised,
                evidence=(EvidenceSignal("ast_annotation", 0.9),),
            )
        )
    for field_stub, type_name in visitor.field_types:
        result.edges.append(
            GraphEdge(
                source_uid=field_stub,
                target_uid=_resolve_symbol(type_name, path=normalised, visitor=visitor),
                edge_type="field_of_type",
                extractor=EXTRACTOR_ID,
                confidence=_annotation_confidence(type_name, visitor),
                source_span=normalised,
                evidence=(EvidenceSignal("ast_annotation", 0.9),),
            )
        )


def _emit_decorators(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    normalised: str,
    heritage_extractor_id: str,
) -> None:
    # Decorators — is_decorated_by.
    decorator_signal = (
        "tree_sitter_decorator"
        if heritage_extractor_id == EXTRACTOR_ID_TS_IMPORTS
        else "ast_decorator"
    )
    for decorated_uid, dec_name in visitor.decorators_edges:
        result.edges.append(
            GraphEdge(
                source_uid=decorated_uid,
                target_uid=_resolve_symbol(dec_name, path=normalised, visitor=visitor),
                edge_type="is_decorated_by",
                extractor=heritage_extractor_id,
                confidence=_decorator_confidence(dec_name, visitor),
                evidence=(EvidenceSignal(decorator_signal, 0.9),),
            )
        )


def _emit_imports(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    normalised: str,
    module_uid_str: str,
    import_extractor_id: str,
) -> None:
    # Imports.
    for imp in visitor.imports:
        # E2 fix: drop {imp.line} from UID so blank-line insertion above
        # an import doesn't spawn a duplicate node. Line is still carried
        # in start_line.
        imp_uid = f"code:import:{normalised}::{imp.local_name}"
        result.nodes.append(
            GraphNode(
                uid=imp_uid,
                kind="code:import",
                label=f"import {imp.local_name}",
                file_path=normalised,
                start_line=imp.line,
                lang="py",
                metadata={
                    "source_module": imp.source_module,
                    "imported": imp.imported,
                    "wildcard": imp.is_wildcard,
                    "extractor": import_extractor_id,
                },
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=imp_uid,
                edge_type="contains",
                extractor=import_extractor_id,
                confidence=1.0,
            )
        )
        target_mod = imp.source_module or imp.imported
        signal_name = (
            "tree_sitter_import" if import_extractor_id == EXTRACTOR_ID_TS_IMPORTS else "ast_import"
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=module_uid(target_mod),
                edge_type="imports",
                extractor=import_extractor_id,
                confidence=0.9,
                source_span=f"{normalised}:{imp.line}",
                evidence=(EvidenceSignal(signal_name, 0.9),),
            )
        )
        # R3: wildcard `from .X import *` is also a re-export from the
        # current module's surface — emit an explicit re_exports edge so
        # consumers see what this module redistributes.
        if imp.is_wildcard:
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid_str,
                    target_uid=module_uid(target_mod),
                    edge_type="re_exports",
                    extractor=import_extractor_id,
                    confidence=0.9,
                    source_span=f"{normalised}:{imp.line}",
                    evidence=(EvidenceSignal("wildcard_import", 0.9),),
                )
            )


def _emit_calls(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    normalised: str,
) -> None:
    # Calls. These are the hardest — the pure-Python baseline uses the
    # 3-step subset of the 7-step lookup (same-scope, enclosing-scope,
    # explicit-import). Unresolved references get confidence 0.3 and an
    # `unresolved_call` evidence signal so the LSP overlay can lift
    # them to 0.95 later without double-writing.
    for call in visitor.calls:
        confidence, evidence, resolved_uid = _resolve_call(call, visitor=visitor, path=normalised)
        if resolved_uid is None:
            continue
        # E5: `await X()` — emit `awaits` instead of `calls`.
        # E11: name-only `Foo()` heuristic over-tags `Path()` / `Counter()`
        # as `constructs`. Promote to `constructs` only when resolved
        # target is a real `code:class:*` node; demote otherwise.
        if call.is_await:
            edge_type = "awaits"
        elif call.is_constructor_like and resolved_uid.startswith("code:class:"):
            edge_type = "constructs"
        else:
            edge_type = "calls"
        result.edges.append(
            GraphEdge(
                source_uid=call.caller_uid,
                target_uid=resolved_uid,
                edge_type=edge_type,
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{normalised}:{call.line}",
                evidence=evidence,
            )
        )
        # E6: dispatches — when a call arg is a known function uid the
        # caller is dispatching that fn (registry.register(fn) etc.).
        # Emit secondary `dispatches` edges; confidence 0.8 (heuristic
        # but only fires on local resolved symbols).
        for dispatched_uid in call.dispatched_uids:
            result.edges.append(
                GraphEdge(
                    source_uid=call.caller_uid,
                    target_uid=dispatched_uid,
                    edge_type="dispatches",
                    extractor=EXTRACTOR_ID,
                    confidence=0.8,
                    source_span=f"{normalised}:{call.line}",
                    evidence=(EvidenceSignal("callable_arg", 0.8),),
                )
            )


def _emit_file_spine(
    *,
    result: ExtractionResult,
    visitor: _PythonVisitor,
    file_uid_str: str,
) -> None:
    # S3: File→Class / File→Function / Class→Method ``contains`` edges.
    # The AST visitor already wires Module→decl and Class→Method; we
    # add File→Class, File→Function, and File→Method(top-level) so the
    # tree-view has a direct spine that bypasses the module node. These
    # are idempotent thanks to the backend's (source,target,edge_type,
    # extractor) uniqueness constraint.
    for decl in visitor.decls:
        if (decl.kind == "code:class" and decl.parent_uid is None) or (
            decl.kind == "code:function" and decl.parent_uid is None
        ):
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_str,
                    target_uid=decl.uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
