"""graph_os — a declaration's body fingerprint, the signal behind clone detection.

Two hashes per declaration, after the clone types of Roy & Cordy (2007): `text`
hashes the token stream with layout and comments dropped, so it matches an exact
copy (Type-1); `structure` also renames every identifier by its first appearance
and blinds every literal, so it matches a copy whose names and constants were
changed (Type-2). A body under MIN_TOKENS — jscpd's default — is too small for a
match to mean a copy, and gets neither.
"""

from __future__ import annotations

import hashlib
import io
import keyword
import tokenize
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

MIN_TOKENS = 50
HASH_CHARS = 16

_NAME = "name"
_LITERAL = "literal"
_OTHER = "other"

_LITERAL_TYPES = frozenset(
    {
        "string",
        "template_string",
        "number",
        "regex",
        "jsx_text",
        "interpreted_string_literal",
        "raw_string_literal",
        "int_literal",
        "float_literal",
        "imaginary_literal",
        "rune_literal",
        "raw_string",
        "ansi_c_string",
        "translated_string",
        "heredoc_body",
    }
)
_PYTHON_SKIPPED = frozenset({tokenize.NL, tokenize.COMMENT, tokenize.ENCODING, tokenize.ENDMARKER})
_PYTHON_LAYOUT = frozenset({tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL})
_PYTHON_MARKS = {tokenize.INDENT: "{", tokenize.DEDENT: "}", tokenize.NEWLINE: ";"}


@dataclass(frozen=True)
class Fingerprint:
    structure: str | None = None
    text: str | None = None


UNFINGERPRINTED = Fingerprint()


def fingerprint(tokens: Iterable[tuple[str, str]]) -> Fingerprint:
    text_hash = hashlib.sha256()
    structure_hash = hashlib.sha256()
    names: dict[str, int] = {}
    count = 0
    for category, token in tokens:
        count += 1
        text_hash.update(token.encode("utf-8", "replace") + b"\0")
        if category == _NAME:
            token = f"${names.setdefault(token, len(names))}"
        elif category == _LITERAL:
            token = "$L"
        structure_hash.update(token.encode("utf-8", "replace") + b"\0")
    if count < MIN_TOKENS:
        return UNFINGERPRINTED
    return Fingerprint(
        structure=structure_hash.hexdigest()[:HASH_CHARS],
        text=text_hash.hexdigest()[:HASH_CHARS],
    )


def body_fields(node: Any) -> dict[str, Any]:
    body = fingerprint(_tree_sitter_tokens(node))
    return {
        "end_line": node.end_point[0] + 1,
        "ast_hash": body.structure,
        "content_hash": body.text,
    }


def _tree_sitter_tokens(node: Any) -> Iterator[tuple[str, str]]:
    stack = [node]
    while stack:
        current = stack.pop()
        kind = current.type
        if kind == "comment":
            continue
        if current.child_count and kind not in _LITERAL_TYPES:
            stack.extend(reversed(current.children))
            continue
        text = current.text.decode("utf-8", "replace") if current.text else ""
        if not text.strip():
            continue
        if kind in _LITERAL_TYPES:
            yield _LITERAL, text
        elif kind.endswith("identifier") or kind == "variable_name":
            yield _NAME, text
        else:
            yield _OTHER, text


def python_fingerprints(
    content: str, spans: Iterable[tuple[str, int, int | None]]
) -> dict[str, Fingerprint]:
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
    except (tokenize.TokenError, SyntaxError):
        return {}
    rows = [token.start[0] for token in tokens]
    prints: dict[str, Fingerprint] = {}
    for uid, start, end in spans:
        if end is None:
            continue
        span = tokens[bisect_left(rows, start) : bisect_right(rows, end)]
        prints[uid] = fingerprint(_python_tokens(_trim_layout(span)))
    return prints


def _trim_layout(span: list[tokenize.TokenInfo]) -> list[tokenize.TokenInfo]:
    start, end = 0, len(span)
    while start < end and span[start].type in _PYTHON_LAYOUT:
        start += 1
    while end > start and span[end - 1].type in _PYTHON_LAYOUT:
        end -= 1
    return span[start:end]


def _python_tokens(span: list[tokenize.TokenInfo]) -> Iterator[tuple[str, str]]:
    # An f-string tokenizes into parts (3.12+); it is one literal, whole.
    depth = 0
    literal: list[str] = []
    body_started = False
    index = 0
    while index < len(span):
        token = span[index]
        index += 1
        name = tokenize.tok_name[token.type]
        depth += name.endswith("STRING_START")
        if depth:
            literal.append(token.string)
            depth -= name.endswith("STRING_END")
            if not depth:
                yield _LITERAL, "".join(literal)
                literal.clear()
            continue
        if token.type in _PYTHON_SKIPPED:
            continue
        if token.type == tokenize.INDENT and not body_started:
            body_started = True
            index = _skip_docstring(span, index)
        if token.type in _PYTHON_MARKS:
            yield _OTHER, _PYTHON_MARKS[token.type]
        elif token.type in (tokenize.STRING, tokenize.NUMBER):
            yield _LITERAL, token.string
        elif token.type == tokenize.NAME and not keyword.iskeyword(token.string):
            yield _NAME, token.string
        else:
            yield _OTHER, token.string


def _skip_docstring(span: list[tokenize.TokenInfo], index: int) -> int:
    after = index
    while after < len(span) and span[after].type in (tokenize.COMMENT, tokenize.NL):
        after += 1
    is_docstring = (
        after + 1 < len(span)
        and span[after].type == tokenize.STRING
        and span[after + 1].type == tokenize.NEWLINE
    )
    return after + 2 if is_docstring else index
