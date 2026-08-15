"""What a graph-less agent pays to answer one structural question.

Three cost models, cheapest to most expensive. Which one a benchmark quotes decides
whether the published saving is meaningful, so the choice is explicit rather than
implied:

``grep_only``
    The agent runs one grep and acts on the match lines alone. This is the floor —
    it under-counts, because match lines rarely settle "does this caller break".

``grep_windows`` (default)
    The agent greps, then opens a bounded window around the matches in the few
    highest-hit files. This is what a competent agent actually does, and it is the
    only baseline a skeptical reader will accept.

``read_all``
    The agent greps, then reads every matching file end to end. This is the ceiling,
    and quoting it alone is how a benchmark produces a number nobody believes.

Spec: docs/engineering/third-party-token-bench.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# A Read around a hit: enough to see the enclosing function and its callers'
# expectations, not the whole module.
WINDOW_LINES = 40
# How many files an agent opens before it decides it has the shape of the answer.
TOP_FILES_READ = 5


class Baseline(str, Enum):
    GREP_ONLY = "grep-only"
    GREP_WINDOWS = "grep-windows"
    READ_ALL = "read-all"


@dataclass(frozen=True)
class Document:
    path: Path
    lines: tuple[str, ...]
    characters: int


@dataclass(frozen=True)
class Corpus:
    """The target repo's text, read once.

    Re-reading the corpus per probe is the N+1 shape: 10 probes over Django's 2,818
    files is 28,180 file reads for 2,818 files' worth of content.
    """

    documents: tuple[Document, ...]

    @classmethod
    def load(cls, paths: list[Path]) -> Corpus:
        documents = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            documents.append(
                Document(path=path, lines=tuple(text.splitlines()), characters=len(text))
            )
        return cls(documents=tuple(documents))

    def __len__(self) -> int:
        return len(self.documents)


@dataclass(frozen=True)
class Hit:
    document: Document
    line_numbers: tuple[int, ...]


def find_hits(corpus: Corpus, symbol: str) -> list[Hit]:
    """Files containing the symbol, ordered by match count then path.

    The path tie-break keeps a run reproducible: without it, two files with equal
    match counts can swap places and move the top-K window.
    """
    hits = []
    for document in corpus.documents:
        numbers = tuple(i for i, line in enumerate(document.lines) if symbol in line)
        if numbers:
            hits.append(Hit(document=document, line_numbers=numbers))
    hits.sort(key=lambda hit: (-len(hit.line_numbers), str(hit.document.path)))
    return hits


def _grep_output_characters(hits: list[Hit]) -> int:
    # `path:lineno:text` per match, the shape an agent actually receives.
    total = 0
    for hit in hits:
        prefix = len(str(hit.document.path)) + len(":000:")
        total += sum(prefix + len(hit.document.lines[n]) for n in hit.line_numbers)
    return total


def _window_characters(hit: Hit) -> int:
    covered: set[int] = set()
    line_count = len(hit.document.lines)
    for number in hit.line_numbers:
        start = max(0, number - WINDOW_LINES)
        end = min(line_count, number + WINDOW_LINES)
        covered.update(range(start, end))
    return sum(len(hit.document.lines[i]) + 1 for i in sorted(covered))


def baseline_characters(corpus: Corpus, symbol: str, baseline: Baseline) -> int:
    """Characters a graph-less agent reads to answer one question about `symbol`."""
    hits = find_hits(corpus, symbol)
    if not hits:
        return 0

    grep_characters = _grep_output_characters(hits)
    if baseline is Baseline.GREP_ONLY:
        return grep_characters
    if baseline is Baseline.GREP_WINDOWS:
        windows = sum(_window_characters(hit) for hit in hits[:TOP_FILES_READ])
        return grep_characters + windows
    return grep_characters + sum(hit.document.characters for hit in hits)


def baseline_note(baseline: Baseline) -> str:
    if baseline is Baseline.GREP_ONLY:
        return "grep match lines only — the floor; under-counts what an agent needs"
    if baseline is Baseline.GREP_WINDOWS:
        return (
            f"grep output plus +/-{WINDOW_LINES} lines around matches in the "
            f"{TOP_FILES_READ} highest-hit files — what a competent agent does"
        )
    return "grep output plus every matching file read in full — the ceiling"


__all__ = [
    "TOP_FILES_READ",
    "WINDOW_LINES",
    "Baseline",
    "Corpus",
    "Document",
    "Hit",
    "baseline_characters",
    "baseline_note",
    "find_hits",
]
