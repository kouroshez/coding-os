---
id: TASK-806
title: "Restore P8 in Hub routes: move claude_agent_sdk imports out of src/core/web behind the dispatcher seam"
swimlane: core
kind: refactor
epic: null
labels: [review-sweep, architecture, docs-update, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-10
started: 2026-07-09
completed: 2026-07-09
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-806: Restore P8 in Hub routes: move claude_agent_sdk imports out of src/core/web behind the dispatcher seam

**Outcome (one sentence):** Resolved via the documented-carve-out path: the enforced P8 boundary (no SDK-type construction in core — guard-tested by tests/test_no_hardcoded_anthropic.py::test_no_claude_agent_options_construction_in_core) is stated precisely in docs/adapters/session-options-builder.md, which stops overclaiming "core never imports claude_agent_sdk directly" and instead lists the three sanctioned lazy fail-soft import sites (cognition._claude_sdk, presence transcript-key helper, roles dispatch probe); refactoring those working guarded sites for a roadmap second-adapter need is explicitly rejected under Rule 22 (no speculation, defer-by-default).

## Read First
- docs/adapters/session-options-builder.md
- tests/test_no_hardcoded_anthropic.py
- docs/architecture/meta-project.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the seam doc's Layering section, **When** read against src/core/web/routes/{cognition,presence,roles}.py, **Then** every claim matches the code: no-construction is the enforced invariant and the three lazy import sites are listed as the sanctioned exception.
- **Given** `make docs-lint`, **When** run after the edit, **Then** the hard gate passes and session-options-builder.md no longer reports a malformed front-matter header.
- **Given** tests/test_no_hardcoded_anthropic.py, **When** run, **Then** the P8 construction guard still passes unchanged.

## Work Log
- 2026-07-10 [claude]: Edit session-options-builder.md
- 2026-07-10 [claude]: Edit session-options-builder.md
- 2026-07-10 [claude]: commit fc54993328 — docs(adapters): state the enforced P8 boundary and sanctioned lazy-import carve-out
- 2026-07-10 [claude]: Status transitioned to complete via cos task-done.
