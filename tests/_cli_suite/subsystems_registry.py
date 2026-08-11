"""cos subsystems — registry parsing, hook ownership, and the toggle state file.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

from pathlib import Path


class TestSubsystemsRegistry:
    def test_registry_parses_with_kernel_and_dependencies(self) -> None:
        from cli.subsystems import load_subsystems

        modules = load_subsystems()
        assert {"kernel", "docs", "tasks", "graph", "memory", "hub-extras"} <= set(modules)
        assert modules["kernel"].kernel is True
        assert "docs" in modules["tasks"].depends_on
        for module in modules.values():
            assert module.label and module.id

    def test_every_declared_hook_exists_in_hook_registry(self) -> None:
        """subsystems.yaml is data — this pins it to the hook SSOT."""
        import yaml as _yaml

        from cli.subsystems import load_subsystems

        repo_root = Path(__file__).resolve().parent.parent.parent
        registry = _yaml.safe_load(
            (repo_root / "src" / "core" / "hooks" / "registry.yaml").read_text(encoding="utf-8")
        )
        hook_entries = registry.get("hooks", registry)
        known = {h["id"] for h in hook_entries}
        for module in load_subsystems().values():
            unknown = [h for h in module.hooks if h not in known]
            assert not unknown, f"module '{module.id}' references unknown hook(s): {unknown}"

    def test_every_registry_hook_has_exactly_one_module_owner(self) -> None:
        """Audit F9 invariant: no orphan hooks, no double-claims. Every hook in
        the registry is owned by exactly one subsystems.yaml module so a new
        hook cannot silently land untoggleable."""
        from collections import Counter

        import yaml as _yaml

        from cli.subsystems import load_subsystems

        repo_root = Path(__file__).resolve().parent.parent.parent
        registry = _yaml.safe_load(
            (repo_root / "src" / "core" / "hooks" / "registry.yaml").read_text(encoding="utf-8")
        )
        registry_ids = {h["id"] for h in registry.get("hooks", [])}
        owners: Counter[str] = Counter()
        for module in load_subsystems().values():
            owners.update(module.hooks)

        orphans = sorted(registry_ids - set(owners))
        duplicates = sorted(h for h, n in owners.items() if n > 1)
        assert not orphans, f"registry hooks with no module owner (F9): {orphans}"
        assert not duplicates, f"hooks claimed by more than one module: {duplicates}"

    def test_no_state_file_means_all_enabled_and_reader_never_writes(self, tmp_path: Path) -> None:
        from cli.subsystems import module_state

        state = module_state(tmp_path)
        assert state and all(state.values())
        assert not (tmp_path / ".coding-os" / "subsystems-state.json").exists()

    def test_kernel_disable_refused_naming_module(self, tmp_path: Path) -> None:
        from cli.subsystems import set_module_enabled

        result = set_module_enabled(tmp_path, "kernel", False)
        assert result.ok is False
        assert "kernel" in result.reason and "cannot be disabled" in result.reason

    def test_dependency_chain_refusals_both_directions(self, tmp_path: Path) -> None:
        from cli.subsystems import module_state, set_module_enabled

        # Disable docs while tasks (dependent) is enabled → refusal names the dependent.
        blocked = set_module_enabled(tmp_path, "docs", False)
        assert blocked.ok is False
        assert "required by enabled module(s) tasks" in blocked.reason

        # Disable the dependent first, then docs — both succeed.
        assert set_module_enabled(tmp_path, "tasks", False).ok is True
        assert set_module_enabled(tmp_path, "docs", False).ok is True

        # Re-enabling tasks while docs is disabled → refusal names the missing dependency.
        reblocked = set_module_enabled(tmp_path, "tasks", True)
        assert reblocked.ok is False
        assert "needs disabled module(s) docs" in reblocked.reason

        # Enable in dependency order — green; state reflects it.
        assert set_module_enabled(tmp_path, "docs", True).ok is True
        assert set_module_enabled(tmp_path, "tasks", True).ok is True
        assert all(module_state(tmp_path).values())

    def test_toggle_creates_state_file_lazily_and_atomically(self, tmp_path: Path) -> None:
        import json as _json

        from cli.subsystems import set_module_enabled

        result = set_module_enabled(tmp_path, "memory", False)
        assert result.ok is True
        state_file = tmp_path / ".coding-os" / "subsystems-state.json"
        assert result.state_path == state_file and state_file.exists()
        data = _json.loads(state_file.read_text(encoding="utf-8"))
        assert data == {"version": 1, "disabled": ["memory"]}
        assert not state_file.with_suffix(".json.tmp").exists()  # atomic replace

    def test_overlay_module_merges_without_forking_core(self, tmp_path: Path, monkeypatch) -> None:
        """TASK-818: an out-of-core $COS_USER_MODULES_DIR/*.yaml module merges into
        the registry (core wins on id collision, kernel claims refused) so a plugin
        author registers a toggleable module without forking the kernel."""
        from cli.subsystems import load_subsystems

        overlay = tmp_path / "modules.d"
        overlay.mkdir()
        (overlay / "redis.yaml").write_text(
            "modules:\n"
            "  - id: redis-cache\n"
            "    label: Redis cache helpers\n"
            "    hooks: []\n"
            "    tools: []\n"
            "    depends_on: [docs]\n",
            encoding="utf-8",
        )
        (overlay / "evil.yaml").write_text(
            "modules:\n  - id: docs\n    label: HIJACKED\n    kernel: true\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("COS_USER_MODULES_DIR", str(overlay))
        modules = load_subsystems()
        assert "redis-cache" in modules, "overlay module not merged"
        assert modules["redis-cache"].label == "Redis cache helpers"
        assert modules["redis-cache"].depends_on == ("docs",), "overlay dep to a core module lost"
        assert modules["docs"].label != "HIJACKED", "overlay shadowed a core module (core must win)"

    def test_unknown_module_refused_listing_available(self, tmp_path: Path) -> None:
        from cli.subsystems import set_module_enabled

        result = set_module_enabled(tmp_path, "no-such", False)
        assert result.ok is False
        assert "unknown module" in result.reason and "docs" in result.reason
