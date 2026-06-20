"""Drift guard for docs/governance/stack-maturity.md.

Maturity is *derived* from three objective signals, never hand-declared:
  - stub   : the stack dir is named ``*-plain`` (language-only skeleton)
  - stable : a golden fixture exists at ``tests/golden/claude_<stack>``
  - beta   : a full overlay (has ``stack.yaml``) that is neither stub nor stable

This test re-derives the three sets from the filesystem and asserts the matrix
doc lists exactly those stacks per tier. Adding / removing / renaming / golden-
validating a stack without updating the doc fails here — the same anti-drift
contract the stack-count lint enforces for the "N stacks" literals.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_TEMPLATES = _REPO / "src" / "templates"
_GOLDEN = _REPO / "tests" / "golden"
_DOC = _REPO / "docs" / "governance" / "stack-maturity.md"

# Not stacks — shared overlays / this repo's own dogfood stack.
_INFRA_DIRS = {"_base", "_presets", "meta"}


def _candidate_stacks() -> set[str]:
    return {
        d.name
        for d in _TEMPLATES.iterdir()
        if d.is_dir() and (d / "stack.yaml").is_file() and d.name not in _INFRA_DIRS
    }


def _derive() -> dict[str, set[str]]:
    candidates = _candidate_stacks()
    stub = {s for s in candidates if s.endswith("-plain")}
    stable = {s for s in candidates - stub if (_GOLDEN / f"claude_{s}").is_dir()}
    beta = candidates - stub - stable
    return {"Stable": stable, "Beta": beta, "Stub": stub}


def _doc_section(tier: str) -> set[str]:
    text = _DOC.read_text()
    # Grab the block from "### <Tier> " up to the next "## " or "### " header.
    m = re.search(rf"### {tier}\b.*?\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if not m:
        return set()
    return set(re.findall(r"`([a-z0-9-]+)`", m.group(1)))


@pytest.mark.parametrize("tier", ["Stable", "Beta", "Stub"])
def test_matrix_matches_filesystem(tier: str) -> None:
    derived = _derive()[tier]
    documented = _doc_section(tier)
    assert documented == derived, (
        f"stack-maturity.md '{tier}' tier drift.\n"
        f"  documented: {sorted(documented)}\n"
        f"  derived   : {sorted(derived)}\n"
        f"  missing from doc: {sorted(derived - documented)}\n"
        f"  stale in doc    : {sorted(documented - derived)}"
    )


def test_every_candidate_stack_is_classified() -> None:
    derived = _derive()
    classified = derived["Stable"] | derived["Beta"] | derived["Stub"]
    assert classified == _candidate_stacks()


# ---------------------------------------------------------------------------
# Stack-count drift lint (TASK-461 / audit A1): a hardcoded "N stacks" literal
# in a governance entry doc rots silently — the "8 stacks" line in AGENTS.md was
# the canonical example (TASK-459). The count's SSOT is this maturity matrix +
# its derivation; entry docs must NOT pin a number that ground truth can outrun.
# ---------------------------------------------------------------------------

# Files scanned for stale counts. The maturity doc is excluded: it is self-
# guarded by the tier tests above and intentionally quotes the "27" marketing
# figure as a bad example.
_COUNT_SCANNED = [
    _REPO / "AGENTS.md",
    *sorted((_REPO / "src" / "core" / "rules").glob("*.md")),
]
_STACK_COUNT_RE = re.compile(r"\b(\d+)\s+stacks?\b", re.IGNORECASE)


def _canonical_counts() -> set[int]:
    n = len(_candidate_stacks())  # user-facing stacks (excl meta/_base/_presets)
    return {n, n + 1}  # allow excl-meta (n) or incl-meta (n+1) — both are "true"


def test_no_stale_stack_count_in_governance_docs() -> None:
    allowed = _canonical_counts()
    violations: list[str] = []
    for path in _COUNT_SCANNED:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for m in _STACK_COUNT_RE.finditer(line):
                if int(m.group(1)) not in allowed:
                    rel = path.relative_to(_REPO)
                    violations.append(f"{rel}:{lineno}: '{m.group(0)}' (canonical: {sorted(allowed)})")
    assert not violations, "stale stack-count literal(s) — update or link stack-maturity.md:\n" + "\n".join(
        violations
    )
