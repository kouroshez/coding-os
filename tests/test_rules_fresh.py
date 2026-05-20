"""Guard: core/rules/{dimension-registry,skill-enforcement}.md are fresh.

If a stack's dimensions or skill_enforcement entries change without
running `make regen-rules`, this test fails with a command to run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DIMENSION_REGISTRY = REPO_ROOT / "src" / "core" / "rules" / "dimension-registry.md"
SKILL_ENFORCEMENT = REPO_ROOT / "src" / "core" / "rules" / "skill-enforcement.md"


def _rendered():
    sys.path.insert(0, str(REPO_ROOT))
    from cli.renderer import (
        render_dimension_registry,
        render_skill_enforcement,
    )
    from scripts.regen_rules import _build_world  # type: ignore

    world = _build_world()
    return render_dimension_registry(world), render_skill_enforcement(world)


@pytest.mark.slow
def test_dimension_registry_is_fresh() -> None:
    fresh_dim, _ = _rendered()
    committed = DIMENSION_REGISTRY.read_text(encoding="utf-8")
    assert committed == fresh_dim, (
        "src/core/rules/dimension-registry.md is stale — run `make regen-rules`"
    )


@pytest.mark.slow
def test_skill_enforcement_is_fresh() -> None:
    _, fresh_enf = _rendered()
    committed = SKILL_ENFORCEMENT.read_text(encoding="utf-8")
    assert committed == fresh_enf, (
        "src/core/rules/skill-enforcement.md is stale — run `make regen-rules`"
    )


def test_rule_files_exist() -> None:
    """Fast smoke test — always runs (non-slow)."""
    assert DIMENSION_REGISTRY.exists()
    assert SKILL_ENFORCEMENT.exists()
    assert "# Dimension Registry" in DIMENSION_REGISTRY.read_text()
    assert "# Skill Enforcement" in SKILL_ENFORCEMENT.read_text()
