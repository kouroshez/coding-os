"""`cos stack-lint [<id>]` — factory-contract completeness check (TASK-361).

Contract SSOT: docs/playbooks/template-authoring.md § Stack bundle standard.
Hard rules exit non-zero (CI gate); soft rules print GAP lines so a stack's
completeness is visible without blocking iteration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import click

from cli._resources import core_dir, templates_dir
from cli.stack_registry import StackProfile, load_stack_registry

_CODE_CATEGORIES = frozenset({"backend", "frontend", "mobile"})
_CATEGORY_VERIFY_KEY = {
    "backend": "VERIFY_BACKEND",
    "frontend": "VERIFY_FRONTEND",
    "mobile": "VERIFY_MOBILE",
}


@dataclass
class LintReport:
    stack_id: str
    hard: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.hard


def _is_exempt_from_work_surfaces(profile: StackProfile) -> bool:
    """Plain-language and library stacks ship skeletons, not work surfaces."""
    return profile.category == "library" or profile.id == f"{profile.language}-plain"


def _skill_resolvable(profile: StackProfile, stack_dir: Path) -> bool:
    if not profile.primary_skill:
        return _is_exempt_from_work_surfaces(profile)
    candidates = (
        stack_dir / "skills" / profile.primary_skill / "SKILL.md",
        core_dir("skills") / profile.primary_skill / "SKILL.md",
    )
    return any(path.is_file() for path in candidates)


def lint_stack(
    profile: StackProfile, stack_dir: Path, golden_root: Path | None = None
) -> LintReport:
    """Apply the factory contract to one loaded stack profile."""
    report = LintReport(stack_id=profile.id)

    if not profile.language:
        report.hard.append("stack.yaml missing `language`")
    structure = profile.structure or {}
    if not structure.get("root"):
        report.hard.append("stack.yaml missing `structure.root`")
    if not structure.get("tree"):
        report.hard.append("stack.yaml missing `structure.tree`")

    if profile.category in _CODE_CATEGORIES:
        verify_key = _CATEGORY_VERIFY_KEY[profile.category]
        # The verification matrix renders from VERIFY_<CAT>_* substitutions —
        # that's the hard contract. `verify:` rows are the newer per-glob
        # mechanism (TASK-348 plain stacks); absence is a visible gap only.
        if not profile.substitutions.get(f"{verify_key}_GLOB"):
            report.hard.append(f"missing substitution `{verify_key}_GLOB`")
        if not profile.verify:
            report.soft.append("no `verify:` rows (per-glob suites — newer mechanism)")

    if profile.primary_skill and not _skill_resolvable(profile, stack_dir):
        report.hard.append(
            f"primary_skill '{profile.primary_skill}' has no SKILL.md in the stack or core skills"
        )
    if profile.primary_skill is None and not _is_exempt_from_work_surfaces(profile):
        report.hard.append("primary_skill is null but the stack is not plain/library")

    for routing_key in ("DOMAIN_ROUTES", "QUICK_ROUTING"):
        if not profile.substitutions.get(routing_key, "").strip():
            report.hard.append(f"missing substitution `{routing_key}`")

    if not _is_exempt_from_work_surfaces(profile):
        if not profile.dimensions:
            report.soft.append("no `dimensions:` rows (Classify-phase read list)")
        if not profile.skill_enforcement:
            report.soft.append("no `skill_enforcement:` globs (auto skill loading)")
        if profile.category in _CODE_CATEGORIES and not (
            stack_dir / "scaffold-boundary.yaml"
        ).is_file():
            report.soft.append("no scaffold-boundary.yaml (write-boundary contract)")
        if not (stack_dir / "scaffold" / ".coding-os" / "scrumban-config.yaml").is_file():
            report.soft.append("no scrumban-config.yaml delta (board lanes)")

        scaffold_docs = stack_dir / "scaffold" / "docs"
        has_docs = scaffold_docs.is_dir() and any(scaffold_docs.rglob("*.md"))
        routes_to_playbook = "playbook" in profile.substitutions.get("DOMAIN_ROUTES", "").lower()
        if not has_docs and not routes_to_playbook:
            report.soft.append("no stack docs under scaffold/docs/ and no playbook routing")

    golden_root = golden_root if golden_root is not None else Path("tests/golden")
    if golden_root.is_dir():
        sections = [p.name for p in golden_root.iterdir() if p.name.endswith(f"_{profile.id}")]
        if not sections:
            report.soft.append("no golden section (make golden-capture SECTION=<agent>_<id>)")

    return report


def lint_all(
    registry_dir: Path | None = None, golden_root: Path | None = None
) -> dict[str, LintReport]:
    root = registry_dir or templates_dir()
    # Lint ONLY the bundled stacks under `root` — a community overlay stack has
    # no golden to assert against (overlay_dirs=() opts out of the user overlay).
    registry = load_stack_registry(root, overlay_dirs=())
    reports = {
        stack_id: lint_stack(registry[stack_id], root / stack_id, golden_root)
        for stack_id in sorted(registry.keys())
    }
    # A schema-rejected stack never loads — surface the loader's precise
    # rejection as a hard failure instead of silently omitting the stack.
    for warning in registry.warnings:
        if not warning.startswith("skipping stack "):
            continue
        skipped_id = warning.split("skipping stack ", 1)[1].split(":", 1)[0].strip()
        reports.setdefault(skipped_id, LintReport(stack_id=skipped_id)).hard.append(warning)
    return reports


@click.command("stack-lint")
@click.argument("stack_id", required=False)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def stack_lint(stack_id: str | None, output_format: str) -> None:
    """Check stack bundle completeness against the factory contract."""
    reports = lint_all()
    if stack_id:
        if stack_id not in reports:
            raise click.ClickException(
                f"stack '{stack_id}' not found — available: {sorted(reports)}"
            )
        reports = {stack_id: reports[stack_id]}

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    sid: {"passed": r.passed, "hard": r.hard, "soft": r.soft}
                    for sid, r in reports.items()
                },
                indent=2,
            )
        )
    else:
        for sid, r in reports.items():
            status = "PASS" if r.passed else "FAIL"
            click.echo(f"{sid}: {status}")
            for issue in r.hard:
                click.echo(f"  HARD: {issue}")
            for gap in r.soft:
                click.echo(f"  GAP:  {gap}")

    if any(not r.passed for r in reports.values()):
        raise SystemExit(1)
