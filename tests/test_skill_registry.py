"""Tests for cli/skill_registry.py + cli/skills_list.py — TASK-129 taxonomy.

Covers:
  - Every core/skills/<name>/SKILL.md loads cleanly (no warnings).
  - tier + domain enums are honored.
  - Loader rejects: missing tier, missing domain, unknown tier, unknown domain,
    name/dir mismatch, short description.
  - cos skills-list groups by tier (default) and domain.
  - --tier and --domain filters narrow output.
  - --format json returns parseable list.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.skill_registry import (
    DOMAIN_ENUM,
    TIER_ENUM,
    load_skill_registry,
)
from cli.skills_list import skills_list as skills_list_cmd

CODING_OS_ROOT = Path(__file__).resolve().parent.parent
CORE_SKILLS_DIR = CODING_OS_ROOT / "src" / "core" / "skills"


class TestRealSkillRegistry:
    """Smoke tests against the actual repo state."""

    def test_all_core_skills_load_without_warnings(self) -> None:
        reg = load_skill_registry(CORE_SKILLS_DIR)
        assert reg.warnings == (), f"unexpected loader warnings: {reg.warnings}"
        # Repo currently ships these skills; serves as drift detection.
        # Note: thinking_os uses snake_case (linter convention), all others
        # use kebab-case. Both forms are honored by skill.schema.json.
        expected = {
            "api-design", "auth-patterns", "db-design", "mobile-fundamentals",
            "state-management", "security-mobile",
            "backend-fundamentals", "clean-code", "codebase-explorer",
            "frontend-fundamentals", "graph-explorer",
            "hexagonal-architecture", "task-driver",
            "thinking_os", "worktree-orchestration",
        }
        assert set(reg.skills.keys()) == expected

    def test_all_core_skills_have_tier_in_enum(self) -> None:
        reg = load_skill_registry(CORE_SKILLS_DIR)
        for s in reg.values():
            assert s.tier in TIER_ENUM, f"{s.name} has bogus tier {s.tier!r}"

    def test_all_core_skills_have_domain_in_enum(self) -> None:
        reg = load_skill_registry(CORE_SKILLS_DIR)
        for s in reg.values():
            assert len(s.domain) >= 1, f"{s.name} has empty domain"
            for d in s.domain:
                assert d in DOMAIN_ENUM, f"{s.name} has bogus domain {d!r}"


class TestLoaderValidation:
    """Drive the loader with crafted SKILL.md fixtures."""

    def _make_skill(self, tmp_path: Path, name: str, frontmatter: str) -> Path:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n# {name}\n")
        return d

    def test_missing_tier_is_warned_not_loaded(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "no-tier",
                         "name: no-tier\ndescription: " + "x" * 35 + "\ndomain: [universal]")
        reg = load_skill_registry(tmp_path)
        assert "no-tier" not in reg.skills
        assert any("tier" in w for w in reg.warnings)

    def test_missing_domain_is_warned_not_loaded(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "no-domain",
                         "name: no-domain\ndescription: " + "x" * 35 + "\ntier: methodology")
        reg = load_skill_registry(tmp_path)
        assert "no-domain" not in reg.skills
        assert any("domain" in w for w in reg.warnings)

    def test_bad_tier_is_warned(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "bad-tier",
                         "name: bad-tier\ndescription: " + "x" * 35 + "\ntier: bogus\ndomain: [universal]")
        reg = load_skill_registry(tmp_path)
        assert "bad-tier" not in reg.skills

    def test_bad_domain_is_warned(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "bad-domain",
                         "name: bad-domain\ndescription: " + "x" * 35 + "\ntier: layer\ndomain: [bogus-domain]")
        reg = load_skill_registry(tmp_path)
        assert "bad-domain" not in reg.skills

    def test_name_mismatch_is_warned(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "real-dir-name",
                         "name: different-name\ndescription: " + "x" * 35 + "\ntier: layer\ndomain: [backend]")
        reg = load_skill_registry(tmp_path)
        assert "different-name" not in reg.skills
        assert "real-dir-name" not in reg.skills

    def test_short_description_is_rejected(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "short-desc",
                         "name: short-desc\ndescription: too short\ntier: layer\ndomain: [backend]")
        reg = load_skill_registry(tmp_path)
        assert "short-desc" not in reg.skills


class TestSkillsListCli:
    def test_default_groups_by_tier(self) -> None:
        runner = CliRunner()
        result = runner.invoke(skills_list_cmd, [])
        assert result.exit_code == 0, result.output
        assert "[methodology]" in result.output
        assert "[layer]" in result.output
        assert "thinking_os" in result.output

    def test_by_domain_groups_by_domain(self) -> None:
        runner = CliRunner()
        result = runner.invoke(skills_list_cmd, ["--by", "domain"])
        assert result.exit_code == 0
        assert "[universal]" in result.output
        assert "[backend]" in result.output

    def test_tier_filter(self) -> None:
        runner = CliRunner()
        result = runner.invoke(skills_list_cmd, ["--tier", "exploration"])
        assert result.exit_code == 0
        assert "codebase-explorer" in result.output
        assert "graph-explorer" in result.output
        # backend-fundamentals is tier=layer, should NOT appear
        assert "backend-fundamentals" not in result.output

    def test_domain_filter_picks_up_listed_domain(self) -> None:
        runner = CliRunner()
        result = runner.invoke(skills_list_cmd, ["--domain", "mobile"])
        assert result.exit_code == 0
        # frontend-fundamentals lists [frontend, mobile] → must appear
        assert "frontend-fundamentals" in result.output
        # backend-fundamentals does NOT list mobile → must not appear
        assert "backend-fundamentals" not in result.output

    def test_json_format_is_parseable(self) -> None:
        runner = CliRunner()
        result = runner.invoke(skills_list_cmd, ["--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 8
        for entry in data:
            assert "name" in entry and "tier" in entry and "domain" in entry
            assert isinstance(entry["domain"], list)
