"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    _claude_entrypoint_name,
    cli,
)

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestMaterialize:
    def test_converts_symlinks_to_files(self, runner: CliRunner, initialized_project: Path) -> None:
        # Verify there are symlinks first
        symlink_count = sum(1 for f in initialized_project.rglob("*") if f.is_symlink())
        assert symlink_count > 0, "Init should create symlinks"

        result = runner.invoke(cli, ["materialize", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "Materialized" in result.output

        # Verify no symlinks remain
        remaining_symlinks = sum(1 for f in initialized_project.rglob("*") if f.is_symlink())
        assert remaining_symlinks == 0

    def test_materialized_files_have_content(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        runner.invoke(cli, ["materialize", "-d", str(initialized_project)])
        # After materialize, settings.json should still be readable
        settings = initialized_project / ".claude" / "settings.json"
        assert settings.exists()
        assert settings.stat().st_size > 0


class TestEject:
    def test_eject_removes_coding_os_keeps_user_code(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        user_file = initialized_project / "src" / "app.py"
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text("print('user code')\n", encoding="utf-8")
        user_hash = hashlib.sha256(user_file.read_bytes()).hexdigest()
        assert sum(1 for f in initialized_project.rglob("*") if f.is_symlink()) > 0

        result = runner.invoke(cli, ["eject", "-d", str(initialized_project), "--yes"])
        assert result.exit_code == 0, result.output
        assert "Ejected coding-os" in result.output
        # coding-os wiring removed
        assert sum(1 for f in initialized_project.rglob("*") if f.is_symlink()) == 0
        assert not (initialized_project / ".coding-os").exists()
        assert not (initialized_project / ".coding-os.yaml").exists()
        assert not (initialized_project / "AGENTS.md").exists()
        # user code byte-identical
        assert hashlib.sha256(user_file.read_bytes()).hexdigest() == user_hash

    def test_eject_keeps_entrypoint_the_user_replaced_with_a_real_file(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        entrypoint = initialized_project / _claude_entrypoint_name()
        entrypoint.unlink()
        entrypoint.write_text("my own instructions\n", encoding="utf-8")

        result = runner.invoke(cli, ["eject", "-d", str(initialized_project), "--yes"])
        assert result.exit_code == 0, result.output
        assert entrypoint.read_text(encoding="utf-8") == "my own instructions\n"

    def test_eject_idempotent_noop_on_clean_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["eject", "-d", str(tmp_path), "--yes"])
        assert result.exit_code == 0, result.output
        assert "nothing to eject" in result.output.lower()


class TestInstallResilience:
    @pytest.fixture(scope="class")
    def resilience_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """One shared consumer project — init is the expensive step."""
        project = tmp_path_factory.mktemp("resilience") / "consumer"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            ["init", "--agent", "claude", "-d", str(project), "--no-index", "--no-register"],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        return project

    def test_update_and_sync_roots_resolve_via_resources(self) -> None:
        """update/sync_all must use the importlib-resolved trees (TASK-219),
        not Path(__file__) hops that break under wheels / moved checkouts."""
        import cli.sync_all as sync_module
        import cli.update as update_module
        from cli._resources import data_root

        root = data_root()
        assert root / "core" == update_module.CORE_DIR
        assert root / "adapters" == update_module.ADAPTERS_DIR
        assert root / "templates" == update_module.TEMPLATES_DIR
        assert root / "core" == sync_module.CORE_DIR
        assert root / "adapters" == sync_module.ADAPTERS_DIR

    def test_update_warns_on_core_version_skew_and_restamps(
        self, runner: CliRunner, resilience_project: Path
    ) -> None:
        import json

        stamp = resilience_project / ".coding-os" / "core-version.json"
        stamp.write_text(
            json.dumps({"core_version": "0.0.1", "stamped_at": "2020-01-01T00:00:00+00:00"})
        )
        result = runner.invoke(cli, ["update", "-d", str(resilience_project)])
        assert result.exit_code == 0, result.output
        assert "core drift" in result.output
        assert "0.0.1" in result.output
        assert json.loads(stamp.read_text())["core_version"] != "0.0.1"

    def test_update_keeps_adapter_owned_hooks(self) -> None:
        """The diff must claim the adapter's own hooks, not just the core set.

        Treating them as unknown made `cos update` delete them — for Codex that
        is every dispatcher, i.e. its whole hook-parity mechanism.
        """
        from cli.update import ADAPTERS_DIR, _build_target_assets

        for agent in ("claude", "codex"):
            owned = ADAPTERS_DIR / agent / "hooks"
            if not owned.is_dir():
                continue
            expected = {
                path.name
                for path in owned.iterdir()
                if path.is_file() and path.suffix in (".sh", ".py")
            }
            assert expected, f"{agent} declares no adapter-owned hooks to guard"

            claimed = {ref.name for ref in _build_target_assets(agent, [])["hooks"]}

            assert expected <= claimed, sorted(expected - claimed)

    def test_update_heals_dangling_symlinks(
        self, runner: CliRunner, resilience_project: Path
    ) -> None:
        """Top-level orphans go via diff removal; nested skill links are
        invisible to _scan_project_assets (SKILL.md.exists() is False on a
        dangling link) and only the leftover-prune pass heals them."""
        ghost_target = resilience_project / ".coding-os" / "ghost-target.sh"
        top_level = resilience_project / ".claude" / "hooks" / "zz-ghost-hook.sh"
        top_level.symlink_to(ghost_target)
        nested_skill_dir = resilience_project / ".claude" / "skills" / "zz-ghost-skill"
        nested_skill_dir.mkdir(parents=True)
        nested = nested_skill_dir / "SKILL.md"
        nested.symlink_to(ghost_target)
        assert top_level.is_symlink() and not top_level.exists()
        assert nested.is_symlink() and not nested.exists()

        result = runner.invoke(cli, ["update", "-d", str(resilience_project)])
        assert result.exit_code == 0, result.output
        assert not top_level.is_symlink()
        assert "Pruned" in result.output
        assert not nested.is_symlink()

    def test_any_command_nudges_on_dangling_links(
        self,
        runner: CliRunner,
        resilience_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The group-level probe fires for any command run inside the project."""
        dangling = resilience_project / ".claude" / "rules" / "zz-ghost-rule.md"
        dangling.symlink_to(resilience_project / "missing-rule.md")
        monkeypatch.chdir(resilience_project)

        result = runner.invoke(cli, ["update", "-d", str(resilience_project), "--dry-run"])
        assert "cos sync-doctor --repair" in result.output
        dangling.unlink()

    def test_registry_failure_prints_recovery_hint(
        self,
        runner: CliRunner,
        project_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import cli.registry as registry_module

        def _raise_disk_full(_project: Path):
            raise OSError("disk full")

        monkeypatch.setattr(registry_module, "add_project", _raise_disk_full)
        project_dir.mkdir()
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-d", str(project_dir), "--no-index"]
        )
        assert result.exit_code == 0, result.output
        assert "cos registry add" in result.output

    def test_db_init_failure_prints_recovery_hint(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import subprocess

        real_run = subprocess.run

        def _fail_init_db(args, **kwargs):
            if isinstance(args, list) and any("init_db" in str(arg) for arg in args):
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")
            return real_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _fail_init_db)
        project = tmp_path / "dbfail"
        project.mkdir()
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-d", str(project), "--no-index", "--no-register"]
        )
        assert result.exit_code != 0
        assert "uv sync --extra rag" in result.output


class TestLanguageLayer:
    def _registry(self):
        from cli._resources import templates_dir
        from cli.stack_registry import load_stack_registry

        return load_stack_registry(templates_dir())

    def test_every_stack_declares_language_and_validates(self) -> None:
        result = self._registry()
        assert list(result.warnings) == []
        for stack_id in result:
            assert result[stack_id].language, f"{stack_id} missing language"

    def test_discovery_groups_by_language(self) -> None:
        from cli.stack_registry import group_stacks_by_language

        result = self._registry()
        profiles = {sid: result[sid] for sid in result}
        groups = group_stacks_by_language(profiles)
        go_ids = [p.id for p in groups["go"]]
        assert "go-plain" in go_ids and "go-fiber" in go_ids

    def test_bare_language_resolves_to_plain_stack_deterministically(self) -> None:
        from cli.stack_registry import plain_stack_by_language

        result = self._registry()
        profiles = {sid: result[sid] for sid in result}
        plain = plain_stack_by_language(profiles)
        assert plain["go"] == "go-plain"  # explicit -plain wins over the chi 'go' stack
        assert plain["python"] == "python"  # pre-convention fallback
        assert plain["typescript"] == "typescript-plain"

    @staticmethod
    def _write_stack(root: Path, stack_id: str, body: str) -> None:
        d = root / stack_id
        d.mkdir()
        (d / "stack.yaml").write_text(body, encoding="utf-8")

    def test_extends_merges_parent_substitutions(self, tmp_path: Path) -> None:
        from cli.stack_registry import load_stack_registry

        self._write_stack(
            tmp_path,
            "parent",
            "version: 1\nid: parent\nlanguage: go\nlabel: P\ncategory: library\n"
            "substitutions: {A: from-parent, B: from-parent}\nskills: [s-parent]\n",
        )
        self._write_stack(
            tmp_path,
            "child",
            "version: 1\nid: child\nlanguage: go\nlabel: C\ncategory: library\n"
            "extends: parent\nsubstitutions: {B: from-child}\nskills: [s-child]\n",
        )
        result = load_stack_registry(tmp_path)
        child = result["child"]
        assert child.substitutions == {"A": "from-parent", "B": "from-child"}
        assert child.skills == ("s-parent", "s-child")

    def test_extends_cycle_skips_with_warning(self, tmp_path: Path) -> None:
        from cli.stack_registry import load_stack_registry

        self._write_stack(
            tmp_path,
            "alpha",
            "version: 1\nid: alpha\nlanguage: go\nlabel: A\ncategory: library\nextends: beta\n",
        )
        self._write_stack(
            tmp_path,
            "beta",
            "version: 1\nid: beta\nlanguage: go\nlabel: B\ncategory: library\nextends: alpha\n",
        )
        result = load_stack_registry(tmp_path)
        assert "alpha" not in result and "beta" not in result
        assert any("cycle" in w for w in result.warnings)

    def test_plain_stacks_scaffold_runnable_skeletons(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = tmp_path / "plainproj"
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
                "typescript-plain",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        go_mod = project / "src" / "backend" / "go.mod"
        assert go_mod.exists()
        # Quoted because the template must parse before substitution (TASK-890);
        # Go normalises it away on the project's first `go mod tidy`.
        assert 'module "plainproj"' in go_mod.read_text()
        assert (project / "tsconfig.json").exists()
        index_ts = project / "src" / "index.ts"
        assert index_ts.exists()
        assert "{{PROJECT_NAME}}" not in index_ts.read_text()
