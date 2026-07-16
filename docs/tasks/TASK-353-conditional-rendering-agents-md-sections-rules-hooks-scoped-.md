---
id: TASK-353
title: "Conditional rendering \u2014 AGENTS.md sections + rules/hooks scoped by active modules"
swimlane: core
kind: feature
epic: G-modularity
labels: [wave-3, onboarding-program, ready]
status: archive
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-349]
blocked_by: []
references: []
---
# TASK-353: Conditional rendering — AGENTS.md sections + rules/hooks scoped by active modules

**Outcome (one sentence):** agents_md_sections entries gain requires:[module]; renderer/aggregator filter AGENTS.md sections and rule concatenation by active modules; hook template render + runtime allowlist derive from module state (extends hook-overrides mechanism).

## Read First
- src/cli/renderer.py
- src/cli/aggregator.py
- src/templates/_base/base.yaml
- src/cli/hook_renderer.py
- src/cli/project_overrides.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project with the tasks module disabled, **When** AGENTS.md is rendered, **Then** task-authoring/task-logging sections and task rules are absent while all kernel sections remain; re-enabling restores them byte-identical.
- **Given** module state, **When** adapter hook templates are regenerated, **Then** hooks owned by disabled modules are skipped at render AND self-skip at runtime via the derived allowlist (both layers tested).
- **Given** a default project (no module state), **When** rendering runs, **Then** output is byte-identical to pre-change rendering (golden test), proving zero regression for existing consumers.
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py tests/test_adapters.py -q` runs, **Then** green including the new conditional-render tests.

## Work Log
- 2026-06-11 [claude]: IMPL DONE (parked, batch 4 #1) — AgentsMdSection.requires:[module] (schema + parser + renderer section-skip); fragments
- 2026-06-11 [claude]: CLOSED on batch-4 suite: tests/test_cli.py 114 passed (25m29s) on top of TestConditionalRendering 5/5, adapters 48/48, g
