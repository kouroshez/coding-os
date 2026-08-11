"""Regex declaration scanning for the TS fallback — classes, interfaces,
functions, and arrow-assigned functions, plus the decorator and heritage
fragments that hang off them.

Pattern-only: a declaration is recognised by its opening line, so nothing here
depends on a parsed tree. Used when the TS/TSX grammar is unavailable.
"""

from __future__ import annotations

import re

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._ts_uids import EXTRACTOR_ID, class_uid, function_uid, interface_uid
from .md_links import ExtractionResult

_CLASS_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?:\s+extends\s+(?P<parent>[A-Za-z_$][\w$.]*))?
        (?:\s+implements\s+(?P<implements>[^{]+?))?
        \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_INTERFACE_RE = re.compile(
    r"""^\s*(?:export\s+)?interface\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?:\s+extends\s+(?P<parents>[^{]+?))?
        \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?P<generics><[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_ARROW_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?
        (?:const|let|var)\s+
        (?P<name>[A-Za-z_$][\w$]*)
        \s*(?::[^=]+)?\s*=\s*
        (?:async\s+)?
        (?:<[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"""^\s*(?:public|protected|private|readonly|async|static|\s)*\s*
        (?P<name>[A-Za-z_$][\w$]*)
        (?P<generics><[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)

# Decorator — lands on the *next* decl.
_DECORATOR_RE = re.compile(
    r"""^\s*@(?P<target>[A-Za-z_$][\w$.]*)
        (?:\s*\([^)]*\))?\s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


def _extract_classes(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _CLASS_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = class_uid(path, name)
        signature = _format_class_signature(
            name=name, parent=match.group("parent"), implements=match.group("implements")
        )
        decorators = _collect_preceding_decorators(content, match.start())
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=path,
                start_line=line,
                signature=signature,
                lang=lang,
                metadata={
                    "extractor": EXTRACTOR_ID,
                    "decorators": list(decorators),
                },
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{path}:{line}",
            )
        )
        if match.group("parent"):
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{match.group('parent')}",
                    edge_type="inherits_from",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                    evidence=(EvidenceSignal("ts_extends", 0.7),),
                )
            )
        if match.group("implements"):
            for iface in _split_implements(match.group("implements")):
                result.edges.append(
                    GraphEdge(
                        source_uid=uid,
                        target_uid=f"code:external:{iface}",
                        edge_type="implements",
                        extractor=EXTRACTOR_ID,
                        confidence=0.6,
                    )
                )
        for decorator in decorators:
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{decorator}",
                    edge_type="is_decorated_by",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                )
            )


def _extract_interfaces(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _INTERFACE_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = interface_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:interface",
                label=name,
                file_path=path,
                start_line=line,
                lang=lang,
                signature=f"interface {name}",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        parents_raw = match.group("parents") or ""
        for parent in _split_implements(parents_raw):
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{parent}",
                    edge_type="extends",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                )
            )


def _extract_functions(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _FUNCTION_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=line,
                signature=f"function {name}({match.group('generics') or ''})".replace("()", "(…)"),
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _extract_arrow_fns(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _ARROW_RE.finditer(content):
        name = match.group("name")
        if name in local_names:
            continue
        line = content[: match.start()].count("\n") + 1
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=line,
                signature=f"const {name} = (…) =>",
                lang=lang,
                metadata={"arrow": True, "extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _collect_preceding_decorators(content: str, idx: int) -> tuple[str, ...]:
    """Walk backwards from `idx` and return decorators attached to the decl."""
    # Scan at most 5 lines upward.
    upper = max(content.rfind("\n", 0, idx), 0)
    # Find the start of that line.
    line_start = content.rfind("\n", 0, upper)
    line_start = line_start + 1 if line_start >= 0 else 0
    block = content[line_start:idx]
    decorators: list[str] = []
    for match in _DECORATOR_RE.finditer(block):
        decorators.append(match.group("target"))
    return tuple(decorators)


def _format_class_signature(*, name: str, parent: str | None, implements: str | None) -> str:
    parts = [f"class {name}"]
    if parent:
        parts.append(f"extends {parent}")
    if implements:
        ifaces = ", ".join(_split_implements(implements))
        if ifaces:
            parts.append(f"implements {ifaces}")
    return " ".join(parts)


def _split_implements(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]
