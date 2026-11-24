"""A stack rule scopes itself with `paths:`, the only field Claude Code reads from a rule.

A rule without `paths` loads in every session whatever file is open; the `globs:`
these rules carried before is Cursor's field, so each one was always loaded.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "src" / "templates"
LINK = re.compile(r"\]\(([^)\s#]+)")


def _rule_entries() -> list[tuple[Path, list[str]]]:
    entries: list[tuple[Path, list[str]]] = []
    for stack_yaml in sorted(TEMPLATES.glob("*/stack.yaml")):
        data = yaml.safe_load(stack_yaml.read_text(encoding="utf-8")) or {}
        for entry in data.get("rules") or []:
            entries.append((stack_yaml.parent / entry["file"], list(entry["globs"])))
    return entries


def _frontmatter(rule: Path) -> dict:
    text = rule.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{rule} has no frontmatter, so it loads in every session"
    head = text[4:].partition("\n---\n")[0]
    return yaml.safe_load(head) or {}


@pytest.mark.parametrize(
    ("rule", "globs"), _rule_entries(), ids=lambda value: getattr(value, "name", "")
)
def test_rule_paths_match_the_stack_yaml_globs(rule: Path, globs: list[str]) -> None:
    front = _frontmatter(rule)
    assert front.get("paths") == globs
    assert "globs" not in front and "alwaysApply" not in front


def _installed_candidates(stack: Path, link: str) -> list[Path]:
    # The agent reads the rule at <project>/.claude/rules/, so the link resolves
    # from there; map the project path back to the sources that produce it.
    target = posixpath.normpath(posixpath.join(".claude/rules", link))
    if target.startswith("../"):
        return []
    if stack.name == "meta":
        return [REPO / target]
    if target.startswith(".claude/skills/"):
        rest = target.removeprefix(".claude/skills/")
        return [stack / "skills" / rest, REPO / "src" / "core" / "skills" / rest]
    return [stack / "scaffold" / target, TEMPLATES / "_base" / "scaffold" / target]


@pytest.mark.parametrize(
    ("rule", "globs"), _rule_entries(), ids=lambda value: getattr(value, "name", "")
)
def test_rule_links_resolve_where_the_rule_is_installed(rule: Path, globs: list[str]) -> None:
    stack = rule.parent.parent
    for link in LINK.findall(rule.read_text(encoding="utf-8")):
        if "://" in link:
            continue
        assert any(path.exists() for path in _installed_candidates(stack, link)), link
