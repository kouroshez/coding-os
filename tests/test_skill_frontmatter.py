"""Pytest gate for SKILL.md frontmatter compliance with claude-agent-sdk."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_GLOB = "src/core/skills/*/SKILL.md"
DESC_LIMIT = 1024
LISTING_LIMIT = 1536
FIRST_PERSON_PATTERNS = [
    re.compile(r"\bI\s+(?:can|will|am|use|help)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:can|will|should|might|may)\b", re.IGNORECASE),
    re.compile(r"\byour\b", re.IGNORECASE),
]


def _parse_frontmatter(text: str) -> dict[str, object]:
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter --- delimiter")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("frontmatter not closed by ---")
    block = text[4:end]
    return yaml.safe_load(block) or {}


def _skill_paths() -> list[Path]:
    return sorted((REPO_ROOT / "src" / "core" / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("path", _skill_paths(), ids=lambda p: p.parent.name)
def test_skill_frontmatter_valid(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert isinstance(fm, dict), f"frontmatter parsed to non-dict: {path}"

    name = fm.get("name") or path.parent.name
    description = fm.get("description", "") or ""
    when_to_use = fm.get("when_to_use", "") or ""

    assert isinstance(name, str), f"name must be a string: {path}"
    assert isinstance(description, str), f"description must be a string: {path}"
    # Official SDK contract per docs §E.1 prefers `[a-z0-9-]+` (≤64
    # chars). The runtime accepts underscores in practice — coding-os
    # ships `thinking_os` to match the corresponding subsystem name.
    # Allow `_` here, but reject anything outside identifier-safe chars.
    assert re.fullmatch(r"[a-z0-9_-]+", name) and len(name) <= 64, (
        f"name {name!r} must match [a-z0-9_-]+ (≤64 chars): {path}"
    )
    assert "anthropic" not in name and "claude" not in name, (
        f"name {name!r} cannot contain 'anthropic'/'claude' per SDK contract"
    )

    assert len(description) <= DESC_LIMIT, (
        f"{name}: description {len(description)} > {DESC_LIMIT} chars: {path}"
    )

    listing = name + str(description) + str(when_to_use)
    assert len(listing) <= LISTING_LIMIT, (
        f"{name}: listing budget {len(listing)} > {LISTING_LIMIT} chars: {path}"
    )

    voice_hits = [p.pattern for p in FIRST_PERSON_PATTERNS if p.search(description)]
    assert not voice_hits, (
        f"{name}: first-person voice in description {voice_hits!r}: {path}"
    )
