"""Regex call-site and JSX-usage scanning for the TS fallback.

Regex cannot determine function boundaries, so every edge is sourced at the
module node; the tree-sitter walk re-homes them to the exact caller when the
grammar is available.
"""

from __future__ import annotations

import re

from ..types import EvidenceSignal, GraphEdge
from ._ts_uids import _TS_KEYWORDS, EXTRACTOR_ID, module_uid
from .md_links import ExtractionResult

# Call-site scanner — looks for `name(` and `name.something(`.
_CALL_RE = re.compile(
    r"""(?<![.\w$])
        (?P<target>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)
        \s*\(
    """,
    re.VERBOSE,
)
# JSX component usage — uppercase tag => React component.
_JSX_COMPONENT_RE = re.compile(r"<(?P<name>[A-Z][A-Za-z0-9_]*)\b")


def _extract_calls(
    *,
    path: str,
    content: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """Emit call / constructs edges sourced at the module level.

    Per plan §7.2 the baseline scanner records call-sites against the
    enclosing module (not the function) because regex alone cannot
    reliably determine function boundaries. The LSP overlay re-homes
    these edges to the exact caller.
    """
    module = module_uid(path)
    for match in _CALL_RE.finditer(content):
        target = match.group("target")
        root = target.split(".")[0]
        if root in _TS_KEYWORDS:
            continue
        line = content[: match.start()].count("\n") + 1
        is_ctor = target.split(".")[-1][:1].isupper()

        if target in local_names:
            resolved = local_names[target]
            confidence = 0.5
            signal = EvidenceSignal("same_scope", 0.5)
        elif root in imported_names:
            specifier = imported_names[root]
            tail = ".".join(target.split(".")[1:]) or root
            resolved = f"code:external:{specifier}:{tail}"
            confidence = 0.4
            signal = EvidenceSignal("explicit_import", 0.4, note=specifier)
        else:
            resolved = f"code:external:unresolved:{target}"
            confidence = 0.3
            signal = EvidenceSignal("unresolved_call", 0.3)

        result.edges.append(
            GraphEdge(
                source_uid=module,
                target_uid=resolved,
                edge_type="constructs" if is_ctor else "calls",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{path}:{line}",
                evidence=(signal,),
            )
        )


def _extract_jsx_components(
    *,
    path: str,
    content: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    module = module_uid(path)
    seen: set[str] = set()
    for match in _JSX_COMPONENT_RE.finditer(content):
        name = match.group("name")
        if name in seen:
            continue
        seen.add(name)
        line = content[: match.start()].count("\n") + 1
        if name in local_names:
            resolved = local_names[name]
            confidence = 0.8
        elif name in imported_names:
            resolved = f"code:external:{imported_names[name]}:{name}"
            confidence = 0.7
        else:
            resolved = f"code:external:unresolved:{name}"
            confidence = 0.4
        result.edges.append(
            GraphEdge(
                source_uid=module,
                target_uid=resolved,
                edge_type="constructs",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("jsx_component", 0.8),),
            )
        )
