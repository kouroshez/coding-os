"""cos subsystems — the cos init --disable-module / --enable-module surface.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


class TestSubsystemsInitFlags:
    def test_init_disable_module_writes_state(self, runner: CliRunner, project_dir: Path) -> None:
        """`cos init --disable-module` disables modules in the scaffold (TASK-421)."""
        from cli.subsystems import module_state

        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "graph",
                "--disable-module",
                "memory",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        state = module_state(project_dir)
        assert state["graph"] is False and state["memory"] is False
        assert state["kernel"] is True  # untouched

    def test_init_enable_module_escapes_profile_union(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """--enable-module keeps a module the profile disabled (the union escape)."""
        from cli.subsystems import load_profiles, load_subsystems, module_state, resolve_profile

        modules = load_subsystems()
        _, default_name = load_profiles()
        candidates = [m for m in resolve_profile(default_name) if not modules[m].hidden]
        assert candidates, "default profile expected to disable at least one visible module"
        target = candidates[0]

        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--enable-module",
                target,
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        state = module_state(project_dir)
        assert state[target] is True, f"{target} must survive the profile union"
        for dep in modules[target].depends_on:
            assert state[dep] is True, f"dependency {dep} must ride along with {target}"

    def test_init_enable_module_conflicts_with_explicit_disable(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "graph",
                "--enable-module",
                "graph",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 2
        assert "both --enable-module and --disable-module" in result.output

    def test_init_disable_module_writes_runtime_allowlist(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """SI-1 (TASK-439): init writes .coding-os/disabled-hook-scripts via write_runtime_allowlist."""
        from cli.project_overrides import disabled_hook_scripts

        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "graph",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        allowlist = project_dir / ".coding-os" / "disabled-hook-scripts"
        assert allowlist.exists(), "init must route through write_runtime_allowlist (SI-1)"
        expected = disabled_hook_scripts(project_dir)
        actual = {ln.strip() for ln in allowlist.read_text().splitlines() if ln.strip()}
        assert expected, "graph module should own disabled hooks"
        assert actual == expected, f"allowlist {actual} != module state {expected}"

    def test_init_disable_module_unlinks_owned_skill_and_gates_agents_md(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """D2-1/D2-2 (TASK-480): a module disabled at init sheds its owned core
        skill from BOTH the adapter skills dir AND the rendered AGENTS.md skills
        list — init reaches the skill-parity `cos module disable` has at runtime."""
        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "graph",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        # D2-1: the graph-owned core skill must NOT be linked in the adapter dir.
        skill_link = project_dir / ".claude" / "skills" / "graph-explorer" / "SKILL.md"
        assert not skill_link.exists(), "graph-explorer must be unlinked when graph is off at init"
        # D2-2: it must also be gone from the AGENTS.md ## Skills list.
        agents_md = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
        assert "`graph-explorer`" not in agents_md, "disabled module's skill leaked into AGENTS.md"

    def test_init_disable_module_unlinks_owned_commands(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """D1-1 (TASK-481): a module disabled at init sheds its owned slash-commands
        from the adapter commands dir; always-on commands survive."""
        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "tasks",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        commands_dir = project_dir / ".claude" / "commands"
        for shed in ("board.md", "daily.md", "retro.md", "task.md"):
            assert not (commands_dir / shed).exists(), f"{shed} must be unlinked when tasks off"
        # An always-on (kernel-level) command survives the tasks disable.
        assert (commands_dir / "classify.md").exists(), "kernel command wrongly shed"

    def test_init_disable_module_unlinks_owned_rule(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """TASK-811: a module disabled at init sheds its owned core rule from the
        adapter rules dir; cross-cutting (unowned) rules survive."""
        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "memory",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        rules_dir = project_dir / ".claude" / "rules"
        assert not (rules_dir / "memory.md").exists(), "memory.md must be unlinked when memory off"
        # A cross-cutting (unowned) rule survives the memory disable.
        assert (rules_dir / "git-workflow.md").exists(), "cross-cutting rule wrongly shed"

    def test_init_disable_module_rejects_unknown(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "no-such-module",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 2
        assert "unknown module" in result.output.lower()

    def test_init_disable_module_rejects_kernel(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--disable-module",
                "kernel",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 2
        assert "kernel" in result.output.lower()
