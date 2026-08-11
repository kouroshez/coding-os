"""Doc uid grammar and governance-path classification for the markdown extractor."""

from __future__ import annotations

import re

from ._extract_base import _normalize_path


def slugify(heading: str) -> str:
    """Compute a stable URL-anchor slug from a heading title.

    Rules match GitHub-flavored Markdown: lowercase, strip non-alnum,
    collapse dashes. Deterministic — same input → same slug across
    platforms and runs (required by the P-I-11 determinism principle).
    """
    lowered = heading.lower()
    cleaned = re.sub(r"[^\w\s-]", "", lowered)
    return re.sub(r"[\s_]+", "-", cleaned).strip("-")


def file_uid(path: str) -> str:
    return f"doc:file:{_normalize_path(path)}"


def heading_uid(path: str, slug: str, level: int, occurrence: int) -> str:
    # occurrence disambiguates repeated headings under different parents.
    suffix = f":{occurrence}" if occurrence > 0 else ""
    return f"doc:heading:{_normalize_path(path)}#{slug}:{level}{suffix}"


def frontmatter_key_uid(path: str, key: str) -> str:
    return f"doc:frontmatter:{_normalize_path(path)}::{key}"


def _classify_governance_path(normalised: str) -> tuple[str | None, str | None]:
    parts = normalised.split("/")
    if len(parts) >= 4 and parts[-1] == "SKILL.md" and "skills" in parts:
        skills_idx = parts.index("skills")
        if skills_idx + 1 < len(parts) - 1:
            return ("cos:skill", parts[skills_idx + 1])
    if (
        len(parts) >= 3
        and parts[-1].endswith(".md")
        and "rules" in parts
        and parts[-1] != "SKILL.md"
    ):
        rules_idx = parts.index("rules")
        if rules_idx + 1 == len(parts) - 1:
            return ("cos:rule", parts[-1][:-3])
    return (None, None)
