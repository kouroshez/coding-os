"""graph_os — Go edge rewrites that need the whole file's extraction.

A type named here but declared in another file of the package points at the
package stub the linker binds; a type parameter (`func F[Row any]`) is no type
at all; and every top-level symbol hangs off its file, which `detect_changes`
and file-level impact walk from.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..types import GraphEdge
from ._go_package import GoImports
from ._go_scopes import receiver_type_arguments
from ._go_uids import EXTRACTOR_ID, _node_text, package_symbol_stub
from .md_links import ExtractionResult


def rewrite_edges(
    result: ExtractionResult,
    root: Any,
    content_bytes: bytes,
    *,
    normalised: str,
    directory: str,
    file_uid_str: str,
    imports: GoImports,
) -> None:
    _drop_type_parameter_edges(result, normalised, _type_parameters(root, content_bytes))
    _point_cross_file_types_at_package(result, normalised, directory, imports)
    _contain_symbols_in_file(result, normalised, file_uid_str)


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
    # Only `pkg.Type`: an import path (`github.com/...`) or a call stub
    # (`<path>:<name>`) is no qualified type, whatever its first segment is.
    if qualified == uid or not (alias.isidentifier() and name.isidentifier()):
        return uid
    if alias not in imports.by_name:
        return uid
    import_path, package_dir = imports.by_name[alias]
    return (
        package_symbol_stub(package_dir, name)
        if package_dir
        else f"code:external:{import_path}:{name}"
    )


def _type_parameters(root: Any, content_bytes: bytes) -> set[str]:
    names: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "type_parameter_declaration":
            names.update(
                _node_text(name, content_bytes) for name in node.children_by_field_name("name")
            )
        elif node.type == "method_declaration":
            names.update(receiver_type_arguments(node, content_bytes))
        stack.extend(node.children)
    return names


def _drop_type_parameter_edges(
    result: ExtractionResult, normalised: str, type_parameters: set[str]
) -> None:
    # `func F[Row any](rows []Row)` named Row a package type: every generic
    # function minted a phantom type and an edge no definition could bind.
    if not type_parameters:
        return
    local_prefix = f"code:class:{normalised}::"
    declared = {node.uid for node in result.nodes if node.uid.startswith(local_prefix)}
    phantoms = {
        f"{local_prefix}{name}"
        for name in type_parameters
        if f"{local_prefix}{name}" not in declared
    }
    result.edges[:] = [edge for edge in result.edges if edge.target_uid not in phantoms]


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
