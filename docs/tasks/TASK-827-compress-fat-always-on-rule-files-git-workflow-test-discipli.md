---
id: TASK-827
title: "Compress fat always-on rule files (git-workflow, test-discipline, transparency-banner) to cut context-injection mass"
swimlane: core
kind: refactor
epic: null
labels: [context-economy, rules, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: null
agent_session: ses-claude-20260716-180747-21b8
depends_on: []
blocked_by: []
references: []
---
# TASK-827: Compress fat always-on rule files (git-workflow, test-discipline, transparency-banner) to cut context-injection mass

**Outcome (one sentence):** The three largest hand-written rule files inject ~25KB every session; compress each to imperative + one-line why + pointer form (detail lives in the already-existing governance/engineering docs) so total always-on rule mass drops ~50% and per-rule attention rises. No normative statement may be dropped; hook-referenced section headings stay stable.

## Read First
- src/core/rules/git-workflow.md
- src/core/rules/test-discipline.md
- src/core/rules/transparency-banner.md
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the three rule files, **When** compressed, **Then** combined size is <= ~12KB (from ~25KB) and every hard rule, allowed-form list, and hard-fail list is still present verbatim-or-condensed. **Given** hooks referencing section anchors (git-workflow § Commit Message Contract, § When to commit), **When** the files are rewritten, **Then** those headings survive unchanged. **Given** make docs-lint, **When** run at close, **Then** it passes.

## Work Log
- 2026-07-16 [claude]: Compressed the 3 fattest always-on rules: git-workflow 10.1K→6.4K, test-discipline 6.7K→4.0K, transparency-banner…
