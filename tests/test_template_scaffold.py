"""
Tests for Phase A — Template Completion.

Verifies that `coding-os init` produces a complete production-grade scaffold
with governance, playbooks, engineering rules, foundation map, and resolved
AGENTS.md placeholders.

Covers:
  - Generic _base scaffold (governance, PRD/architecture/api-contracts/ops indexes)
  - Django stack overlay (backend playbook, backend-rules, etc.)
  - Next.js stack overlay (frontend playbook, design system, etc.)
  - Multi-template merge (django + nextjs)
  - AGENTS.md placeholder substitution (no `{{...}}` left after init)
  - Stack-specific Makefile targets reachable
  - Workflow docs copied (thinking_os-final-edition.md from core/docs/)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

# Make cli module importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.main import cli

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses (TASK-008 L3)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Return a clean temporary project directory."""
    target = tmp_path / "test-project"
    target.mkdir()
    return target


def _init_project(
    runner: CliRunner,
    project_dir: Path,
    *templates: str,
    agent: str = "claude",
) -> None:
    """Run `coding-os init` and assert success."""
    args = ["init", "--agent", agent, "-d", str(project_dir)]
    for tpl in templates:
        args += ["-t", tpl]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"init failed: {result.output}"


def _class_scaffold(
    tmp_path_factory: pytest.TempPathFactory, name: str, *templates: str
) -> Path:
    """Scaffold one cos-init project shared across a class of read-only tests.

    Class-scoped fixtures run before the function-scoped _isolate_registry
    autouse fixture, so this re-isolates COS_REGISTRY_PATH itself via a
    standalone MonkeyPatch — otherwise `cos init` would write the real
    ~/.coding-os/registry.json.
    """
    base = tmp_path_factory.mktemp(name)
    project = base / "test-project"
    project.mkdir()
    mp = pytest.MonkeyPatch()
    mp.setenv("COS_REGISTRY_PATH", str(base / "registry.json"))
    try:
        _init_project(CliRunner(), project, *templates)
    finally:
        mp.undo()
    return project


# ---------------------------------------------------------------------------
# Base scaffold (every init creates these)
# ---------------------------------------------------------------------------


class TestBaseScaffold:
    @pytest.fixture(scope="class")
    def initialized(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "base-scaffold")

    def test_creates_root_index(self, initialized: Path) -> None:
        assert (initialized / "docs" / "00-index.md").exists()

    def test_creates_foundation_map(self, initialized: Path) -> None:
        assert (initialized / "docs" / "_meta" / "foundation-map.md").exists()

    def test_creates_roadmap(self, initialized: Path) -> None:
        assert (initialized / "docs" / "_meta" / "roadmap.md").exists()

    def test_creates_feature_dependency_tree(self, initialized: Path) -> None:
        assert (initialized / "docs" / "_meta" / "feature-dependency-tree.md").exists()

    def test_creates_governance_files(self, initialized: Path) -> None:
        gov = initialized / "docs" / "governance"
        for required in (
            "agent-workflow.md",
            "task-lifecycle.md",
            "docs-system.md",
            "decision-records.md",
            "risk-register.md",
            "mcp-tool-inventory.md",
            "wrapper-derivation.md",
            "gdpr-compliance.md",
        ):
            assert (gov / required).exists(), f"missing {required}"

    def test_creates_governance_templates(self, initialized: Path) -> None:
        templates = initialized / "docs" / "governance" / "_templates"
        assert (templates / "task-detail.md").exists()

    def test_task_detail_template_has_required_sections(self, initialized: Path) -> None:
        """Verify the Phase L lean Scrumban template is in place.

        Replaces the pre-Phase-L 12-section legacy template.
        See docs/phase-l-scrumban-task-system-plan.md §6.2 for the lean
        body layout (Outcome + Read First + Acceptance + Work Log +
        optional Rollback).
        """
        content = (
            initialized / "docs" / "governance" / "_templates" / "task-detail.md"
        ).read_text()
        for section in (
            "## Read First",
            "## Acceptance",
            "## Work Log",
        ):
            assert section in content, f"lean task-detail template missing {section}"
        # Outcome marker (the one-sentence statement, not a separate H2)
        assert "Outcome" in content, "lean template missing Outcome marker"

    def test_task_detail_has_lean_frontmatter_axes(self, initialized: Path) -> None:
        """Phase L: the four categorization axes (swimlane/kind/epic/labels)
        must appear in the frontmatter of the scaffolded template."""
        content = (
            initialized / "docs" / "governance" / "_templates" / "task-detail.md"
        ).read_text()
        for axis in ("swimlane:", "kind:", "epic:", "labels:"):
            assert axis in content, f"lean template missing axis {axis!r}"
        # All tasks start in icebox
        assert "status: icebox" in content

    def test_creates_prd_index(self, initialized: Path) -> None:
        assert (initialized / "docs" / "prd" / "00-index.md").exists()

    def test_creates_architecture_index(self, initialized: Path) -> None:
        assert (initialized / "docs" / "architecture" / "00-index.md").exists()

    def test_creates_adr_index(self, initialized: Path) -> None:
        assert (initialized / "docs" / "architecture" / "adr" / "00-index.md").exists()

    def test_creates_api_contracts(self, initialized: Path) -> None:
        api = initialized / "docs" / "api-contracts"
        assert (api / "00-index.md").exists()
        assert (api / "error-format.md").exists()

    def test_creates_ops_index(self, initialized: Path) -> None:
        assert (initialized / "docs" / "ops" / "00-index.md").exists()

    def test_creates_workflow_docs(self, initialized: Path) -> None:
        wf = initialized / "docs" / "workflow"
        assert (wf / "workflow-guide.md").exists()
        assert (wf / "thinking_os-final-edition.md").exists(), (
            "thinking_os-final-edition.md should be copied from core/docs/"
        )

    def test_no_tasks_md_index(self, initialized: Path) -> None:
        # The legacy `docs/tasks.md` flat index was retired in favor of
        # `cos board` + per-task detail files under `docs/tasks/`. See
        # docs/governance/docs-system.md § Task File Rules.
        tasks_md = initialized / "docs" / "tasks.md"
        assert not tasks_md.exists(), (
            "docs/tasks.md is retired — use `cos board` + docs/tasks/TASK-*.md"
        )
        tasks_dir = initialized / "docs" / "tasks"
        assert tasks_dir.is_dir(), "docs/tasks/ dir must exist for per-task files"

    def test_creates_questions(self, initialized: Path) -> None:
        questions = initialized / "docs" / "_meta" / "questions.md"
        assert questions.exists()
        # New scaffold has front-matter header
        assert questions.read_text().startswith("<!-- domain:")


# ---------------------------------------------------------------------------
# Placeholder resolution
# ---------------------------------------------------------------------------


class TestPlaceholderResolution:
    @pytest.fixture(scope="class")
    def django_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "ph-django", "django")

    @pytest.fixture(scope="class")
    def nextjs_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "ph-nextjs", "nextjs")

    @pytest.fixture(scope="class")
    def base_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "ph-base")

    def test_no_unresolved_placeholders_in_agents_md(self, django_project: Path) -> None:
        agents_md = (django_project / "AGENTS.md").read_text()
        unresolved = re.findall(r"\{\{[^}]+\}\}", agents_md)
        assert not unresolved, f"AGENTS.md has unresolved placeholders: {unresolved}"

    def test_no_unresolved_placeholders_in_scaffold_docs(self, django_project: Path) -> None:
        for md_file in (django_project / "docs").rglob("*.md"):
            content = md_file.read_text()
            unresolved = re.findall(r"\{\{[A-Z_]+\}\}", content)
            # Allow {{DOMAIN}}, {{DATE}} only inside the task-detail template (it's a meta-template)
            if md_file.name == "task-detail.md":
                continue
            assert not unresolved, f"{md_file}: unresolved {unresolved}"

    def test_django_substitution_includes_backend_routing(self, django_project: Path) -> None:
        agents_md = (django_project / "AGENTS.md").read_text()
        assert "Django" in agents_md
        assert "Backend" in agents_md
        assert "python-django" in agents_md

    def test_nextjs_substitution_includes_frontend_routing(self, nextjs_project: Path) -> None:
        agents_md = (nextjs_project / "AGENTS.md").read_text()
        assert "Next.js" in agents_md
        assert "Frontend" in agents_md
        assert "nextjs-react" in agents_md

    def test_no_template_substitution_uses_defaults(self, base_project: Path) -> None:
        """Init without --template should still produce a valid AGENTS.md."""
        agents_md = (base_project / "AGENTS.md").read_text()
        assert "{{" not in agents_md
        assert "Polyglot" in agents_md  # default stack label


# ---------------------------------------------------------------------------
# Django overlay
# ---------------------------------------------------------------------------


class TestDjangoOverlay:
    @pytest.fixture(scope="class")
    def django_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "django-overlay", "django")

    def test_creates_backend_playbook(self, django_project: Path) -> None:
        assert (django_project / "docs" / "playbooks" / "backend-api.md").exists()

    def test_creates_security_playbook(self, django_project: Path) -> None:
        assert (django_project / "docs" / "playbooks" / "security-review.md").exists()

    def test_creates_research_playbook(self, django_project: Path) -> None:
        assert (django_project / "docs" / "playbooks" / "research-validation.md").exists()

    def test_creates_backend_engineering_rules(self, django_project: Path) -> None:
        eng = django_project / "docs" / "engineering"
        for required in (
            "backend-rules.md",
            "naming-conventions.md",
            "logging-standards.md",
            "secrets-rotation-runbook.md",
            "glossary.md",
            "anti-ambiguity.md",
        ):
            assert (eng / required).exists(), f"missing {required}"


# ---------------------------------------------------------------------------
# Next.js overlay
# ---------------------------------------------------------------------------


class TestNextjsOverlay:
    @pytest.fixture(scope="class")
    def nextjs_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "nextjs-overlay", "nextjs")

    def test_creates_frontend_playbook(self, nextjs_project: Path) -> None:
        assert (nextjs_project / "docs" / "playbooks" / "frontend-ui.md").exists()

    def test_creates_content_seo_playbook(self, nextjs_project: Path) -> None:
        assert (nextjs_project / "docs" / "playbooks" / "content-seo.md").exists()

    def test_creates_docs_governance_playbook(self, nextjs_project: Path) -> None:
        assert (nextjs_project / "docs" / "playbooks" / "docs-governance.md").exists()

    def test_creates_frontend_engineering_rules(self, nextjs_project: Path) -> None:
        eng = nextjs_project / "docs" / "engineering"
        for required in (
            "frontend-rules.md",
            "frontend-rendering-rules.md",
            "copywriting-standard.md",
            "formatting-rules.md",
            "i18n-policy.md",
            "accessibility-checklist.md",
        ):
            assert (eng / required).exists(), f"missing {required}"

    def test_creates_design_system(self, nextjs_project: Path) -> None:
        design = nextjs_project / "docs" / "design"
        assert (design / "00-index.md").exists()
        for token_file in (
            "colors-tokens.md",
            "typography-spacing.md",
            "components-patterns.md",
            "motion-accessibility.md",
        ):
            assert (design / token_file).exists(), f"missing design/{token_file}"

    def test_creates_pages_content_spec(self, nextjs_project: Path) -> None:
        assert (nextjs_project / "docs" / "pages-content-spec" / "00-index.md").exists()


# ---------------------------------------------------------------------------
# Multi-template merge
# ---------------------------------------------------------------------------


class TestMultiTemplate:
    @pytest.fixture(scope="class")
    def fullstack_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "fullstack", "django", "nextjs")

    def test_both_playbooks_present(self, fullstack_project: Path) -> None:
        playbooks = fullstack_project / "docs" / "playbooks"
        assert (playbooks / "backend-api.md").exists()
        assert (playbooks / "frontend-ui.md").exists()

    def test_both_engineering_rule_sets_present(self, fullstack_project: Path) -> None:
        eng = fullstack_project / "docs" / "engineering"
        # Django side
        assert (eng / "backend-rules.md").exists()
        # Next.js side
        assert (eng / "frontend-rules.md").exists()

    def test_agents_md_lists_both_stacks(self, fullstack_project: Path) -> None:
        agents_md = (fullstack_project / "AGENTS.md").read_text()
        assert "Django" in agents_md
        assert "Next.js" in agents_md

    def test_agents_md_lists_both_skills(self, fullstack_project: Path) -> None:
        agents_md = (fullstack_project / "AGENTS.md").read_text()
        assert "python-django" in agents_md
        assert "nextjs-react" in agents_md

    def test_no_unresolved_placeholders_in_multi_template(self, fullstack_project: Path) -> None:
        agents_md = (fullstack_project / "AGENTS.md").read_text()
        assert "{{" not in agents_md


# ---------------------------------------------------------------------------
# Foundation map references
# ---------------------------------------------------------------------------


class TestFoundationMap:
    def test_base_foundation_map_has_governance_refs(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        _init_project(runner, project_dir)
        fm = (project_dir / "docs" / "_meta" / "foundation-map.md").read_text()
        # REF:TASKS was retired alongside docs/tasks.md — use `cos board`.
        for ref in (
            "REF:AGENTS",
            "REF:DOCS-INDEX",
            "REF:AGENT-WORKFLOW",
            "REF:DOCS-SYSTEM",
        ):
            assert ref in fm, f"foundation-map missing {ref}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_init_twice_without_force_leaves_user_edits_intact(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """A second init without --force must refuse to touch the project.

        This is the post-`--name/--force` contract: non-empty targets require
        explicit --force. This test confirms the user's edits are never lost
        silently on a re-run.
        """
        _init_project(runner, project_dir, "django")
        # Modify a generated file to look like user edit
        roadmap = project_dir / "docs" / "roadmap.md"
        roadmap.write_text("# CUSTOM USER ROADMAP\n")
        # Run init again WITHOUT --force — must fail cleanly (exit 3)
        result = runner.invoke(
            cli,
            ["init", "--agent", "claude", "-d", str(project_dir), "-t", "django"],
        )
        assert result.exit_code == 3
        assert "not empty" in result.output or "--force" in result.output
        # User edit must survive
        assert roadmap.read_text() == "# CUSTOM USER ROADMAP\n"
