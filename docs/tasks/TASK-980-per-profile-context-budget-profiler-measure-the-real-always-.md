---
id: TASK-980
title: "Per-profile context-budget profiler \u2014 measure the real always-on token cost"
swimlane: infra
kind: feature
epic: honest-benchmarks
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: null
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-980: Per-profile context-budget profiler — measure the real always-on token cost

**Outcome (one sentence):** A reproducible measurement of what coding-os actually costs in always-on context, per project profile — because a WordPress consumer and a polyglot consumer do not pay the same tax, and publishing one averaged number would misrepresent both.

## Read First
- src/cli/_init_preview.py
- src/templates/_presets/
- src/core/rules/
- docs/engineering/third-party-token-bench.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a preset id, **When** the profiler runs, **Then** it scaffolds that preset into a temp dir outside the repo and reports measured always-on bytes/tokens split by AGENTS.md, static core rules, generated rules, and stack rules.
- **Given** the full preset set, **When** the profiler runs, **Then** it emits a table spanning the smallest real profile (single-stack CMS) to the largest (polyglot), so no single number is published as "the" cost.
- **Given** a published number, **When** a reader checks it, **Then** the exact command that produced it appears next to it.

## Work Log
- 2026-08-15 [claude]: Edit context-budget.md
- 2026-08-15 [claude]: Edit context_budget.py
- 2026-08-15 [claude]: Edit context-budget.md
- 2026-08-15 [claude]: Built src/scripts/context_budget.py — scaffolds each preset with the real `cos init --no-register --no-index` into a…
