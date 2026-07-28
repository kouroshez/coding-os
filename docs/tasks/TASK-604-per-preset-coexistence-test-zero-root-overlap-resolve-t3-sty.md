---
id: TASK-604
title: "per-preset coexistence test (zero root overlap) + resolve t3-style nested-root"
swimlane: cli
kind: test
epic: stack-factory-v2
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: [TASK-600]
blocked_by: []
references: []
---
# TASK-604: per-preset coexistence test (zero root overlap) + resolve t3-style nested-root

**Outcome (one sentence):** A test runs boundary aggregation across every _presets/*.yaml stack-list and asserts zero overlapping roots + zero ambiguous owner, so a bad preset can never ship green; and the t3-style preset's nested-root is resolved per the T13 (TASK-600) containment primitive.

## Read First
- tests/test_cli.py
- src/templates/_presets/t3-style.yaml
- src/cli/stack_registry.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** every preset in src/templates/_presets/*.yaml, **When** the new test runs boundary aggregation across its stacks, **Then** it asserts zero root overlap and zero ambiguous file_pattern owner.
**Given** t3-style, **When** resolved, **Then** either typescript-plain is dropped (anti-overengineering — the second stack only adds a colliding root) or given a non-`src` root, and the new test passes for it.
**Then** `uv run pytest tests/test_cli.py -q` is green.

## Work Log
- 2026-06-27 [claude]: Deliberation: probed all 17 presets — only t3-style + hexagonal-product collide. hexagonal (go+go-fiber+fastapi on…
- 2026-06-27 [claude]: Edit t3-style.yaml
- 2026-06-27 [claude]: Edit test_cli.py
- 2026-06-27 [claude]: Edit stack_registry.py
- 2026-06-27 [claude]: Edit test_cli.py
- 2026-06-27 [claude]: Edit stack-factory-v2-epic.md
- 2026-06-27 [claude]: Edit stack-factory-v2-epic.md
- 2026-06-27 [claude]: Done: dropped typescript-plain from t3-style.yaml ([nextjs]); added…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-27 [claude]: committed cf0b33a3 · 3 files
