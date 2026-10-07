"""graph_os — what an `.astro` template renders and calls.

code_ts reads only the frontmatter and scripts (`_astro_split`), so `<Card />`
and `{formatDate(post.date)}` in the template made no edge. This pass reads the
template with the frontmatter's own bindings: a capitalised tag renders the
component (`constructs`), and a name called inside `{…}` is a call. Only the
code counts: strings, comments and the text of JSX written in an expression
(`<li>Don't miss {fmt(i)}</li>`, whose apostrophe opens no string) are
blanked first. Targets match the TSX pass for the same name; a name the
frontmatter neither imports nor declares — `Astro.props`, a global — makes no
edge rather than a guess.
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
# A `<` after one of these, or after `return`, opens JSX rather than comparing.
_JSX_AFTER = frozenset("(,=:?&|![{;>")
_RETURN_RE = re.compile(r"(?<![\w$])return$")


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
    for match in _CALL_RE.finditer(_code(template)):
        name = match.group(1)
        head = name.split(".")[0]
        # `press.items.map()` walks imported data; only `fn()` / `ns.fn()` name a function.
        if head in _TS_KEYWORDS or name.count(".") > 1:
            continue
        target = _target(name, ts_member_tail(head, name, namespaces), imported_names, local_names)
        if target is not None:
            _append(
                result,
                module_uid_,
                target,
                "calls",
                "astro_expression",
                path,
                template,
                match.start(),
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


def _code(template: str) -> str:
    # The template with all but the code of its `{…}` expressions blanked, so
    # offsets still map to lines. A mode stack: the template's own text, code,
    # a JSX tag being written, and the children text of a JSX element.
    code = [False] * len(template)
    modes = ["text"]
    index = 0
    while index < len(template):
        char, mode = template[index], modes[-1]
        if mode == "code":
            if char in "\"'`":
                index = _closing(template, index, char)
            elif template.startswith("//", index):
                index = _found(template, "\n", index) - 1
            elif template.startswith("/*", index):
                index = _found(template, "*/", index) + 1
            elif char == "}":
                modes.pop()
            elif char == "<" and _opens_jsx(template, index, code):
                modes.append("tag")
            else:
                code[index] = True
                if char == "{":
                    modes.append("code")
        elif char == "{":
            modes.append("code")
        elif mode == "tag" and char in "\"'":
            index = _closing(template, index, char)
        elif mode == "tag" and template.startswith("/>", index):
            modes.pop()
            index += 1
        elif mode == "tag" and char == ">":
            modes[-1] = "children"
        elif mode == "children" and template.startswith("</", index):
            index = _found(template, ">", index)
            modes.pop()
        elif mode == "children" and char == "<" and _tag_start(template, index):
            modes.append("tag")
        index += 1
    return "".join(
        char if keep or char == "\n" else " " for char, keep in zip(template, code, strict=True)
    )


def _opens_jsx(template: str, index: int, code: list[bool]) -> bool:
    if not _tag_start(template, index):
        return False
    before = index - 1
    while before >= 0 and template[before].isspace():
        before -= 1
    if before < 0 or not code[before]:
        return True
    return template[before] in _JSX_AFTER or bool(
        _RETURN_RE.search(template, max(0, before - 5), before + 1)
    )


def _tag_start(template: str, index: int) -> bool:
    following = template[index + 1 : index + 2]
    return following.isalpha() or following == ">"


def _closing(template: str, index: int, quote: str) -> int:
    index += 1
    while index < len(template) and template[index] != quote:
        index += 2 if template[index] == "\\" else 1
    return index


def _found(template: str, needle: str, index: int) -> int:
    found = template.find(needle, index)
    return len(template) if found < 0 else found


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
