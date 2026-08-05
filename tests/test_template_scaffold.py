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

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

# Make cli module importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.main import cli

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses


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


def _class_scaffold(tmp_path_factory: pytest.TempPathFactory, name: str, *templates: str) -> Path:
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

    def test_inherits_base_universal_playbooks(self, nextjs_project: Path) -> None:
        # security-review + research-validation moved to _base (TASK-350): a
        # non-django composition must still get them via _base inheritance.
        playbooks = nextjs_project / "docs" / "playbooks"
        assert (playbooks / "security-review.md").exists()
        assert (playbooks / "research-validation.md").exists()

    def test_creates_frontend_engineering_rules(self, nextjs_project: Path) -> None:
        eng = nextjs_project / "docs" / "engineering"
        for required in (
            "frontend-rules.md",
            "frontend-rendering-rules.md",
            "copywriting-standard.md",
            "formatting-rules.md",
            "i18n-policy.md",
            "accessibility-web.md",
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
# Per-language toolchain config bundle (TASK-602)
# ---------------------------------------------------------------------------


class TestLanguageConfigBundle:
    """`_base/lang/<language>/` overlays ruff/pytest (python) and
    eslint/prettier/vitest/tsconfig (typescript) into every consumer of that
    language, selected by stack.yaml `language:` and overlaid last."""

    @pytest.fixture(scope="class")
    def python_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "lang-python", "django")

    @pytest.fixture(scope="class")
    def ts_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        # typescript-plain keeps the bundle's makefile eslint form; the framework
        # stacks (nextjs/react-native) moved to a per-stack-root npm script (607).
        return _class_scaffold(tmp_path_factory, "lang-ts", "typescript-plain")

    @pytest.fixture(scope="class")
    def framework_ts_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "lang-svelte", "svelte-sveltekit")

    @pytest.fixture(scope="class")
    def go_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "lang-go", "go-plain")

    @pytest.fixture(scope="class")
    def ruby_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "lang-ruby", "rails")

    @pytest.fixture(scope="class")
    def java_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "lang-java", "java-plain")

    def test_python_ships_pyproject_with_ruff_and_pytest(self, python_project: Path) -> None:
        pyproject = python_project / "pyproject.toml"
        assert pyproject.exists(), "python language bundle must ship pyproject.toml"
        text = pyproject.read_text()
        assert "[tool.ruff]" in text
        assert "[tool.pytest.ini_options]" in text

    def test_python_lint_target_uses_configured_ruff(self, python_project: Path) -> None:
        makefile = python_project / ".coding-os" / "Makefile.stacks"
        assert makefile.exists()
        assert "ruff" in makefile.read_text()

    def test_ts_ships_flat_eslint_config(self, ts_project: Path) -> None:
        eslint = ts_project / "eslint.config.js"
        assert eslint.exists(), "ts language bundle must ship eslint.config.js"
        assert "typescript-eslint" in eslint.read_text()

    def test_ts_ships_prettier_vitest_tsconfig(self, ts_project: Path) -> None:
        assert (ts_project / ".prettierrc.json").exists()
        assert (ts_project / "vitest.config.ts").exists()
        assert (ts_project / "tsconfig.json").exists()

    def test_ts_lint_target_runs_eslint_and_typecheck(self, ts_project: Path) -> None:
        makefile = (ts_project / ".coding-os" / "Makefile.stacks").read_text()
        assert "eslint ." in makefile
        assert "tsc --noEmit" in makefile

    def test_framework_ts_gets_bundle_and_keeps_framework_check(
        self, framework_ts_project: Path
    ) -> None:
        # The bundle adds eslint even where the stack's own check is framework-aware.
        assert (framework_ts_project / "eslint.config.js").exists()
        makefile = (framework_ts_project / ".coding-os" / "Makefile.stacks").read_text()
        assert "eslint ." in makefile  # eslint added
        assert "npm run lint" in makefile  # framework check (svelte-check) kept

    def test_go_ships_golangci_v2_config(self, go_project: Path) -> None:
        golangci = go_project / ".golangci.yml"
        assert golangci.exists(), "go language bundle must ship .golangci.yml"
        assert 'version: "2"' in golangci.read_text()  # v2 schema, not legacy v1

    def test_ruby_ships_rubocop_config(self, ruby_project: Path) -> None:
        assert (ruby_project / ".rubocop.yml").exists()

    def test_cross_language_isolation(self, go_project: Path) -> None:
        # A go project gets its own bundle but never another language's config.
        assert not (go_project / "eslint.config.js").exists()
        assert not (go_project / "pyproject.toml").exists()
        assert not (go_project / ".rubocop.yml").exists()

    def test_language_without_bundle_gets_nothing(self, java_project: Path) -> None:
        # Java has no _base/lang/java bundle (Spotless lives in pom.xml).
        for name in ("eslint.config.js", "pyproject.toml", ".golangci.yml", ".rubocop.yml"):
            assert not (java_project / name).exists()


# ---------------------------------------------------------------------------
# Bootable scaffold (work-surface stacks ship a runnable seed)
# ---------------------------------------------------------------------------


class TestBootableScaffold:
    """fastapi/django ship a runnable seed under `src/backend/` — manifest +
    entrypoint + sample test + .env + a `verify:` block — so `cos init` output
    is green after a dependency install. The python library stack is exempt:
    it ships a skeleton, not an app."""

    _REPO = Path(__file__).resolve().parent.parent

    @pytest.fixture(scope="class")
    def fastapi_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-fastapi", "fastapi")

    @pytest.fixture(scope="class")
    def django_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-django", "django")

    @pytest.fixture(scope="class")
    def python_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-python", "python")

    @pytest.fixture(scope="class")
    def go_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-go", "go")

    @pytest.fixture(scope="class")
    def gofiber_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-gofiber", "go-fiber")

    @pytest.fixture(scope="class")
    def nextjs_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-nextjs", "nextjs")

    @pytest.fixture(scope="class")
    def reactnative_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-rn", "react-native")

    @pytest.fixture(scope="class")
    def wordpress_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold(tmp_path_factory, "boot-wp", "wordpress")

    def test_fastapi_ships_runnable_seed(self, fastapi_project: Path) -> None:
        backend = fastapi_project / "src" / "backend"
        pyproject = (backend / "pyproject.toml").read_text()
        assert "fastapi" in pyproject
        assert "[tool.pytest.ini_options]" in pyproject
        main = (backend / "app" / "main.py").read_text()
        assert "FastAPI" in main and "/health" in main
        assert (backend / "tests" / "test_health.py").exists()
        assert (backend / ".env.example").exists()

    def test_fastapi_drops_stale_gitkeep(self, fastapi_project: Path) -> None:
        # The empty-dir marker is negated once real files land under src/backend.
        assert not (fastapi_project / "src" / "backend" / ".gitkeep").exists()

    def test_django_ships_runnable_seed(self, django_project: Path) -> None:
        backend = django_project / "src" / "backend"
        pyproject = (backend / "pyproject.toml").read_text()
        assert "django" in pyproject.lower()
        assert "DJANGO_SETTINGS_MODULE" in pyproject
        assert (backend / "manage.py").exists()
        assert "INSTALLED_APPS" in (backend / "config" / "settings.py").read_text()
        assert "health/" in (backend / "config" / "urls.py").read_text()
        assert (backend / "tests" / "test_health.py").exists()
        assert (backend / ".env.example").exists()

    def test_python_library_is_seed_exempt(self, python_project: Path) -> None:
        # Library stack ships a skeleton, not a runnable app: no forced service
        # root, entrypoint, or app seed (decision recorded in stack_lint.py).
        assert not (python_project / "src" / "backend").exists()
        assert not (python_project / "manage.py").exists()
        assert not (python_project / "src" / "app" / "main.py").exists()

    def test_go_ships_runnable_seed(self, go_project: Path) -> None:
        backend = go_project / "src" / "backend"
        assert (backend / "go.mod").exists()
        assert "/health" in (backend / "cmd" / "api" / "main.go").read_text()
        assert (backend / "cmd" / "api" / "main_test.go").exists()
        assert not (backend / ".gitkeep").exists()

    def test_gofiber_ships_fiber_v3_seed(self, gofiber_project: Path) -> None:
        backend = gofiber_project / "src" / "backend"
        assert "gofiber/fiber/v3" in (backend / "go.mod").read_text()
        main = (backend / "cmd" / "api" / "main.go").read_text()
        assert "fiber.New" in main and "/health" in main
        assert (backend / "cmd" / "api" / "main_test.go").exists()

    def test_nextjs_ships_runnable_seed(self, nextjs_project: Path) -> None:
        frontend = nextjs_project / "src" / "frontend"
        pkg = (frontend / "package.json").read_text()
        assert '"next"' in pkg and '"type": "module"' in pkg
        assert (frontend / "eslint.config.js").exists()
        assert (frontend / "app" / "page.tsx").exists()
        assert (frontend / "app" / "layout.tsx").exists()
        assert (frontend / "lib" / "greeting.test.ts").exists()

    def test_reactnative_migrates_eslintrc_to_flat(self, reactnative_project: Path) -> None:
        mobile = reactnative_project / "src" / "mobile"
        assert '"react-native"' in (mobile / "package.json").read_text()
        assert (mobile / "eslint.config.js").exists()
        assert not (mobile / ".eslintrc.cjs").exists()  # legacy config migrated
        assert (mobile / "App.tsx").exists()
        assert (mobile / "src" / "greeting.test.ts").exists()

    def test_wordpress_ships_composer_and_phpcs(self, wordpress_project: Path) -> None:
        backend = wordpress_project / "src" / "backend"
        composer = (backend / "composer.json").read_text()
        assert '"lint"' in composer and "phpcs" in composer
        assert (backend / "phpcs.xml.dist").exists()
        assert (backend / "plugin" / "plugin.php").exists()

    @pytest.mark.parametrize(
        "stack,tokens",
        [
            ("fastapi", ("ruff check", "pytest")),
            ("django", ("ruff check", "pytest")),
            ("go", ("go vet", "go test")),
            ("go-fiber", ("go vet", "go test")),
            ("nextjs", ("npm run lint",)),
            ("react-native", ("npm run lint", "npm test")),
            ("wordpress", ("composer lint",)),
        ],
    )
    def test_work_surface_stack_has_verify_block(self, stack: str, tokens: tuple) -> None:
        data = yaml.safe_load((self._REPO / "src" / "templates" / stack / "stack.yaml").read_text())
        verify = data.get("verify")
        assert verify, f"{stack} must declare a verify: block"
        cmd = verify[0]["cmd"]
        for tok in tokens:
            assert tok in cmd, f"{stack} verify missing {tok!r}"


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


# ── Scaffold self-consistency guards (TASK-133) ──────────────────────
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "templates"


def _stack_dirs() -> list[Path]:
    return [
        d
        for d in sorted(_TEMPLATES_DIR.iterdir())
        if d.is_dir() and d.name != "_base" and (d / "stack.yaml").exists()
    ]


def test_every_dimension_read_file_resolves() -> None:
    # D2-F1: a stack's dimensions[].read_files must resolve in that stack's
    # scaffold OR _base's scaffold — no dangling Read List entries (the
    # go-fiber security-review.md class of bug).
    base_scaffold = _TEMPLATES_DIR / "_base" / "scaffold"
    repo_root = _TEMPLATES_DIR.parent.parent
    dangling: list[str] = []
    for stack in _stack_dirs():
        spec = yaml.safe_load((stack / "stack.yaml").read_text(encoding="utf-8")) or {}
        # `meta` is the dogfood stack — its read_files point at the live repo
        # (docs/, src/core/), not a scaffold tree; resolve those at repo root.
        bases = [repo_root] if stack.name == "meta" else [stack / "scaffold", base_scaffold]
        for dim in spec.get("dimensions", []) or []:
            for rf in dim.get("read_files", []) or []:
                if not any((b / rf).exists() for b in bases):
                    dangling.append(f"{stack.name}:{dim.get('name')} -> {rf}")
    assert not dangling, "Dangling dimension read_files:\n" + "\n".join(dangling)


def test_no_engineering_doc_filename_collision_across_stacks() -> None:
    # D2-F4: two stacks must not ship the same docs/engineering/*.md filename —
    # `cos add-stack` of a second stack would overwrite the first's copy
    # (the accessibility-checklist.md collision). Shared docs belong in _base.
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for stack in _stack_dirs():
        eng = stack / "scaffold" / "docs" / "engineering"
        if not eng.is_dir():
            continue
        for md in sorted(eng.glob("*.md")):
            if md.name in seen:
                collisions.append(f"{md.name}: {seen[md.name]} vs {stack.name}")
            else:
                seen[md.name] = stack.name
    assert not collisions, "Colliding engineering doc filenames across stacks:\n" + "\n".join(
        collisions
    )


# ---------------------------------------------------------------------------
# Tag-driven docs composition — TASK-360
# ---------------------------------------------------------------------------


class TestTagDrivenDocs:
    def test_default_scaffold_strips_tags_and_keeps_everything(self, tmp_path):
        from click.testing import CliRunner

        from cli.main import cli

        project = tmp_path / "alltags"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        vision = (project / "docs" / "prd" / "01-snapshot-vision.md").read_text(encoding="utf-8")
        index = (project / "docs" / "00-index.md").read_text(encoding="utf-8")
        lifecycle = (project / "docs" / "governance" / "task-lifecycle.md").read_text(
            encoding="utf-8"
        )
        assert "[PRD Index](./prd/00-index.md)" in index  # gated link present by default
        for rendered in (vision, index, lifecycle):
            assert "module:" not in rendered.split("\n")[0]  # tag stripped from header
            assert "if-module" not in rendered and "end-if" not in rendered  # markers stripped

    def test_docs_module_disabled_drops_tagged_tree_and_index_link(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        import cli.subsystems as subsystems_module
        from cli.main import cli
        from cli.subsystems import load_subsystems

        # Docs (and its dependent tasks) disabled before the scaffold copy —
        # the wizard/preset path writes this state pre-overlay.
        def _docs_off(project_root, modules=None):
            modules = modules or load_subsystems()
            return {mid: mid not in {"docs", "tasks"} for mid in modules}

        monkeypatch.setattr(subsystems_module, "module_state", _docs_off)

        project = tmp_path / "nodocs"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        assert not (project / "docs" / "prd" / "01-snapshot-vision.md").exists()
        assert not (project / "docs" / "prd" / "00-index.md").exists()
        assert not (project / "docs" / "governance" / "task-lifecycle.md").exists()
        index = (project / "docs" / "00-index.md").read_text(encoding="utf-8")
        assert "[PRD Index]" not in index  # no dangling link
        assert "[Risk Register]" in index  # untagged kernel docs remain

    def test_stack_conditional_blocks_render_both_branches(self):
        from cli.main import _apply_doc_conditions

        doc = (
            "<!-- domain:X | layer:y | updated:1 -->\n"
            "intro\n"
            "<!-- if-stack:go-fiber,fastapi -->\n"
            "backend guidance\n"
            "<!-- end-if -->\n"
            "outro\n"
        )
        skip, with_stack = _apply_doc_conditions(doc, set(), {"go-fiber"})
        assert skip is False
        assert "backend guidance" in with_stack and "if-stack" not in with_stack

        skip, without_stack = _apply_doc_conditions(doc, set(), {"nextjs"})
        assert skip is False
        assert "backend guidance" not in without_stack
        assert "intro" in without_stack and "outro" in without_stack

    def test_module_block_and_file_tag_semantics(self):
        from cli.main import _apply_doc_conditions

        tagged = "<!-- domain:X | module:docs -->\nbody\n"
        assert _apply_doc_conditions(tagged, {"docs"}, set()) == (True, "")
        skip, kept = _apply_doc_conditions(tagged, set(), set())
        assert skip is False and "module:docs" not in kept and "body" in kept

        block = "head\n<!-- if-module:tasks -->\ntask hint\n<!-- end-if -->\ntail\n"
        _, disabled = _apply_doc_conditions(block, {"tasks"}, set())
        assert "task hint" not in disabled
        _, enabled = _apply_doc_conditions(block, set(), set())
        assert "task hint" in enabled


# ---------------------------------------------------------------------------
# Stack bundle factory contract — TASK-361
# ---------------------------------------------------------------------------


class TestStackBundleLint:
    def test_all_shipped_stacks_pass_hard_rules(self):
        """CI gate: a new stack missing a bundle artifact fails before merge."""
        from cli.stack_lint import lint_all

        reports = lint_all()
        assert len(reports) >= 10
        failing = {sid: r.hard for sid, r in reports.items() if not r.passed}
        assert not failing, f"factory-contract hard failures: {failing}"

    def test_known_gaps_are_reported_not_hidden(self):
        from cli.stack_lint import lint_all

        reports = lint_all()
        # Honest completeness: stacks without golden sections say so.
        assert any("golden" in gap for gap in reports["fastapi"].soft)
        # django ships goldens → no golden gap for it.
        assert not any("golden" in gap for gap in reports["django"].soft)

    def test_broken_fixture_stack_fails_with_named_artifacts(self, tmp_path):
        import shutil as _shutil

        from cli.stack_lint import lint_all

        fixtures = tmp_path / "templates"
        fixtures.mkdir()
        _shutil.copytree(Path("src/templates/_base"), fixtures / "_base", symlinks=True)
        broken = fixtures / "brokenstack"
        broken.mkdir()
        (broken / "stack.yaml").write_text(
            "version: 1\n"
            "id: brokenstack\n"
            "label: Broken\n"
            "category: backend\n"
            "language: go\n"
            "structure: {root: src/backend, tree: 'src/backend/'}\n"
            "primary_skill: ghost-skill\n"
            "skills: []\n"
            "substitutions: {}\n",
            encoding="utf-8",
        )
        reports = lint_all(registry_dir=fixtures, golden_root=tmp_path / "no-goldens")
        # Layer 1 — schema-invalid stack is rejected by the loader; the lint
        # surfaces that rejection with the named missing properties.
        report = reports["brokenstack"]
        assert report.passed is False
        joined = " | ".join(report.hard)
        assert "VERIFY_BACKEND_GLOB" in joined
        assert "DOMAIN_ROUTES" in joined and "QUICK_ROUTING" in joined

        # Layer 2 — schema-valid stack with a ghost skill loads but fails lint.
        ghost = fixtures / "ghoststack"
        ghost.mkdir()
        (ghost / "stack.yaml").write_text(
            "version: 1\n"
            "id: ghoststack\n"
            "label: Ghost\n"
            "category: backend\n"
            "language: go\n"
            "structure: {root: src/backend, tree: 'src/backend/'}\n"
            "primary_skill: ghost-skill\n"
            "skills: []\n"
            "substitutions:\n"
            "  DOMAIN_ROUTES: x\n  SKILL_ROUTES: x\n  ENGINEERING_RULE_ROUTING: x\n"
            "  TOOL_ROUTING_IMPL: x\n  QUICK_ROUTING: x\n  STACK_REF_CODES: ''\n"
            "  VERIFY_BACKEND_GLOB: x\n  VERIFY_BACKEND_SUITES: x\n  VERIFY_BACKEND: x\n",
            encoding="utf-8",
        )
        reports = lint_all(registry_dir=fixtures, golden_root=tmp_path / "no-goldens")
        ghost_report = reports["ghoststack"]
        assert ghost_report.passed is False
        assert any("ghost-skill" in issue for issue in ghost_report.hard)

    def test_plain_and_library_stacks_exempt_from_work_surfaces(self):
        from cli.stack_lint import lint_all

        reports = lint_all()
        for stack_id in ("go-plain", "typescript-plain", "python", "meta"):
            assert reports[stack_id].passed, reports[stack_id].hard
            assert not any("dimensions" in gap for gap in reports[stack_id].soft)

    def test_factory_v2_completeness_checks_are_hard(self, tmp_path):
        """TASK-611: post-backfill, runtime-manifest / lint-config / reference-
        integrity block (HARD) instead of warn (soft), so a future stack can
        never regress below the v2 bar."""
        import shutil as _shutil

        from cli.stack_lint import lint_all

        fixtures = tmp_path / "templates"
        fixtures.mkdir()
        _shutil.copytree(Path("src/templates/_base"), fixtures / "_base", symlinks=True)
        bare = fixtures / "barestack"
        bare.mkdir()
        (bare / "stack.yaml").write_text(
            "version: 1\nid: barestack\nlabel: Bare\ncategory: backend\nlanguage: go\n"
            "structure: {root: src/backend, tree: 'src/backend/'}\n"
            "primary_skill: null\nskills: []\n"
            "substitutions:\n"
            "  DOMAIN_ROUTES: x\n  SKILL_ROUTES: x\n  ENGINEERING_RULE_ROUTING: x\n"
            "  TOOL_ROUTING_IMPL: x\n  QUICK_ROUTING: x\n  STACK_REF_CODES: ''\n"
            "  VERIFY_BACKEND_GLOB: x\n  VERIFY_BACKEND_SUITES: x\n  VERIFY_BACKEND: 'go vet ./...'\n",
            encoding="utf-8",
        )
        report = lint_all(registry_dir=fixtures, golden_root=tmp_path / "no-goldens")["barestack"]
        # go backend with no scaffold manifest now blocks, and never as a soft gap.
        assert report.passed is False
        assert any("no runtime manifest" in issue for issue in report.hard)
        assert not any("no runtime manifest" in gap for gap in report.soft)


# ---------------------------------------------------------------------------
# node-express stack bundle — TASK-367
# ---------------------------------------------------------------------------


class TestNodeExpressStack:
    def test_factory_lint_passes_with_golden(self):
        from cli.stack_lint import lint_all

        report = lint_all()["node-express"]
        assert report.passed, report.hard
        assert not any("golden" in gap for gap in report.soft)  # golden shipped

    def test_scaffold_structure_and_skill_routing(self, tmp_path):
        import yaml as _yaml
        from click.testing import CliRunner

        from cli.main import cli

        project = tmp_path / "expressapp"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--template",
                "node-express",
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        backend = project / "src" / "backend"
        for piece in (
            "package.json",
            "tsconfig.json",
            "src/index.ts",
            "src/routes/health.ts",
            "src/middleware/error-handler.ts",
        ):
            assert (backend / piece).is_file(), piece
        assert "{{PROJECT_NAME}}" not in (backend / "package.json").read_text(encoding="utf-8")

        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        # Producer shape: domain → raw command (main._derive_verify_from_world).
        assert config["verify"]["backend"] == "cd src/backend && npm run lint && npm test"
        agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "express-service.md" in agents_md  # playbook routed

    def test_scaffold_typechecks_pre_install(self, tmp_path):
        import shutil as _shutil
        import subprocess

        tsc = Path("src/core/web/ui/node_modules/.bin/tsc").resolve()
        if not tsc.exists():
            pytest.skip("workspace tsc unavailable")
        from click.testing import CliRunner

        from cli.main import cli

        project = tmp_path / "tscheck"
        project.mkdir()
        assert (
            CliRunner()
            .invoke(
                cli,
                [
                    "init",
                    "--agent",
                    "claude",
                    "-d",
                    str(project),
                    "--template",
                    "node-express",
                    "--yes",
                    "--no-index",
                    "--no-register",
                ],
            )
            .exit_code
            == 0
        )
        proc = subprocess.run(
            [str(tsc), "--noEmit"],
            cwd=project / "src" / "backend",
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_regen_registries_include_node_express(self):
        registry_text = Path("src/core/rules/skill-enforcement.md").read_text(encoding="utf-8")
        assert "node-express" in registry_text
        dimensions_text = Path("src/core/rules/dimension-registry.md").read_text(encoding="utf-8")
        assert "Express route" in dimensions_text


# ---------------------------------------------------------------------------
# vue-nuxt stack bundle — TASK-368
# ---------------------------------------------------------------------------


class TestVueNuxtStack:
    def test_factory_lint_passes_with_golden(self):
        from cli.stack_lint import lint_all

        report = lint_all()["vue-nuxt"]
        assert report.passed, report.hard
        assert not any("golden" in gap for gap in report.soft)

    def test_scaffold_structure_and_routing(self, tmp_path):
        import yaml as _yaml
        from click.testing import CliRunner

        from cli.main import cli

        project = tmp_path / "nuxtapp"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--template",
                "vue-nuxt",
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        frontend = project / "src" / "frontend"
        for piece in ("nuxt.config.ts", "app.vue", "pages/index.vue", "package.json"):
            assert (frontend / piece).is_file(), piece
        index_page = (frontend / "pages" / "index.vue").read_text(encoding="utf-8")
        assert (
            "{{PROJECT_NAME}}" not in index_page
        )  # placeholder resolved in .vue? (md/json/ts only)

        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert config["verify"]["frontend"] == "cd src/frontend && npm run lint && npm test"
        agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "nuxt-app.md" in agents_md

    def test_regen_registries_include_vue_nuxt(self):
        registry_text = Path("src/core/rules/skill-enforcement.md").read_text(encoding="utf-8")
        assert "vue-nuxt" in registry_text
        dimensions_text = Path("src/core/rules/dimension-registry.md").read_text(encoding="utf-8")
        assert "Nuxt page / route" in dimensions_text


class TestGoModuleDirectiveParses:
    """Guard TASK-890: `module {{PROJECT_NAME}}` is unparseable by Go's modfile lexer.

    `{` and `}` are token delimiters there, so the unquoted placeholder passes more
    than one argument to the `module` directive. GitHub's dependency-graph job hit
    exactly that and put a "Dependency file checks have 1 error" banner on the public
    security page. Quoting keeps the literal placeholder (which the scaffold-verify
    "no leftover placeholders" gate requires) while parsing cleanly; Go's own tooling
    normalises the quotes away on the first `go mod edit -fmt` / `go mod tidy`.
    """

    GO_STACKS = ("go", "go-plain", "go-fiber")

    @pytest.mark.parametrize("stack", GO_STACKS)
    def test_module_placeholder_is_quoted(self, stack: str) -> None:
        go_mod = Path(f"src/templates/{stack}/scaffold/src/backend/go.mod")
        first = go_mod.read_text(encoding="utf-8").splitlines()[0]
        assert first == 'module "{{PROJECT_NAME}}"', (
            f"{go_mod}: expected the module path quoted so Go can parse the template; "
            f"got {first!r}. See the class docstring before 'tidying' this."
        )

    @pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
    @pytest.mark.parametrize("stack", GO_STACKS)
    def test_go_toolchain_parses_the_template(self, stack: str) -> None:
        mod_dir = Path(f"src/templates/{stack}/scaffold/src/backend").resolve()
        proc = subprocess.run(
            ["go", "mod", "edit", "-json"], cwd=mod_dir, capture_output=True, text=True
        )
        assert proc.returncode == 0, f"{mod_dir}/go.mod does not parse:\n{proc.stderr}"
        assert json.loads(proc.stdout)["Module"]["Path"] == "{{PROJECT_NAME}}"
