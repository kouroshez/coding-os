"""graph_os — tree-sitter overlay for Python imports, heritage and decorators.

Opt-in via `COS_EXTRACTOR_PREFERENCE=tree-sitter`; when inactive the facade
keeps the stdlib-`ast` path. Both entry points return None when the grammar is
unavailable so the caller falls back without a branch of its own.
"""

from __future__ import annotations

from ._python_decls import _ImportDecl
from ._python_uids import class_uid, function_uid, method_uid


def _tree_sitter_imports_active() -> bool:
    """True when imports should be parsed via tree-sitter.

    Activation conditions:
      - tree-sitter-python grammar is loadable, AND
      - COS_EXTRACTOR_PREFERENCE is "tree-sitter" (default `auto`
        keeps the legacy ast path so existing graphs don't double-emit
        edges with two different extractor tags during rollout).
    """
    import os as _os

    pref = (_os.environ.get("COS_EXTRACTOR_PREFERENCE") or "auto").lower()
    if pref != "tree-sitter":
        return False
    try:
        from ..tree_sitter_overlay import _load_language

        return _load_language("python") is not None
    except Exception:
        return False


def _imports_via_tree_sitter(content: str) -> list[_ImportDecl] | None:
    """Parse Python imports via tree-sitter.

    Notes:
      - Aliases are honoured: `from pkg.sub import Foo as F` keeps
        `imported="Foo"` and `local_name="F"`.
      - Wildcards (`from pkg import *`) emit a single `_ImportDecl`
        with `is_wildcard=True`.
      - Relative imports (`from . import X` / `from ..pkg import Y`)
        prepend the dot count to source_module to match ast semantics.
    """
    try:
        from ..tree_sitter_overlay import parse
    except ImportError:
        return None

    parsed = parse("python", content)
    if parsed is None:
        return None

    out: list[_ImportDecl] = []
    content_bytes = content.encode("utf-8")

    def _walk(node):
        # Pre-order walk; we only act on import_statement /
        # import_from_statement nodes — siblings recurse via children.
        kind = getattr(node, "type", None)
        if kind == "import_statement":
            _emit_import_statement(node, content_bytes, out)
            return
        if kind == "import_from_statement":
            _emit_import_from(node, content_bytes, out)
            return
        for child in node.children:
            _walk(child)

    _walk(parsed.root)
    out.sort(key=lambda d: d.line)
    return out


def _emit_import_statement(node, content_bytes: bytes, out: list[_ImportDecl]) -> None:
    """Handle `import X` / `import X as Y` / `import X, Y`."""
    # The tree-sitter Python grammar exposes each imported alias as a
    # `dotted_name` (or `aliased_import` when `as` is present) child.
    line = (node.start_point[0] if hasattr(node, "start_point") else 0) + 1
    for child in node.children:
        ctype = getattr(child, "type", None)
        if ctype == "dotted_name":
            name = _node_text(child, content_bytes)
            out.append(
                _ImportDecl(
                    source_module=None,
                    imported=name,
                    local_name=name.split(".")[0],
                    line=line,
                )
            )
        elif ctype == "aliased_import":
            name_node = child.child_by_field_name("name")
            alias_node = child.child_by_field_name("alias")
            if name_node is None or alias_node is None:
                continue
            name = _node_text(name_node, content_bytes)
            alias = _node_text(alias_node, content_bytes)
            out.append(
                _ImportDecl(
                    source_module=None,
                    imported=name,
                    local_name=alias,
                    line=line,
                )
            )


def _emit_import_from(node, content_bytes: bytes, out: list[_ImportDecl]) -> None:
    """Handle `from X import Y as Z`, `from . import X`, `from X import *`."""
    line = (node.start_point[0] if hasattr(node, "start_point") else 0) + 1
    module_node = node.child_by_field_name("module_name")
    name_nodes = list(node.children_by_field_name("name") or [])

    # Tree-sitter's grammar represents `from . import x` with a
    # `relative_import` or a series of `import_prefix` children for
    # the dots; rebuild the leading-dot count from the source text.
    module_text = ""
    if module_node is not None:
        module_text = _node_text(module_node, content_bytes)
    else:
        for child in node.children:
            if getattr(child, "type", None) == "relative_import":
                module_text = _node_text(child, content_bytes)
                break

    # Wildcard import: the body is a `*` token, no aliased_import children.
    is_wildcard = any(
        getattr(c, "type", None) == "wildcard_import"
        or (getattr(c, "type", None) == "*" and getattr(c, "is_named", True) is False)
        for c in node.children
    )
    if is_wildcard:
        out.append(
            _ImportDecl(
                source_module=module_text,
                imported="*",
                local_name="*",
                line=line,
                is_wildcard=True,
            )
        )
        return

    if not name_nodes:
        # Older grammars expose the imported names as `dotted_name` /
        # `aliased_import` children of the `import_from_statement`.
        name_nodes = [
            c
            for c in node.children
            if getattr(c, "type", None) in ("dotted_name", "aliased_import")
        ]

    for name_node in name_nodes:
        ntype = getattr(name_node, "type", None)
        if ntype == "aliased_import":
            inner_name = name_node.child_by_field_name("name")
            inner_alias = name_node.child_by_field_name("alias")
            if inner_name is None or inner_alias is None:
                continue
            imported = _node_text(inner_name, content_bytes)
            local = _node_text(inner_alias, content_bytes)
        elif ntype == "dotted_name":
            imported = _node_text(name_node, content_bytes)
            local = imported
        else:
            continue
        out.append(
            _ImportDecl(
                source_module=module_text,
                imported=imported,
                local_name=local,
                line=line,
            )
        )


def _node_text(node, content_bytes: bytes) -> str:
    try:
        return content_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _tree_sitter_heritage_active() -> bool:
    """True when class heritage and decorator edges should be parsed via
    tree-sitter.  Same activation rule as `_tree_sitter_imports_active`
    so a single ``--extractor=tree-sitter`` flag flips both paths in
    lock-step (TASK-119 + TASK-120)."""
    return _tree_sitter_imports_active()


def _heritage_via_tree_sitter(
    path: str,
    content: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]] | None:
    """Walk the tree-sitter Python AST and return ``(inherits, decorators)``.

    Notes:
      - Qualnames mirror the ast visitor (nested classes nest, nested
        functions still emit at module level for the ast path → we
        match that to keep edge counts identical).
      - Decorators are captured for both functions and classes.
      - Self / parent decorator chains preserve their dotted form
        (`a.b.c`) via tree-sitter's `attribute` node textual extent.
    """
    try:
        from ..tree_sitter_overlay import parse
    except ImportError:
        return None

    parsed = parse("python", content)
    if parsed is None:
        return None

    content_bytes = content.encode("utf-8")
    inherits: list[tuple[str, str]] = []
    decorators_edges: list[tuple[str, str]] = []

    def _walk(node, qual_stack: list[str], scope_uid: str | None) -> None:
        ntype = getattr(node, "type", None)
        if ntype == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            class_name = _node_text(name_node, content_bytes)
            new_qual = [*qual_stack, class_name]
            class_qualname = ".".join(new_qual)
            class_uid_ = class_uid(path, class_qualname)

            # Bases — `superclasses` field carries an `argument_list`.
            superclasses = node.child_by_field_name("superclasses")
            if superclasses is not None:
                for child in superclasses.children:
                    if getattr(child, "type", None) in (
                        "identifier",
                        "attribute",
                    ):
                        base_name = _node_text(child, content_bytes)
                        if base_name:
                            inherits.append((class_uid_, base_name))

            # Decorators — sibling `decorator` nodes that precede this
            # class_definition inside a `decorated_definition` parent.
            for dec_name in _decorator_names(node, content_bytes):
                decorators_edges.append((class_uid_, dec_name))

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    _walk(child, new_qual, class_uid_)
            return

        if ntype in ("function_definition", "async_function_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            fn_name = _node_text(name_node, content_bytes)
            new_qual = [*qual_stack, fn_name]
            qualname = ".".join(new_qual)
            in_class = scope_uid is not None and scope_uid.startswith("code:class:")
            uid = (
                method_uid(path, qualname)
                if in_class
                else function_uid(
                    path,
                    qualname,
                )
            )

            for dec_name in _decorator_names(node, content_bytes):
                decorators_edges.append((uid, dec_name))

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    _walk(child, new_qual, uid)
            return

        if ntype == "decorated_definition":
            # Recurse into the wrapped definition; the `_decorator_names`
            # helper handles the decorators attached to that definition.
            for child in node.children:
                _walk(child, qual_stack, scope_uid)
            return

        # Plain pass-through for module-level / unrelated nodes.
        for child in node.children:
            _walk(child, qual_stack, scope_uid)

    _walk(parsed.root, [], None)
    return inherits, decorators_edges


def _decorator_names(definition_node, content_bytes: bytes) -> list[str]:
    """Return dotted names for every decorator attached to
    ``definition_node`` (a class_definition or function_definition).

    The grammar nests the decorator(s) and the definition under a
    ``decorated_definition`` parent.  We walk parent siblings in
    document order so chained decorators preserve their original
    sequence — matching the ast visitor's iteration of
    ``node.decorator_list``.
    """
    parent = getattr(definition_node, "parent", None)
    if parent is None or getattr(parent, "type", None) != "decorated_definition":
        return []
    out: list[str] = []
    for child in parent.children:
        if child is definition_node:
            break
        if getattr(child, "type", None) == "decorator":
            # decorator → expression child carrying the dotted name.
            for inner in child.children:
                itype = getattr(inner, "type", None)
                if itype in ("identifier", "attribute", "call"):
                    text = _node_text(inner, content_bytes).strip()
                    if not text:
                        continue
                    # `@decorator(args)` → strip the `(...)` to keep the
                    # dotted name only, matching `_dotted_name(ast.Call)`.
                    if "(" in text:
                        text = text.split("(", 1)[0].strip()
                    if text:
                        out.append(text)
                    break
    return out
