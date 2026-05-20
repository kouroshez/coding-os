#!/usr/bin/env python3
"""Regenerate core/rules/dimension-registry.md and core/rules/skill-enforcement.md.

Both files are generated from the live stack registry:

    core/rules/dimension-registry.md   ← aggregated world.dimensions
    core/rules/skill-enforcement.md    ← aggregated world.skill_enforcement

Run after editing any `templates/<stack>/stack.yaml` that changes
`dimensions:` or `skill_enforcement:` lists. `tests/test_rules_fresh.py`
guards freshness in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORE_RULES = REPO_ROOT / "src" / "core" / "rules"
DIMENSION_REGISTRY_PATH = CORE_RULES / "dimension-registry.md"
SKILL_ENFORCEMENT_PATH = CORE_RULES / "skill-enforcement.md"


def _build_world():
    """Build an AggregatedWorld containing every installed stack."""
    sys.path.insert(0, str(REPO_ROOT))
    from cli._data_types import AdapterProfile
    from cli.adapter_registry import load_adapter_registry
    from cli.aggregator import aggregate, today_iso
    from cli.stack_registry import load_base_profile, load_stack_registry

    base = load_base_profile(REPO_ROOT / "src" / "templates" / "_base")
    stacks_reg = load_stack_registry(REPO_ROOT / "src" / "templates")
    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")

    # Use claude if available, otherwise first adapter, otherwise a stub.
    if "claude" in adapters:
        adapter = adapters["claude"]
    elif adapters:
        adapter = next(iter(adapters.values()))
    else:
        adapter = AdapterProfile(
            id="stub",
            label="stub",
            settings_file=None,
            hooks_dir=None,
            rules_dir=None,
            skills_dir=None,
            sourced_hooks=(),
            supports_rules=False,
            supports_settings_json=False,
            install_script=Path("."),
            default_settings={},
            source_dir=Path("."),
        )

    all_stacks = [stacks_reg[sid] for sid in sorted(stacks_reg.keys())]
    return aggregate(
        base,
        all_stacks,
        adapter,
        "coding-os",
        today=today_iso(),
    )


def main() -> int:
    from cli.renderer import (
        render_dimension_registry,
        render_skill_enforcement,
    )

    world = _build_world()

    CORE_RULES.mkdir(parents=True, exist_ok=True)
    dim_content = render_dimension_registry(world)
    enf_content = render_skill_enforcement(world)

    DIMENSION_REGISTRY_PATH.write_text(dim_content, encoding="utf-8")
    SKILL_ENFORCEMENT_PATH.write_text(enf_content, encoding="utf-8")

    print(f"[regen-rules] wrote {DIMENSION_REGISTRY_PATH.relative_to(REPO_ROOT)}")
    print(f"[regen-rules] wrote {SKILL_ENFORCEMENT_PATH.relative_to(REPO_ROOT)}")
    print(
        f"[regen-rules] {len(world.dimensions)} dimensions, "
        f"{len(world.skill_enforcement)} skill-enforcement rows, "
        f"from {len(world.stack_ids)} stacks"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
