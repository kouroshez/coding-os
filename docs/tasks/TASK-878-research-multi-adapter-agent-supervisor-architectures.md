---
id: TASK-878
title: "Research multi-adapter agent supervisor architectures"
swimlane: core
kind: spike
epic: null
labels: [orchestration, adapters, research, codex, claude, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-04
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-codex-019fc9ac-216e-7211-a224-dad139ff5712
depends_on: []
blocked_by: []
references: []
---

# TASK-878: Research multi-adapter agent supervisor architectures

**Outcome (one sentence):** Produce an evidence-backed architecture recommendation for a provider-neutral Coding OS supervisor that can coordinate Claude, Codex, and future adapters without coupling core to provider SDKs.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the current Coding OS Claude/Codex adapter and Hub contracts, **when** the research is complete, **then** the deliverable reviews official Codex sources and popular relevant GitHub projects with point-in-time star counts, architecture patterns, tradeoffs, and direct links.
- **Given** Coding OS already owns board, cognition, roles, formula dispatch, and traces, **when** recommending an architecture, **then** it defines a provider-neutral runtime port, durable supervisor semantics, safety invariants, implementation phases, and rejected alternatives without importing an adapter SDK into core.
- **Given** this task is research-first, **when** it closes, **then** no multi-adapter runtime implementation is claimed and `make docs-lint` plus `git diff --check` pass for the research deliverable.

## Work Log
- 2026-08-04 [codex]: Reviewed official Codex docs plus popular GitHub agent systems and authored…
- 2026-08-04 [claude]: committed 1254119d · 2 files
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-04 [codex]: Closure attribution corrected to this Codex session through an explicit semantic transition; the two earlier…
