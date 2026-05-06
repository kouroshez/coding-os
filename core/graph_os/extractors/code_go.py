"""graph_os — Go source file extractor (Wave 1 A3).

DEPENDS:  stdlib regex only — no go AST library to keep the dep
          surface tight.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath

from ..types import GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    _normalize_path,
)

logger = logging.getLogger("graph_os.extractors.code_go")
EXTRACTOR_ID = "code_go@v1"


_PACKAGE_RE = re.compile(r"^\s*package\s+(?P<name>[A-Za-z_][\w]*)\s*$", re.MULTILINE)

_FUNC_RE = re.compile(
    r"""^\s*
        func\s+
        (?:\((?P<recv>[^)]*)\)\s+)?     # optional method receiver
        (?P<name>[A-Za-z_][\w]*)
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)

_TYPE_RE = re.compile(
    r"""^\s*
        type\s+
        (?P<name>[A-Za-z_][\w]*)
        \s+
        (?P<kind>struct|interface)
        \b
    """,
    re.VERBOSE | re.MULTILINE,
)

# Single import:  import "fmt"
# Grouped import: import ( "fmt" \n "os" )
_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+(?:[A-Za-z_]\w*\s+)?"(?P<path>[^"]+)"\s*$', re.MULTILINE)
_IMPORT_BLOCK_RE = re.compile(r"^\s*import\s+\(\s*(?P<body>[^)]*?)\s*\)", re.MULTILINE | re.DOTALL)
_IMPORT_LINE_RE = re.compile(r'^\s*(?:[A-Za-z_]\w*\s+)?"(?P<path>[^"]+)"', re.MULTILINE)

# Heuristic call detection — qualified call like `pkg.Func(` or method
# call `recv.Method(`. Bounded to avoid false positives on selectors.
_CALL_RE = re.compile(
    r"\b(?P<lhs>[A-Za-z_][\w]*)\.(?P<name>[A-Z][\w]*)\s*\(",
)


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:{_normalize_path(path)}"


def func_uid(path: str, name: str) -> str:
    return f"code:function:{_normalize_path(path)}::{name}"


def method_uid(path: str, recv_type: str, name: str) -> str:
    return f"code:method:{_normalize_path(path)}::{recv_type}.{name}"


def class_uid(path: str, name: str) -> str:
    return f"code:class:{_normalize_path(path)}::{name}"


def import_uid(target_pkg: str) -> str:
    """Imports resolve to an external `code:external:` uid because the
    extractor cannot pin a Go import path to a repo file without the
    full module map. The cross-repo joiner (groups/cross_repo.py) can
    promote to real file uids when present."""
    return f"code:external:{target_pkg}"


def _parse_receiver(recv: str) -> str:
    """Extract the type from a Go method receiver clause.

    Examples (input → output):
        ``s *Server``    → ``Server``
        ``r Reader``     → ``Reader``
        ``*Server``      → ``Server``
        ``s *T[int]``    → ``T``  (generics — strip type parameters)
    """
    if not recv:
        return ""
    raw = recv.strip()
    parts = raw.split()
    type_part = parts[-1] if parts else raw
    type_part = type_part.lstrip("*")
    # Strip generic type parameters: T[int] -> T
    if "[" in type_part:
        type_part = type_part.split("[", 1)[0]
    return type_part


def _line_number_for(content: str, span_start: int) -> int:
    """1-based line number of a regex match start position."""
    return content.count("\n", 0, span_start) + 1


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a Go source file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    pkg_match = _PACKAGE_RE.search(content)
    pkg_name = pkg_match.group("name") if pkg_match else PurePosixPath(normalised).stem

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="go",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID, "package": pkg_name},
    )
    result.nodes.append(file_node)

    module_node = GraphNode(
        uid=module_uid(path),
        kind="code:module",
        label=pkg_name,
        file_path=normalised,
        lang="go",
        metadata={"extractor": EXTRACTOR_ID, "package": pkg_name},
    )
    result.nodes.append(module_node)
    result.edges.append(
        GraphEdge(
            source_uid=file_uid(path),
            target_uid=module_node.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    _emit_funcs_and_methods(content, normalised, path, module_node, result)
    _emit_types(content, normalised, path, module_node, result)
    _emit_imports(content, path, module_node, result)
    _emit_qualified_calls(content, normalised, path, result)

    return result


def _emit_funcs_and_methods(
    content: str,
    normalised: str,
    path: str,
    module_node: GraphNode,
    result: ExtractionResult,
) -> None:
    seen_uids: set[str] = set()
    for match in _FUNC_RE.finditer(content):
        name = match.group("name")
        recv = match.group("recv") or ""
        recv_type = _parse_receiver(recv)
        line = _line_number_for(content, match.start())

        if recv_type:
            uid = method_uid(path, recv_type, name)
            kind = "code:method"
            label = f"{recv_type}.{name}"
        else:
            uid = func_uid(path, name)
            kind = "code:function"
            label = name

        if uid in seen_uids:
            continue
        seen_uids.add(uid)

        result.nodes.append(
            GraphNode(
                uid=uid,
                kind=kind,
                label=label,
                file_path=normalised,
                start_line=line,
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "receiver": recv_type or ""},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_node.uid,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _emit_types(
    content: str,
    normalised: str,
    path: str,
    module_node: GraphNode,
    result: ExtractionResult,
) -> None:
    seen: set[str] = set()
    for match in _TYPE_RE.finditer(content):
        name = match.group("name")
        uid = class_uid(path, name)
        if uid in seen:
            continue
        seen.add(uid)
        line = _line_number_for(content, match.start())
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=normalised,
                start_line=line,
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "go_kind": match.group("kind")},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_node.uid,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _emit_imports(
    content: str,
    path: str,
    module_node: GraphNode,
    result: ExtractionResult,
) -> None:
    targets: set[str] = set()
    for match in _IMPORT_SINGLE_RE.finditer(content):
        targets.add(match.group("path"))
    for block in _IMPORT_BLOCK_RE.finditer(content):
        body = block.group("body") or ""
        for line_match in _IMPORT_LINE_RE.finditer(body):
            targets.add(line_match.group("path"))

    for target_pkg in sorted(targets):
        target_uid_str = import_uid(target_pkg)
        result.nodes.append(
            GraphNode(
                uid=target_uid_str,
                kind="code:external",
                label=target_pkg,
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "external_kind": "go_import"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_node.uid,
                target_uid=target_uid_str,
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.95,
            )
        )


def _emit_qualified_calls(
    content: str,
    normalised: str,
    path: str,
    result: ExtractionResult,
) -> None:
    """Best-effort `pkg.Func` / `recv.Method` call detection.

    Confidence is conservative (0.5) because regex cannot disambiguate
    between a real call and a struct field reference followed by a
    parenthesized expression. The cross-repo joiner can re-rank these
    when type information becomes available.
    """
    module_uid_str = module_uid(path)
    seen: set[tuple[str, str]] = set()
    for match in _CALL_RE.finditer(content):
        lhs = match.group("lhs")
        name = match.group("name")
        target = f"code:external:{lhs}.{name}"
        key = (module_uid_str, target)
        if key in seen:
            continue
        seen.add(key)
        result.nodes.append(
            GraphNode(
                uid=target,
                kind="code:external",
                label=f"{lhs}.{name}",
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "external_kind": "go_call"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=target,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=0.5,
            )
        )


__all__ = [
    "EXTRACTOR_ID",
    "extract",
    "file_uid",
    "module_uid",
    "func_uid",
    "method_uid",
    "class_uid",
    "import_uid",
]
