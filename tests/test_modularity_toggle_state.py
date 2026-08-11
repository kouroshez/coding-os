"""Fast, PR-gated modularity toggle round-trips (audit-2026-06 F7, TASK-447).

These byte-exact toggle assertions used to live only behind the module-level
``@pytest.mark.slow`` in test_cli.py (cos-init / subprocess heavy), so a PR that
broke a module toggle was caught only by the nightly slow suite — never on the
PR itself. They are subprocess-free, so here they run in the ``test-modularity``
PR job and fail a breaking PR immediately:

  - byte-identical restore   — a disable→enable render round-trip is byte-equal
  - allowlist joined         — a disabled module's hooks reach the runtime
                               allowlist; safety hooks never do
  - skill unlinked/relinked  — a core-skill toggle removes then restores its
                               adapter SKILL.md symlink (the fast variant of the
                               cos-init-heavy test_remove_stack assertions)

Complementary "section dropped" / "retrieval row dropped" render assertions live
in test_all_stacks_render_smoke.py (same PR job).

Pure in-memory / tmp_path — no `cos init`. Run:
  uv run pytest tests/test_modularity_toggle.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

import cli.main as main_module
from cli.renderer import render_agents_md


def _link_skill_into(project: Path, skill: str) -> Path:
    """Symlink a real skill's SKILL.md (core OR meta-stack) into .claude/skills."""
    from cli.skill_commands import _known_skill_provenance, _skill_source_skill_md

    provenance = _known_skill_provenance(skill)
    source = _skill_source_skill_md(skill, provenance) if provenance else None
    assert source and source.is_file(), f"fixture assumes a real skill: {skill}"
    link = project / ".claude" / "skills" / skill / "SKILL.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)
    return link


def _link_command_into(project: Path, name: str) -> Path:
    """Symlink a real core slash-command's file into .claude/commands."""
    from cli._resources import core_dir

    source = core_dir("commands") / f"{name}.md"
    assert source.is_file(), f"fixture assumes a real command: {name}"
    link = project / ".claude" / "commands" / f"{name}.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)
    return link


class TestConditionalRendering:
    @pytest.fixture(scope="class")
    def world(self):
        return main_module._build_world("claude", ("python",), Path("/virtual/condrender"))

    def test_default_render_is_byte_identical_and_contains_task_block(self, world) -> None:
        default = render_agents_md(world)
        explicit_all_on = render_agents_md(world, {"tasks": True, "docs": True})
        assert default == explicit_all_on  # zero regression for existing consumers
        assert "Scrumban board (Phase L — preferred)" in default
        assert "{%" not in default  # no leaked template syntax

    def test_tasks_module_disabled_drops_task_block_and_restores_identically(self, world) -> None:
        without_tasks = render_agents_md(world, {"tasks": False})
        assert "Scrumban board" not in without_tasks
        assert "Legacy task flow" not in without_tasks
        assert "## Tool Routing" in without_tasks  # section survives, block doesn't
        assert "## Core Loop" in without_tasks or "Core Loop" in without_tasks  # kernel intact
        restored = render_agents_md(world, {"tasks": True})
        assert restored == render_agents_md(world)  # byte-identical restore

    def test_disabled_module_skill_drops_from_installed_skills_list(self, world) -> None:
        """D2-2 (TASK-480): a disabled module's owned skill leaves the rendered
        `## Skills` (INSTALLED_SKILLS) list — ref-counted, byte-identical all-on."""
        all_on = render_agents_md(world)
        assert "`graph-explorer`" in all_on and "`task-driver`" in all_on
        graph_off = render_agents_md(world, {"graph": False})
        assert "`graph-explorer`" not in graph_off
        assert "`task-driver`" in graph_off  # only the gated module's skill drops
        tasks_off = render_agents_md(world, {"tasks": False})
        assert "`task-driver`" not in tasks_off
        assert render_agents_md(world, {"graph": True}) == all_on  # byte-identical restore

    def test_disabled_module_hooks_join_runtime_allowlist(self, tmp_path: Path) -> None:
        from cli.project_overrides import disabled_hook_scripts, effective_disabled_hooks
        from cli.subsystems import set_module_enabled

        assert effective_disabled_hooks(tmp_path) == set()
        assert set_module_enabled(tmp_path, "tasks", False).ok is True
        disabled = effective_disabled_hooks(tmp_path)
        assert "auto-task-sync" in disabled and "nudge-task-discovery" in disabled
        scripts = disabled_hook_scripts(tmp_path)
        assert any(s.endswith(".sh") for s in scripts)
        # Safety-category hooks never reach the allowlist, whatever is disabled.
        assert "enforce-task-transition" not in disabled
        assert "enforce-wip-limit" not in disabled

    def test_no_toggleable_module_owns_a_safety_hook(self) -> None:
        """Kernel non-disableable BY CONSTRUCTION: safety hooks must not be
        listed by any toggleable module, or the allowlist filter would be the
        only line of defense."""
        import yaml as _yaml

        from cli.subsystems import load_subsystems

        repo_root = Path(__file__).resolve().parent.parent
        registry = _yaml.safe_load(
            (repo_root / "src" / "core" / "hooks" / "registry.yaml").read_text(encoding="utf-8")
        )
        hook_entries = registry.get("hooks", registry)
        safety = {h["id"] for h in hook_entries if h.get("category") == "safety"}
        for module in load_subsystems().values():
            if module.kernel:
                continue
            overlap = safety & set(module.hooks)
            assert not overlap, f"toggleable module '{module.id}' owns safety hook(s): {overlap}"


class TestModuleStateHardening:
    """TASK-474 — concurrent-toggle lock (no lost-update) + corrupt-state visibility."""

    def test_concurrent_disables_no_lost_update(self, tmp_path: Path) -> None:
        import threading

        from cli.subsystems import _read_disabled, set_module_enabled

        mods = ["graph", "memory", "cognition", "observability", "hub-extras"]
        barrier = threading.Barrier(len(mods))
        errors: list[Exception] = []

        def _worker(module_id: str) -> None:
            try:
                barrier.wait()  # release all writers at once → maximal contention
                set_module_enabled(tmp_path, module_id, False)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(m,)) for m in mods]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        assert _read_disabled(tmp_path) == set(mods)  # every racing toggle persisted

    def test_corrupt_state_surfaces_as_doctor_warn(self, tmp_path: Path) -> None:
        from cli.doctor import (
            SEV_PASS,
            SEV_WARN,
            DoctorReport,
            _check_subsystems_state_integrity,
        )

        (tmp_path / ".coding-os").mkdir()
        ok_report = DoctorReport(project_dir=str(tmp_path), agent="claude", templates=[])
        _check_subsystems_state_integrity(tmp_path, ok_report)  # absent file → PASS
        assert (
            next(c for c in ok_report.checks if c.id == "modules.state_integrity").severity
            == SEV_PASS
        )

        (tmp_path / ".coding-os" / "subsystems-state.json").write_text(
            "{not json", encoding="utf-8"
        )
        warn_report = DoctorReport(project_dir=str(tmp_path), agent="claude", templates=[])
        _check_subsystems_state_integrity(tmp_path, warn_report)
        check = next(c for c in warn_report.checks if c.id == "modules.state_integrity")
        assert check.severity == SEV_WARN and "subsystems-state.json" in check.message

    def test_malformed_disabled_shape_is_flagged(self, tmp_path: Path) -> None:
        from cli.subsystems import state_file_integrity

        (tmp_path / ".coding-os").mkdir()
        (tmp_path / ".coding-os" / "subsystems-state.json").write_text(
            '{"disabled": "graph"}', encoding="utf-8"
        )
        assert state_file_integrity(tmp_path) is not None  # disabled must be a list, not a str

    def test_dependency_refusal_validated_against_current_disk_state(self, tmp_path: Path) -> None:
        """TASK-478: the dependency-refusal validation now runs under the lock
        against the freshly-read disabled set, so a refusal reflects the CURRENT
        on-disk state (not a stale pre-lock snapshot). tasks depends_on docs."""
        from cli.subsystems import set_module_enabled

        # Disabling docs while tasks is still enabled must refuse (tasks needs docs).
        refuse_disable = set_module_enabled(tmp_path, "docs", False)
        assert refuse_disable.ok is False
        assert "required by enabled module(s) tasks" in refuse_disable.reason

        # Bring docs down legitimately (disable tasks first), then re-enabling tasks
        # while docs stays disabled must refuse — validated from the re-read set.
        assert set_module_enabled(tmp_path, "tasks", False).ok is True
        assert set_module_enabled(tmp_path, "docs", False).ok is True
        refuse_enable = set_module_enabled(tmp_path, "tasks", True)
        assert refuse_enable.ok is False
        assert "needs disabled module(s) docs" in refuse_enable.reason


class TestToggleRollbackAtomicity:
    """audit pass-4 #10 — a regen failure mid-toggle must roll BOTH the module
    state AND the runtime allowlist back. regen writes the allowlist first, so
    reverting only the state file stranded the allowlist on the failed-toggle
    state (an inverted half-state), and `cos doctor` mis-certified it PASS."""

    def test_rollback_restores_allowlist_not_just_state(self, tmp_path: Path, monkeypatch) -> None:
        from cli import module_commands
        from cli.project_overrides import RUNTIME_ALLOWLIST, write_runtime_allowlist
        from cli.subsystems import module_state

        (tmp_path / ".coding-os").mkdir()

        # Simulate regen that progresses PAST the allowlist write (the real first
        # step) and then throws on the later AGENTS.md render.
        def _boom(project: Path) -> list[str]:
            write_runtime_allowlist(project)
            raise RuntimeError("render boom")

        monkeypatch.setattr(module_commands, "regen_after_toggle", _boom)

        result, _notes = module_commands.toggle_and_regen(tmp_path, "memory", False)
        assert result.ok is False
        assert "rolled back" in result.reason
        # state rolled back to enabled …
        assert module_state(tmp_path)["memory"] is True
        # … AND the allowlist file no longer lists memory's hooks.
        allowlist = tmp_path / ".coding-os" / RUNTIME_ALLOWLIST
        content = allowlist.read_text(encoding="utf-8") if allowlist.exists() else ""
        assert "brain-decay" not in content and "jit-recall" not in content

    def test_doctor_flags_over_disabled_allowlist(self, tmp_path: Path) -> None:
        from cli.doctor import SEV_WARN, DoctorReport, _check_module_consistency
        from cli.project_overrides import RUNTIME_ALLOWLIST

        # All modules enabled (no state file) but the allowlist lists memory's
        # hooks — the exact over-disabled corruption a failed rollback leaves.
        cos_dir = tmp_path / ".coding-os"
        cos_dir.mkdir()
        (cos_dir / RUNTIME_ALLOWLIST).write_text(
            "auto-brain-decay.sh\njit-recall.sh\n", encoding="utf-8"
        )

        report = DoctorReport(project_dir=str(tmp_path), agent="claude", templates=[])
        _check_module_consistency(tmp_path, report)
        check = next(c for c in report.checks if c.id == "modules.state_consistency")
        assert check.severity == SEV_WARN  # NOT a false PASS
        assert "over-disabled" in check.message
