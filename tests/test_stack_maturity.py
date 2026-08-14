"""Advertised must mean CI-proven.

The stack list read uniformly whether or not a stack had ever been built by CI,
so 16 of 27 were presented exactly like the 11 the workflow really scaffolds,
installs, lints and tests. Maturity is derived from scaffold-verify.yml rather
than recorded per stack, so adding a toolchain job promotes that stack with no
second fact to update — and no way for the two to disagree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from cli.stack_maturity import (
    EXPERIMENTAL,
    UNKNOWN,
    VERIFIED,
    maturity_of,
    verified_stacks,
)


def test_verified_set_matches_the_workflow_matrix() -> None:
    found = verified_stacks()
    assert found, "no stacks parsed out of scaffold-verify.yml"
    # Spot-check both shapes the workflow uses: bare `stack: [a, b]` lists and
    # `include:` dicts carrying a `stack` key.
    assert "django" in found, "python matrix (bare list) not parsed"
    assert "nextjs" in found, "node matrix (include dicts) not parsed"


@pytest.mark.parametrize("stack_id", ["django", "fastapi", "go", "nextjs", "nestjs"])
def test_stacks_with_a_ci_job_are_verified(stack_id: str) -> None:
    assert maturity_of(stack_id) == VERIFIED


@pytest.mark.parametrize("stack_id", ["rust-axum", "spring-boot", "flutter", "rails"])
def test_stacks_named_unproven_in_the_workflow_are_experimental(stack_id: str) -> None:
    """These four are listed in scaffold-verify.yml's own FOLLOW-UP comment."""
    assert maturity_of(stack_id) == EXPERIMENTAL


def test_absent_workflow_reports_unknown_rather_than_claiming_verified(tmp_path: Path) -> None:
    """An installed wheel ships no .github/ — say nothing, never say 'verified'."""
    verified_stacks.cache_clear()
    try:
        assert maturity_of("django", workflow_dir=tmp_path) == UNKNOWN
    finally:
        verified_stacks.cache_clear()


def test_list_stacks_json_exposes_maturity() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "cli.main", "list-stacks", "--format", "json"],
        cwd=REPO / "src",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    by_id = {s["id"]: s for s in payload["stacks"]}
    assert by_id["django"]["ci_maturity"] == VERIFIED
    assert by_id["rust-axum"]["ci_maturity"] == EXPERIMENTAL


def test_readme_counts_match_the_registry_and_the_workflow() -> None:
    """Hand-written counts in prose are the classic drift; pin them to the source.

    README states a total and a CI-verified count. Both are derivable, so a
    stack added or a toolchain job landed must not leave the prose behind.
    """
    import re

    from cli.stack_registry import load_stack_registry

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    registry = load_stack_registry(REPO / "src" / "templates")
    total = len(registry.stacks)
    verified = len(verified_stacks() & set(registry.keys()))

    claimed_totals = {int(n) for n in re.findall(r"(\d+) stacks", readme)}
    assert claimed_totals, "README no longer states a stack total — update this test"
    assert claimed_totals == {total}, (
        f"README claims {sorted(claimed_totals)} stacks; the registry holds {total}"
    )

    claimed_verified = {int(n) for n in re.findall(r"(\d+) (?:of them |CI-)verified", readme)}
    assert claimed_verified == {verified}, (
        f"README claims {sorted(claimed_verified)} CI-verified stacks; "
        f"scaffold-verify.yml covers {verified}"
    )
