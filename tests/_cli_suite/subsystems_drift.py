"""cos subsystems — doctor drift detection and the toggle-and-regen sweep.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


class TestSubsystemsDrift:
    def test_doctor_detects_disabled_hook_scripts_drift(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """modules.state_consistency (TASK-439): doctor WARNs when the allowlist drifts from state."""
        from cli.doctor import DoctorReport, _check_module_consistency

        project_dir.mkdir()
        runner.invoke(
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
        (project_dir / ".coding-os" / "disabled-hook-scripts").unlink()
        report = DoctorReport(project_dir=str(project_dir), agent=None, templates=[])
        _check_module_consistency(project_dir, report)
        consistency = [c for c in report.checks if c.id == "modules.state_consistency"]
        assert consistency, "module consistency check missing"
        assert consistency[0].severity == "WARN", consistency[0].message

    def test_doctor_detects_module_rule_drift(self, runner: CliRunner, project_dir: Path) -> None:
        """modules.rule_drift (TASK-812): WARN when a disabled module's rule is still linked."""
        import json as _json

        from cli.doctor import DoctorReport, _check_module_rule_drift

        project_dir.mkdir()
        runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--profile",
                "full",
                "--no-index",
                "--no-register",
            ],
        )
        # memory.md linked at init (full profile); disable memory in state only
        # (no cascade) to simulate a residue and assert the check flags it.
        state = project_dir / ".coding-os" / "subsystems-state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(_json.dumps({"version": 1, "disabled": ["memory"]}), encoding="utf-8")
        report = DoctorReport(project_dir=str(project_dir), agent=None, templates=[])
        _check_module_rule_drift(project_dir, report)
        rule_drift = [c for c in report.checks if c.id == "modules.rule_drift"]
        assert rule_drift, "rule drift check missing"
        assert rule_drift[0].severity == "WARN", rule_drift[0].message
        assert "memory.md" in rule_drift[0].message

    def test_doctor_detects_module_doc_drift(self, runner: CliRunner, project_dir: Path) -> None:
        """modules.doc_drift (TASK-812/813): WARN when a disabled module's tagged
        scaffold doc is still present — mapped via the tagged SOURCE, since the
        consumer copy has its `| module:` tag stripped at init."""
        import json as _json

        from cli.doctor import DoctorReport, _check_module_doc_drift

        project_dir.mkdir()
        runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--profile",
                "full",
                "--no-index",
                "--no-register",
            ],
        )
        # tasks enabled at init → task-lifecycle.md (| module:tasks) materialized
        # (tag stripped in the copy). Disable tasks in state and assert the map.
        state = project_dir / ".coding-os" / "subsystems-state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(_json.dumps({"version": 1, "disabled": ["tasks"]}), encoding="utf-8")
        report = DoctorReport(project_dir=str(project_dir), agent=None, templates=[])
        _check_module_doc_drift(project_dir, report)
        doc_drift = [c for c in report.checks if c.id == "modules.doc_drift"]
        assert doc_drift, "doc drift check missing"
        assert doc_drift[0].severity == "WARN", doc_drift[0].message
        assert "task-lifecycle.md" in doc_drift[0].message

    def test_module_doc_sync_prunes_and_restores(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """TASK-813: disable backs up + prunes a module's tagged docs; enable restores them."""
        from cli.module_commands import sync_module_docs

        project_dir.mkdir()
        runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--profile",
                "full",
                "--no-index",
                "--no-register",
            ],
        )
        doc = project_dir / "docs" / "governance" / "task-lifecycle.md"
        assert doc.is_file(), "task-lifecycle.md should be materialized at full init"
        backup = (
            project_dir / ".coding-os" / "pruned-docs" / "docs" / "governance" / "task-lifecycle.md"
        )
        out = sync_module_docs(project_dir, (), "tasks", enabled=False)
        assert "docs/governance/task-lifecycle.md" in out["pruned"]
        assert not doc.exists(), "doc must be pruned on disable"
        assert backup.is_file(), "doc must be backed up, never destroyed"
        out = sync_module_docs(project_dir, (), "tasks", enabled=True)
        assert "docs/governance/task-lifecycle.md" in out["restored"]
        assert doc.is_file(), "doc must be restored on enable"

    def test_toggle_and_regen_sheds_all_surfaces_at_once(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """TASK-816: one live toggle_and_regen(disable) sheds allowlist + AGENTS.md
        block + skill symlink + command symlink + tagged doc together — pins the
        orchestrator so dropping any cascade line fails CI."""
        from cli.module_commands import toggle_and_regen
        from cli.project_overrides import disabled_hook_scripts

        project_dir.mkdir()
        runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--profile",
                "full",
                "--no-index",
                "--no-register",
            ],
        )
        skill = project_dir / ".claude" / "skills" / "task-driver" / "SKILL.md"
        command = project_dir / ".claude" / "commands" / "board.md"
        doc = project_dir / "docs" / "governance" / "task-lifecycle.md"
        agents = project_dir / "AGENTS.md"
        assert skill.exists() and command.exists() and doc.exists(), (
            "tasks not fully linked at init"
        )
        assert "## Task Logging" in agents.read_text(encoding="utf-8")

        result, _notes = toggle_and_regen(project_dir, "tasks", enabled=False)
        assert result.ok, result.reason
        assert not skill.exists(), "task-driver skill not unlinked"
        assert not command.exists(), "board command not unlinked"
        assert not doc.exists(), "task-lifecycle doc not pruned"
        assert "## Task Logging" not in agents.read_text(encoding="utf-8"), (
            "AGENTS task block leaked"
        )
        assert any("task" in str(h) for h in disabled_hook_scripts(project_dir)), (
            "tasks hooks not gated"
        )

    def test_toggle_and_regen_logs_refusal(
        self, runner: CliRunner, project_dir: Path, caplog
    ) -> None:
        """TASK-816: a refused toggle emits a queryable warning (scope cli.module)
        so a headless CI/nightly toggle failure is discoverable, not silent."""
        import logging

        from cli.module_commands import toggle_and_regen

        project_dir.mkdir()
        runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project_dir),
                "--profile",
                "full",
                "--no-index",
                "--no-register",
            ],
        )
        with caplog.at_level(logging.WARNING, logger="cli.module"):
            result, _ = toggle_and_regen(project_dir, "docs", enabled=False)  # required by tasks
        assert not result.ok
        assert any(
            "refused" in r.getMessage() and "docs" in r.getMessage() for r in caplog.records
        ), [r.getMessage() for r in caplog.records]

    def test_module_regen_in_meta_repo_preserves_handwritten_agents_md(
        self, tmp_path: Path
    ) -> None:
        """Meta-repo guard (TASK-439): regen_after_toggle never clobbers the hand-written AGENTS.md."""
        from cli.module_commands import regen_after_toggle

        (tmp_path / ".coding-os").mkdir()
        (tmp_path / "src" / "core" / "thinking_os").mkdir(parents=True)
        (tmp_path / "src" / "core" / "thinking_os" / "server.py").write_text("# meta\n")
        (tmp_path / "src" / "cli").mkdir(parents=True)
        (tmp_path / "src" / "cli" / "main.py").write_text("# meta\n")
        (tmp_path / ".coding-os.yaml").write_text("agents: [claude]\n")
        original = "# Hand-written AGENTS.md — preserve me\n"
        (tmp_path / "AGENTS.md").write_text(original)
        notes = regen_after_toggle(tmp_path)
        assert (tmp_path / "AGENTS.md").read_text() == original
        assert any("meta-repo" in n for n in notes), notes
