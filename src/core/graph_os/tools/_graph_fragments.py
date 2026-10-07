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
listed again. A block repeated back to back matches itself one copy along, so
that run is cut into its copies.

Every file is read, since a copy's partner can live anywhere, but with a
`focus` (the files of a scope) those files are read first and a file outside it
is kept only when it shares a hash with them. Token streams are held interned
with their lines in arrays, 31 bytes a token against 109 before (measured on
this repo's 654,460 tokens), and reading stops at MAX_TOKENS: at 7.8 bytes of
source a token, about 40 MB of code.
"""

from __future__ import annotations

import re
import sys
from array import array
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
MAX_TOKENS = 5_000_000

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
    # Only a statement that names a module: `export function` and `export const` are code.
    "script": re.compile(
        r"^[ \t]*(?:import|export)[ \t]+(?:type[ \t]+)?(?:[\w$]+[ \t]*,[ \t]*)?"
        r"(?:\{[^{}]*\}|\*(?:[ \t]+as[ \t]+[\w$]+)?|[\w$]+)[ \t]*from[ \t]*['\"][^'\"\n]+['\"][ \t]*;?"
        r"|^[ \t]*import[ \t]*['\"][^'\"\n]+['\"][ \t]*;?",
        re.M,
    ),
}
_SCRIPT_SUFFIXES = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".astro"}
)


@dataclass
class _File:
    path: str
    tokens: list[str]
    starts: array[int]
    ends: array[int]


def fragment_clones(
    root: Path,
    paths: Iterable[str],
    covered: dict[str, list[tuple[int, int]]],
    *,
    focus: set[str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Groups of identical runs of MIN_TOKENS or more outside the symbol clones, and whether all files fit."""
    ordered = sorted(set(paths), key=lambda path: (focus is not None and path not in focus, path))
    files: list[_File] = []
    occurrences: dict[int, list[tuple[int, int]]] = defaultdict(list)
    focus_hashes: set[int] | None = None
    held, complete = 0, True
    for path in ordered:
        if focus is not None and focus_hashes is None and path not in focus:
            focus_hashes = set(occurrences)
        file = _read(root, path)
        if file is None:
            continue
        picked = [
            (position, value)
            for position, value in _winnow(file.tokens)
            if focus_hashes is None or value in focus_hashes
        ]
        if not picked:
            continue
        held += len(file.tokens)
        if held > MAX_TOKENS:
            complete = False
            break
        for position, value in picked:
            occurrences[value].append((len(files), position))
        files.append(file)
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
            grown[diagonal].append((start, start + length))
            copies = {(first, start, length), (second, other_start, length)}
            if first == second and other_start - start < length:
                period = other_start - start
                if period < MIN_TOKENS:
                    continue
                copies = {(first, start + step, period) for step in range(0, length + 1, period)}
                length = period
            key = tuple(files[first].tokens[start : start + length])
            groups[key] |= copies
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
    return found, complete


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
    file = _File(path, [], array("L"), array("L"))
    for match in _TOKEN_RE.finditer(code):
        file.tokens.append(sys.intern(match.group(0)))
        file.starts.append(bisect_right(newlines, match.start()) + 1)
        file.ends.append(bisect_right(newlines, match.end() - 1) + 1)
    return file


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
    return file.path, file.starts[start], file.ends[start + length - 1]


def _overlaps(span: tuple[str, int, int], spans: list[tuple[int, int]]) -> bool:
    _, begin, end = span
    return any(start <= end and begin <= stop for start, stop in spans)


def _inside(span: tuple[str, int, int], spans: list[tuple[int, int]]) -> bool:
    _, begin, end = span
    return any(start <= begin and end <= stop for start, stop in spans)
