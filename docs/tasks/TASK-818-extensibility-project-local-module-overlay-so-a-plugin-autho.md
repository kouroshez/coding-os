---
id: TASK-818
title: "Extensibility \u2014 project-local module overlay so a plugin author adds a module without forking core + pruning-contract spec (F-F / ranks 8+9)"
swimlane: core
kind: feature
epic: modularity-completion
labels: [ready]
status: archive
priority: P3
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-818: Extensibility — project-local module overlay so a plugin author adds a module without forking core + pruning-contract spec (F-F / ranks 8+9)

**Outcome (one sentence):** A third party can register a toggleable module without forking the kernel — an out-of-core overlay is merged over subsystems.yaml in both load_subsystems and the MCP tool-gate reader (bundled wins on id collision, mirroring the stack/adapter/skill overlay) — and the per-artifact pruning contract is documented in one spec so the module lifecycle is legible.

## Read First
- src/cli/subsystems.py
- src/cli/_resources.py
- src/core/thinking_os/tools/_shared.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project-local module overlay ($COS_STATE_DIR/modules.d/*.yaml or a modules: block in .coding-os.yaml), **When** load_subsystems and the tool-gate reader run, **Then** the overlay module merges over the core registry (core wins on id collision), toggles + gating honor it, and a single per-artifact pruning-contract spec (physically-removed vs runtime-gated vs tag-skipped) is documented.
Checklist:
- [ ] Decide roadmap: pluggable (build overlay) vs curated-core (document). Owner leans pluggable (100k-star / plugin vision).
- [ ] load_subsystems merges an out-of-core overlay (mirror _resources overlay_template_dirs pattern); validate no kernel shadow / no dep break.
- [ ] tool-gate reader (_shared._tool_module_map) honors the same overlay (currently hardcodes the in-core path).
- [ ] Optional: mcp_server field + .mcp.json register/deregister in toggle_and_regen (defer if out of appetite; file follow-up).
- [ ] Write the per-artifact pruning-contract spec (one doc) covering hooks/tools/skills/commands/rules/docs.
- [ ] Tests: overlay module discovered + toggle + gate; core wins collision.
- [ ] Verify: uv run pytest tests/test_cli.py -q + uv run --extra rag pytest src/core/thinking_os/tests/test_module_gating.py -q.

## Work Log
- 2026-07-16 [claude]: Edit _resources.py
- 2026-07-16 [claude]: Edit subsystems.py
- 2026-07-16 [claude]: Edit test_cli.py
- 2026-07-16 [claude]: Edit modularity-audit-2026-07.md
- 2026-07-16 [claude]: Out-of-core module overlay: cli._resources.user_modules_dir/overlay_module_files ($COS_USER_MODULES_DIR, default…
- 2026-07-16 [claude]: commit 91d4ea0fa3 — feat(core): out-of-core module overlay so a plugin registers a module without forking (F-F)
