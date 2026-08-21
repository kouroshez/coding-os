---
id: TASK-1015
title: "Auto-dispatch cross-provider roles so multi-model supervision actually fires"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [supervision, routing, hub, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-21
started: 2026-08-20
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1015: Auto-dispatch cross-provider roles so multi-model supervision actually fires

**Outcome (one sentence):** Opening a session on any adapter and working a COMPLICATED+ task automatically dispatches the roles pinned to a different provider (reviewer, security_auditor → Codex) at the moment there is something to review, records adapter/model/cost per run, and surfaces who ran what — while same-provider roles stay inline because delegation costs ~$0.56 and ~50s that simple work should not pay.

## Read First
- docs/engineering/agent-supervision.md
- src/adapters/codex/adapter.yaml
- src/core/hooks/resolve-supervise-route.sh
- src/core/hooks/auto-compose-roles.sh
- src/core/thinking_os/supervision.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** supervision is enabled and a role is pinned to an adapter other than the running session's
**When** a COMPLICATED+ task reaches the point where that role's work is due
**Then** the role is dispatched automatically without the agent choosing to, and a row lands in `formula_dispatches` carrying adapter, model and cost.

**Given** a role pinned to the same adapter as the session
**When** the trigger evaluates it
**Then** it is NOT dispatched — it runs inline, because a sub-agent would cost more and take longer for identical capability.

**Given** the codex adapter
**When** a role is routed to `gpt-5.6-sol`
**Then** descriptor validation accepts it, because the adapter declares its models and efforts.

**Given** all 11 roles
**When** the supervision policy is read
**Then** every role resolves to an explicit adapter/model/effort rather than falling through to the session default.

**Given** a dispatch has run
**When** the next turn starts
**Then** the operator can see which adapter and model ran the role, without querying the database by hand.

## Work Log
- 2026-08-21 [claude]: Trigger built and proven live: auto-dispatch-crossprovider (PostToolUse on cos_task_move -> testing) fires detached…
