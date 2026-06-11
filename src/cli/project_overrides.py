"""Per-project hook/skill enable-disable override layer (TASK-256).

A project carries two optional override files (written by the Config UI):

    .coding-os/hook-overrides.json   {"disabled": ["<hook-id>", ...]}
    .coding-os/skill-overrides.json  {"disabled": ["<skill-name>", ...]}

Safety-category hooks are NON-disableable. `effective_disabled_hooks` drops
them, and `write_runtime_allowlist` writes only safe-to-skip script basenames
into `.coding-os/disabled-hook-scripts` — the file cos-env.sh consults at
runtime to self-skip a disabled hook. The global registry.yaml is never touched.

Contract: docs/engineering/hub-architecture.md#per-project-hookskill-overrides-config-toggles
"""

from __future__ import annotations

import json
from pathlib import Path

SAFETY_CATEGORY = "safety"
STATE_DIR = ".coding-os"
HOOK_OVERRIDES = "hook-overrides.json"
SKILL_OVERRIDES = "skill-overrides.json"
RUNTIME_ALLOWLIST = "disabled-hook-scripts"


def _default_registry_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "src" / "core" / "hooks" / "registry.yaml"


def _read_disabled(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    items = data.get("disabled") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return set()
    return {str(x) for x in items if isinstance(x, str) and x.strip()}


def load_hook_overrides(project_root: Path) -> set[str]:
    """Hook ids the project requested to disable (raw, unvalidated)."""
    return _read_disabled(Path(project_root) / STATE_DIR / HOOK_OVERRIDES)


def load_skill_overrides(project_root: Path) -> set[str]:
    """Skill names the project requested to disable."""
    return _read_disabled(Path(project_root) / STATE_DIR / SKILL_OVERRIDES)


def _hook_index(registry_path: Path | None) -> dict[str, tuple[str, str]]:
    """hook id -> (script, category) from the global registry."""
    from cli.hook_renderer import load_registry

    registry = load_registry(registry_path or _default_registry_path())
    return {h.id: (h.script, h.category) for h in registry}


def _requested_disabled_hooks(project_root: Path) -> set[str]:
    """Per-hook overrides UNION hooks owned by disabled modules (TASK-353)."""
    from cli.subsystems import module_disabled_hook_ids

    return load_hook_overrides(project_root) | module_disabled_hook_ids(project_root)


def effective_disabled_hooks(
    project_root: Path, registry_path: Path | None = None
) -> set[str]:
    """Hook ids that WILL be disabled — requested minus safety + unknown ids."""
    idx = _hook_index(registry_path)
    return {
        hid
        for hid in _requested_disabled_hooks(project_root)
        if hid in idx and idx[hid][1] != SAFETY_CATEGORY
    }


def refused_safety_hooks(
    project_root: Path, registry_path: Path | None = None
) -> set[str]:
    """Requested ids that are refused because they are safety-category."""
    idx = _hook_index(registry_path)
    return {
        hid
        for hid in load_hook_overrides(project_root)
        if hid in idx and idx[hid][1] == SAFETY_CATEGORY
    }


def disabled_hook_scripts(
    project_root: Path, registry_path: Path | None = None
) -> set[str]:
    """Script basenames for the effective-disabled hooks (runtime allowlist)."""
    idx = _hook_index(registry_path)
    return {idx[hid][0] for hid in effective_disabled_hooks(project_root, registry_path)}


def write_runtime_allowlist(
    project_root: Path, registry_path: Path | None = None
) -> Path:
    """Write .coding-os/disabled-hook-scripts (cos-env.sh consumes it). Returns the path."""
    scripts = sorted(disabled_hook_scripts(project_root, registry_path))
    out = Path(project_root) / STATE_DIR / RUNTIME_ALLOWLIST
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(scripts)
    out.write_text(body + ("\n" if body else ""), encoding="utf-8")
    return out


def _main(argv: list[str]) -> int:
    """`python -m cli.project_overrides <project_root>` — regenerate the derived
    runtime allowlist from the override file. The Config UI / a sync step calls
    this whenever hook-overrides.json changes so a toggle takes effect."""
    root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    out = write_runtime_allowlist(root)
    refused = refused_safety_hooks(root)
    print(f"[overrides] wrote {out}")
    if refused:
        print(f"[overrides] refused (safety, non-disableable): {', '.join(sorted(refused))}")
    return 0


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(_main(_sys.argv))
