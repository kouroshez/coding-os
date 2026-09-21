"""A reference oracle the graph's own extractor cannot agree with by construction.

Grading a syntax walk against a second syntax walk measures agreement, not
accuracy: both go blind in the same places, so recall reads clean exactly where
it is not. jedi is a different kind of tool — it infers types and follows
assignments — so where it and the extractor disagree, the disagreement carries
information.

The unit of comparison is a **reference location**, `(repo-relative path, line)`.
It is the only unit both sides express: the graph emits `source_span` as
`path:line` on every reference row, and jedi returns `module_path` + `line`.
Comparing symbol names instead would score a hit for a caller found in the wrong
file. Measured on this repo, wherever the two name the same file their line
numbers agree exactly, so the unit is sound.

## Why jedi is adjudicator first and enumerator second

`get_references(scope="project")` is **not symmetric**, measured: asked from the
definition of `GraphNode` it returned 155 references across 31 files and omitted
`extractors/_php_symbols.py` entirely; asked from line 79 of that same omitted
file it returned 163 references across 32 files, including the definition. An
enumerator that misses locations it can itself resolve is not ground truth, and
scoring the graph against it directly would bill jedi's blind spots to the graph.

So the oracle asks jedi the question it answers reliably. For each location the
graph claims, `goto(follow_imports=True)` resolves that exact position and the
answer is checked against the probe's definition. That is a per-site decision
with no enumeration in it, and it costs about 32 ms.

- **Precision is sound.** Every graph-claimed site is adjudicated individually.
- **Recall is a lower bound.** Its denominator is jedi's definition-seeded
  enumeration unioned with the graph's confirmed sites, and that enumeration is
  known to be incomplete. A site neither side names is counted by neither, so
  the true recall can only be higher than the reported one, never lower.

jedi is optional and deliberately not a dependency of this package. Absent, every
probe reports `no_oracle` and the benchmark still runs — an unmeasured number is
honest, a fabricated one is not. Install with `uv run --with jedi`.

DEPENDS: jedi (optional).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# A project-wide enumeration is the slow half of a probe. Past this many files
# jedi's own indexing dominates the benchmark it is meant to grade, so the
# oracle declines instead of quietly taking minutes per symbol.
MAX_ORACLE_FILES = 4_000

# Adjudication is ~32 ms per site, so a 500-degree hub would spend 16 s on one
# probe. Past the cap the probe is reported unadjudicated rather than sampled:
# a precision figure over an arbitrary subset of sites is not a precision figure.
MAX_ADJUDICATED_SITES = 250

BUCKET_RESOLVABLE = "resolvable"
BUCKET_NO_ORACLE = "no_oracle"

Site = tuple[str, int]


@dataclass(frozen=True)
class OracleResult:
    enumerated: frozenset[Site] = frozenset()
    confirmed: frozenset[Site] = frozenset()
    refuted: frozenset[Site] = frozenset()
    bucket: str = BUCKET_NO_ORACLE
    note: str = ""

    @property
    def available(self) -> bool:
        return self.bucket == BUCKET_RESOLVABLE

    @property
    def truth(self) -> frozenset[Site]:
        """Every location known to reference the symbol, from either side."""
        return self.enumerated | self.confirmed


def oracle_available() -> bool:
    try:
        import jedi  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def _relative(path: object, root: Path) -> str | None:
    if not path:
        return None
    try:
        # Rule 5: /tmp and /private/tmp are the same directory on macOS, and a
        # clone under either one resolves differently than the root it came from.
        return str(Path(str(path)).resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def _column_of(source: str, line: int, symbol: str) -> int | None:
    lines = source.splitlines()
    if not 1 <= line <= len(lines):
        return None
    found = lines[line - 1].find(symbol)
    return found if found >= 0 else None


def _script(root: Path, path: Path, source: str) -> Any:
    import jedi

    return jedi.Script(code=source, path=str(path), project=jedi.Project(str(root)))


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def grade(
    root: Path,
    definition_file: str,
    definition_line: int,
    symbol: str,
    graph_sites: frozenset[Site],
    *,
    file_count: int,
) -> OracleResult:
    """Enumerate references from the definition, then adjudicate each graph claim."""
    if file_count > MAX_ORACLE_FILES:
        return OracleResult(
            note=f"repo has {file_count} files > cap {MAX_ORACLE_FILES}",
        )
    if len(graph_sites) > MAX_ADJUDICATED_SITES:
        return OracleResult(
            note=f"{len(graph_sites)} graph sites > cap {MAX_ADJUDICATED_SITES}",
        )
    try:
        import jedi  # noqa: F401
    except ImportError:
        return OracleResult(note="jedi not installed")

    target = root / definition_file
    source = _read(target)
    if source is None:
        return OracleResult(note=f"unreadable: {definition_file}")
    column = _column_of(source, definition_line, symbol)
    if column is None:
        return OracleResult(note=f"{symbol} not on line {definition_line} of {definition_file}")

    try:
        script = _script(root, target, source)
        references = script.get_references(line=definition_line, column=column, scope="project")
    except Exception as exc:
        # jedi raises a wide family here (recursion limits, parser errors on
        # syntax it cannot handle). Any of them means no oracle for this probe,
        # never a recall of zero — see the module docstring.
        return OracleResult(note=f"jedi enumeration failed: {type(exc).__name__}")

    enumerated: set[Site] = set()
    for ref in references:
        rel = _relative(getattr(ref, "module_path", None), root)
        line = getattr(ref, "line", None)
        if rel is None or not isinstance(line, int):
            continue
        if rel == definition_file and line == definition_line:
            # The definition is not a reference to itself.
            continue
        enumerated.add((rel, line))

    confirmed, refuted = _adjudicate(root, graph_sites, symbol, target.resolve(), definition_line)
    return OracleResult(
        enumerated=frozenset(enumerated),
        confirmed=frozenset(confirmed),
        refuted=frozenset(refuted),
        bucket=BUCKET_RESOLVABLE,
    )


def _adjudicate(
    root: Path,
    sites: frozenset[Site],
    symbol: str,
    definition_path: Path,
    definition_line: int,
) -> tuple[set[Site], set[Site]]:
    confirmed: set[Site] = set()
    refuted: set[Site] = set()
    for rel, line in sorted(sites):
        path = root / rel
        source = _read(path)
        if source is None:
            refuted.add((rel, line))
            continue
        column = _column_of(source, line, symbol)
        if column is None:
            # The graph named a line that does not contain the symbol at all.
            refuted.add((rel, line))
            continue
        try:
            goto = _script(root, path, source).goto(line=line, column=column, follow_imports=True)
        except Exception:
            refuted.add((rel, line))
            continue
        hit = any(
            getattr(d, "module_path", None) == definition_path
            and getattr(d, "line", None) == definition_line
            for d in goto
        )
        (confirmed if hit else refuted).add((rel, line))
    return confirmed, refuted


def score(graph_sites: frozenset[Site], oracle: OracleResult) -> dict[str, object]:
    """Precision and recall of the graph's locations against the oracle's."""
    if not oracle.available:
        return {
            "bucket": oracle.bucket,
            "oracle_sites": None,
            "graph_sites": len(graph_sites),
            "matched_sites": None,
            "recall": None,
            "precision": None,
        }
    truth = oracle.truth
    matched = graph_sites & truth
    adjudicated = len(oracle.confirmed) + len(oracle.refuted)
    return {
        "bucket": oracle.bucket,
        "oracle_sites": len(truth),
        "graph_sites": len(graph_sites),
        "matched_sites": len(matched),
        "recall": round(len(matched) / len(truth), 3) if truth else None,
        "precision": round(len(oracle.confirmed) / adjudicated, 3) if adjudicated else None,
    }


__all__ = [
    "BUCKET_NO_ORACLE",
    "BUCKET_RESOLVABLE",
    "MAX_ADJUDICATED_SITES",
    "MAX_ORACLE_FILES",
    "OracleResult",
    "grade",
    "oracle_available",
    "score",
]
