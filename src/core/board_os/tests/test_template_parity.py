"""R-L-24: master template + scaffold copy must stay byte-equal.

Both files exist for distinct reasons (master = what `cos task-create`
fills in this repo; scaffold = what `cos init` copies into consumer
projects), but the body MUST be identical so a contributor reading
either sees the same agent guidance.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
MASTER = REPO_ROOT / "src" / "templates" / "_base" / "task-detail.template.md"
SCAFFOLD = (
    REPO_ROOT
    / "src" / "templates"
    / "_base"
    / "scaffold"
    / "docs"
    / "governance"
    / "_templates"
    / "task-detail.md"
)


def test_master_template_exists():
    assert MASTER.exists(), f"missing: {MASTER}"


def test_scaffold_template_exists():
    assert SCAFFOLD.exists(), f"missing: {SCAFFOLD}"


def test_master_and_scaffold_byte_identical():
    """No drift allowed.  If you need to change one, change both."""
    master = MASTER.read_text(encoding="utf-8")
    scaffold = SCAFFOLD.read_text(encoding="utf-8")
    assert master == scaffold, (
        "src/templates/_base/task-detail.template.md and "
        "src/templates/_base/scaffold/docs/governance/_templates/task-detail.md "
        "have drifted (R-L-24).  Sync them or add an explicit allowed-diff "
        "exception to this test."
    )


def test_lean_template_has_required_sections():
    """L.0 ship gate: lean template must contain frontmatter + 4 H2s."""
    body = MASTER.read_text(encoding="utf-8")

    # YAML frontmatter (between two `---` lines)
    assert body.startswith("---\n"), "must start with YAML frontmatter"
    parts = body.split("---\n", 2)
    assert len(parts) >= 3, "must have closing --- after frontmatter"

    # Required sections (per plan §6.2)
    required = [
        "## Read First",
        "## Acceptance",
        "## Work Log",
    ]
    missing = [s for s in required if s not in body]
    assert not missing, f"lean template missing sections: {missing}"

    # Must contain Outcome marker (the one-sentence statement)
    assert "Outcome" in body, "Outcome marker missing"


def test_lean_template_contains_agent_guidance_comments():
    """The <!-- AGENT: ... --> inline comments are the L.0 fallback layer
    of the 5-layer guidance system (plan §24.3 layer 4)."""
    body = MASTER.read_text(encoding="utf-8")
    # At least 4 AGENT-prefixed comments (Outcome, Read First, Acceptance, Work Log)
    n = body.count("<!-- AGENT:") + body.count("# AGENT:")
    assert n >= 4, f"only {n} AGENT-prefixed guidance markers; expected ≥ 4"


def test_lean_template_token_budget():
    """Rule 15: lean template body ≤ 1500 tokens (pre-fill).

    Approximated as `wc -w * 1.3` per plan §15.  Hard cap from §15.2.
    """
    body = MASTER.read_text(encoding="utf-8")
    word_count = len(body.split())
    approx_tokens = int(word_count * 1.3)
    assert approx_tokens < 1500, (
        f"template approx {approx_tokens} tokens — exceeds Rule 15 lean budget. "
        f"Reduce by inlining less, linking more."
    )


def test_lean_template_mentions_four_axes():
    """Plan §6.1.1: four axes must be visible in the template frontmatter."""
    body = MASTER.read_text(encoding="utf-8")
    for axis in ("swimlane:", "kind:", "epic:", "labels:"):
        assert axis in body, f"axis {axis!r} missing from template"


def test_lean_template_mentions_status_starts_at_icebox():
    body = MASTER.read_text(encoding="utf-8")
    assert "status: icebox" in body, "tasks must start in icebox per state machine"
