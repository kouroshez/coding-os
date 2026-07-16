---
id: TASK-199
title: "Fix Hub audits page crash \u2014 coerce list-typed audit fields to arrays at the producer"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-199: Fix Hub audits page crash — coerce list-typed audit fields to arrays at the producer

**Outcome (one sentence):** /diagnostics/audits no longer throws TypeError (e.predicates ?? []).join is not a function; audits.py guarantees predicates/matched_exhaustive/matched_scope are always JSON arrays even when frontmatter holds a free-form scalar.

## Read First
- [src/core/rules/api-contract-discipline.md](../../src/core/rules/api-contract-discipline.md) — producer is the source of truth for response shape
- src/core/web/routes/audits.py (removed 2026-06-09) — the producer
- src/core/web/ui/src/pages/AuditsPage.tsx (removed 2026-06-09) — the crashing consumer

## Repro Steps
1. Open http://127.0.0.1:9188/p/coding-os/diagnostics/audits in the Hub UI.
2. Page crashes with the React error overlay.
Expected: audits table renders; Predicates column joins the list with ", ".
Actual: `TypeError: (e.predicates ?? []).join is not a function` — the whole page is blank.
Root cause: a retired audit artifact wrote `predicates:` as a free-form prose scalar; the naive line parser stores it as a string and `or []` only catches None/empty, so the route emits a string for a field the UI joins as an array.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an audit-*.md whose `predicates:` (or `matched_*`) frontmatter is a free-form scalar string, not a YAML list
- **When** GET /api/audits (and /api/audits/{id}) serialises that audit
- **Then** the field is always a JSON array (scalar wrapped as a single-element list, empty → []), so `(a.predicates ?? []).join(', ')` never throws and the page renders

## Work Log
- 2026-06-06 [claude]: audits.py: added _as_str_list guard so predicates/matched_* always serialise as arrays; +4 regression tests (28 passed);
