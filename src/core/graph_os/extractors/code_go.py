"""graph_os — Go source file extractor (tree-sitter-go primary, regex fallback).

Coverage targets Python parity for the Go ecosystem:

  Node kinds emitted
    - code:file              one per .go file
    - code:module            one per file (Go package); also the package
                             grouping node (uid `code:package:go:<dir>`,
                             canonical kind `module`)
    - code:function          top-level funcs, including init() and TestXxx/etc.
    - code:method            receiver-bound funcs `func (r *T) M()`
    - code:class             struct + interface + alias + generic type defs
    - code:variable          var-block and const-block specs
    - code:external          imports + cross-module qualified calls

  Edge kinds emitted
    - contains               file → module → {func, method, type, var, const}
    - imports                module → code:external:<import-path>
    - inherits_from          struct → embedded-field, interface → embedded-iface
    - field_of_type          struct → external/local field type
    - has_param_type         func/method → external/local param type
    - returns_type           func/method → external/local return type
    - constructs             func/method → composite literal target type
    - is_decorated_by        file → code:external:build-tag:<expr>
    - calls                  func/method → same-file callee, or a
                             `code:external:gopkg:<dir>:<name>` stub the linker
                             binds (other file of the package / in-repo import),
                             or `code:external:<import path>:<name>` (library)
    - handles_test           module → code:external:test:<func-name>

  Go specifics handled
    - generics: `func F[T any](…)` and `type Container[T any] struct{}` ;
      the receiver normaliser strips `[T]` so methods on `*C[T]` resolve.
    - pointer vs value receivers — both fold into the same method uid.
    - init() funcs flagged with metadata.init=true.
    - test funcs: TestXxx / BenchmarkXxx / ExampleXxx / FuzzXxx / TestMain
      annotated with metadata.test_kind so contracts can route them.
    - build tags: `//go:build linux,!cgo` becomes is_decorated_by edges.
    - blank, dot and aliased imports keep their alias in evidence.
    - embedded fields (anonymous struct fields) emit inherits_from edges.
    - embedded interfaces (method-less type_elem inside an interface)
      also emit inherits_from edges.
    - dotted call detection unchanged (regex pass).

Spec: docs/playbooks/polyglot-extractor-roadmap.md §4.3 (Epic C1).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from .. import resolve_go
from ..toolchain import get_active
from ..types import GraphEdge, GraphNode
from ._go_calls import _walk_composite_constructs, _walk_go_calls_ast
from ._go_package import GoImports, _walk_build_tags, _walk_imports, _walk_var_const
from ._go_regex import _PACKAGE_RE, _walk_regex
from ._go_routes import walk_fiber_routes
from ._go_symbols import _walk_function_decl, _walk_method_decl
from ._go_types import _walk_type_decl
from ._go_uids import (
    _TS_AVAILABLE,
    EXTRACTOR_ID,
    _classify_test_func,  # noqa: F401  — pre-split re-export
    _node_text,
    _parse_receiver,  # noqa: F401  — pre-split re-export
    _ts_overlay,
    class_uid,
    file_uid,
    func_uid,
    import_uid,
    method_uid,
    module_uid,
    package_symbol_stub,
    package_uid,
    variable_uid,
)
from .md_links import ExtractionResult, _normalize_path, _promote_stubs, emit_contains_spine


def _walk_ts(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    imports: GoImports,
    result: ExtractionResult,
) -> tuple[str, int]:
    """Walk a tree-sitter-go AST. Returns (package_name, error_count)."""
    seen_funcs: set[str] = set()
    seen_types: set[str] = set()
    seen_vars: set[str] = set()
    pkg_name = ""
    err_count = 0

    stack = [root]
    while stack:
        node = stack.pop()
        ntype = node.type
        if ntype == "ERROR":
            err_count += 1
            stack.extend(reversed(list(node.children)))
            continue
        if ntype == "package_clause":
            for ident in node.children:
                if ident.type == "package_identifier":
                    pkg_name = _node_text(ident, content_bytes)
                    break
        elif ntype == "function_declaration":
            _walk_function_decl(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_funcs,
            )
        elif ntype == "method_declaration":
            _walk_method_decl(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_funcs,
            )
        elif ntype == "type_declaration":
            _walk_type_decl(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_types,
            )
        elif ntype == "import_declaration":
            _walk_imports(
                node,
                content_bytes,
                module_uid_str=module_uid_str,
                result=result,
                imports=imports,
            )
        elif ntype == "var_declaration":
            _walk_var_const(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_vars,
                is_const=False,
            )
        elif ntype == "const_declaration":
            _walk_var_const(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_vars,
                is_const=True,
            )
        elif ntype == "composite_literal":
            _walk_composite_constructs(
                node,
                content_bytes,
                path=path,
                module_uid_str=module_uid_str,
                result=result,
            )
        stack.extend(reversed(list(node.children)))
    return pkg_name, err_count


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a Go source file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_uid_str = file_uid(path)
    module_uid_str = module_uid(path)
    directory = PurePosixPath(normalised).parent.as_posix()
    imports = GoImports(package_dir_for=_package_dir_resolver(normalised))

    # Cheap pkg_name probe via regex; tree-sitter overrides if it finds one.
    _pkg_match = _PACKAGE_RE.search(content)
    pkg_name = _pkg_match.group("name") if _pkg_match else ""
    used_ts = False
    if _TS_AVAILABLE and _ts_overlay is not None:
        parsed = _ts_overlay.parse("go", content)
        if parsed is not None:
            used_ts = True
            pkg_name, err_count = _walk_ts(
                parsed.root,
                content.encode("utf-8"),
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                imports=imports,
                result=result,
            )
            if err_count:
                from .md_links import ParseError

                result.parse_errors.append(
                    ParseError(
                        kind="tree_sitter_error",
                        detail=f"tree-sitter recorded {err_count} ERROR node(s)",
                    )
                )

    if not used_ts:
        pkg_name = _walk_regex(
            content,
            path=path,
            normalised=normalised,
            module_uid_str=module_uid_str,
            file_uid_str=file_uid_str,
            result=result,
        )

    if not pkg_name:
        pkg_name = PurePosixPath(normalised).stem

    # File node created last with full metadata (GraphNode is frozen).
    file_node = GraphNode(
        uid=file_uid_str,
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="go",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID, "package": pkg_name},
    )
    # Prepend so the file node leads its descendants in emission order.
    result.nodes.insert(0, file_node)

    module_node = GraphNode(
        uid=module_uid_str,
        kind="code:module",
        label=pkg_name,
        file_path=normalised,
        lang="go",
        metadata={"extractor": EXTRACTOR_ID, "package": pkg_name},
    )
    result.nodes.append(module_node)
    result.edges.append(
        GraphEdge(
            source_uid=file_uid_str,
            target_uid=module_uid_str,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    # Package node (shared across files of the same package).
    pkg_node_uid = package_uid(directory, pkg_name)
    result.nodes.append(
        GraphNode(
            # Go package node is a module-tier namespace; emit the canonical
            # `module` kind (uid keeps the `code:package:` namespace so it
            # never collides with the per-file module node) —
            uid=pkg_node_uid,
            kind="module",
            label=pkg_name,
            lang="go",
            metadata={"extractor": EXTRACTOR_ID, "directory": directory},
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=pkg_node_uid,
            target_uid=module_uid_str,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    _walk_build_tags(content, file_uid_str=file_uid_str, result=result)

    # Without a grammar `_walk_regex` already emitted its regex calls. With one,
    # the AST pass owns every call: the regex pass it used to add labelled
    # method calls on values (`err.Error`) as package calls — 58% of its stubs.
    if used_ts:
        _walk_go_calls_ast(
            parsed.root,
            content.encode("utf-8"),
            path=normalised,
            directory=directory,
            module_uid_str=module_uid_str,
            imports=imports.by_name,
            result=result,
        )
        walk_fiber_routes(
            parsed.root,
            content.encode("utf-8"),
            path=normalised,
            directory=directory,
            file_uid_str=file_uid_str,
            imports=imports.by_name,
            result=result,
        )
        _point_cross_file_types_at_package(result, normalised, directory, imports)
        _contain_symbols_in_file(result, normalised, file_uid_str)

    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid_str,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    _promote_stubs(result)
    return result


def _package_dir_resolver(normalised: str) -> Callable[[str], str | None]:
    context = get_active()
    if context is None or not context.repo_root:
        return lambda _import_path: None
    root = Path(context.repo_root)
    return lambda import_path: resolve_go.package_dir(normalised, import_path, root)


def _point_cross_file_types_at_package(
    result: ExtractionResult, normalised: str, directory: str, imports: GoImports
) -> None:
    # A type named here but declared in another file of the package used to
    # become `code:class:<this file>::T` — a phantom with no file. It now names
    # the package's stub, which the linker binds to the real declaration; a
    # qualified `pkg.T` goes through the import like a call does.
    local_prefix = f"code:class:{normalised}::"
    declared = {node.uid for node in result.nodes if node.uid.startswith(local_prefix)}
    for index, edge in enumerate(result.edges):
        source = _retarget_type(edge.source_uid, declared, local_prefix, directory, imports)
        target = _retarget_type(edge.target_uid, declared, local_prefix, directory, imports)
        if (source, target) != (edge.source_uid, edge.target_uid):
            result.edges[index] = replace(edge, source_uid=source, target_uid=target)


def _retarget_type(
    uid: str, declared: set[str], local_prefix: str, directory: str, imports: GoImports
) -> str:
    if uid.startswith(local_prefix) and uid not in declared:
        return package_symbol_stub(directory, uid[len(local_prefix) :])
    qualified = uid.removeprefix("code:external:")
    alias, _, name = qualified.partition(".")
    if qualified == uid or not name or alias not in imports.by_name:
        return uid
    import_path, package_dir = imports.by_name[alias]
    return (
        package_symbol_stub(package_dir, name)
        if package_dir
        else f"code:external:{import_path}:{name}"
    )


def _contain_symbols_in_file(result: ExtractionResult, normalised: str, file_uid_str: str) -> None:
    # File → symbol edges are what `detect_changes` and file-level impact walk
    # from; Go had only file → module → symbol, so both returned nothing.
    for node in list(result.nodes):
        if node.file_path == normalised and node.kind in _FILE_LEVEL_KINDS:
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_str,
                    target_uid=node.uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )


_FILE_LEVEL_KINDS = {"code:function", "code:method", "code:class"}


__all__ = [
    "EXTRACTOR_ID",
    "class_uid",
    "extract",
    "file_uid",
    "func_uid",
    "import_uid",
    "method_uid",
    "module_uid",
    "package_uid",
    "variable_uid",
]
