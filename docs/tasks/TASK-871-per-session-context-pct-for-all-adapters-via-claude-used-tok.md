---
id: TASK-871
title: "Per-session context pct for all adapters via claude used-tokens and codex rollout tail"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-153956-0acf
depends_on: []
blocked_by: []
references: []
---
# TASK-871: Per-session context pct for all adapters via claude used-tokens and codex rollout tail

**Outcome (one sentence):** The Live-agents ctx badge shows a real percentage per session for every supported adapter — claude from stamped used_tokens, codex from its rollout token_count tail — instead of `ctx ?` for everyone.

## Read First

- src/core/web/routes/presence.py — _context_pct_from_used_tokens / _context_window
- src/core/web/routes/sessions.py — /api/sessions/active row builder
- src/core/web/ui/src/pages/DashboardPage.tsx — ContextPctBadge lookup
- docs/engineering/hub-architecture.md § Live-agent context window

## Repro Steps

1. Open Dashboard › Live agents with two claude sessions + one codex session live.
2. Every row shows `ctx ?` — /api/sessions/active carries no context fields, and /api/presence/agents only covers each agent's current-marker session, so the per-session badge lookup misses.

## Acceptance

- **Given** a claude session with used_tokens stamped, **When** /api/sessions/active returns its row, **Then** context_pct/used_tokens/context_window are present and the badge renders a percent.
- **Given** a live codex session with a rollout file, **When** the row is returned, **Then** context_pct derives from last_token_usage.total_tokens over model_context_window.
- **Given** no usage signal, **When** rows render, **Then** context_pct stays honest-null (`ctx ?`), never fabricated.

## Work Log
- 2026-08-04 [claude]: Edit hub-architecture.md
- 2026-08-04 [claude]: Edit presence.py
- 2026-08-04 [claude]: Edit presence.py
- 2026-08-04 [claude]: Edit sessions.py
- 2026-08-04 [claude]: Edit sessions.py
- 2026-08-04 [claude]: Edit DashboardPage.tsx
- 2026-08-04 [claude]: Edit DashboardPage.tsx
- 2026-08-04 [claude]: Edit presence.py
- 2026-08-04 [claude]: Edit sessions.py
- 2026-08-04 [claude]: Root cause: /api/sessions/active (the Live-agents panel producer) carried no context fields and /api/presence/agents…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
