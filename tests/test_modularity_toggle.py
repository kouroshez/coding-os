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
