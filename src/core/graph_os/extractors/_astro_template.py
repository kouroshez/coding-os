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
# After one of these, or after `return`, an operand starts.
_OPERAND_AFTER = frozenset("(,=:?&|![{;>")
_RETURN_RE = re.compile(r"(?<![\w$])return$")
_TAG_NAME_RE = re.compile(r"[A-Za-z][\w.:-]*")
_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
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
    # a template literal, a JSX tag being written (`void` for `<img>`, which
    # never closes), and the children text of a JSX element. Each step returns
    # the index of the last character it consumed.
    code = [False] * len(template)
    modes = ["text"]
    index = 0
    while index < len(template):
        if modes[-1] == "code":
            index = _code_step(template, index, modes, code)
        elif modes[-1] == "literal":
            index = _literal_step(template, index, modes)
        else:
            index = _markup_step(template, index, modes)
        index += 1
    return "".join(
        char if keep or char == "\n" else " " for char, keep in zip(template, code, strict=True)
    )


def _code_step(template: str, index: int, modes: list[str], code: list[bool]) -> int:
    char = template[index]
    if char in "\"'":
        return _closing(template, index, char)
    if char == "`":
        modes.append("literal")
    elif template.startswith("//", index):
        return _found(template, "\n", index) - 1
    elif template.startswith("/*", index):
        return _found(template, "*/", index + 2) + 1
    elif char == "/" and _operand_position(template, index, code):
        return _regex_end(template, index)
    elif char == "}":
        modes.pop()
    elif char == "<" and _tag_start(template, index) and _operand_position(template, index, code):
        modes.append(_tag_mode(template, index))
    else:
        code[index] = True
        if char == "{":
            modes.append("code")
    return index


def _literal_step(template: str, index: int, modes: list[str]) -> int:
    if template[index] == "`":
        modes.pop()
    elif template[index] == "\\":
        return index + 1
    elif template.startswith("${", index):
        modes.append("code")
        return index + 1
    return index


def _markup_step(template: str, index: int, modes: list[str]) -> int:
    char, mode = template[index], modes[-1]
    in_tag = mode in ("tag", "void")
    if char == "{":
        modes.append("code")
    elif char == "}" and "code" in modes:
        # JSX text holds no bare `}`: it closes the expression an unclosed tag left open.
        while modes.pop() != "code":
            pass
    elif in_tag and char in "\"'":
        return _closing(template, index, char)
    elif in_tag and template.startswith("/>", index):
        modes.pop()
        return index + 1
    elif in_tag and char == ">":
        if modes.pop() == "tag":
            modes.append("children")
    elif mode == "children" and template.startswith("</", index):
        modes.pop()
        return _found(template, ">", index)
    elif mode == "children" and char == "<" and _tag_start(template, index):
        modes.append(_tag_mode(template, index))
    return index


def _operand_position(template: str, index: int, code: list[bool]) -> bool:
    # Where an operand may start, `<` opens JSX and `/` a regex rather than an operator.
    before = index - 1
    while before >= 0 and template[before].isspace():
        before -= 1
    if before < 0 or not code[before]:
        return True
    return template[before] in _OPERAND_AFTER or bool(
        _RETURN_RE.search(template, max(0, before - 5), before + 1)
    )


def _tag_mode(template: str, index: int) -> str:
    name = _TAG_NAME_RE.match(template, index + 1)
    return "void" if name is not None and name.group(0) in _VOID_ELEMENTS else "tag"


def _regex_end(template: str, index: int) -> int:
    index, in_class = index + 1, False
    while index < len(template) and template[index] != "\n":
        char = template[index]
        if char == "\\":
            index += 1
        elif char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            return index
        index += 1
    return index


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
