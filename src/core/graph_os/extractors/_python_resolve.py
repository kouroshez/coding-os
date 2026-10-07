"""graph_os — turn a name a Python file uses into a uid, and that uid's confidence.

Same-file symbols first, then the file's imports (a dotted import resolves to
the longest imported module the expression starts with), else an unresolved
stub. Imports the two leaves; the visitor type is for annotations only.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..types import EvidenceSignal
from ._python_decls import _BUILTIN_TYPES, _CallSite, _ImportDecl
from ._python_uids import _absolute_module_for

if TYPE_CHECKING:
    from ._python_visitor import _PythonVisitor


def _resolve_symbol(name: str, *, path: str, visitor: _PythonVisitor) -> str:
    root = name.split(".")[0]
    if root in visitor.symbols_by_name:
        return visitor.symbols_by_name[root]
    imp = visitor.imported_local_names.get(root)
    if imp is not None:
        return _import_target(name, imp, path=path)
    return f"code:external:unresolved:{name}"


def _import_target(expression: str, imp: _ImportDecl, *, path: str) -> str:
    """Stub for a name reached through an import: `code:external:<module>:<attribute>`.

    `pydantic.BaseModel` under `import pydantic` is `pydantic:BaseModel` — it
    used to collapse to `pydantic:pydantic`, dropping the attribute — and
    `os.path.join` under `import os.path` is `os.path:join`, the longest
    imported module the expression starts with.
    """
    parts = expression.split(".")
    source = _absolute_module_for(imp.source_module, path=path)
    if source:
        if len(parts) == 1:
            return f"code:external:{source}:{imp.imported}"
        return f"code:external:{source}.{imp.imported}:{'.'.join(parts[1:])}"
    module_parts = imp.imported.split(".")
    if parts[0] != module_parts[0]:
        module, rest = imp.imported, parts[1:]
    else:
        depth = len(module_parts) if parts[: len(module_parts)] == module_parts else 1
        module, rest = ".".join(parts[:depth]), parts[depth:]
    attribute = ".".join(rest) or module.split(".")[-1]
    return f"code:external:{module}:{attribute}"


# Dotted-name shape an unresolved-call stub may carry — anything else is an
# over-captured expression, not an identifier.
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
    if call.enclosing_class_uid and call.full_expr == "cls":
        return (0.9, (EvidenceSignal("cls_constructs", 0.9),), call.enclosing_class_uid)

    # Only a bare name may resolve by its name: `requests.get()` used to bind,
    # at confidence 1.0, to whatever `get` this file defined.
    bare = call.full_expr == call.callee_name
    root = call.full_expr.split(".")[0]
    class_methods = visitor.methods_by_class.get(visitor.symbols_by_name.get(root, ""), {})
    if bare and call.callee_name in visitor.symbols_by_name:
        signals.append(EvidenceSignal("same_scope", 1.0))
        confidence = 1.0
        resolved = visitor.symbols_by_name[call.callee_name]
    elif bare and call.callee_name in visitor.imported_local_names:
        imp = visitor.imported_local_names[call.callee_name]
        signals.append(EvidenceSignal("explicit_import", 0.9, note=imp.source_module))
        confidence = 0.9
        resolved = _import_target(call.full_expr, imp, path=path)
    elif not bare and call.full_expr.count(".") == 1 and call.callee_name in class_methods:
        signals.append(EvidenceSignal("class_method", 0.95))
        confidence = 0.95
        resolved = class_methods[call.callee_name]
    elif not bare and root in visitor.imported_local_names and root not in visitor.symbols_by_name:
        imp = visitor.imported_local_names[root]
        signals.append(EvidenceSignal("explicit_import", 0.9, note=imp.source_module))
        confidence = 0.9
        # The alias may be a module (`import pkg.mod as g`, `from pkg import
        # mod`): `g.func` resolves to <module>:func so the linker can bind it.
        resolved = _import_target(call.full_expr, imp, path=path)
    else:
        # An "identifier" stub must be identifier-shaped (dotted names only).
        # Complex receivers (`(a or b / 'x').resolve`) used to mint
        # expression-shaped stubs — 956 junk rows that nothing can ever
        # link. Skip the edge entirely; the LSP overlay can
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
