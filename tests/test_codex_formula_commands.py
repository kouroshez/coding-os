"""Tests that Phase M formula symlinks in adapters/codex/commands/ resolve correctly.

Phase N (Rule 15) replaced legacy F<N>_<name>.md filenames with semantic role
ids: researcher · analyst · architect · documenter · implementer · reviewer ·
debugger · security_auditor · deployer · observer · refactorer. The
formula-f<N>.md symlinks remain as the codex CLI surface; their targets are
now the semantic agent files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CODEX_COMMANDS = REPO_ROOT / "src" / "adapters" / "codex" / "commands"
AGENTS_DIR = REPO_ROOT / "src" / "core" / "thinking_os" / "agents"

# Canonical Formula <N> → semantic role mapping. Source: AGENTS.md Rule 15
# and core/thinking_os/agents/README.md.
FORMULA_TO_ROLE: dict[int, str] = {
    1: "researcher",
    2: "analyst",
    3: "architect",
    4: "documenter",
    5: "implementer",
    6: "reviewer",
    7: "debugger",
    8: "security_auditor",
    9: "deployer",
    10: "observer",
    11: "refactorer",
}


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

    def test_symlinks_target_canonical_role(self):
        """Each formula-fN.md must resolve to its canonical semantic role file."""
        for n, role in FORMULA_TO_ROLE.items():
            link = CODEX_COMMANDS / f"formula-f{n}.md"
            target = link.resolve()
            assert target.name == f"{role}.md", (
                f"formula-f{n}.md → {target.name}, expected {role}.md"
            )

    def test_agent_files_have_semantic_id(self):
        """Frontmatter `id` field is the semantic role, not F<N>."""
        for n, role in FORMULA_TO_ROLE.items():
            link = CODEX_COMMANDS / f"formula-f{n}.md"
            content = link.read_text()
            assert f"id: {role}" in content, (
                f"formula-f{n}.md missing 'id: {role}' in frontmatter"
            )

    def test_all_role_agent_files_exist(self):
        """Each canonical role has a corresponding agent file."""
        for role in FORMULA_TO_ROLE.values():
            agent_file = AGENTS_DIR / f"{role}.md"
            assert agent_file.exists(), f"agent file missing: {agent_file}"
