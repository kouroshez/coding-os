---
id: TASK-1018
title: "Show real provider account state \u2014 Codex/Claude quota windows and an OpenAI price table"
swimlane: core
kind: feature
epic: null
labels: [supervision, hub, adapters, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-21
started: 2026-08-21
completed: 2026-08-21
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1018: Show real provider account state — Codex/Claude quota windows and an OpenAI price table

**Outcome (one sentence):** An operator on a subscription sees how much of each provider's 5h/weekly window is spent without leaving the Hub, and an operator on an API key sees Codex spend in dollars. Both numbers come from the provider's own on-disk state, never from an estimate.

## Read First
- docs/engineering/agent-supervision.md
- src/core/thinking_os/adapter_registry.py
- src/core/web/routes/cognition_dispatch_views.py
- src/adapters/codex/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a Claude subscription login
**When** the Hub quota panel loads
**Then** every window the provider reports renders with its percent, reset time and severity, and the cache age is shown so a stale figure cannot read as live.

**Given** a Codex login
**When** the panel loads
**Then** the newest rollout's rate_limits windows render, labelled from window_minutes rather than from a hardcoded primary/secondary meaning.

**Given** a provider whose state file is absent
**When** the panel loads
**Then** that adapter reports unavailable with a reason, and never a zero percent.

**Given** a codex dispatch with recorded token usage
**When** cost is computed
**Then** it uses the adapter-declared per-Mtok table, bills cached and cache-write tokens at their own rates, and applies the long-context tier above 272000 input tokens.

## Work Log
- 2026-08-21 [claude]: Chose an adapter-owned `account` port over a kernel-side reader: only the adapter knows where its runtime caches…
- 2026-08-21 [claude]: commit 876494cee1 — feat(supervision): report each provider's plan quota from its own on-disk state
- 2026-08-21 [claude]: commit a9f2ad52ad — feat(codex): price dispatches from the published OpenAI rate table
- 2026-08-21 [claude]: Verified by running, not reading: live /api/cognition/quota returns claude 0/49/78% and codex 2%; Playwright…
- 2026-08-21 [claude]: Status transitioned to complete via cos task-done.
