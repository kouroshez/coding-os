"""graph_os — Go regex fallback, used only when the tree-sitter grammar is absent.

Conservative by design: it matches the v1 capability set so a missing grammar
degrades the graph rather than corrupting it. Imports the declaration walkers it
shares with the tree-sitter path, never the facade.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from ..types import GraphEdge, GraphNode
from ._go_calls import _walk_calls_regex
from ._go_symbols import _emit_func_node
from ._go_uids import EXTRACTOR_ID, _classify_test_func, _parse_receiver, class_uid, import_uid
from .md_links import ExtractionResult

_PACKAGE_RE = re.compile(r"^\s*package\s+(?P<name>[A-Za-z_][\w]*)\s*$", re.MULTILINE)

_FUNC_RE = re.compile(
    r"""^\s*
        func\s+
        (?:\((?P<recv>[^)]*)\)\s+)?
        (?P<name>[A-Za-z_][\w]*)
        (?:\[[^\]]*\])?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)

_TYPE_RE = re.compile(
    r"""^\s*
        type\s+
        (?P<name>[A-Za-z_][\w]*)
        (?:\[[^\]]*\])?
        \s+
        (?P<kind>struct|interface|=|[A-Za-z_])
    """,
    re.VERBOSE | re.MULTILINE,
)

_IMPORT_SINGLE_RE = re.compile(
    r'^\s*import\s+(?:(?P<alias>[A-Za-z_]\w*|\.|_)\s+)?"(?P<path>[^"]+)"\s*$',
    re.MULTILINE,
)

_IMPORT_BLOCK_RE = re.compile(r"^\s*import\s+\(\s*(?P<body>[^)]*?)\s*\)", re.MULTILINE | re.DOTALL)

_IMPORT_LINE_RE = re.compile(
    r'^\s*(?:(?P<alias>[A-Za-z_]\w*|\.|_)\s+)?"(?P<path>[^"]+)"', re.MULTILINE
)


def _emit_regex_import(
    raw_path: str,
    alias: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen_imports: set[str],
) -> None:
    if not raw_path or raw_path in seen_imports:
        return
    seen_imports.add(raw_path)
    target = import_uid(raw_path)
    is_dot = alias == "."
    is_blank = alias == "_"
    metadata: dict[str, Any] = {
        "extractor": EXTRACTOR_ID,
        "external_kind": "go_import",
    }
    if alias and not is_dot and not is_blank:
        metadata["alias"] = alias
    if is_dot:
        metadata["dot_import"] = True
    if is_blank:
        metadata["blank_import"] = True
    result.nodes.append(
        GraphNode(
            uid=target,
            kind="code:external",
            label=raw_path,
            lang="go",
            metadata=metadata,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=target,
            edge_type="imports",
            extractor=EXTRACTOR_ID,
            confidence=0.95,
        )
    )


def _walk_regex(
    content: str,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    file_uid_str: str,
    result: ExtractionResult,
) -> str:
    pkg_match = _PACKAGE_RE.search(content)
    pkg_name = pkg_match.group("name") if pkg_match else PurePosixPath(normalised).stem

    seen_funcs: set[str] = set()
    seen_types: set[str] = set()
    seen_imports: set[str] = set()

    for match in _FUNC_RE.finditer(content):
        name = match.group("name")
        recv = match.group("recv") or ""
        receiver_type = _parse_receiver(recv)
        line = content.count("\n", 0, match.start()) + 1
        _emit_func_node(
            name=name,
            line=line,
            path=path,
            normalised=normalised,
            receiver_type=receiver_type,
            is_init=(name == "init" and not receiver_type),
            test_kind=_classify_test_func(name, normalised),
            has_generics=False,
            module_uid_str=module_uid_str,
            result=result,
            seen=seen_funcs,
        )

    for match in _TYPE_RE.finditer(content):
        name = match.group("name")
        uid = class_uid(path, name)
        if uid in seen_types:
            continue
        seen_types.add(uid)
        line = content.count("\n", 0, match.start()) + 1
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=normalised,
                start_line=line,
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "go_kind": match.group("kind") or "type"},
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

    for match in _IMPORT_SINGLE_RE.finditer(content):
        _emit_regex_import(
            match.group("path"),
            match.group("alias") or "",
            module_uid_str,
            result,
            seen_imports,
        )
    for block in _IMPORT_BLOCK_RE.finditer(content):
        body = block.group("body") or ""
        for line_match in _IMPORT_LINE_RE.finditer(body):
            _emit_regex_import(
                line_match.group("path"),
                line_match.group("alias") or "",
                module_uid_str,
                result,
                seen_imports,
            )

    _walk_calls_regex(content, module_uid_str=module_uid_str, result=result)
    return pkg_name
