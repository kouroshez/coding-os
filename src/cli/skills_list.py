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


def _profile_entry(profile: SkillProfile, provenance: str) -> dict:
    return {
        "name": profile.name,
        "tier": profile.tier,
        "domain": list(profile.domain),
        "description": profile.description,
        "provenance": provenance,
        "validated": True,
    }


def _missing_entry(name: str) -> dict:
    # Referenced by a stack but no SKILL.md ships yet — visible, not dropped
    # (skill-architecture.md § Per-stack skill groups).
    return {
        "name": name,
        "tier": None,
        "domain": [],
        "description": "",
        "provenance": "missing",
        "validated": False,
    }


def collect_skill_catalog() -> dict:
    """Global core+stack catalog with provenance — SSOT for GET /api/hub/skills."""
    entries: list[dict] = []
    warnings: list[str] = []

    core_reg = load_skill_registry(CORE_SKILLS_DIR)
    entries.extend(_profile_entry(p, "core") for p in core_reg.values())
    warnings.extend(core_reg.warnings)

    if TEMPLATES_DIR.is_dir():
        for stack_dir in sorted(TEMPLATES_DIR.iterdir()):
            stack_skills = stack_dir / "skills"
            if not stack_dir.is_dir() or not stack_skills.is_dir():
                continue
            stack_reg = load_skill_registry(stack_skills)
            entries.extend(_profile_entry(p, f"stack:{stack_dir.name}") for p in stack_reg.values())
            warnings.extend(f"[stack {stack_dir.name}] {w}" for w in stack_reg.warnings)

    entries.sort(key=lambda e: (e["provenance"] != "core", e["name"]))
    return {"skills": entries, "count": len(entries), "warnings": warnings}


def collect_stack_skill_groups(stack_id: str) -> dict:
    """Per-stack required/recommended/optional groups — SSOT for the onboarding
    preview, consumed by `cos skills-list --stack` AND GET /api/hub/stacks/{id}/skills
    (skill-architecture.md § Per-stack skill groups). Raises KeyError on unknown stack."""
    from cli._resources import overlay_template_dirs
    from cli.stack_registry import load_stack_registry

    stacks = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    if stack_id not in stacks:
        raise KeyError(stack_id)
    stack = stacks[stack_id]

    core_reg = load_skill_registry(CORE_SKILLS_DIR)
    # source_dir resolves the overlay dir for a community stack (== TEMPLATES_DIR/id
    # for a bundled one), so the preview reads the right skills tree (TASK-478).
    stack_skills_dir = stack.source_dir / "skills"
    stack_reg = load_skill_registry(stack_skills_dir) if stack_skills_dir.is_dir() else None
    warnings = list(core_reg.warnings)
    if stack_reg:
        warnings.extend(f"[stack {stack_id}] {w}" for w in stack_reg.warnings)

    def _entry(name: str) -> dict:
        if stack_reg and name in stack_reg:
            return _profile_entry(stack_reg[name], f"stack:{stack_id}")
        if name in core_reg:
            return _profile_entry(core_reg[name], "core")
        return _missing_entry(name)

    required: list[str] = []
    if stack.primary_skill:
        required.append(stack.primary_skill)
    for name in stack.skills:
        if name not in required:
            required.append(name)

    recommended: list[str] = []
    for row in stack.skill_enforcement:
        for name in row.secondary:
            if name not in required and name not in recommended:
                recommended.append(name)

    grouped = {*required, *recommended}
    optional = [
        p.name for p in sorted(core_reg.values(), key=lambda p: p.name) if p.name not in grouped
    ]

    return {
        "stack": stack_id,
        "groups": {
            "required": [_entry(n) for n in required],
            "recommended": [_entry(n) for n in recommended],
            "optional": [_entry(n) for n in optional],
        },
        "warnings": warnings,
    }


def _render_groups_text(payload: dict) -> str:
    lines = [f"Skill groups for stack: {payload['stack']}"]
    for group in ("required", "recommended", "optional"):
        entries = payload["groups"][group]
        lines.append(f"\n[{group}] ({len(entries)})")
        for e in entries:
            flag = "" if e["validated"] else "  (MISSING SKILL.md)"
            lines.append(f"  {e['name']:<32} tier={e['tier'] or '—':<14} {e['provenance']}{flag}")
    return "\n".join(lines)


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
@click.option(
    "--stack",
    "stack_id",
    default=None,
    help="Show the required/recommended/optional skill groups for one stack (onboarding SSOT view).",
)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def skills_list(
    by: str,
    tier_filter: str | None,
    domain_filter: str | None,
    include_stacks: bool,
    stack_id: str | None,
    output_format: str,
) -> None:
    """List all skills, grouped by tier (default) or domain.

    Reads SKILL.md frontmatter from src/core/skills/ (and optionally
    src/templates/<stack>/skills/). Shows tier, domain(s), description.
    """
    if stack_id:
        try:
            payload = collect_stack_skill_groups(stack_id)
        except KeyError:
            click.echo(f"ERROR: stack '{stack_id}' not found.", err=True)
            sys.exit(2)
        click.echo(
            json.dumps(payload, indent=2)
            if output_format == "json"
            else _render_groups_text(payload)
        )
        return

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
