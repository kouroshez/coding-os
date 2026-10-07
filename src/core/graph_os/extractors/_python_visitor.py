"""graph_os — the stdlib-`ast` walk over one Python file.

`_PythonVisitor` collects declarations, imports, annotations and call-sites in a
single pass; `_python_resolve` turns a collected name into a uid. Imports the
two leaves and the resolver, never the facade.
"""

from __future__ import annotations

import ast

from ._python_decls import (
    _CallSite,
    _class_signature,
    _dotted_name,
    _function_param_annotations,
    _function_return_annotation,
    _function_signature,
    _ImportDecl,
    _SymbolDecl,
)
from ._python_resolve import _resolve_symbol
from ._python_uids import (
    class_uid,
    function_uid,
    method_uid,
    module_uid,
)

# FastAPI's calls that take the dependency itself: only here is a `module.fn`
# argument a callback rather than a value (`print(sys.stderr)`).
_DEPENDENCY_CALLS = frozenset({"Depends", "Security"})


_COMPOUND_STATEMENTS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
    *((ast.TryStar,) if hasattr(ast, "TryStar") else ()),
)
_BLOCK_FIELDS = frozenset({"body", "orelse", "finalbody", "handlers", "cases"})


def _dependency_calls(node: ast.AST) -> list[ast.Call]:
    return [
        sub
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call) and _dotted_name(sub.func).split(".")[-1] in _DEPENDENCY_CALLS
    ]


def _parameter_annotations(arguments: ast.arguments) -> list[ast.expr]:
    every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    every += [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
    return [arg.annotation for arg in every if arg.annotation is not None]


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
        # Every declaration by bare name, built once the walk is done.
        self.decls_by_name: dict[str, list[_SymbolDecl]] | None = None
        # GE: per-class method map so `self.method()` resolves to THIS class's
        # method, not the last same-named method in the file (bare-name collision).
        self.methods_by_class: dict[str, dict[str, str]] = {}
        self.imported_local_names: dict[str, _ImportDecl] = {}
        # `SessionDep = Annotated[Session, Depends(get_db)]` → its Depends calls.
        self.dependency_aliases: dict[str, list[ast.Call]] = {}
        self._type_checking = 0

    # -- import handling ---------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            decl = _ImportDecl(
                source_module=None,
                imported=alias.name,
                local_name=alias.asname or alias.name.split(".")[0],
                line=node.lineno,
                type_only=self._type_checking > 0,
            )
            self.imports.append(decl)
            self.imported_local_names.setdefault(decl.local_name, decl)

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
                type_only=self._type_checking > 0,
            )
            self.imports.append(decl)
            # `try: from .impl import f / except ImportError: from impl import f`:
            # the first binding is the one meant; the fallback must not replace it.
            self.imported_local_names.setdefault(decl.local_name, decl)

    # `if TYPE_CHECKING:` imports exist for the type checker only: they never
    # run, so they are no runtime dependency and close no import cycle.
    def visit_If(self, node: ast.If) -> None:
        test = node.test
        guarded = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not guarded:
            self.generic_visit(node)
            return
        self._type_checking += 1
        try:
            for stmt in node.body:
                self.visit(stmt)
        finally:
            self._type_checking -= 1
        for stmt in node.orelse:
            self.visit(stmt)

    # -- module-level names --------------------------------------------------

    # Only module scope reaches these: function bodies and class bodies are
    # walked for calls, never visited. `app = FastAPI()`, `router`, constants —
    # what other modules import by name.
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            for name in _target_names(target):
                self._module_variable(name, node)
                self._dependency_alias(name, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        for name in _target_names(node.target):
            self._module_variable(name, node)
            if node.value is not None:
                self._dependency_alias(name, node.value)
        self.generic_visit(node)

    def _dependency_alias(self, name: str, value: ast.AST) -> None:
        calls = _dependency_calls(value)
        if calls:
            self.dependency_aliases[name] = calls

    def _module_variable(self, name: str, node: ast.AST) -> None:
        uid = f"code:variable:{self.path}::{name}"
        if name in self.symbols_by_name or any(decl.uid == uid for decl in self.decls):
            return
        self.decls.append(
            _SymbolDecl(
                uid=uid,
                kind="code:variable",
                name=name,
                qualname=name,
                line=node.lineno,  # type: ignore[attr-defined]
                end_line=getattr(node, "end_lineno", None),
                signature="",
                docstring=None,
                decorators=(),
                parent_uid=None,
            )
        )

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
            # A class body runs when the class is built: `x = Field(default_factory=f)`
            # calls happen there, not in any method.
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.visit(stmt)
                else:
                    self._walk_calls(stmt)
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
            # `db = Depends(get_db)` and `@router.get(..., dependencies=[Depends(auth)])`
            # are this function's dependencies, though they run at definition.
            arguments = node.args  # type: ignore[attr-defined]
            for default in [*arguments.defaults, *arguments.kw_defaults]:
                if default is not None:
                    self._walk_calls(default)
            # `db: Annotated[Session, Depends(get_db)]`, or the alias of one.
            for annotation in _parameter_annotations(arguments):
                if isinstance(annotation, ast.Name) and annotation.id in self.dependency_aliases:
                    for call in self.dependency_aliases[annotation.id]:
                        self._walk_calls(call)
                else:
                    for call in _dependency_calls(annotation):
                        self._walk_calls(call)
            for dec in node.decorator_list:  # type: ignore[attr-defined]
                if isinstance(dec, ast.Call):
                    for value in [*dec.args, *(keyword.value for keyword in dec.keywords)]:
                        self._walk_calls(value)
            # Walk the body for two things: nested decls (visit them so we
            # emit code:function / code:method nodes with full qualnames)
            # AND Call nodes (emit call edges scoped to this function).
            self._walk_body(node.body)  # type: ignore[attr-defined]
        finally:
            self._scope_uid_stack.pop()
            self._pop_qual()

    def _walk_body(self, statements: list[ast.stmt], *, module_level: bool = False) -> None:
        # A def under `if` / `try` / `with` / `for` / `match` is still this
        # function's nested function, and its calls are its own. At module
        # level the visit already reached every def, class and import, so
        # only the code around them is walked.
        register_imports = not module_level
        for child in statements:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not module_level:
                    self.visit(child)
            elif isinstance(child, _COMPOUND_STATEMENTS):
                for field_name, value in ast.iter_fields(child):
                    if field_name in _BLOCK_FIELDS:
                        continue
                    for part in value if isinstance(value, list) else [value]:
                        if isinstance(part, ast.AST):
                            self._walk_calls(part, register_imports=register_imports)
                for field_name in ("body", "orelse", "finalbody"):
                    self._walk_body(
                        getattr(child, field_name, None) or [], module_level=module_level
                    )
                for clause in [*getattr(child, "handlers", []), *getattr(child, "cases", [])]:
                    for field_name, value in ast.iter_fields(clause):
                        if field_name != "body" and isinstance(value, ast.AST):
                            self._walk_calls(value, register_imports=register_imports)
                    self._walk_body(clause.body, module_level=module_level)
            else:
                self._walk_calls(child, register_imports=register_imports)

    def _walk_calls(self, node: ast.AST, *, register_imports: bool = True) -> None:
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
                if register_imports:
                    self.visit_Import(sub)
            elif isinstance(sub, ast.ImportFrom):
                if register_imports:
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
                target = _dotted_name(func) if not _on_computed_value(func) else ""
                if not target:
                    for child in ast.iter_child_nodes(sub):
                        stack.append((child, sub))
                    continue
                last_segment = target.split(".")[-1]
                is_ctor = last_segment[:1].isupper()
                # E6: collect any args that resolve to known function uids
                # in this file's symbols_by_name — these are dispatched fns.
                dispatched: list[str] = []
                for arg in [*sub.args, *(keyword.value for keyword in sub.keywords)]:
                    if isinstance(arg, ast.Attribute) and last_segment in _DEPENDENCY_CALLS:
                        dotted = _dotted_name(arg)
                        if dotted.split(".")[0] in self.imported_local_names:
                            dispatched.append(_resolve_symbol(dotted, path=self.path, visitor=self))
                        continue
                    if not isinstance(arg, ast.Name):
                        continue
                    if arg.id in self.symbols_by_name:
                        resolved = self.symbols_by_name[arg.id]
                        if resolved.startswith(("code:function:", "code:method:")):
                            dispatched.append(resolved)
                    elif arg.id in self.imported_local_names:
                        # An imported callback (`Depends(get_db)`) is a stub
                        # the linker binds like a call.
                        dispatched.append(_resolve_symbol(arg.id, path=self.path, visitor=self))
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


def _on_computed_value(func: ast.expr) -> bool:
    # `hashlib.sha256(x).hexdigest()` calls a method on a value the call made;
    # folding it into `hashlib.sha256.hexdigest` named a symbol that does not
    # exist. The inner `hashlib.sha256` call is still recorded on its own.
    # `super().m()` is the exception: its receiver is the base class.
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Call)
        and isinstance(func.value.func, ast.Name)
        and func.value.func.id == "super"
    ):
        return False
    node = func
    while isinstance(node, ast.Attribute):
        node = node.value
        if isinstance(node, (ast.Call, ast.Subscript)):
            return True
    return isinstance(node, (ast.Call, ast.Subscript))


def _target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _target_names(element)]
    return []
