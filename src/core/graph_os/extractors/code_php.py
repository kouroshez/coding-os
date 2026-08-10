r"""graph_os — PHP source file extractor (tree-sitter-php primary, regex fallback).

Targets Python-gold parity for the PHP ecosystem (spec §4.9):

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

  Module layout
    - `_php_uids`    uid grammar + node-text primitives (leaf; imports no sibling)
    - `_php_symbols` declaration walker (nodes, heritage/type/attribute edges)
    - `_php_calls`   same-file call + construction edges
    - this module    parser bootstrap, regex fallback, and result assembly
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

from ..types import GraphEdge, GraphNode
from ._php_calls import _walk_php_calls
from ._php_symbols import _walk_php_symbols
from ._php_uids import (
    EXTRACTOR_ID,
    class_uid,
    file_uid,
    func_uid,
    interface_uid,
    method_uid,
    module_uid,
    variable_uid,
)
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

try:
    import tree_sitter as _ts
    import tree_sitter_php as _ts_php

    _PHP_LANG = _ts.Language(_ts_php.language_php())
    _TS_AVAILABLE = True
except Exception:  # pragma: no cover - lean install path
    _ts = None  # type: ignore[assignment]
    _PHP_LANG = None  # type: ignore[assignment]
    _TS_AVAILABLE = False


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
