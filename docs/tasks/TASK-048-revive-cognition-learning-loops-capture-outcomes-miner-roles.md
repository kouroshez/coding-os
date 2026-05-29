---
id: TASK-048
title: "Revive cognition/learning loops — capture, outcomes, miner, roles, doctor"
swimlane: thinking_os
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-05-29
started: 2026-05-29
completed: 2026-05-29
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-048: Revive cognition/learning loops — capture, outcomes, miner, roles, doctor

**Outcome (one sentence):** The cognitive telemetry loops (observation capture, task-outcome quality, pattern mining, role composition, doctor surfacing) actually persist real signal so `learned_patterns`/`observations`/roles stop being empty.

## Read First
- [docs/tasks/audits/audit-cognition-loops.md](audits/audit-cognition-loops.md) — full diagnosis + grouped implementation checklist (G1–G9).

## Repro Steps
1. Open admin Hub → diagnostics → doctor → sqlite: `learned_patterns=0`, `observations=2`, `doc_audit_trail=0`, `agent_metrics`=389 identical session/success.
2. Edit any file → `capture-observation` fires but `observations` count never increments (live probe confirmed).
3. Nightly `learn_extract` runs `status:ok` but `extracted:[]` because all 25 task_outcomes are success/CLEAR with no rework/skills/backtrack fuel.
Expected: capture persists observations; outcomes carry real outcome/skills/model; miner emits patterns; roles page reflects activity.
Actual: every learning/recall/roles loop is plumbed but starved; nothing is learned.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent edits a file, **When** the PostToolUse capture hook fires, **Then** the `observations` row persists (count increments, FTS-indexed).
- **Given** ≥3 success task_outcomes with skills/model populated, **When** `learn_extract` runs, **Then** `extracted` is non-empty and `learned_patterns` gains rows.
- **Given** a supervised session, **When** the Hub roles page loads, **Then** it reflects real role activity instead of "No agent session active".
- **Given** the matrix verification per changed layer, **Then** all targeted suites pass.

## Work Log
- 2026-05-29 [claude]: G1–G9 landed (8 commits). Capture now synchronous (observations persist, probe 2→3); outcomes carry skills/model/duration + MCP path records; learn_extract mines success → learned_patterns 0→1 LIVE; agent_metrics real model + session_summary digest; routing_weights 0→1; compose_chain writes .roles; doctor surfaces diagnosis + UI banner; enforce-skill panel-first + hook path fixes. Verified: thinking_os 1210/0, board_os 61/0, verify-hooks clean. Deferred: graph code_python@v1 2-edge resolver gap + D1–D5 dormant. See audits/audit-cognition-loops.md. ⚠️ user must restart MCP server for in-memory tool code to update.
- 2026-05-29 [claude]: Status transitioned to complete via cos task-done.
