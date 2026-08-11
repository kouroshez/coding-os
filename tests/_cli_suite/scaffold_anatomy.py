"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

from pathlib import Path

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
