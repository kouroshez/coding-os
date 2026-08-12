---
id: TASK-941
title: "feat: one output contract for the scripts and tests the agent writes"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-941: feat: one output contract for the scripts and tests the agent writes

**Outcome (one sentence):** Every script and verification run the agent authors reports in one shared vocabulary — same status markers, same failure shape, and a visible progress signal for anything long-running — so a human reads two different runs the same way.

## Read First
- src/core/skills/clean-code/SKILL.md
- src/core/rules/test-discipline.md
- src/core/rules/anti-overengineering.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the rule is in force **When** the agent writes a new script that reports status **Then** it uses the single documented marker set rather than inventing FAIL:/ERROR:/OK: variants. **Given** a run that iterates over more than a handful of units **When** it executes **Then** it emits progress (count and position), not silence until the end. **Given** the meta repo **When** the rule lands **Then** it is reachable from the clean-code skill and the always-active rule set.

## Work Log
- 2026-08-12 [claude]: Edit SKILL.md
- 2026-08-12 [claude]: Edit output-contract.md
- 2026-08-12 [claude]: Edit output-contract.md
- 2026-08-12 [claude]: Edit test-discipline.md
- 2026-08-12 [claude]: commit 99d6000551 — docs(clean-code): adopt one output contract for scripts and checks
- 2026-08-12 [claude]: Adopted cos doctor's [OK]/[WARN]/[FAIL]/[SKIP] as SSOT (no new vocabulary); progress + repro-on-failure required;…
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-12 [claude]: Edit _init_world.py
- 2026-08-12 [claude]: Edit _init_world.py
- 2026-08-12 [claude]: Edit _init_world.py
- 2026-08-12 [claude]: Edit init_command.py
- 2026-08-12 [claude]: Edit init_command.py
- 2026-08-12 [claude]: Edit init_command.py
- 2026-08-12 [claude]: Edit _init_summary.py
- 2026-08-12 [claude]: Edit test_init_setup_mode.py
- 2026-08-12 [claude]: Edit _config_mcp.py
- 2026-08-12 [claude]: Edit _config_read.py
- 2026-08-12 [claude]: Edit _config_mutate.py
- 2026-08-12 [claude]: Edit test_hub_mcp_scope.py
- 2026-08-12 [claude]: Edit test_hub_mcp_scope.py
- 2026-08-12 [claude]: Edit test_hub_mcp_scope.py
- 2026-08-12 [claude]: commit bd008b7625 — feat(cli): offer quick vs custom setup and close init with an actionable panel
