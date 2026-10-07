"""graph_os — a Python file this interpreter cannot parse, read by tree-sitter.

A file written for a newer Python (`type Alias = …`, `def first[T]()`) is a
SyntaxError to an older host's `ast`, and the whole file used to vanish from
the graph. The grammar still reads its functions, classes, methods and
imports; they are named exactly as the `ast` path names them, and leave
through the same emitters. Calls and annotations need the `ast` walk.
"""

from __future__ import annotations

from typing import Any

from ._python_decls import _SymbolDecl
from ._python_tree_sitter import _imports_via_tree_sitter
from ._python_uids import class_uid, function_uid, method_uid
from ._python_visitor import _PythonVisitor

_DEFINITIONS = {"function_definition": "function", "class_definition": "class"}


def recovered_visitor(content: str, *, path: str, module_name: str) -> _PythonVisitor | None:
    from ..tree_sitter_overlay import parse

    parsed = parse("python", content)
    imports = _imports_via_tree_sitter(content)
    if parsed is None or imports is None:
        return None
    visitor = _PythonVisitor(path=path, module_name=module_name, content=content)
    visitor.imports = imports
    visitor.imported_local_names = {
        decl.local_name: decl for decl in imports if decl.local_name != "*"
    }
    _collect(parsed.root, content.encode("utf-8"), visitor, (), None)
    return visitor


def _collect(
    node: Any,
    content: bytes,
    visitor: _PythonVisitor,
    scope: tuple[str, ...],
    owner: tuple[str, str] | None,
) -> None:
    # `owner` is the enclosing (uid, kind): a def directly in a class is its method.
    for child in node.named_children:
        definition = (
            child.child_by_field_name("definition")
            if child.type == "decorated_definition"
            else child
        )
        kind = _DEFINITIONS.get(definition.type) if definition is not None else None
        if kind is None:
            _collect(child, content, visitor, scope, owner)
            continue
        name_node = definition.child_by_field_name("name")
        if name_node is None:
            continue
        name = content[name_node.start_byte : name_node.end_byte].decode("utf-8", "replace")
        qualname = ".".join((*scope, name))
        in_class = owner is not None and owner[1] == "class"
        if kind == "class":
            uid, decl_kind = class_uid(visitor.path, qualname), "code:class"
        elif in_class:
            uid, decl_kind = method_uid(visitor.path, qualname), "code:method"
        else:
            uid, decl_kind = function_uid(visitor.path, qualname), "code:function"
        visitor.decls.append(
            _SymbolDecl(
                uid=uid,
                kind=decl_kind,
                name=name,
                qualname=qualname,
                line=definition.start_point[0] + 1,
                end_line=definition.end_point[0] + 1,
                signature="",
                docstring=None,
                decorators=(),
                parent_uid=owner[0] if owner else None,
                is_method=in_class and kind == "function",
            )
        )
        visitor.symbols_by_name.setdefault(name, uid)
        if in_class and owner is not None and kind == "function":
            visitor.methods_by_class.setdefault(owner[0], {})[name] = uid
        _collect(definition, content, visitor, (*scope, name), (uid, kind))
