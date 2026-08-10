"""graph_os — the stdlib-`ast` walk plus same-file name resolution.

`_PythonVisitor` collects declarations, imports, annotations and call-sites in a
single pass; the resolver functions turn a collected name into a uid and the
confidence that uid deserves. Imports the two leaves, never the facade.
"""

from __future__ import annotations

import ast
import re

from ..types import EvidenceSignal
from ._python_decls import (
    _BUILTIN_TYPES,
    _CallSite,
    _class_signature,
    _dotted_name,
    _function_param_annotations,
    _function_return_annotation,
    _function_signature,
    _ImportDecl,
    _SymbolDecl,
)
from ._python_uids import (
    _absolute_module_for,
    class_uid,
    function_uid,
    method_uid,
    module_uid,
)


class _PythonVisitor(ast.NodeVisitor):
    """Walk an AST once, collecting decls + imports + calls."""

    def __init__(self, *, path: str, module_name: str, content: str) -> None:
        self.path = path
        self.module_name = module_name
        self.content = content
        self.decls: list[_SymbolDecl] = []
        self.imports: list[_ImportDecl] = []
        self.inherits: list[tuple[str, str]] = []
        self.decorators_edges: list[tuple[str, str]] = []
        self.calls: list[_CallSite] = []
        # type-annotation edges discovered during the AST walk.
        # `param_types`     : (function_uid, type_name)
        # `return_types`    : (function_uid, type_name)
        # `field_types`     : (field_uid,    type_name) — field_uid is
        #                     the per-class field stub `<class_uid>.<name>`.
        self.param_types: list[tuple[str, str]] = []
        self.return_types: list[tuple[str, str]] = []
        self.field_types: list[tuple[str, str]] = []
        # Scope stack: the uid each new call-site counts as living inside.
        self._scope_uid_stack: list[str] = [module_uid(module_name)]
        # Qualname stack: dotted path for nested classes / functions.
        self._qualname_stack: list[str] = []
        # Name -> uid map for same-scope lookup (step 1 of 7-step lookup).
        self.symbols_by_name: dict[str, str] = {}
        # GE: per-class method map so `self.method()` resolves to THIS class's
        # method, not the last same-named method in the file (bare-name collision).
        self.methods_by_class: dict[str, dict[str, str]] = {}
        self.imported_local_names: dict[str, _ImportDecl] = {}

    # -- import handling ---------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            decl = _ImportDecl(
                source_module=None,
                imported=alias.name,
                local_name=alias.asname or alias.name.split(".")[0],
                line=node.lineno,
            )
            self.imports.append(decl)
            self.imported_local_names[decl.local_name] = decl

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = ("." * (node.level or 0)) + (node.module or "")
        for alias in node.names:
            if alias.name == "*":
                self.imports.append(
                    _ImportDecl(
                        source_module=module,
                        imported="*",
                        local_name="*",
                        line=node.lineno,
                        is_wildcard=True,
                    )
                )
                continue
            decl = _ImportDecl(
                source_module=module,
                imported=alias.name,
                local_name=alias.asname or alias.name,
                line=node.lineno,
            )
            self.imports.append(decl)
            self.imported_local_names[decl.local_name] = decl

    # -- class / function / method ----------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = self._push_qual(node.name)
        uid = class_uid(self.path, qualname)
        parent_uid = self._scope_uid_stack[-1]
        decl = _SymbolDecl(
            uid=uid,
            kind="code:class",
            name=node.name,
            qualname=qualname,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", None),
            signature=_class_signature(node),
            docstring=ast.get_docstring(node),
            decorators=tuple(_dotted_name(d) for d in node.decorator_list),
            parent_uid=parent_uid if parent_uid != module_uid(self.module_name) else None,
        )
        self.decls.append(decl)
        self.symbols_by_name[node.name] = uid

        for base in node.bases:
            self.inherits.append((uid, _dotted_name(base)))
        for dec in node.decorator_list:
            self.decorators_edges.append((uid, _dotted_name(dec)))

        # scan class body for `name: T` and `name: T = default`.
        # Each annotated field becomes a real `code:variable` decl so it
        # appears in the contains tree (parent class → field) instead of
        # surfacing as an orphan stub. The stub UID still anchors the
        # `field_of_type` edge that points at the annotation type.
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                ann_name = _dotted_name(stmt.annotation)
                field_name = stmt.target.id
                field_stub = f"code:variable:{self.path}::{qualname}.{field_name}"
                if ann_name:
                    self.field_types.append((field_stub, ann_name))
                self.decls.append(
                    _SymbolDecl(
                        uid=field_stub,
                        kind="code:variable",
                        name=field_name,
                        qualname=f"{qualname}.{field_name}",
                        line=stmt.lineno,
                        end_line=getattr(stmt, "end_lineno", None),
                        signature=ann_name or "",
                        docstring=None,
                        decorators=(),
                        parent_uid=uid,
                    )
                )

        self._scope_uid_stack.append(uid)
        try:
            self.generic_visit(node)
        finally:
            self._scope_uid_stack.pop()
            self._pop_qual()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(self, node: ast.AST, *, is_async: bool) -> None:
        name = node.name  # type: ignore[attr-defined]
        qualname = self._push_qual(name)
        in_class = self._scope_uid_stack[-1].startswith("code:class:")
        if in_class:
            uid = method_uid(self.path, qualname)
            kind = "code:method"
        else:
            uid = function_uid(self.path, qualname)
            kind = "code:function"
        parent_uid = self._scope_uid_stack[-1]
        decl = _SymbolDecl(
            uid=uid,
            kind=kind,
            name=name,
            qualname=qualname,
            line=node.lineno,  # type: ignore[attr-defined]
            end_line=getattr(node, "end_lineno", None),
            signature=_function_signature(node, is_async=is_async),
            docstring=ast.get_docstring(node),  # type: ignore[arg-type]
            decorators=tuple(_dotted_name(d) for d in node.decorator_list),  # type: ignore[attr-defined]
            parent_uid=parent_uid if parent_uid != module_uid(self.module_name) else None,
            is_method=in_class,
        )
        self.decls.append(decl)
        self.symbols_by_name[name] = uid
        if in_class:
            self.methods_by_class.setdefault(parent_uid, {})[name] = uid

        for dec in node.decorator_list:  # type: ignore[attr-defined]
            self.decorators_edges.append((uid, _dotted_name(dec)))

        # collect param + return type annotations.
        for ann_name in _function_param_annotations(node):
            self.param_types.append((uid, ann_name))
        ret_ann = _function_return_annotation(node)
        if ret_ann:
            self.return_types.append((uid, ret_ann))

        self._scope_uid_stack.append(uid)
        try:
            # Walk the body for two things: nested decls (visit them so we
            # emit code:function / code:method nodes with full qualnames)
            # AND Call nodes (emit call edges scoped to this function).
            for child in node.body:  # type: ignore[attr-defined]
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.visit(child)
                else:
                    self._walk_calls(child)
        finally:
            self._scope_uid_stack.pop()
            self._pop_qual()

    def _walk_calls(self, node: ast.AST) -> None:
        # E5/E6: track parent ast.Await so we can emit `awaits` instead
        # of `calls`. ast.walk loses parent info → walk with our own
        # stack that records the immediate parent type.
        stack: list[tuple[ast.AST, ast.AST | None]] = [(node, None)]
        while stack:
            sub, parent = stack.pop()
            # Function-local / nested-block imports must register so
            # call-site resolution can rewrite a bare `init_db()` call
            # into `code:external:database:init_db` which
            # `link_external_stubs` then promotes to the canonical uid.
            if isinstance(sub, ast.Import):
                self.visit_Import(sub)
            elif isinstance(sub, ast.ImportFrom):
                self.visit_ImportFrom(sub)
            elif isinstance(sub, ast.Call):
                # R2: skip when target is method-access on a literal
                # (`{'a': 'b'}.get(...)` → bogus unresolved identifier).
                func = sub.func
                if isinstance(func, ast.Attribute) and isinstance(
                    func.value,
                    (ast.Dict, ast.Set, ast.List, ast.Tuple, ast.JoinedStr),
                ):
                    # Still descend into args
                    for child in ast.iter_child_nodes(sub):
                        stack.append((child, sub))
                    continue
                target = _dotted_name(func)
                if not target:
                    for child in ast.iter_child_nodes(sub):
                        stack.append((child, sub))
                    continue
                last_segment = target.split(".")[-1]
                is_ctor = last_segment[:1].isupper()
                # E6: collect any args that resolve to known function uids
                # in this file's symbols_by_name — these are dispatched fns.
                dispatched: list[str] = []
                for arg in sub.args:
                    if isinstance(arg, ast.Name) and arg.id in self.symbols_by_name:
                        resolved = self.symbols_by_name[arg.id]
                        if resolved.startswith(("code:function:", "code:method:")):
                            dispatched.append(resolved)
                encl_class = next(
                    (u for u in reversed(self._scope_uid_stack) if u.startswith("code:class:")),
                    None,
                )
                self.calls.append(
                    _CallSite(
                        caller_uid=self._scope_uid_stack[-1],
                        callee_name=last_segment,
                        full_expr=target,
                        line=sub.lineno,
                        is_constructor_like=is_ctor,
                        is_await=isinstance(parent, ast.Await),
                        dispatched_uids=tuple(dispatched),
                        enclosing_class_uid=encl_class,
                    )
                )
                for child in ast.iter_child_nodes(sub):
                    stack.append((child, sub))
                continue
            for child in ast.iter_child_nodes(sub):
                stack.append((child, sub))

    # -- qualname stack helpers --------------------------------------------

    def _push_qual(self, name: str) -> str:
        self._qualname_stack.append(name)
        return ".".join(self._qualname_stack)

    def _pop_qual(self) -> None:
        self._qualname_stack.pop()


def _resolve_symbol(name: str, *, path: str, visitor: _PythonVisitor) -> str:
    root = name.split(".")[0]
    if root in visitor.symbols_by_name:
        return visitor.symbols_by_name[root]
    imp = visitor.imported_local_names.get(root)
    if imp is not None:
        target_mod = _absolute_module_for(imp.source_module, path=path) or imp.imported
        return f"code:external:{target_mod}:{imp.imported}"
    return f"code:external:unresolved:{name}"


# Dotted-name shape an unresolved-call stub may carry — anything else is an
# over-captured expression, not an identifier (TASK-405).
_IDENTIFIER_EXPR_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")


def _resolve_call(
    call: _CallSite,
    *,
    visitor: _PythonVisitor,
    path: str,
) -> tuple[float, tuple[EvidenceSignal, ...], str | None]:
    """Return (confidence, evidence, resolved_uid) for a call-site.

    E4 calibration (audit: was 0.3-0.5 ceiling; 58.7% of calls at 0.3):
      same_scope (real fn in this file)  → 1.0 (AST-certain)
      explicit_import (resolved to mod)  → 0.9 (origin known)
      unresolved                          → 0.3 (best-effort stub)
    """
    signals: list[EvidenceSignal] = []
    confidence = 0.0

    # GE: `self.method()` / `cls.method()` → resolve to the ENCLOSING class's
    # method, not the bare-name match (which picks the last same-named method
    # in the file — a wrong-target collision). Falls through for inherited /
    # attribute access not defined on this class.
    if call.enclosing_class_uid and (
        call.full_expr.startswith("self.") or call.full_expr.startswith("cls.")
    ):
        own_methods = visitor.methods_by_class.get(call.enclosing_class_uid, {})
        if call.callee_name in own_methods:
            return (0.95, (EvidenceSignal("self_method", 0.95),), own_methods[call.callee_name])

    if call.callee_name in visitor.symbols_by_name:
        signals.append(EvidenceSignal("same_scope", 1.0))
        confidence = 1.0
        resolved = visitor.symbols_by_name[call.callee_name]
    elif call.callee_name in visitor.imported_local_names:
        imp = visitor.imported_local_names[call.callee_name]
        signals.append(EvidenceSignal("explicit_import", 0.9, note=imp.source_module))
        confidence = 0.9
        target_mod = _absolute_module_for(imp.source_module, path=path) or imp.imported
        resolved = f"code:external:{target_mod}:{imp.imported}"
    elif "." in call.full_expr and call.full_expr.split(".")[0] in visitor.imported_local_names:
        root = call.full_expr.split(".")[0]
        imp = visitor.imported_local_names[root]
        signals.append(EvidenceSignal("explicit_import", 0.9, note=imp.source_module))
        confidence = 0.9
        tail = ".".join(call.full_expr.split(".")[1:])
        # The alias is a MODULE: `from pkg import mod as g` → module pkg.mod;
        # `import pkg.mod as g` → module imp.imported. Resolving the attribute
        # (`g.func`) to <module>:func lets link_external_stubs bind it to the
        # real function instead of dropping the call on the bare package —
        # this is what made rename/references miss `g.func()` sites.
        abs_source = _absolute_module_for(imp.source_module, path=path)
        root_module = f"{abs_source}.{imp.imported}" if abs_source else imp.imported
        resolved = f"code:external:{root_module}:{tail}"
    else:
        # An "identifier" stub must be identifier-shaped (dotted names only).
        # Complex receivers (`(a or b / 'x').resolve`) used to mint
        # expression-shaped stubs — 956 junk rows that nothing can ever
        # link (TASK-405). Skip the edge entirely; the LSP overlay can
        # still resolve such sites later.
        if not _IDENTIFIER_EXPR_RE.fullmatch(call.full_expr or ""):
            return (0.0, tuple(signals), None)
        signals.append(EvidenceSignal("unresolved_call", 0.3))
        confidence = 0.3
        resolved = f"code:external:unresolved:{call.full_expr}"

    return (round(min(confidence, 1.0), 4), tuple(signals), resolved)


def _inherit_confidence(base_name: str, visitor: _PythonVisitor) -> float:
    if base_name.split(".")[0] in visitor.symbols_by_name:
        return 0.95
    if base_name.split(".")[0] in visitor.imported_local_names:
        return 0.8
    return 0.5


def _decorator_confidence(name: str, visitor: _PythonVisitor) -> float:
    if name.split(".")[0] in visitor.symbols_by_name:
        return 0.9
    if name.split(".")[0] in visitor.imported_local_names:
        return 0.85
    return 0.6


def _annotation_confidence(type_name: str, visitor: _PythonVisitor) -> float:
    """Confidence for has_param_type / returns_type / field_of_type edges.

    Mirrors `_inherit_confidence` but slightly stricter: same-scope
    binding wins (0.95 — directly observed declaration), explicit
    import next (0.85 — origin is known but not the symbol body),
    builtin / unresolved fall back to 0.3 so consumers know the edge
    is best-effort.
    """
    head = type_name.split(".")[0]
    if head in visitor.symbols_by_name:
        return 0.95
    if head in visitor.imported_local_names:
        return 0.85
    if head in _BUILTIN_TYPES:
        # Edges to bare builtins are still useful (UI heat-maps), but
        # they should not win against any user-resolved type.
        return 0.7
    return 0.3
