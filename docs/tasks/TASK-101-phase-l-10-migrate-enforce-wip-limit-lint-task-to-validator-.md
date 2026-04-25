---
id: TASK-101
title: "Phase L.10 — migrate enforce-wip-limit + lint-task to validator framework"
swimlane: core
kind: chore
epic: null
labels: []
status: icebox
priority: P2
appetite: "1d"
created: 2026-04-25
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-101: Phase L.10 — migrate enforce-wip-limit + lint-task to validator framework

**Outcome (one sentence):** Replace the standalone WIP cap and size-limit thresholds in `enforce-wip-limit.sh` and `lint-task.sh` with reads from `core/board_os/transition-gates.yaml::wip_limits` and `::size_limits` so all five gates share one SSOT.

## Read First
- [docs/phase-l10-plan.md](../phase-l10-plan.md)
- [core/board_os/transition_gates.py](../../core/board_os/transition_gates.py)
- [core/board_os/scrumban-config.yaml](../../core/board_os/scrumban-config.yaml)
- [core/hooks/enforce-wip-limit.sh](../../core/hooks/enforce-wip-limit.sh)
- [core/hooks/lint-task.sh](../../core/hooks/lint-task.sh)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an edited `transition-gates.yaml` with `wip_limits.in_progress: 2`
- **When** an agent attempts to start a 2nd task while one is already `in_progress`
- **Then** the WIP gate uses the new value (2) without restarting any process or editing scrumban-config.yaml
- **And** existing test_workflow + test_mcp_tools suites continue to pass after the refactor
- **And** `lint-task.sh` reads `size_limits.warn_tokens` / `size_limits.block_tokens` from the same SSOT

## Work Log
