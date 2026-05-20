"""Discover and load skill profiles from SKILL.md frontmatter.

PURPOSE
    Scan src/core/skills/<name>/SKILL.md and src/templates/<stack>/skills/<name>/SKILL.md.
    Parse YAML frontmatter, validate against src/core/schemas/skill.schema.json,
    return a SkillProfile per skill. Mirrors src/cli/stack_registry.py and
    src/cli/adapter_registry.py for consistency.

INPUT
    skills_root: Path to src/core/skills/ (or any directory whose immediate
    subdirs each contain a SKILL.md).

OUTPUT
    SkillRegistry — dict-like {name: SkillProfile} + list of WARN-level
    issues (invalid frontmatter, missing required field, etc).

DEPENDENCIES
    pyyaml (already in pyproject), jsonschema (optional — falls back to
    handwritten checks if missing, same pattern as stack_registry).

NOTES
    - Invalid frontmatter is skipped with WARN, not crash (D9 discipline).
    - Tier + domain are required for new skills (TASK-129); existing
      8 core skills are migrated in the same task.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from jsonschema import Draft202012Validator, ValidationError as _JSValidationError

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    _HAS_JSONSCHEMA = False
    _JSValidationError = Exception  # type: ignore

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"
_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "schemas"
_SKILL_SCHEMA_PATH = _SCHEMA_DIR / "skill.schema.json"

# Frontmatter delimiter. SKILL.md starts with `---\n<yaml>\n---\n<body>`.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Authoritative enums — duplicated here so a missing schema file doesn't
# silently pass invalid data through. Kept in sync with skill.schema.json.
TIER_ENUM = frozenset(
    {
        "methodology",
        "workflow",
        "exploration",
        "quality",
        "layer",
        "cross-cutting",
        "stack",
    }
)
DOMAIN_ENUM = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class SkillProfile:
    """Loaded SKILL.md frontmatter + source path."""

    name: str
    description: str
    tier: str
    domain: tuple[str, ...]
    source_path: Path
    globs: str | None = None
    context: str | None = None
    depends_on: tuple[str, ...] = ()
    phase: str | None = None


@dataclass(frozen=True)
class SkillRegistry:
    """All discovered skills under a root, plus any WARN-level issues."""

    skills: dict[str, SkillProfile]
    warnings: tuple[str, ...]

    def values(self) -> list[SkillProfile]:
        return list(self.skills.values())

    def __contains__(self, name: str) -> bool:
        return name in self.skills

    def __getitem__(self, name: str) -> SkillProfile:
        return self.skills[name]


@lru_cache(maxsize=1)
def _skill_schema_validator() -> Draft202012Validator | None:
    if not _HAS_JSONSCHEMA or not _SKILL_SCHEMA_PATH.exists():
        return None
    import json

    schema = json.loads(_SKILL_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _extract_frontmatter(skill_md: Path) -> dict[str, Any] | None:
    """Read SKILL.md and return parsed YAML frontmatter, or None on miss."""
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    raw = match.group(1)
    try:
        return yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        logger.warning("malformed frontmatter in %s: %s", skill_md, exc)
        return None


def _validate(data: dict[str, Any], skill_md: Path) -> tuple[bool, str | None]:
    """Validate frontmatter against schema + handwritten checks.

    Returns (ok, error_message). On schema availability we let jsonschema
    do the heavy lifting; otherwise we fall back to required-field checks.
    """
    validator = _skill_schema_validator()
    if validator is not None:
        try:
            validator.validate(data)
        except _JSValidationError as exc:
            return (
                False,
                f"{skill_md}: schema violation: {exc.message} at {list(exc.absolute_path)}",
            )

    # Handwritten safety net (works without jsonschema too).
    name = data.get("name")
    if not isinstance(name, str) or not name:
        return False, f"{skill_md}: missing or non-string 'name'"
    if name != skill_md.parent.name:
        return False, f"{skill_md}: name '{name}' must equal directory '{skill_md.parent.name}'"
    desc = data.get("description")
    if not isinstance(desc, str) or len(desc.strip()) < 30:
        return False, f"{skill_md}: 'description' missing or shorter than 30 chars"
    tier = data.get("tier")
    if tier not in TIER_ENUM:
        return False, f"{skill_md}: 'tier' must be one of {sorted(TIER_ENUM)}, got {tier!r}"
    domain = data.get("domain")
    if not isinstance(domain, list) or not domain:
        return False, f"{skill_md}: 'domain' must be a non-empty list"
    bad = [d for d in domain if d not in DOMAIN_ENUM]
    if bad:
        return (
            False,
            f"{skill_md}: 'domain' contains unknown values {bad}; allowed: {sorted(DOMAIN_ENUM)}",
        )
    return True, None


def _build_profile(data: dict[str, Any], skill_md: Path) -> SkillProfile:
    """Coerce validated frontmatter into a SkillProfile."""
    raw_desc = data["description"]
    # YAML scalar `>` produces multi-line; collapse newlines for display.
    desc = " ".join(str(raw_desc).split())
    return SkillProfile(
        name=data["name"],
        description=desc,
        tier=data["tier"],
        domain=tuple(data["domain"]),
        source_path=skill_md,
        globs=data.get("globs"),
        context=data.get("context"),
        depends_on=tuple(data.get("depends_on") or ()),
        phase=str(data["phase"]) if data.get("phase") is not None else None,
    )


def load_skill_registry(skills_root: Path) -> SkillRegistry:
    """Scan skills_root for */SKILL.md, return SkillRegistry.

    Invalid skills are skipped with a WARN message captured in
    registry.warnings — same D9 discipline as stack_registry.
    """
    skills: dict[str, SkillProfile] = {}
    warnings: list[str] = []

    if not skills_root.is_dir():
        return SkillRegistry(skills={}, warnings=(f"skills root not a directory: {skills_root}",))

    for child in sorted(skills_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
            continue
        skill_md = child / SKILL_FILENAME
        if not skill_md.exists():
            warnings.append(f"{child}: missing {SKILL_FILENAME}")
            continue
        data = _extract_frontmatter(skill_md)
        if data is None:
            warnings.append(f"{skill_md}: no YAML frontmatter delimiter")
            continue
        ok, err = _validate(data, skill_md)
        if not ok:
            warnings.append(err or f"{skill_md}: unknown validation failure")
            continue
        profile = _build_profile(data, skill_md)
        if profile.name in skills:
            warnings.append(
                f"duplicate skill name '{profile.name}' at {skill_md} (already at {skills[profile.name].source_path})"
            )
            continue
        skills[profile.name] = profile

    return SkillRegistry(skills=skills, warnings=tuple(warnings))
