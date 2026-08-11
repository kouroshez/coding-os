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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "templates"


def _stack_dirs() -> list[Path]:
    return [
        d
        for d in sorted(_TEMPLATES_DIR.iterdir())
        if d.is_dir() and d.name != "_base" and (d / "stack.yaml").exists()
    ]


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
