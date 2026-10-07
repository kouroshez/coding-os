"""Fragment clones: a block of code copied into two otherwise different places.

The clone groups in _graph_clones compare whole declarations, so a block copied
into two functions that differ elsewhere never matches. This pass reads the
indexed code files at query time, as CPD and jscpd do. Each file becomes a token
stream (comments and layout dropped, string literals kept whole, so a match is an
exact copy). Every 25-token window is hashed, and winnowing (Schleimer, Wilkerson
and Aiken, 2003) keeps the smallest hash of each 26 consecutive windows, which
still guarantees that a shared run of 50 tokens shares a kept hash. Each shared
hash is grown token by token into the longest common run. A run of at least 50
tokens is a fragment clone unless every copy lies inside a symbol the clone
groups already report. Import statements are left out, as CPD's
`--ignore-usings` does: a shared import list is no copy to refactor. A hash
found in more than 32 places is boilerplate (a license header) and is not
followed, and a run that only overlaps a wider run already reported is not
listed again.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Any

from ..extractors._fingerprint import MIN_TOKENS

WINDOW_TOKENS = 25
WINNOW_WINDOW = MIN_TOKENS - WINDOW_TOKENS + 1
MAX_OCCURRENCES = 32

_HASH_COMMENT_SUFFIXES = frozenset({".py", ".sh", ".bash", ".zsh", ".rb"})
_CODE_SUFFIXES = _HASH_COMMENT_SUFFIXES | frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".astro", ".go", ".php"}
)
_STRINGS = (
    r'"""[\s\S]*?"""|' + r"'''[\s\S]*?'''|"
    r'"(?:\\.|[^"\\\n])*"|' + r"'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`"
)
# A comment is blanked only outside a string; `$#` and `${#x}` are no shell comment.
_HASH_SCAN_RE = re.compile(rf"(?P<string>{_STRINGS})|(?<![\w$\{{])#[^\n]*")
_SLASH_SCAN_RE = re.compile(rf"(?P<string>{_STRINGS})|//[^\n]*|/\*[\s\S]*?\*/|<!--[\s\S]*?-->")
_TOKEN_RE = re.compile(rf"{_STRINGS}|[A-Za-z_$][\w$]*|\d[\w.]*|\S")
_IMPORT_RE = {
    ".py": re.compile(r"^[ \t]*(?:from[ \t]+\S+[ \t]+)?import[ \t]+(?:\([^)]*\)|[^\n]*)", re.M),
    ".go": re.compile(r"^import[ \t]*(?:\([^)]*\)|[^\n]*)", re.M),
    "script": re.compile(
        r"^[ \t]*(?:import|export)\b[^;'\"]*?(?:from[ \t]*)?['\"][^'\"\n]+['\"][ \t]*;?", re.M
    ),
}
_SCRIPT_SUFFIXES = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".astro"}
)


@dataclass
class _File:
    path: str
    tokens: list[str]
    lines: list[tuple[int, int]]


def fragment_clones(
    root: Path,
    paths: Iterable[str],
    covered: dict[str, list[tuple[int, int]]],
) -> list[dict[str, Any]]:
    """Groups of identical code runs of MIN_TOKENS or more, outside the reported symbol clones."""
    files = [read for path in sorted(set(paths)) if (read := _read(root, path)) is not None]
    occurrences: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for index, file in enumerate(files):
        for position, value in _winnow(file.tokens):
            occurrences[value].append((index, position))
    groups: dict[tuple[str, ...], set[tuple[int, int, int]]] = defaultdict(set)
    grown: dict[tuple[int, int, int], list[tuple[int, int]]] = defaultdict(list)
    for places in occurrences.values():
        if not 2 <= len(places) <= MAX_OCCURRENCES:
            continue
        for (first, at), (second, other) in combinations(places, 2):
            diagonal = (first, second, at - other)
            if any(start <= at < end for start, end in grown[diagonal]):
                continue
            run = _grow(files[first].tokens, at, files[second].tokens, other)
            if run is None:
                continue
            start, other_start, length = run
            if first == second and abs(start - other_start) < length:
                continue
            grown[diagonal].append((start, start + length))
            key = tuple(files[first].tokens[start : start + length])
            groups[key] |= {(first, start, length), (second, other_start, length)}
    candidates = []
    for key, members in groups.items():
        spans = [_span(files[index], start, length) for index, start, length in sorted(members)]
        if all(_inside(span, covered.get(span[0], [])) for span in spans):
            continue
        widest = max(end - begin + 1 for _, begin, end in spans)
        candidates.append((widest * (len(spans) - 1), len(key), spans))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    kept: dict[str, list[tuple[int, int]]] = defaultdict(list)
    found = []
    for duplicated, tokens, spans in candidates:
        if all(_overlaps(span, kept[span[0]]) for span in spans):
            continue
        for path, begin, end in spans:
            kept[path].append((begin, end))
        found.append(
            {
                "tokens": tokens,
                "duplicated_lines": duplicated,
                "members": [{"file": path, "lines": [begin, end]} for path, begin, end in spans],
            }
        )
    return found


def _read(root: Path, path: str) -> _File | None:
    suffix = PurePosixPath(path).suffix
    if suffix not in _CODE_SUFFIXES:
        return None
    try:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    scan = _HASH_SCAN_RE if suffix in _HASH_COMMENT_SUFFIXES else _SLASH_SCAN_RE
    code = scan.sub(lambda match: match.group(0) if match.group("string") else _blank(match), text)
    imports = _IMPORT_RE.get("script" if suffix in _SCRIPT_SUFFIXES else suffix)
    if imports is not None:
        code = imports.sub(_blank, code)
    newlines = [offset for offset, char in enumerate(code) if char == "\n"]
    tokens, lines = [], []
    for match in _TOKEN_RE.finditer(code):
        tokens.append(match.group(0))
        lines.append(
            (bisect_right(newlines, match.start()) + 1, bisect_right(newlines, match.end() - 1) + 1)
        )
    return _File(path, tokens, lines)


def _blank(match: re.Match[str]) -> str:
    return "".join(char if char == "\n" else " " for char in match.group(0))


def _winnow(tokens: list[str]) -> list[tuple[int, int]]:
    # The rightmost smallest hash of every WINNOW_WINDOW consecutive windows.
    hashes = [
        hash(tuple(tokens[i : i + WINDOW_TOKENS])) for i in range(len(tokens) - WINDOW_TOKENS + 1)
    ]
    picked: list[tuple[int, int]] = []
    window: deque[int] = deque()
    for index, value in enumerate(hashes):
        while window and hashes[window[-1]] >= value:
            window.pop()
        window.append(index)
        if window[0] <= index - WINNOW_WINDOW:
            window.popleft()
        if index >= WINNOW_WINDOW - 1 or index == len(hashes) - 1:
            chosen = window[0]
            if not picked or picked[-1][0] != chosen:
                picked.append((chosen, hashes[chosen]))
    return picked


def _grow(first: list[str], at: int, second: list[str], other: int) -> tuple[int, int, int] | None:
    while at > 0 and other > 0 and first[at - 1] == second[other - 1]:
        at, other = at - 1, other - 1
    length = 0
    while (
        at + length < len(first)
        and other + length < len(second)
        and first[at + length] == second[other + length]
    ):
        length += 1
    return (at, other, length) if length >= MIN_TOKENS else None


def _span(file: _File, start: int, length: int) -> tuple[str, int, int]:
    return file.path, file.lines[start][0], file.lines[start + length - 1][1]


def _overlaps(span: tuple[str, int, int], spans: list[tuple[int, int]]) -> bool:
    _, begin, end = span
    return any(start <= end and begin <= stop for start, stop in spans)


def _inside(span: tuple[str, int, int], spans: list[tuple[int, int]]) -> bool:
    _, begin, end = span
    return any(start <= begin and end <= stop for start, stop in spans)
