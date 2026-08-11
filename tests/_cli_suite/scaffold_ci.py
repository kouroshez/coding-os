"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
    main_module,
)


class TestCiWorkflow:
    def _world(self, *stacks: str):
        return main_module._build_world("claude", tuple(stacks), Path("/tmp/ci-probe"))

    def test_multi_stack_emits_language_matrix_delegating_to_make(self) -> None:
        from cli.renderer import render_ci_workflow

        out = render_ci_workflow(self._world("django", "nextjs"))
        doc = yaml.safe_load(out)
        verify = doc["jobs"]["verify"]
        legs = {m["language"]: m["targets"] for m in verify["strategy"]["matrix"]["include"]}
        assert legs["python"] == "lint-backend test-backend"
        assert legs["typescript"] == "lint-frontend test-frontend"
        # Body delegates to make — never pins a ruff/pytest/eslint version.
        assert "make ${{ matrix.targets }}" in out
        assert verify["runs-on"] == "ubuntu-latest"

    def test_macos_kept_off_per_push_path(self) -> None:
        from cli.renderer import render_ci_workflow

        out = render_ci_workflow(self._world("django", "nextjs"))
        assert "macos" not in out.lower()  # github-actions-cost-macos-10x
        assert 'paths-ignore: ["docs/tasks/**"]' in out

    def test_adding_a_stack_auto_includes_its_language(self) -> None:
        from cli.renderer import render_ci_workflow

        one = render_ci_workflow(self._world("nextjs"))
        two = render_ci_workflow(self._world("nextjs", "django"))
        assert "language: python" not in one
        assert "language: python" in two  # new stack's targets appear, no hand edit

    def test_empty_world_renders_nothing(self) -> None:
        from cli.renderer import render_ci_workflow

        assert render_ci_workflow(self._world()) == ""

    def test_materialize_writes_consumer_owned_file(self, tmp_path: Path) -> None:
        from cli._init_helpers import materialize_ci_workflow

        assert materialize_ci_workflow(tmp_path, self._world("django", "nextjs"))
        ci = tmp_path / ".github" / "workflows" / "ci.yml"
        assert ci.is_file() and not ci.is_symlink()  # init-strip, not a live symlink
        assert not materialize_ci_workflow(tmp_path, self._world())  # empty → no write

    def test_cicd_module_off_in_lean_profiles_on_in_full(self) -> None:
        from cli.subsystems import load_profiles, load_subsystems

        assert "cicd" in load_subsystems()
        profiles, _ = load_profiles()
        assert "cicd" in profiles["standard"] and "cicd" in profiles["core"]
        assert "cicd" not in profiles["full"]

    def test_lite_profile_is_kernel_only_and_dependency_safe(self) -> None:
        from cli.subsystems import load_profiles, load_subsystems

        modules = load_subsystems()
        profiles, _ = load_profiles()
        lite = set(profiles["lite"])
        toggleable = {m.id for m in modules.values() if not m.kernel and not m.hidden}
        assert toggleable <= lite, f"lite leaves a toggleable module on: {toggleable - lite}"
        for m in modules.values():
            if m.id in lite:
                continue
            assert not (set(m.depends_on) & lite), f"{m.id} depends on a lite-disabled module"

    def test_module_payload_includes_hint(self, tmp_path: Path) -> None:
        from cli.module_commands import module_state_payload

        payload = module_state_payload(tmp_path)
        assert payload["modules"], "no modules in payload"
        assert all("hint" in m for m in payload["modules"]), "hint missing from module payload"
        assert any(m["hint"] for m in payload["modules"])

    def test_module_payload_includes_commands_reason_and_owned(self, tmp_path: Path) -> None:
        """TASK-814: the Config→Modules payload carries the commands count, the
        dependency rationale, and owned artifact identities for the UI disclosure."""
        from cli.module_commands import module_state_payload

        payload = module_state_payload(tmp_path)
        by_id = {m["id"]: m for m in payload["modules"]}
        assert by_id["tasks"]["commands"] == 4, by_id["tasks"]
        assert by_id["tasks"]["depends_on_reason"], "tasks->docs reason missing"
        assert "board" in by_id["tasks"]["owned"]["commands"]
        assert "memory.md" in by_id["memory"]["owned"]["rules"]

    def test_full_profile_init_emits_ci_default_does_not(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        for profile, expected in (("full", True), ("standard", False)):
            project = tmp_path / profile
            project.mkdir()
            result = runner.invoke(
                cli,
                [
                    "init",
                    "--agent",
                    "claude",
                    "-d",
                    str(project),
                    "--template",
                    "django",
                    "--template",
                    "nextjs",
                    "--profile",
                    profile,
                    "--no-index",
                    "--no-register",
                ],
            )
            assert result.exit_code == 0, result.output
            ci = project / ".github" / "workflows" / "ci.yml"
            assert ci.exists() is expected, (
                f"{profile}: ci.yml exists={ci.exists()}, want {expected}"
            )

    def test_materialize_is_write_once_preserving_consumer_edits(self, tmp_path: Path) -> None:
        # TASK-625: write-once (the ensure_* idiom) — cos update must never
        # clobber a consumer's ci.yml edits.
        from cli._init_helpers import materialize_ci_workflow

        world = self._world("django", "nextjs")
        assert materialize_ci_workflow(tmp_path, world)
        ci = tmp_path / ".github" / "workflows" / "ci.yml"
        ci.write_text("# consumer added a deploy job\n", encoding="utf-8")
        assert materialize_ci_workflow(tmp_path, world) is False  # second call is a no-op
        assert ci.read_text(encoding="utf-8") == "# consumer added a deploy job\n"


class TestRegenChainRelocation:
    """project-anatomy.md § Glob/verify propagation for relocated services."""

    @pytest.fixture(scope="class")
    def composed_world(self):
        return main_module._build_world("claude", ("go-fiber", "fastapi"), Path("/virtual/twosvc"))

    @pytest.fixture(scope="class")
    def composed_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """One shared two-backend consumer — init is the expensive step."""
        project = tmp_path_factory.mktemp("regen-chain") / "twosvc"
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
                "go-fiber",
                "--template",
                "fastapi",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        return project

    def test_registry_tables_are_service_scoped(self, composed_world) -> None:
        from cli.renderer import render_dimension_registry, render_skill_enforcement

        enforcement = render_skill_enforcement(composed_world)
        assert "`src/services/fastapi/**/*.py`" in enforcement
        assert "`src/services/go-fiber/**/*.go`" in enforcement
        assert "src/backend" not in enforcement
        registry = render_dimension_registry(composed_world)
        assert "## fastapi" in registry and "## go-fiber" in registry

    def test_single_stack_world_passthrough(self) -> None:
        """Backward compatibility: no collision → emitted globs unchanged."""
        from cli.renderer import render_skill_enforcement

        world = main_module._build_world("claude", ("fastapi",), Path("/virtual/solo"))
        enforcement = render_skill_enforcement(world)
        assert "`src/backend/**/*.py`" in enforcement
        assert "src/services/" not in enforcement
        names = [t.name for t in world.makefile_targets]
        assert "lint-backend" in names
        assert not any(n.endswith("-fastapi") for n in names)
        assert world.substitutions["VERIFY_BACKEND_SUITES"] == "lint-backend + test-backend"

    def test_makefile_targets_do_not_dedupe_collide(self, composed_world) -> None:
        """Both stacks declare lint-backend/test-backend; unsuffixed names
        would dedupe-by-name and silently drop one stack's suite."""
        cmds = {t.name: t.cmd for t in composed_world.makefile_targets}
        assert "lint-backend-go-fiber" in cmds and "lint-backend-fastapi" in cmds
        assert "test-backend-go-fiber" in cmds and "test-backend-fastapi" in cmds
        assert "lint-backend" not in cmds and "test-backend" not in cmds
        assert "src/services/fastapi" in cmds["lint-backend-fastapi"]
        assert "src/services/go-fiber" in cmds["test-backend-go-fiber"]

    def test_verify_substitutions_join_both_services(self, composed_world) -> None:
        substitutions = composed_world.substitutions
        assert "src/services/go-fiber" in substitutions["VERIFY_BACKEND_GLOB"]
        assert "src/services/fastapi" in substitutions["VERIFY_BACKEND_GLOB"]
        assert "lint-backend-go-fiber" in substitutions["VERIFY_BACKEND_SUITES"]
        assert "lint-backend-fastapi" in substitutions["VERIFY_BACKEND_SUITES"]

    def test_init_artifacts_service_scoped(self, composed_project: Path) -> None:
        import yaml

        agents_md = (composed_project / "AGENTS.md").read_text(encoding="utf-8")
        assert "src/services/go-fiber" in agents_md
        assert "src/services/fastapi" in agents_md
        # Stack makefile targets are not materialized into the consumer
        # Makefile by init (pre-existing gap, all stacks — TASK-392); the
        # renamed suites reach the consumer through AGENTS.md text.
        assert "lint-backend-go-fiber" in agents_md
        assert "lint-backend-fastapi" in agents_md

        boundary = yaml.safe_load(
            (composed_project / ".coding-os" / "scaffold-boundary.yaml").read_text(encoding="utf-8")
        )
        forbids = {e["stack"]: e["forbids_writing_in"] for e in boundary["stacks"]}
        assert "src/services/fastapi/" in forbids["go-fiber"]
        assert "src/services/go-fiber/" in forbids["fastapi"]
        assert "src/services/go-fiber/" not in forbids["go-fiber"]

    def test_cross_service_write_blocked_by_boundary_delegate(self, composed_project: Path) -> None:
        """Acceptance: a write crossing another service's subtree is flagged
        using the parameterized boundary data (exit 2 from the delegate)."""
        import subprocess

        repo_root = Path(__file__).resolve().parent.parent.parent
        delegate = repo_root / "src" / "core" / "hooks" / "_enforce_scaffold_boundary.py"
        boundary_file = composed_project / ".coding-os" / "scaffold-boundary.yaml"

        def _verdict(rel_path: str) -> int:
            return subprocess.run(
                [
                    sys.executable,
                    str(delegate),
                    str(boundary_file),
                    rel_path,
                    str(composed_project),
                ],
                capture_output=True,
                timeout=10,
            ).returncode

        # Unowned cross-service write (a .go file inside the fastapi service).
        assert _verdict("src/services/fastapi/rogue.go") == 2
        # Owned writes inside each service stay allowed.
        assert _verdict("src/services/fastapi/app/api.py") == 0
        assert _verdict("src/services/go-fiber/internal/handler.go") == 0

    def test_boundary_longest_pattern_owner_resolution(self) -> None:
        import importlib.util

        repo_root = Path(__file__).resolve().parent.parent.parent
        helper = repo_root / "src" / "core" / "hooks" / "_enforce_scaffold_boundary.py"
        spec = importlib.util.spec_from_file_location("_boundary_owner_t600", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        broad = {"stack": "typescript-plain", "file_patterns": ["src/**"]}
        specific = {"stack": "nextjs", "file_patterns": ["src/frontend/**/*.ts"]}
        # Most-specific (longest) pattern wins regardless of stack list order —
        # not first-match-in-list (which would flip with the order below).
        assert (
            module._resolve_owner([broad, specific], "src/frontend/app/page.ts")["stack"]
            == "nextjs"
        )
        assert (
            module._resolve_owner([specific, broad], "src/frontend/app/page.ts")["stack"]
            == "nextjs"
        )
        # A path only the broad pattern matches still resolves to the broad stack.
        assert (
            module._resolve_owner([broad, specific], "src/backend/x.go")["stack"]
            == "typescript-plain"
        )

    def test_skill_primer_remaps_relocated_globs(self, composed_project: Path) -> None:
        import importlib.util

        repo_root = Path(__file__).resolve().parent.parent.parent
        helper = repo_root / "src" / "core" / "hooks" / "_helpers" / "skill_primer.py"
        spec = importlib.util.spec_from_file_location("skill_primer_t355", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        stacks = [
            (stack_id, module._load_stack(repo_root, stack_id))
            for stack_id in ("go-fiber", "fastapi")
        ]
        state_dir = composed_project / ".coding-os"
        overrides = module._service_root_overrides(state_dir, stacks)
        assert overrides == {
            "go-fiber": ("src/backend", "src/services/go-fiber"),
            "fastapi": ("src/backend", "src/services/fastapi"),
        }
        card = module._format_card(stacks, overrides)
        assert "src/services/go-fiber/**/*.go" in card
        assert "src/services/fastapi/**/*.py" in card
        assert "src/backend" not in card

    def test_skill_primer_dimension_readlist_scoped_to_installed_stacks(self) -> None:
        """F3/R8: the SessionStart Classify Read List shows ONLY installed
        stacks' dimensions; an uninstalled stack (and meta, for a non-meta
        consumer) never appears."""
        import importlib.util

        repo_root = Path(__file__).resolve().parent.parent.parent
        helper = repo_root / "src" / "core" / "hooks" / "_helpers" / "skill_primer.py"
        spec = importlib.util.spec_from_file_location("skill_primer_f3", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        stacks = [("python", module._load_stack(repo_root, "python"))]
        card = module._format_card(stacks)

        assert "Classify Read List" in card
        assert "[python] Python module / API" in card  # installed dimension shows
        assert "[angular]" not in card  # uninstalled stack absent
        assert "[meta]" not in card  # meta excluded for non-meta consumer
