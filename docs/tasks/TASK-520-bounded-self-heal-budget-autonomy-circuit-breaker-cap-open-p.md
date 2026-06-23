---
id: TASK-520
title: "Bounded self-heal budget + autonomy circuit-breaker (cap open PRs, CI-runnable probe, escalate-to-blocked)"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, autonomy, safety]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-22
started: null
completed: null
agent_session: null
depends_on: [TASK-517]
blocked_by: []
references: []
---

# TASK-520: Bounded self-heal budget + autonomy circuit-breaker (cap open PRs, CI-runnable probe, escalate-to-blocked)

**Outcome (one sentence):** The autonomous loop can never burn unbounded tokens/CI-quota. A max-N self-heal cycle per PR escalates the task to blocked with the CI failure log (no infinite loop). A circuit-breaker probes that CI is actually runnable before arming auto-merge and caps simultaneously-open agent PRs, so a quota-dead/red CI (TASK-513) parks work instead of piling PRs forever. Reuses cos_task_move(blocked) + cos_work_log_append as the escalation path; no new board concept.

## Read First
- src/core/board_os/mcp_tools.py
- docs/playbooks/pr-workflow.md
- docs/tasks/TASK-513-restore-green-ci-linux-only-failures-golden-prd-case-manifes.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a PR whose CI stays red for N consecutive heal attempts, **When** the budget is exhausted, **Then** the task moves to blocked with the failure log attached and the agent stops re-pushing. **Given** CI not runnable (Actions disabled/quota-exhausted) or no required check, **When** the loop attempts to arm auto-merge past the open-PR cap, **Then** it does not open a new PR and surfaces the circuit-breaker state to the operator. **Given** tests for the budget + circuit-breaker, **Then** green.

## Work Log
