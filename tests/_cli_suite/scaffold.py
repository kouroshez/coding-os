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


class TestProjectAnatomy:
    def test_every_stack_declares_structure_root(self) -> None:
        from cli._resources import templates_dir
        from cli.stack_registry import load_stack_registry

        result = load_stack_registry(templates_dir())
        for stack_id in result:
            structure = result[stack_id].structure
            assert structure.get("root"), f"{stack_id} missing structure.root"
            assert structure.get("tree"), f"{stack_id} missing structure.tree"

    def test_colliding_roots_compute_service_relocations(self) -> None:
        relocations = main_module._service_relocations(("go-plain", "go-fiber"))
        assert relocations == {
            "go-plain": "src/services/go-plain",
            "go-fiber": "src/services/go-fiber",
        }
        # Single owner → untouched.
        assert main_module._service_relocations(("go-plain", "nextjs")) == {}

    def test_nested_roots_compute_service_relocations(self) -> None:
        # typescript-plain root `src` CONTAINS nextjs root `src/frontend`, both
        # typescript — a nested same-language collision exact-root grouping
        # missed (shipped t3-style); both own src/frontend/**/*.ts.
        relocations = main_module._service_relocations(("typescript-plain", "nextjs"))
        assert relocations == {
            "typescript-plain": "src/services/typescript-plain",
            "nextjs": "src/services/nextjs",
        }
        # A nested root of a DIFFERENT language is the language-layer pattern, not
        # a collision: typescript-plain (`src`, .ts) legitimately contains
        # go-plain (`src/backend`, .go) — no overlap, no relocation.
        assert main_module._service_relocations(("typescript-plain", "go-plain")) == {}

    def test_every_shipped_preset_composes_to_disjoint_boundaries(self) -> None:
        # A bad preset must never ship green: for every _presets/*.yaml, the
        # composed scaffold must own disjoint file trees. Real backend services
        # that share a root legitimately relocate to src/services/<id>
        # (hexagonal-product), but a *-plain language layer carries no service —
        # only the language-driven _base/lang config — so relocating one is the
        # redundant-stack smell (shipped t3-style: typescript-plain nested under
        # nextjs, both typescript). Reuses the production collision predicate.
        from cli._resources import templates_dir
        from cli.preset_registry import load_preset_registry
        from cli.stack_registry import (
            _roots_collide,
            load_stack_registry,
            resolve_relocated_profiles,
        )

        td = templates_dir()
        registry = load_stack_registry(td)
        presets = load_preset_registry(td, include_user=False).presets

        for pid, profile in presets.items():
            stacks = tuple(profile.stacks)
            relocations = main_module._service_relocations(stacks)
            relocated_plain = sorted(s for s in relocations if s.endswith("-plain"))
            assert not relocated_plain, (
                f"preset '{pid}': language-layer {relocated_plain} collides and would "
                f"relocate as a service — drop the redundant *-plain (another stack already "
                f"owns that language) or give it a non-src root"
            )
            profiles = resolve_relocated_profiles(registry, stacks)
            roots = [(p.id, (p.structure or {}).get("root", "").rstrip("/")) for p in profiles]
            for index, (id_a, root_a) in enumerate(roots):
                for id_b, root_b in roots[index + 1 :]:
                    lang_a = registry[id_a].language if id_a in registry else ""
                    lang_b = registry[id_b].language if id_b in registry else ""
                    assert not _roots_collide(root_a, lang_a, root_b, lang_b), (
                        f"preset '{pid}': roots {id_a}={root_a!r} and {id_b}={root_b!r} "
                        f"overlap after resolution — ambiguous file_pattern owner"
                    )

    def test_multi_backend_init_relocates_to_services(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = tmp_path / "twoback"
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
                "go-plain",
                "--template",
                "go-fiber",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        relocated = project / "src" / "services" / "go-plain" / "go.mod"
        assert relocated.exists()
        assert 'module "twoback"' in relocated.read_text()
        assert not (project / "src" / "backend" / "go.mod").exists()


# ---------------------------------------------------------------------------
# Generated CI workflow — TASK-609 (render_ci_workflow, modules.cicd-gated)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Generated backend Dockerfiles — TASK-610 (render_dockerfile, backend-only)
# ---------------------------------------------------------------------------


class TestDockerfile:
    def _world(self, *stacks: str):
        return main_module._build_world("claude", tuple(stacks), Path("/tmp/df-probe"))

    def test_backend_language_yields_multi_stage_non_root_skeleton(self) -> None:
        from cli.renderer import render_dockerfile

        out = render_dockerfile("python")
        assert out.count("FROM ") >= 2  # multi-stage: build + runtime
        assert "USER appuser" in out  # non-root
        assert "EXPOSE" in out and "HEALTHCHECK" in out and "CMD" in out

    def test_non_backend_language_yields_nothing(self) -> None:
        from cli.renderer import render_dockerfile

        assert render_dockerfile("flutter-dart-na") == ""

    def test_materialize_writes_only_for_backend_roots(self, tmp_path: Path) -> None:
        from cli._init_helpers import materialize_dockerfiles

        assert materialize_dockerfiles(tmp_path, self._world("django", "nextjs"))
        backend = tmp_path / "src" / "backend" / "Dockerfile"
        assert backend.is_file() and not backend.is_symlink()  # consumer-owned, not a symlink
        assert (tmp_path / "src" / "backend" / ".dockerignore").is_file()
        assert not (tmp_path / "src" / "frontend" / "Dockerfile").exists()  # frontend: static build

    def test_mobile_stack_gets_no_dockerfile(self, tmp_path: Path) -> None:
        from cli._init_helpers import materialize_dockerfiles

        materialize_dockerfiles(tmp_path, self._world("react-native"))
        assert not list(tmp_path.rglob("Dockerfile"))  # flutter/react-native NA

    def test_ci_carries_commented_security_scan_seam(self) -> None:
        from cli.renderer import render_ci_workflow

        out = render_ci_workflow(self._world("django"))
        assert "# security-scan:" in out  # seam, scanner stays an agent skill (Rule 22)
        assert "trivy" not in out.lower() and "grype" not in out.lower()  # nothing inlined

    def test_full_profile_init_emits_backend_dockerfile(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = tmp_path / "withdf"
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
                "--profile",
                "full",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (project / "src" / "backend" / "Dockerfile").exists()

    def test_go_skeleton_builds_all_packages_and_is_write_once(self, tmp_path: Path) -> None:
        # TASK-625: go build must use ./... (works for cmd/api AND root main.go,
        # e.g. go-plain) not the framework-specific ./cmd/api; and the Dockerfile
        # is write-once so cos update keeps the consumer's CMD/entrypoint edits.
        from cli._init_helpers import materialize_dockerfiles
        from cli.renderer import render_dockerfile

        assert "go build -o /out/server ./..." in render_dockerfile("go")
        assert "./cmd/api" not in render_dockerfile("go")
        world = self._world("go")
        assert materialize_dockerfiles(tmp_path, world)
        dockerfile = tmp_path / "src" / "backend" / "Dockerfile"
        dockerfile.write_text("# consumer set the real CMD\n", encoding="utf-8")
        assert materialize_dockerfiles(tmp_path, world) is False  # write-once
        assert dockerfile.read_text(encoding="utf-8") == "# consumer set the real CMD\n"


# ---------------------------------------------------------------------------
# Regen-chain parameterization — TASK-355 (service-scoped glob propagation)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Presets + dry-config — TASK-356 (config-composition.md § Presets)
# ---------------------------------------------------------------------------
