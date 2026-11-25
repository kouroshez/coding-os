"""A consumer's always-loaded text names only commands and paths that exist in that consumer."""

from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN_ROOT = Path(__file__).parent / "golden"
AGENTS_FILES = sorted(GOLDEN_ROOT.glob("*/AGENTS.md"))
CORE_FREE_RULES = sorted(
    path
    for name in ("api-contract-discipline.md", "timestamp-discipline.md")
    for path in GOLDEN_ROOT.glob(f"*/.*/rules/{name}")
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
