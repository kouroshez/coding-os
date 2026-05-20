"""`cos skills-list` — show the skill registry, grouped or filtered by facet.

PURPOSE
    Surface the discoverability story for skills (TASK-129 taxonomy).
    Pure read-only; loads src/core/skills/ and src/templates/<stack>/skills/ via
    src/cli/skill_registry.py and prints a grouped or filtered view.

INPUT
    --by tier|domain          group output by facet (default: tier)
    --tier T                  filter to a single tier
    --domain D                filter to a single domain (matches if listed)
    --format text|json        default text

OUTPUT
    Text: `<facet>` headers, then `<name>  <tier>  [<domains>]  description`.
    JSON: list of {name, tier, domain, description, source}.

DEPENDENCIES
    cli.skill_registry.load_skill_registry, click.

NOTES
    - Mirrors the layout of `cos hooks-list` for muscle memory.
    - Includes stack-overlay skills if `--include-stacks` is set
      (off by default — meta-repo authors care about core skills).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from cli.skill_registry import (
    DOMAIN_ENUM,
    TIER_ENUM,
    SkillProfile,
    load_skill_registry,
)

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
CORE_SKILLS_DIR = CODING_OS_ROOT / "src" / "core" / "skills"
TEMPLATES_DIR = CODING_OS_ROOT / "src" / "templates"


def _collect_skills(include_stacks: bool) -> list[SkillProfile]:
    """Load src/core/skills/ and optionally each src/templates/<stack>/skills/."""
    out: list[SkillProfile] = []
    warnings: list[str] = []

    core_reg = load_skill_registry(CORE_SKILLS_DIR)
    out.extend(core_reg.values())
    warnings.extend(core_reg.warnings)

    if include_stacks and TEMPLATES_DIR.is_dir():
        for stack_dir in sorted(TEMPLATES_DIR.iterdir()):
            if not stack_dir.is_dir():
                continue
            stack_skills = stack_dir / "skills"
            if not stack_skills.is_dir():
                continue
            stack_reg = load_skill_registry(stack_skills)
            out.extend(stack_reg.values())
            warnings.extend(f"[stack {stack_dir.name}] {w}" for w in stack_reg.warnings)

    if warnings:
        for w in warnings:
            click.echo(f"  WARN: {w}", err=True)

    return out


def _render_text(skills: list[SkillProfile], by: str) -> str:
    if not skills:
        return "(no skills found)"

    groups: dict[str, list[SkillProfile]] = {}
    if by == "tier":
        for s in skills:
            groups.setdefault(s.tier, []).append(s)
        order = [
            "methodology",
            "workflow",
            "exploration",
            "quality",
            "layer",
            "cross-cutting",
            "stack",
        ]
    else:  # domain
        for s in skills:
            for d in s.domain:
                groups.setdefault(d, []).append(s)
        order = [
            "universal",
            "backend",
            "frontend",
            "mobile",
            "data",
            "security",
            "architecture",
            "performance",
            "infra",
            "governance",
        ]

    out_lines: list[str] = []
    for key in order:
        bucket = groups.get(key)
        if not bucket:
            continue
        out_lines.append(f"\n[{key}]")
        for s in sorted(bucket, key=lambda x: x.name):
            domains = ",".join(s.domain)
            desc = s.description if len(s.description) <= 80 else s.description[:77] + "..."
            out_lines.append(f"  {s.name:<32} tier={s.tier:<14} domains=[{domains}]")
            out_lines.append(f"    {desc}")
    # Trailing groups (anything not in canonical order) — keeps unknown
    # values discoverable even if a typo slips in.
    for key, bucket in sorted(groups.items()):
        if key in order:
            continue
        out_lines.append(f"\n[{key}]  (UNKNOWN — outside canonical enum)")
        for s in sorted(bucket, key=lambda x: x.name):
            out_lines.append(f"  {s.name:<32} tier={s.tier:<14}")
    return "\n".join(out_lines).lstrip("\n")


def _render_json(skills: list[SkillProfile]) -> str:
    payload = [
        {
            "name": s.name,
            "description": s.description,
            "tier": s.tier,
            "domain": list(s.domain),
            "source": str(s.source_path),
            "globs": s.globs,
            "depends_on": list(s.depends_on),
            "phase": s.phase,
        }
        for s in sorted(skills, key=lambda x: (x.tier, x.name))
    ]
    return json.dumps(payload, indent=2)


@click.command("skills-list")
@click.option(
    "--by",
    "by",
    type=click.Choice(["tier", "domain"]),
    default="tier",
    help="Group output by facet (default: tier).",
)
@click.option(
    "--tier",
    "tier_filter",
    type=click.Choice(sorted(TIER_ENUM)),
    default=None,
    help="Filter to skills of a single tier.",
)
@click.option(
    "--domain",
    "domain_filter",
    type=click.Choice(sorted(DOMAIN_ENUM)),
    default=None,
    help="Filter to skills that list this domain.",
)
@click.option(
    "--include-stacks",
    is_flag=True,
    default=False,
    help="Also load src/templates/<stack>/skills/ (default: core only).",
)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def skills_list(
    by: str,
    tier_filter: str | None,
    domain_filter: str | None,
    include_stacks: bool,
    output_format: str,
) -> None:
    """List all skills, grouped by tier (default) or domain.

    Reads SKILL.md frontmatter from src/core/skills/ (and optionally
    src/templates/<stack>/skills/). Shows tier, domain(s), description.
    """
    skills = _collect_skills(include_stacks)
    if tier_filter:
        skills = [s for s in skills if s.tier == tier_filter]
    if domain_filter:
        skills = [s for s in skills if domain_filter in s.domain]

    if output_format == "json":
        click.echo(_render_json(skills))
    else:
        click.echo(_render_text(skills, by))
        click.echo(f"\n  total: {len(skills)} skill(s)")
