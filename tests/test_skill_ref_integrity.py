"""Skill referential-integrity guard (audit-2026-06 R5, TASK-438).

Sibling of test_no_phantom_tool_refs.py, but for SKILL names instead of
cos_* tools. The generated src/core/rules/skill-enforcement.md routes every
Write/Edit to a Primary + Secondary skill set; enforce-skill.sh then tells the
agent to `Skill <name>`. If a row names a skill with no skill directory, the
agent is told to load a phantom skill and the BLOCK can never be satisfied.

This guard harvests the real skill universe (agent-agnostic fundamentals in
src/core/skills/ + per-stack specializations in src/templates/<stack>/skills/)
and asserts every skill named in skill-enforcement.md resolves to one. It is a
pure-filesystem check (no `cos init` sandbox), so it is fast and CI-gateable.

Run: uv run pytest tests/test_skill_ref_integrity.py -q
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL_ENFORCEMENT = REPO / "src" / "core" / "rules" / "skill-enforcement.md"


def _known_skills() -> set[str]:
    """Every skill slug that physically exists, across both skill layers."""
    known: set[str] = set()
    for skill_md in REPO.glob("src/core/skills/*/SKILL.md"):
        known.add(skill_md.parent.name)
    for skill_md in REPO.glob("src/templates/*/skills/*/SKILL.md"):
        known.add(skill_md.parent.name)
    return known


def _referenced_skills() -> dict[str, list[int]]:
    """Skill slugs named in the Primary + Secondary columns of the table.

    Returns slug -> line numbers where it appears (for a precise failure)."""
    refs: dict[str, list[int]] = {}
    for lineno, line in enumerate(SKILL_ENFORCEMENT.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        # Table shape: | Globs | Primary Skill | Secondary Skills | Stack |
        if len(cells) < 3:
            continue
        primary, secondary = cells[1], cells[2]
        if primary in ("Primary Skill", "---") or set(primary) <= {"-", ":"}:
            continue  # header / separator row
        names = [primary]
        names.extend(part for part in secondary.split(",") if part.strip())
        for raw in names:
            slug = raw.strip().strip("`").strip()
            if not slug:
                continue
            refs.setdefault(slug, []).append(lineno)
    return refs


KNOWN_SKILLS = _known_skills()
REFERENCED_SKILLS = _referenced_skills()


def test_skill_harvest_found_skills() -> None:
    """Sanity: the skill-universe harvest must work, else every ref looks phantom."""
    assert len(KNOWN_SKILLS) >= 20, f"harvested only {len(KNOWN_SKILLS)} skills — extraction broken"
    assert "clean-code" in KNOWN_SKILLS  # canonical agent-agnostic fundamental
    assert "thinking_os" in KNOWN_SKILLS  # underscore-slug exception is real


def test_skill_enforcement_table_parsed() -> None:
    """Sanity: the table parse must find references, else the guard is a no-op."""
    assert REFERENCED_SKILLS, "parsed zero skill references — table format changed"


def test_no_phantom_skill_refs() -> None:
    """Every skill named in skill-enforcement.md resolves to a real skill dir."""
    phantoms = {
        slug: lines for slug, lines in REFERENCED_SKILLS.items() if slug not in KNOWN_SKILLS
    }
    assert not phantoms, (
        "skill-enforcement.md names skill(s) with no skill directory "
        "(src/core/skills/<name>/SKILL.md or src/templates/<stack>/skills/<name>/SKILL.md):\n"
        + "\n".join(
            f"  {slug}  (line {', '.join(map(str, lines))})"
            for slug, lines in sorted(phantoms.items())
        )
    )


# --- Companion-dir projection (TASK-1023) ----------------------------------
# A SKILL.md links references/, assets/ and scripts/ by relative path. Three
# independent sites project a skill into a consumer project, and for months all
# three linked SKILL.md alone, so every one of those links dangled in a consumer
# while resolving fine in this repo. Golden fixtures cannot catch it: rglob does
# not descend a symlinked directory, so the fixture looks identical either way.

_PROJECTION_SITES = (
    ("src/cli/_skill_project.py", "SKILL_COMPANION_DIRS"),
    ("src/core/scripts/install-adapter.sh", "SKILL_COMPANION_DIRS"),
    ("src/core/scripts/link-stack-skills.sh", "for sub in references assets scripts"),
)


def test_every_projection_site_links_companion_dirs() -> None:
    """All three producers must project the same companion directories."""
    missing = [
        path
        for path, marker in _PROJECTION_SITES
        if marker not in (REPO / path).read_text(encoding="utf-8")
    ]
    assert not missing, "skill projection sites that no longer link companion dirs: " + ", ".join(
        missing
    )


def test_skill_relative_links_resolve_at_source() -> None:
    """Every relative link in a SKILL.md resolves inside its own skill dir."""
    import re

    broken: list[str] = []
    link_re = re.compile(r"\[[^\]]*\]\((?!https?://|#|mailto:)([^)#]+)")
    fence_re = re.compile(r"```.*?```", re.DOTALL)
    for skill_md in sorted(REPO.glob("src/core/skills/*/SKILL.md")):
        # Fenced blocks carry illustrative markup, not live links.
        body = fence_re.sub("", skill_md.read_text(encoding="utf-8"))
        for target in link_re.findall(body):
            if target.startswith("../") or target.split("/")[0] in {"src", "docs", "tests"}:
                continue  # outside the skill dir; docs-lint owns those
            if not (skill_md.parent / target).exists():
                broken.append(f"{skill_md.parent.name}/SKILL.md -> {target}")
    assert not broken, "unresolvable relative links in SKILL.md:\n  " + "\n  ".join(broken)
