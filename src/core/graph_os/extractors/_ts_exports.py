"""graph_os — what a TS / JS module exports beyond its functions and classes.

An exported value with no function or class behind it — a store, a query
client, design tokens, `memo(Card)` — had no node, so every import of it
dangled. And a default import names the module's default export, whatever the
importer calls it locally: the default export is marked so the linker can bind
`import Anything from './Card'` to it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..types import GraphEdge, GraphNode
from ._fingerprint import body_fields
from ._ts_nodes import _ts_line
from ._ts_uids import EXTRACTOR_ID_TS, function_uid
from .md_links import ExtractionResult, _normalize_path

_VARIABLE_STATEMENTS = frozenset({"lexical_declaration", "variable_declaration"})
_DECLARATION_NAMES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
    }
)
_ANONYMOUS_FUNCTIONS = frozenset(
    {"function_expression", "function", "arrow_function", "function_declaration", "class"}
)


def variable_uid(path: str, name: str) -> str:
    return f"code:variable:{_normalize_path(path)}::{name}"


def emit_exports(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    file_uid_: str,
    lang: str,
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    declarators = _top_level_declarators(root)
    exported: dict[str, str] = {}
    default_target: Any = None
    default_name: str | None = None
    for statement in root.named_children:
        if statement.type != "export_statement":
            continue
        declaration = _unwrap(statement.child_by_field_name("declaration"))
        if _is_default(statement):
            default_target = declaration or statement.child_by_field_name("value")
            default_name = _exported_name(default_target)
        elif declaration is not None and declaration.type in _VARIABLE_STATEMENTS:
            exported.update((name, name) for name in _declared_names(declaration))
        elif declaration is not None and declaration.type == "function_signature":
            _emit_signature(declaration, path, (module_uid_, file_uid_), lang, local_names, result)
        elif statement.child_by_field_name("source") is None:
            for local, alias in _clause_names(statement):
                if alias == "default":
                    default_name = local
                else:
                    exported[local] = alias
    values: dict[str, str] = {}
    for local in exported:
        if local in local_names or local not in declarators:
            continue
        values[local] = variable_uid(path, local)
        _emit(
            values[local],
            local,
            declarators[local],
            path,
            (module_uid_, file_uid_),
            lang,
            _value_metadata(declarators[local]),
            result,
        )
    known = {**local_names, **values}
    if default_name and default_name in known:
        _mark(known[default_name], result)
    elif default_name and default_name in declarators:
        uid = variable_uid(path, default_name)
        metadata = {**_value_metadata(declarators[default_name]), "default_export": True}
        _emit(
            uid,
            default_name,
            declarators[default_name],
            path,
            (module_uid_, file_uid_),
            lang,
            metadata,
            result,
        )
    elif default_target is not None:
        # `export default () => …` or `export default {…}`: the export is anonymous.
        anonymous = default_target.type in _ANONYMOUS_FUNCTIONS
        uid = function_uid(path, "default") if anonymous else variable_uid(path, "default")
        metadata = {"extractor": EXTRACTOR_ID_TS, "default_export": True}
        kind = "code:function" if anonymous else "code:variable"
        _emit(
            uid,
            "default",
            default_target,
            path,
            (module_uid_, file_uid_),
            lang,
            metadata,
            result,
            kind=kind,
        )


def _unwrap(declaration: Any) -> Any:
    # `export declare const X: T` wraps the declaration in an ambient node.
    if declaration is not None and declaration.type == "ambient_declaration":
        return next(iter(declaration.named_children), None)
    return declaration


def emit_ambient(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    file_uid_: str,
    lang: str,
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """The globals a declaration file adds: `declare function`, `declare const`, `declare global`."""
    containers = (module_uid_, file_uid_)
    stack = [child for child in root.named_children if child.type == "ambient_declaration"]
    while stack:
        for child in stack.pop().named_children:
            if child.type == "function_signature":
                _emit_signature(child, path, containers, lang, local_names, result, exported=False)
            elif child.type in _VARIABLE_STATEMENTS:
                for declarator in child.named_children:
                    name = declarator.child_by_field_name("name")
                    label = (
                        name.text.decode("utf-8", "replace")
                        if name is not None and name.text
                        else ""
                    )
                    if (
                        declarator.type == "variable_declarator"
                        and label
                        and label not in local_names
                    ):
                        local_names[label] = variable_uid(path, label)
                        metadata = {"extractor": EXTRACTOR_ID_TS, "ambient": True}
                        _emit(
                            local_names[label],
                            label,
                            declarator,
                            path,
                            containers,
                            lang,
                            metadata,
                            result,
                        )
            elif child.type in ("statement_block", "internal_module", "module"):
                stack.append(child)


def _emit_signature(
    signature: Any,
    path: str,
    containers: tuple[str, str],
    lang: str,
    local_names: dict[str, str],
    result: ExtractionResult,
    *,
    exported: bool = True,
) -> None:
    name = signature.child_by_field_name("name")
    label = name.text.decode("utf-8", "replace") if name is not None and name.text else ""
    if label and label not in local_names:
        local_names[label] = function_uid(path, label)
        metadata = {"extractor": EXTRACTOR_ID_TS, "exported": exported, "ambient": True}
        _emit(
            local_names[label],
            label,
            signature,
            path,
            containers,
            lang,
            metadata,
            result,
            kind="code:function",
        )


def _top_level_declarators(root: Any) -> dict[str, Any]:
    declarators: dict[str, Any] = {}
    for statement in root.named_children:
        declaration = _unwrap(statement)
        if statement.type == "export_statement":
            declaration = _unwrap(statement.child_by_field_name("declaration"))
        if declaration is None or declaration.type not in _VARIABLE_STATEMENTS:
            continue
        for declarator in declaration.named_children:
            name = (
                declarator.child_by_field_name("name")
                if declarator.type == "variable_declarator"
                else None
            )
            if name is not None and name.type == "identifier" and name.text:
                declarators[name.text.decode("utf-8", "replace")] = declarator
    return declarators


def _declared_names(declaration: Any) -> list[str]:
    names = []
    for declarator in declaration.named_children:
        name = (
            declarator.child_by_field_name("name")
            if declarator.type == "variable_declarator"
            else None
        )
        if name is not None and name.type == "identifier" and name.text:
            names.append(name.text.decode("utf-8", "replace"))
    return names


def _clause_names(statement: Any) -> list[tuple[str, str]]:
    clause = next(
        (child for child in statement.named_children if child.type == "export_clause"), None
    )
    names = []
    for specifier in clause.named_children if clause is not None else []:
        name, alias = specifier.child_by_field_name("name"), specifier.child_by_field_name("alias")
        if name is not None and name.text:
            local = name.text.decode("utf-8", "replace")
            names.append(
                (
                    local,
                    alias.text.decode("utf-8", "replace")
                    if alias is not None and alias.text
                    else local,
                )
            )
    return names


def _value_metadata(declarator: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {"extractor": EXTRACTOR_ID_TS, "exported": True}
    value = declarator.child_by_field_name("value")
    if value is not None and value.type == "call_expression":
        callee = value.child_by_field_name("function")
        if callee is not None and callee.text:
            metadata["wrapped"] = callee.text.decode("utf-8", "replace")
    return metadata


def _is_default(statement: Any) -> bool:
    return any(child.type == "default" for child in statement.children)


def _exported_name(target: Any) -> str | None:
    # `export default Card`, `export default memo(Card)`, `connect(map)(Card)`.
    while target is not None:
        if target.type == "identifier":
            return target.text.decode("utf-8", "replace") if target.text else None
        if target.type in _DECLARATION_NAMES:
            name = target.child_by_field_name("name")
            return name.text.decode("utf-8", "replace") if name is not None and name.text else None
        if target.type != "call_expression":
            return None
        arguments = target.child_by_field_name("arguments")
        named = [a for a in (arguments.named_children if arguments else []) if a.type != "comment"]
        target = named[0] if named else None
    return None


def _mark(uid: str, result: ExtractionResult) -> None:
    for index, node in enumerate(result.nodes):
        if node.uid == uid:
            result.nodes[index] = replace(node, metadata={**node.metadata, "default_export": True})
            return


def _emit(
    uid: str,
    label: str,
    declaration: Any,
    path: str,
    containers: tuple[str, str],
    lang: str,
    metadata: dict[str, Any],
    result: ExtractionResult,
    *,
    kind: str = "code:variable",
) -> None:
    result.nodes.append(
        GraphNode(
            uid=uid,
            kind=kind,
            label=label,
            file_path=path,
            start_line=_ts_line(declaration),
            lang=lang,
            metadata=metadata,
            **body_fields(declaration),
        )
    )
    result.edges.extend(
        GraphEdge(
            source_uid=container,
            target_uid=uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID_TS,
            confidence=1.0,
        )
        for container in containers
    )
