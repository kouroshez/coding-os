"""graph_os — PHP source file extractor (tree-sitter-php primary, regex fallback).

Targets Python-gold parity for the PHP ecosystem (TASK-069, spec §4.9):

  Node kinds emitted
    - code:file              one per .php file
    - code:module            one per file (the declared namespace)
    - code:class             class + trait (metadata.php_kind=trait)
    - code:interface         interface declarations
    - code:function          top-level functions
    - code:method            class/interface/trait methods
    - code:variable          typed properties + class constants
    - code:import            `use` statements (incl alias + grouped use)
    - code:external          unresolved cross-namespace references

  Edge kinds emitted
    - contains               file → module → {class, function}; class → method/property
    - imports                module → code:external:<FQN>
    - inherits_from          class → parent (extends) + trait composition (use Trait)
    - implements             class → interface
    - has_param_type         method/function → param type
    - returns_type           method/function → return type
    - field_of_type          property → declared type
    - is_decorated_by        class/method → PHP-8 attribute #[Attr]
    - calls                  same-file resolved: bare f(), $this->m(), self::m(),
                             static::m(), Class::m() → real uid @0.9 (same_scope parity)
    - constructs             `new X()` → class uid (local) / external stub

  PHP specifics handled
    - namespaces + `use` (alias `as`, grouped `use A\{B, C}`)
    - traits: declaration → class node; `use TraitName;` inside a class → inherits_from
    - typed params/returns/properties: nullable `?T`, union `A|B`, intersection `A&B`
    - PHP-8 attributes `#[Route(...)]` → is_decorated_by
    - constructor property promotion (`__construct(private User $u)`) → property + field_of_type
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_php")
EXTRACTOR_ID = "code_php@v1"

try:
    import tree_sitter as _ts
    import tree_sitter_php as _ts_php

    _PHP_LANG = _ts.Language(_ts_php.language_php())
    _TS_AVAILABLE = True
except Exception:  # pragma: no cover - lean install path
    _ts = None  # type: ignore[assignment]
    _PHP_LANG = None  # type: ignore[assignment]
    _TS_AVAILABLE = False


_PHP_PRIMITIVES = {
    "int",
    "float",
    "string",
    "bool",
    "array",
    "object",
    "callable",
    "iterable",
    "void",
    "null",
    "mixed",
    "never",
    "false",
    "true",
    "self",
    "static",
    "parent",
}


# ---------------------------------------------------------------------------
# Regex fallback (only when tree-sitter-php unavailable)
# ---------------------------------------------------------------------------

_RE_NAMESPACE = re.compile(r"^\s*namespace\s+(?P<name>[\w\\]+)\s*;", re.MULTILINE)
_RE_USE = re.compile(r"^\s*use\s+(?P<fqn>[\w\\]+)(?:\s+as\s+(?P<alias>\w+))?\s*;", re.MULTILINE)
_RE_TYPE = re.compile(
    r"^\s*(?:abstract\s+|final\s+)*(?P<kind>class|interface|trait)\s+(?P<name>\w+)",
    re.MULTILINE,
)
_RE_FUNC = re.compile(
    r"^\s*(?:(?:public|private|protected|static|abstract|final)\s+)*function\s+(?P<name>\w+)\s*\(",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# UID helpers
# ---------------------------------------------------------------------------


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:{_normalize_path(path)}"


def class_uid(path: str, name: str) -> str:
    return f"code:class:{_normalize_path(path)}::{name}"


def interface_uid(path: str, name: str) -> str:
    return f"code:interface:{_normalize_path(path)}::{name}"


def func_uid(path: str, name: str) -> str:
    return f"code:function:{_normalize_path(path)}::{name}"


def method_uid(path: str, cls: str, name: str) -> str:
    return f"code:method:{_normalize_path(path)}::{cls}.{name}"


def variable_uid(path: str, name: str) -> str:
    return f"code:variable:{_normalize_path(path)}::{name}"


# ---------------------------------------------------------------------------
# tree-sitter node helpers
# ---------------------------------------------------------------------------


def _node_text(node: Any, content_bytes: bytes) -> str:
    if node is None:
        return ""
    return content_bytes[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _find_field(node: Any, field: str) -> Any | None:
    try:
        return node.child_by_field_name(field)
    except Exception:
        return None


def _php_short(name: str) -> str:
    """Last segment of a possibly-qualified PHP name (App\\Models\\User → User)."""
    return name.replace("/", "\\").split("\\")[-1].strip()


def _resolve_php_type(name: str, local_names: dict[str, str], imported: dict[str, str]) -> str:
    short = _php_short(name)
    if short in local_names:
        return local_names[short]
    if short in imported:
        return f"code:external:{imported[short]}"
    if name.lstrip("\\") in imported.values():
        return f"code:external:{name.lstrip(chr(92))}"
    return f"code:external:unresolved:{short}"


def _php_collect_type_names(type_node: Any, content_bytes: bytes) -> list[str]:
    """Resolvable class/interface names in a type expression (skip primitives)."""
    if type_node is None:
        return []
    out: list[str] = []
    stack = [type_node]
    while stack:
        n = stack.pop()
        if n.type in ("named_type", "qualified_name"):
            txt = _node_text(n, content_bytes).strip().lstrip("?").lstrip("\\")
            if txt and _php_short(txt).lower() not in _PHP_PRIMITIVES:
                out.append(txt)
            continue
        if n.type == "primitive_type":
            continue
        stack.extend(n.children)
    return out


def _php_attr_names(attr_list_node: Any, content_bytes: bytes) -> list[str]:
    out: list[str] = []
    stack = [attr_list_node]
    while stack:
        n = stack.pop()
        if n.type == "attribute":
            nm = _find_field(n, "name") or next(
                (c for c in n.children if c.type in ("name", "qualified_name")), None
            )
            if nm is not None:
                txt = _node_text(nm, content_bytes).strip().lstrip("\\")
                if txt:
                    out.append(txt)
            continue
        stack.extend(n.children)
    return out


# ---------------------------------------------------------------------------
# Same-file call resolution (Python `same_scope` parity)
# ---------------------------------------------------------------------------


def _collect_php_callables(
    root: Any, content_bytes: bytes, path: str
) -> tuple[dict[str, str], dict[tuple[str, str], str], dict[str, str]]:
    """Pre-pass: top-level funcs, (class, method) map, and class-name → uid."""
    funcs: dict[str, str] = {}
    methods: dict[tuple[str, str], str] = {}
    classes: dict[str, str] = {}

    def walk(node: Any, cur_class: str | None) -> None:
        t = node.type
        if t in ("class_declaration", "interface_declaration", "trait_declaration"):
            nm = _find_field(node, "name")
            cname = _node_text(nm, content_bytes) if nm is not None else ""
            if cname:
                classes[cname] = (
                    interface_uid(path, cname)
                    if t == "interface_declaration"
                    else class_uid(path, cname)
                )
            for c in node.children:
                walk(c, cname or cur_class)
            return
        if t == "function_definition":
            nm = _find_field(node, "name")
            name = _node_text(nm, content_bytes) if nm is not None else ""
            if name and cur_class is None:
                funcs[name] = func_uid(path, name)
        elif t == "method_declaration" and cur_class:
            nm = _find_field(node, "name")
            name = _node_text(nm, content_bytes) if nm is not None else ""
            if name:
                methods[(cur_class, name)] = method_uid(path, cur_class, name)
        for c in node.children:
            walk(c, cur_class)

    walk(root, None)
    return funcs, methods, classes


def _enclosing_php_scope(
    node: Any, content_bytes: bytes, path: str
) -> tuple[str | None, str | None]:
    """Return (enclosing_uid, enclosing_class_name) for a call node."""
    cur = node.parent
    while cur is not None:
        if cur.type == "method_declaration":
            nm = _find_field(cur, "name")
            mname = _node_text(nm, content_bytes) if nm is not None else ""
            cls = cur.parent
            while cls is not None and cls.type not in (
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
            ):
                cls = cls.parent
            cname = ""
            if cls is not None:
                cn = _find_field(cls, "name")
                cname = _node_text(cn, content_bytes) if cn is not None else ""
            if mname and cname:
                return method_uid(path, cname, mname), cname
        if cur.type == "function_definition":
            nm = _find_field(cur, "name")
            name = _node_text(nm, content_bytes) if nm is not None else ""
            return (func_uid(path, name) if name else None), None
        cur = cur.parent
    return None, None


def _walk_php_calls(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    imported: dict[str, str],
    result: ExtractionResult,
) -> None:
    funcs, methods, classes = _collect_php_callables(root, content_bytes, path)
    if not funcs and not methods and not classes:
        return
    seen: set[tuple[str, str, str]] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        t = node.type
        if t in (
            "function_call_expression",
            "member_call_expression",
            "scoped_call_expression",
            "object_creation_expression",
        ):
            src_uid, enc_class = _enclosing_php_scope(node, content_bytes, path)
            src = src_uid or module_uid_str
            target: str | None = None
            edge_type = "calls"
            conf = 0.9
            signal = "php_same_scope"
            line = node.start_point[0] + 1
            if t == "function_call_expression":
                fn = _find_field(node, "function")
                if fn is not None and fn.type == "name":
                    target = funcs.get(_node_text(fn, content_bytes))
            elif t == "member_call_expression":
                obj = _find_field(node, "object")
                nm = _find_field(node, "name")
                method = _node_text(nm, content_bytes) if nm is not None else ""
                if obj is not None and obj.type == "variable_name" and method:
                    var = _node_text(obj, content_bytes).lstrip("$")
                    if var == "this" and enc_class:
                        target = methods.get((enc_class, method))
            elif t == "scoped_call_expression":
                scope = _find_field(node, "scope")
                nm = _find_field(node, "name")
                method = _node_text(nm, content_bytes) if nm is not None else ""
                if scope is not None and method:
                    stext = _node_text(scope, content_bytes).strip()
                    if stext in ("self", "static", "parent") and enc_class:
                        target = methods.get((enc_class, method))
                    else:
                        target = methods.get((_php_short(stext), method))
            elif t == "object_creation_expression":
                cls_node = next(
                    (c for c in node.children if c.type in ("name", "qualified_name")), None
                )
                if cls_node is not None:
                    cname = _php_short(_node_text(cls_node, content_bytes))
                    edge_type = "constructs"
                    target = classes.get(cname)
                    if target is None:
                        # imported / external class — still a real instantiation.
                        target = _resolve_php_type(cname, {}, imported)
                        conf = 0.3 if ":unresolved:" in target else 0.6
                        signal = "php_construct"
            if target and target != src:
                key = (src, target, edge_type)
                if key not in seen:
                    seen.add(key)
                    result.edges.append(
                        GraphEdge(
                            source_uid=src,
                            target_uid=target,
                            edge_type=edge_type,
                            extractor=EXTRACTOR_ID,
                            confidence=conf,
                            source_span=f"{normalised}:{line}",
                            evidence=(EvidenceSignal(signal, conf),),
                        )
                    )
        stack.extend(node.children)


# ---------------------------------------------------------------------------
# Structural walker (nodes + heritage/type/attr edges)
# ---------------------------------------------------------------------------


def _walk_php_symbols(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
) -> tuple[str, dict[str, str], dict[str, str]]:
    """Emit declarations + edges. Returns (namespace, local_names, imported)."""
    namespace = ""
    local_names: dict[str, str] = {}
    imported: dict[str, str] = {}
    pending_types: list[tuple[str, str, str]] = []  # (owner_uid, type_name, edge_type)
    pending_heritage: list[tuple[str, str, str]] = []  # (owner_uid, name, edge_type)
    pending_attrs: list[tuple[str, str]] = []  # (owner_uid, attr_name)

    def emit_type_edges(owner_uid: str, fn_node: Any) -> None:
        params = _find_field(fn_node, "parameters")
        if params is not None:
            for p in params.children:
                if p.type not in (
                    "simple_parameter",
                    "variadic_parameter",
                    "property_promotion_parameter",
                ):
                    continue
                type_node = _find_field(p, "type") or next(
                    (c for c in p.children if c.type.endswith("_type")), None
                )
                for tname in _php_collect_type_names(type_node, content_bytes):
                    pending_types.append((owner_uid, tname, "has_param_type"))
                if p.type == "property_promotion_parameter":
                    _emit_promoted_property(owner_uid, p, type_node)
        rt = _find_field(fn_node, "return_type")
        for tname in _php_collect_type_names(rt, content_bytes):
            pending_types.append((owner_uid, tname, "returns_type"))

    def _emit_promoted_property(class_uid_str: str, param: Any, type_node: Any) -> None:
        var = next((c for c in param.children if c.type == "variable_name"), None)
        if var is None:
            return
        pname = _node_text(var, content_bytes).lstrip("$")
        # owner is the method; the property belongs to the enclosing class —
        # resolve it via the method uid prefix (…::Class.method → …::Class.prop).
        cls_prefix = class_uid_str.split("::")[0].replace("code:method:", "code:class:")
        cls_name = class_uid_str.split("::")[-1].split(".")[0]
        puid = variable_uid(path, f"{cls_name}.{pname}")
        result.nodes.append(
            GraphNode(
                uid=puid,
                kind="code:variable",
                label=pname,
                file_path=normalised,
                start_line=param.start_point[0] + 1,
                lang="php",
                metadata={"extractor": EXTRACTOR_ID, "php_kind": "promoted_property"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=f"{cls_prefix}::{cls_name}",
                target_uid=puid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        for tname in _php_collect_type_names(type_node, content_bytes):
            pending_types.append((puid, tname, "field_of_type"))

    def emit_class(node: Any, kind: str) -> str:
        nm = _find_field(node, "name")
        name = _node_text(nm, content_bytes) if nm is not None else ""
        if not name:
            return ""
        is_iface = kind == "interface"
        uid = interface_uid(path, name) if is_iface else class_uid(path, name)
        node_kind = "code:interface" if is_iface else "code:class"
        meta: dict[str, Any] = {"extractor": EXTRACTOR_ID}
        if kind == "trait":
            meta["php_kind"] = "trait"
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind=node_kind,
                label=name,
                file_path=normalised,
                start_line=node.start_point[0] + 1,
                lang="php",
                metadata=meta,
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        # extends
        base = _find_field(node, "base_clause") or next(
            (c for c in node.children if c.type == "base_clause"), None
        )
        if base is not None:
            for c in base.children:
                if c.type in ("name", "qualified_name"):
                    pending_heritage.append((uid, _node_text(c, content_bytes), "inherits_from"))
        # implements
        impl = next((c for c in node.children if c.type == "class_interface_clause"), None)
        if impl is not None:
            for c in impl.children:
                if c.type in ("name", "qualified_name"):
                    pending_heritage.append((uid, _node_text(c, content_bytes), "implements"))
        # attributes
        for c in node.children:
            if c.type == "attribute_list":
                for an in _php_attr_names(c, content_bytes):
                    pending_attrs.append((uid, an))
        # body: trait-use, properties, consts, methods
        body = next((c for c in node.children if c.type == "declaration_list"), None)
        if body is not None:
            for member in body.children:
                if member.type == "use_declaration":
                    for c in member.children:
                        if c.type in ("name", "qualified_name"):
                            pending_heritage.append(
                                (uid, _node_text(c, content_bytes), "uses_trait")
                            )
                elif member.type == "property_declaration":
                    emit_property(uid, name, member)
                elif member.type == "const_declaration":
                    emit_const(uid, name, member)
                elif member.type == "method_declaration":
                    emit_method(uid, name, member)
        return uid

    def emit_property(class_uid_str: str, class_name: str, node: Any) -> None:
        type_node = _find_field(node, "type") or next(
            (c for c in node.children if c.type.endswith("_type")), None
        )
        for el in node.children:
            if el.type != "property_element":
                continue
            nm = _find_field(el, "name") or next(
                (c for c in el.children if c.type == "variable_name"), None
            )
            pname = _node_text(nm, content_bytes).lstrip("$") if nm is not None else ""
            if not pname:
                continue
            puid = variable_uid(path, f"{class_name}.{pname}")
            result.nodes.append(
                GraphNode(
                    uid=puid,
                    kind="code:variable",
                    label=pname,
                    file_path=normalised,
                    start_line=el.start_point[0] + 1,
                    lang="php",
                    metadata={"extractor": EXTRACTOR_ID, "php_kind": "property"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=class_uid_str,
                    target_uid=puid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
            for tname in _php_collect_type_names(type_node, content_bytes):
                pending_types.append((puid, tname, "field_of_type"))

    def emit_const(class_uid_str: str, class_name: str, node: Any) -> None:
        for el in node.children:
            if el.type != "const_element":
                continue
            nm = next((c for c in el.children if c.type == "name"), None)
            cname = _node_text(nm, content_bytes) if nm is not None else ""
            if not cname:
                continue
            cuid = variable_uid(path, f"{class_name}.{cname}")
            result.nodes.append(
                GraphNode(
                    uid=cuid,
                    kind="code:variable",
                    label=cname,
                    file_path=normalised,
                    start_line=el.start_point[0] + 1,
                    lang="php",
                    metadata={"extractor": EXTRACTOR_ID, "php_kind": "const"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=class_uid_str,
                    target_uid=cuid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )

    def emit_method(class_uid_str: str, class_name: str, node: Any) -> None:
        nm = _find_field(node, "name")
        name = _node_text(nm, content_bytes) if nm is not None else ""
        if not name:
            return
        uid = method_uid(path, class_name, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:method",
                label=name,
                file_path=normalised,
                start_line=node.start_point[0] + 1,
                signature=f"{class_name}.{name}()",
                lang="php",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=class_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        for c in node.children:
            if c.type == "attribute_list":
                for an in _php_attr_names(c, content_bytes):
                    pending_attrs.append((uid, an))
        emit_type_edges(uid, node)

    def emit_function(node: Any) -> None:
        nm = _find_field(node, "name")
        name = _node_text(nm, content_bytes) if nm is not None else ""
        if not name:
            return
        uid = func_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=normalised,
                start_line=node.start_point[0] + 1,
                signature=f"function {name}()",
                lang="php",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        emit_type_edges(uid, node)

    # Top-level walk (declarations only — nested funcs/classes are rare in PHP
    # and emit_class recurses into its own body).
    for node in _iter_top_level(root):
        t = node.type
        if t == "namespace_definition":
            nm = _find_field(node, "name")
            namespace = _node_text(nm, content_bytes).strip() if nm is not None else ""
        elif t == "namespace_use_declaration":
            _emit_use(node, content_bytes, module_uid_str, result, imported, normalised)
        elif t == "class_declaration":
            emit_class(node, "class")
        elif t == "interface_declaration":
            emit_class(node, "interface")
        elif t == "trait_declaration":
            emit_class(node, "trait")
        elif t == "function_definition":
            emit_function(node)

    # Resolve deferred heritage / type / attribute edges (local_names complete).
    for owner_uid, name, etype in pending_heritage:
        signal = "php_use_trait" if etype == "uses_trait" else f"php_{etype}"
        edge_type = "inherits_from" if etype in ("inherits_from", "uses_trait") else etype
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=_resolve_php_type(name, local_names, imported),
                edge_type=edge_type,
                extractor=EXTRACTOR_ID,
                confidence=0.9 if etype != "implements" else 0.8,
                evidence=(EvidenceSignal(signal, 0.9),),
            )
        )
    for owner_uid, tname, etype in pending_types:
        target = _resolve_php_type(tname, local_names, imported)
        conf = 0.8 if target.startswith(("code:class:", "code:interface:")) else 0.5
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=target,
                edge_type=etype,
                extractor=EXTRACTOR_ID,
                confidence=conf,
                evidence=(EvidenceSignal("php_type", conf),),
            )
        )
    for owner_uid, attr in pending_attrs:
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=_resolve_php_type(attr, local_names, imported),
                edge_type="is_decorated_by",
                extractor=EXTRACTOR_ID,
                confidence=0.85,
                evidence=(EvidenceSignal("php_attribute", 0.85),),
            )
        )
    return namespace, local_names, imported


def _iter_top_level(root: Any) -> list[Any]:
    """Top-level declarations, descending through the program + namespace bodies."""
    out: list[Any] = []
    for child in root.children:
        out.append(child)
        if child.type == "namespace_definition":
            body = next((c for c in child.children if c.type == "compound_statement"), None)
            if body is not None:
                out.extend(body.children)
    return out


def _emit_use(
    node: Any,
    content_bytes: bytes,
    module_uid_str: str,
    result: ExtractionResult,
    imported: dict[str, str],
    normalised: str,
) -> None:
    # Grouped: `use App\Lib\{A, B as C};` → prefix namespace_name + namespace_use_group.
    prefix = ""
    group = next((c for c in node.children if c.type == "namespace_use_group"), None)
    if group is not None:
        pn = next((c for c in node.children if c.type == "namespace_name"), None)
        prefix = _node_text(pn, content_bytes).strip().rstrip("\\") if pn is not None else ""
        clauses = [c for c in group.children if c.type == "namespace_use_clause"]
    else:
        clauses = [c for c in node.children if c.type == "namespace_use_clause"]
    for clause in clauses:
        _emit_use_clause(clause, content_bytes, module_uid_str, result, imported, prefix)


def _emit_use_clause(
    clause: Any,
    content_bytes: bytes,
    module_uid_str: str,
    result: ExtractionResult,
    imported: dict[str, str],
    prefix: str,
) -> None:
    name_node = next(
        (c for c in clause.children if c.type in ("qualified_name", "namespace_name", "name")), None
    )
    if name_node is None:
        return
    raw = _node_text(name_node, content_bytes).strip().lstrip("\\")
    fqn = f"{prefix}\\{raw}" if prefix else raw
    alias_node = _find_field(clause, "alias")
    alias = _node_text(alias_node, content_bytes).strip() if alias_node is not None else ""
    local = alias or _php_short(fqn)
    imported[local] = fqn
    target = f"code:external:{fqn}"
    meta: dict[str, Any] = {"extractor": EXTRACTOR_ID, "external_kind": "php_use"}
    if alias:
        meta["alias"] = alias
    result.nodes.append(
        GraphNode(uid=target, kind="code:external", label=fqn, lang="php", metadata=meta)
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=target,
            edge_type="imports",
            extractor=EXTRACTOR_ID,
            confidence=0.95,
            evidence=(EvidenceSignal("php_use", 0.95),),
        )
    )


# ---------------------------------------------------------------------------
# Regex fallback walker
# ---------------------------------------------------------------------------


def _walk_regex(
    content: str, *, path: str, normalised: str, module_uid_str: str, result: ExtractionResult
) -> str:
    ns_match = _RE_NAMESPACE.search(content)
    namespace = ns_match.group("name") if ns_match else ""
    seen: set[str] = set()
    for match in _RE_USE.finditer(content):
        fqn = match.group("fqn").lstrip("\\")
        target = f"code:external:{fqn}"
        if target in seen:
            continue
        seen.add(target)
        result.nodes.append(
            GraphNode(
                uid=target,
                kind="code:external",
                label=fqn,
                lang="php",
                metadata={"extractor": EXTRACTOR_ID, "external_kind": "php_use"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=target,
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
            )
        )
    for match in _RE_TYPE.finditer(content):
        name = match.group("name")
        kind = match.group("kind")
        uid = interface_uid(path, name) if kind == "interface" else class_uid(path, name)
        if uid in seen:
            continue
        seen.add(uid)
        meta = {"extractor": EXTRACTOR_ID}
        if kind == "trait":
            meta["php_kind"] = "trait"
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:interface" if kind == "interface" else "code:class",
                label=name,
                file_path=normalised,
                start_line=content.count("\n", 0, match.start()) + 1,
                lang="php",
                metadata=meta,
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
    for match in _RE_FUNC.finditer(content):
        name = match.group("name")
        uid = func_uid(path, name)
        if uid in seen:
            continue
        seen.add(uid)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=normalised,
                start_line=content.count("\n", 0, match.start()) + 1,
                lang="php",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
    return namespace


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a PHP source file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_uid_str = file_uid(path)
    module_uid_str = module_uid(path)

    namespace = ""
    used_ts = False
    if _TS_AVAILABLE and _PHP_LANG is not None:
        try:
            parser = _ts.Parser(_PHP_LANG)
            content_bytes = content.encode("utf-8")
            tree = parser.parse(content_bytes)
            used_ts = True
            namespace, _local, _imp = _walk_php_symbols(
                tree.root_node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
            )
            _walk_php_calls(
                tree.root_node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                imported=_imp,
                result=result,
            )
            if _has_error(tree.root_node):
                result.parse_errors.append(
                    ParseError(
                        kind="tree_sitter_error", detail="tree-sitter recorded ERROR node(s)"
                    )
                )
        except Exception as exc:  # pragma: no cover - defensive
            result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
            used_ts = False

    if not used_ts:
        namespace = _walk_regex(
            content, path=path, normalised=normalised, module_uid_str=module_uid_str, result=result
        )

    file_node = GraphNode(
        uid=file_uid_str,
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="php",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID, "namespace": namespace},
    )
    result.nodes.insert(0, file_node)

    module_label = namespace or PurePosixPath(normalised).stem
    result.nodes.append(
        GraphNode(
            uid=module_uid_str,
            kind="code:module",
            label=module_label,
            file_path=normalised,
            lang="php",
            metadata={"extractor": EXTRACTOR_ID, "namespace": namespace},
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=file_uid_str,
            target_uid=module_uid_str,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    emit_contains_spine(
        file_path=path, file_uid_=file_uid_str, result=result, extractor_id=EXTRACTOR_ID
    )
    _promote_stubs(result)
    return result


def _has_error(root: Any) -> bool:
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            return True
        stack.extend(n.children)
    return False


__all__ = [
    "EXTRACTOR_ID",
    "class_uid",
    "extract",
    "file_uid",
    "func_uid",
    "interface_uid",
    "method_uid",
    "module_uid",
    "variable_uid",
]
