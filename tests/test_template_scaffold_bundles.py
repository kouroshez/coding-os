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


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "templates"


def _stack_dirs() -> list[Path]:
    return [
        d
        for d in sorted(_TEMPLATES_DIR.iterdir())
        if d.is_dir() and d.name != "_base" and (d / "stack.yaml").exists()
    ]


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
