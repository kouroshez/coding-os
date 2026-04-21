"""Tests that Phase M formula symlinks in adapters/codex/commands/ resolve correctly."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CODEX_COMMANDS = REPO_ROOT / "adapters" / "codex" / "commands"
AGENTS_DIR = REPO_ROOT / "core" / "thinking_os" / "agents"


class TestCodexFormulaSymlinks:
    def test_all_11_formula_files_exist(self):
        for n in range(1, 12):
            link = CODEX_COMMANDS / f"formula-f{n}.md"
            assert link.exists(), f"formula-f{n}.md missing in adapters/codex/commands/"

    def test_symlinks_resolve_to_agent_files(self):
        for n in range(1, 12):
            link = CODEX_COMMANDS / f"formula-f{n}.md"
            assert link.is_symlink(), f"formula-f{n}.md is not a symlink"
            target = link.resolve()
            assert target.exists(), f"Symlink target missing: {target}"
            assert "agents" in str(target), f"Target not in agents/: {target}"

    def test_agent_files_have_frontmatter(self):
        for n in range(1, 12):
            link = CODEX_COMMANDS / f"formula-f{n}.md"
            content = link.read_text()
            assert content.startswith("---"), f"formula-f{n}.md missing frontmatter"

    def test_agent_files_have_id_field(self):
        for n in range(1, 12):
            link = CODEX_COMMANDS / f"formula-f{n}.md"
            content = link.read_text()
            assert f"id: F{n}" in content, f"formula-f{n}.md missing 'id: F{n}' in frontmatter"

    def test_all_agent_files_exist_directly(self):
        for n in range(1, 12):
            # Find the corresponding agent file
            matches = list(AGENTS_DIR.glob(f"F{n}_*.md"))
            assert matches, f"No agent file found for F{n} in agents/"
