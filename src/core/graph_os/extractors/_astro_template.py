"""graph_os — what an `.astro` template renders and calls.

code_ts reads only the frontmatter and scripts (`_astro_split`), so `<Card />`
and `{formatDate(post.date)}` in the template made no edge. This pass reads the
template with the frontmatter's own bindings: a capitalised tag renders the
component (`constructs`), a name called inside `{…}` — outside its comments and
strings — is a call. Targets match
the TSX pass for the same name; a name the frontmatter neither imports nor
declares — `Astro.props`, a global — makes no edge rather than a guess.
"""

from __future__ import annotations

import re

from ..types import EvidenceSignal, GraphEdge
from ._astro_split import astro_template
from ._ts_nodes import ts_member_tail, ts_namespace_imports
from ._ts_uids import _TS_KEYWORDS, EXTRACTOR_ID_TS
from .md_links import ExtractionResult

_TAG_RE = re.compile(r"<([A-Z][\w$]*(?:\.[A-Za-z_$][\w$]*)*)(?=[\s/>])")
_CALL_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(")
_NOT_CODE_RE = re.compile(
    r"/\*.*?\*/|//[^\n]*|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", re.DOTALL
)


def emit_template_edges(
    text: str,
    *,
    path: str,
    module_uid_: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    template = astro_template(text)
    namespaces = ts_namespace_imports(result)
    for match in _TAG_RE.finditer(template):
        name = match.group(1)
        target = _target(
            name, ts_member_tail(name.split(".")[0], name, namespaces), imported_names, local_names
        )
        if target is not None:
            _append(
                result,
                module_uid_,
                target,
                "constructs",
                "astro_component",
                path,
                template,
                match.start(),
            )
    for start, end in _expressions(template):
        code = _NOT_CODE_RE.sub(lambda match: _blank(match.group(0)), template[start:end])
        for match in _CALL_RE.finditer(code):
            name = match.group(1)
            head = name.split(".")[0]
            # `press.items.map()` walks imported data; only `fn()` / `ns.fn()` name a function.
            if head in _TS_KEYWORDS or name.count(".") > 1:
                continue
            target = _target(
                name, ts_member_tail(head, name, namespaces), imported_names, local_names
            )
            if target is not None:
                _append(
                    result,
                    module_uid_,
                    target,
                    "calls",
                    "astro_expression",
                    path,
                    template,
                    start + match.start(),
                )


def _target(
    name: str, tail: str, imported_names: dict[str, str], local_names: dict[str, str]
) -> str | None:
    if name in local_names:
        return local_names[name]
    head = name.split(".")[0]
    if head in imported_names:
        return f"code:external:{imported_names[head]}:{tail}"
    return None


def _blank(text: str) -> str:
    return "".join(char if char == "\n" else " " for char in text)


def _expressions(template: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    depth, start, quote = 0, 0, ""
    for index, char in enumerate(template):
        if depth and quote:
            quote = "" if char == quote else quote
        elif depth and char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
            if depth == 1:
                start = index + 1
        elif char == "}" and depth:
            depth -= 1
            if not depth:
                spans.append((start, index))
    return spans


def _append(
    result: ExtractionResult,
    source: str,
    target: str,
    edge_type: str,
    signal: str,
    path: str,
    template: str,
    offset: int,
) -> None:
    confidence = (
        0.8 if target.startswith("code:") and not target.startswith("code:external:") else 0.7
    )
    result.edges.append(
        GraphEdge(
            source_uid=source,
            target_uid=target,
            edge_type=edge_type,
            extractor=EXTRACTOR_ID_TS,
            confidence=confidence,
            source_span=f"{path}:{template.count(chr(10), 0, offset) + 1}",
            evidence=(EvidenceSignal(signal, confidence),),
        )
    )
