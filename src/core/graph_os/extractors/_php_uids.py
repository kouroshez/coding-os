"""graph_os — PHP extractor uid scheme + tree-sitter node primitives.

Leaf module: the PHP walkers and the `code_php` facade all import from here,
and it imports none of them. That keeps the uid grammar single-defined and the
sibling walkers acyclic.
"""

from __future__ import annotations

from typing import Any

from .md_links import _normalize_path

EXTRACTOR_ID = "code_php@v1"

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
