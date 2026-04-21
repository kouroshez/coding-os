---
id: TASK-032
title: "Phase N.SDK — claude-agent-sdk dispatcher integration"
swimlane: adapters
kind: feature
epic: phase-n
labels: [claude-adapter, sdk, dispatcher]
status: complete
priority: P1
appetite: "1d"
created: 2026-04-20
started: 2026-04-20
completed: 2026-04-20
agent_session: ses-claude-20260420-sdk
depends_on: []
blocked_by: []
references: []
---

# TASK-032: Phase N.SDK — claude-agent-sdk dispatcher integration

**Outcome (one sentence):** Claude adapter spawns real formula sub-agents via `claude-agent-sdk`; other adapters fall back to default inline dispatch.

## Read First
- docs/adapters/claude-sdk.md
- AGENTS.md §P8 (adapter-SDK autonomy)
- core/thinking_os/dispatcher.py
- adapters/claude/sdk_dispatcher.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Claude + `--extra claude-sdk` **When** `cos_dispatch_formula_run("F5", …)` **Then** real sub-session spawned, output persisted to bundle, row in `formula_dispatches`.
- **Given** Codex/Cursor/no-SDK **When** same tool called **Then** status=`skipped`, error=`inline-dispatch-required`.
- **Given** `dispatch_parallel` **When** `cos_dispatch_parallel_run` with 2 formulas **Then** wall ≥1.5× faster than sequential equivalent.

## Work Log
- **2026-04-20** — Shipped. 11/11 unit tests + E2E PASS (single+parallel+bundle+DB). Parallel speedup measured **1.93×** (F5+F7: 13.8s vs 24.5s seq). `make verify` green.
