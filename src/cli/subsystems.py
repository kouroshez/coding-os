"""Subsystem (module) registry loader + per-project toggle state (TASK-349).

src/core/subsystems.yaml declares the toggleable modules (docs, tasks, graph,
memory, hub-extras) and the always-on kernel. Per-project state lives in
$COS_STATE_DIR/subsystems-state.json as {"disabled": [...]} — absent file
means everything enabled (backward compatible); the file is created lazily on
the first toggle, never by readers. Toggle behavior (MCP gating, Config tab,
`cos module` CLI) is TASK-354/357; this module is the data + state SSOT.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from cli._resources import core_dir as _core_dir

logger = logging.getLogger(__name__)

STATE_DIR = ".coding-os"
STATE_FILENAME = "subsystems-state.json"
_SUBSYSTEMS_PATH = _core_dir() / "subsystems.yaml"


@dataclass(frozen=True)
class Module:
    id: str
    label: str
    kernel: bool = False
    hooks: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    # Reserved-but-not-yet-shipped module: kept in the registry so its id stays
    # stable, but suppressed from every toggle surface (no live no-op switch).
    hidden: bool = False


@dataclass(frozen=True)
class ToggleResult:
    ok: bool
    module_id: str
    enabled: bool | None = None
    reason: str = ""
    state_path: Path | None = None


def load_subsystems(path: Path | None = None) -> dict[str, Module]:
    """Parse subsystems.yaml → {module_id: Module}. Raises on structural errors."""
    manifest = path or _SUBSYSTEMS_PATH
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    modules: dict[str, Module] = {}
    for raw in data.get("modules") or []:
        module = Module(
            id=str(raw["id"]),
            label=str(raw.get("label") or raw["id"]),
            kernel=bool(raw.get("kernel", False)),
            hooks=tuple(str(h) for h in raw.get("hooks") or ()),
            tools=tuple(str(t) for t in raw.get("tools") or ()),
            skills=tuple(str(s) for s in raw.get("skills") or ()),
            commands=tuple(str(c) for c in raw.get("commands") or ()),
            depends_on=tuple(str(d) for d in raw.get("depends_on") or ()),
            hidden=bool(raw.get("hidden", False)),
        )
        modules[module.id] = module
    for module in modules.values():
        unknown = [d for d in module.depends_on if d not in modules]
        if unknown:
            raise ValueError(f"module '{module.id}' depends on unknown module(s): {unknown}")
    return modules


def _state_path(project_root: Path) -> Path:
    return Path(project_root) / STATE_DIR / STATE_FILENAME


def _read_disabled(project_root: Path) -> set[str]:
    path = _state_path(project_root)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(x) for x in data.get("disabled") or []}
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("subsystems state unreadable (%s) — treating as all-enabled", exc)
        return set()


def state_file_integrity(project_root: Path) -> str | None:
    """Human reason if subsystems-state.json exists but is unreadable/malformed,
    else None. _read_disabled silently falls back to ALL-ENABLED on corruption
    (the next toggle then persists the loss); this lets `cos doctor` surface it
    (TASK-474 P4-12) instead of certifying the desync PASS."""
    path = _state_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"unparseable ({exc})"
    if not isinstance(data, dict) or not isinstance(data.get("disabled", []), list):
        return 'malformed (expected {"disabled": [...]})'
    return None


def module_state(
    project_root: Path, modules: dict[str, Module] | None = None
) -> dict[str, bool]:
    """{module_id: enabled} for a project. No state file → all enabled.

    Read-only: never creates the state file (lazy creation happens on the
    first set_module_enabled)."""
    modules = modules or load_subsystems()
    disabled = _read_disabled(project_root)
    return {mid: (mid not in disabled) or m.kernel for mid, m in modules.items()}


def module_disabled_hook_ids(
    project_root: Path, modules: dict[str, Module] | None = None
) -> set[str]:
    """Hook ids owned by disabled modules — merged into the runtime
    allowlist by cli.project_overrides (safety-category still refused there)."""
    modules = modules or load_subsystems()
    state = module_state(project_root, modules)
    return {
        hook_id
        for module_id, module in modules.items()
        if not state[module_id]
        for hook_id in module.hooks
    }


def enabled_dependents(
    module_id: str, modules: dict[str, Module], state: dict[str, bool]
) -> list[str]:
    return sorted(
        m.id for m in modules.values() if module_id in m.depends_on and state.get(m.id, True)
    )


def set_module_enabled(
    project_root: Path,
    module_id: str,
    enabled: bool,
    modules: dict[str, Module] | None = None,
) -> ToggleResult:
    """Toggle a module with refusal semantics; persists state atomically.

    Refusals: unknown module; kernel module disable; disable while an enabled
    module still depends on it (chain spelled out); enable while a dependency
    is disabled (chain spelled out)."""
    modules = modules or load_subsystems()
    if module_id not in modules:
        return ToggleResult(
            ok=False,
            module_id=module_id,
            reason=f"unknown module '{module_id}' — available: {sorted(modules)}",
        )
    module = modules[module_id]
    # Kernel-pin + unknown-id are STATIC refusals (no concurrent toggle can change
    # them), so they stay outside the lock. The dependency refusals depend on OTHER
    # modules' enabled state and are re-validated under the lock below.
    if not enabled and module.kernel:
        return ToggleResult(
            ok=False,
            module_id=module_id,
            reason=f"module '{module_id}' is kernel (always on) and cannot be disabled",
        )

    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Concurrency-safe read-modify-write (TASK-474 P4-11): an advisory exclusive
    # lock serializes racing toggles, and the disabled set is RE-READ under the
    # lock so a concurrent writer's change survives (no silent lost-update). The
    # dependency-refusal validation is re-run under the lock against that fresh set
    # (TASK-478): a concurrent toggle of a DIFFERENT module could otherwise slip an
    # orphaned-dependency state past a pre-lock snapshot. Per-pid temp = no torn write.
    lock_path = path.with_suffix(".json.lock")
    with open(lock_path, "w", encoding="utf-8") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        disabled = _read_disabled(project_root)
        state = {mid: (mid not in disabled) or m.kernel for mid, m in modules.items()}
        if not enabled:
            dependents = enabled_dependents(module_id, modules, state)
            if dependents:
                return ToggleResult(
                    ok=False,
                    module_id=module_id,
                    reason=(
                        f"cannot disable '{module_id}': enabled module(s) depend on it — "
                        + ", ".join(f"{d} → {module_id}" for d in dependents)
                        + ". Disable the dependent(s) first."
                    ),
                )
        else:
            missing = [d for d in module.depends_on if not state.get(d, True)]
            if missing:
                return ToggleResult(
                    ok=False,
                    module_id=module_id,
                    reason=(
                        f"cannot enable '{module_id}': dependency chain not satisfied — "
                        + ", ".join(f"{module_id} → {d} (disabled)" for d in missing)
                        + ". Enable the dependency first."
                    ),
                )
        if enabled:
            disabled.discard(module_id)
        else:
            disabled.add(module_id)
        tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
        try:
            tmp.write_text(
                json.dumps({"version": 1, "disabled": sorted(disabled)}, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
    return ToggleResult(ok=True, module_id=module_id, enabled=enabled, state_path=path)
