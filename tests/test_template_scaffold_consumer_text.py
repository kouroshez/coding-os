"""A consumer's always-loaded text names only commands and paths that exist in that consumer."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

GOLDEN_ROOT = Path(__file__).parent / "golden"
AGENTS_FILES = sorted(GOLDEN_ROOT.glob("*/AGENTS.md"))
CORE_FREE_RULES = sorted(
    path
    for name in ("api-contract-discipline.md", "timestamp-discipline.md")
    for rules in ("dot-claude/rules", ".agents/skills/core-rules/references")
    for path in GOLDEN_ROOT.glob(f"*/{rules}/{name}")
)
DEAD_AGENTS_PHRASES = (
    "make task-start",
    "make task-done",
    "make task-block",
    "make task-create",
    "WHAT+FILES",
    "Rule 15",
    "direct MD",
)


def test_goldens_are_present() -> None:
    assert AGENTS_FILES
    assert CORE_FREE_RULES


@pytest.mark.parametrize("agents_md", AGENTS_FILES, ids=lambda path: path.parent.name)
def test_agents_md_names_no_dead_task_commands(agents_md: Path) -> None:
    text = agents_md.read_text()
    assert [phrase for phrase in DEAD_AGENTS_PHRASES if phrase in text] == []


@pytest.mark.parametrize(
    "rule", CORE_FREE_RULES, ids=lambda path: str(path.relative_to(GOLDEN_ROOT))
)
def test_shipped_rule_cites_no_coding_os_source_path(rule: Path) -> None:
    assert "src/core/" not in rule.read_text()


SOURCE_ROOT = Path(__file__).parent.parent / "src"
SHIPPED_DIRS = ("scaffold", "skills", "rules", "fragments")
SHIPPED_TEXT = sorted(
    path
    for root in (
        *(
            stack / sub
            for stack in (SOURCE_ROOT / "templates").iterdir()
            if stack.name != "meta"
            for sub in SHIPPED_DIRS
        ),
        SOURCE_ROOT / "core" / "rules",
        SOURCE_ROOT / "core" / "skills",
    )
    for path in root.rglob("*")
    if path.suffix in (".md", ".tmpl") and not path.is_symlink()
)
MAKE_COMMAND = re.compile(r"`make [a-z][\w-]*|^\s*make [a-z][\w-]*", re.MULTILINE)
BARE_OLD_TARGET = re.compile(
    r"`(?:log-latest|log-write|log-search|cos-health|verify-hooks|session-init)\b"
)
ADVICE_ABOUT_THE_USERS_OWN_MAKEFILE = ("A Makefile target is a script too",)


def test_shipped_text_is_present() -> None:
    assert len(SHIPPED_TEXT) > 300


def test_shipped_text_names_no_make_command() -> None:
    offenders = [
        f"{path}: {match.group(0).strip()}"
        for path in (*SHIPPED_TEXT, *AGENTS_FILES)
        for line in path.read_text(errors="ignore").splitlines()
        if not line.startswith(ADVICE_ABOUT_THE_USERS_OWN_MAKEFILE)
        for pattern in (MAKE_COMMAND, BARE_OLD_TARGET)
        for match in pattern.finditer(line)
    ]
    assert offenders == []
