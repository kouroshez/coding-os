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
from cli._resources import core_dir
from cli.renderer import render_agents_md


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


def test_core_skill_toggle_unlinks_and_relinks_symlink(tmp_path: Path) -> None:
    """Disabling a core skill removes its adapter SKILL.md symlink and records it
    in disabled_skills; re-enabling restores the symlink to the same source. The
    fast variant of test_remove_stack's cos-init-heavy unlink assertions."""
    import yaml

    from cli.skill_commands import set_project_skill

    skill = "incident-response"
    source = core_dir("skills") / skill / "SKILL.md"
    assert source.is_file(), "fixture assumes a real core skill"

    (tmp_path / ".coding-os.yaml").write_text("templates: []\n", encoding="utf-8")
    link = tmp_path / ".claude" / "skills" / skill / "SKILL.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(source)
    assert link.is_symlink()

    off = set_project_skill(tmp_path, skill, enabled=False)
    assert off["changed"] is True
    assert not link.exists(), "disable must unlink the SKILL.md symlink"
    cfg_off = yaml.safe_load((tmp_path / ".coding-os.yaml").read_text(encoding="utf-8"))
    assert skill in (cfg_off.get("disabled_skills") or [])

    on = set_project_skill(tmp_path, skill, enabled=True)
    assert on["changed"] is True
    assert link.is_symlink() and link.resolve() == source.resolve()
    cfg_on = yaml.safe_load((tmp_path / ".coding-os.yaml").read_text(encoding="utf-8"))
    assert skill not in (cfg_on.get("disabled_skills") or [])


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


class TestModuleSkillCascade:
    """TASK-475 — disabling a module unlinks its owned skills (ref-counted,
    override-aware); re-enabling relinks them except the user's explicit opt-outs."""

    def _project(self, tmp_path: Path) -> Path:
        (tmp_path / ".coding-os.yaml").write_text("templates: []\n", encoding="utf-8")
        # An installed adapter skills dir must exist for relinks to land (the
        # cascade only touches dirs `_installed_adapter_skills_dirs` reports).
        (tmp_path / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
        return tmp_path

    def test_disable_unlinks_owned_skills(self, tmp_path: Path) -> None:
        from cli.skill_commands import cascade_module_skills

        project = self._project(tmp_path)
        links = {s: _link_skill_into(project, s) for s in ("graph-explorer", "graph-os-authoring")}

        out = cascade_module_skills(project, "graph", enabled=False)

        assert set(out["unlinked"]) == {"graph-explorer", "graph-os-authoring"}
        for link in links.values():
            assert not link.exists(), "owned skill symlink must be unlinked"

    def test_keep_skills_leaves_links(self, tmp_path: Path) -> None:
        from cli.skill_commands import cascade_module_skills

        project = self._project(tmp_path)
        link = _link_skill_into(project, "graph-explorer")

        out = cascade_module_skills(project, "graph", enabled=False, keep_skills=True)

        assert out["unlinked"] == [] and "graph-explorer" in out["kept"]
        assert link.is_symlink(), "--keep-skills must leave the link in place"

    def test_shared_skill_survives_when_other_owner_enabled(self, tmp_path: Path) -> None:
        """Ref-count: a skill another ENABLED module also owns is never unlinked."""
        from cli.skill_commands import cascade_module_skills
        from cli.subsystems import Module

        project = self._project(tmp_path)
        shared = _link_skill_into(project, "graph-explorer")
        solo = _link_skill_into(project, "graph-os-authoring")
        synthetic = {
            "graph": Module(id="graph", label="g", skills=("graph-explorer", "graph-os-authoring")),
            "twin": Module(id="twin", label="t", skills=("graph-explorer",)),
        }

        out = cascade_module_skills(project, "graph", enabled=False, modules=synthetic)

        assert out["unlinked"] == ["graph-os-authoring"]
        assert "graph-explorer" in out["kept"]
        assert shared.is_symlink(), "shared skill (twin still enabled) must survive"
        assert not solo.exists(), "solely-graph skill must be unlinked"

    def test_reenable_relinks_except_user_disabled(self, tmp_path: Path) -> None:
        import yaml

        from cli.skill_commands import cascade_module_skills

        project = self._project(tmp_path)
        # User explicitly opted graph-explorer out; module re-enable must respect it.
        (project / ".coding-os.yaml").write_text(
            "templates: []\ndisabled_skills: [graph-explorer]\n", encoding="utf-8"
        )

        out = cascade_module_skills(project, "graph", enabled=True)

        assert "graph-os-authoring" in out["linked"]
        assert "graph-explorer" in out["kept"]  # user override outranks the relink
        relinked = project / ".claude" / "skills" / "graph-os-authoring" / "SKILL.md"
        overridden = project / ".claude" / "skills" / "graph-explorer" / "SKILL.md"
        assert relinked.is_symlink()
        assert not overridden.exists()
        # disabled_skills is the user's list — the cascade must not have touched it.
        cfg = yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert cfg["disabled_skills"] == ["graph-explorer"]

    def test_kernel_skills_never_module_owned(self) -> None:
        from cli.subsystems import load_subsystems

        always_on = {"clean-code", "thinking_os", "search"}
        for module in load_subsystems().values():
            overlap = always_on & set(module.skills)
            assert not overlap, f"module '{module.id}' owns always-on skill(s): {overlap}"

    def test_every_owned_skill_resolves(self) -> None:
        from cli.skill_commands import _known_skill_provenance
        from cli.subsystems import load_subsystems

        for module in load_subsystems().values():
            for name in module.skills:
                assert _known_skill_provenance(name) is not None, (
                    f"module '{module.id}' owns unresolvable skill '{name}'"
                )

    def test_doctor_flags_module_skill_drift(self, tmp_path: Path) -> None:
        from cli.doctor import SEV_PASS, SEV_WARN, DoctorReport, _check_module_skill_drift
        from cli.subsystems import set_module_enabled

        project = self._project(tmp_path)
        _link_skill_into(project, "graph-explorer")

        ok_report = DoctorReport(project_dir=str(project), agent="claude", templates=[])
        _check_module_skill_drift(project, ok_report)
        assert next(c for c in ok_report.checks if c.id == "modules.skill_drift").severity == SEV_PASS

        assert set_module_enabled(project, "graph", False).ok is True  # skill stays linked
        drift_report = DoctorReport(project_dir=str(project), agent="claude", templates=[])
        _check_module_skill_drift(project, drift_report)
        check = next(c for c in drift_report.checks if c.id == "modules.skill_drift")
        assert check.severity == SEV_WARN and "graph-explorer" in check.message


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
