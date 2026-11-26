---
id: TASK-1135
title: "refactor(rules): one owner per rule \u2014 bodies to skills, one pointer line in AGENTS.md, no .codex/rules"
swimlane: infra
kind: refactor
epic: null
labels: [ready, governance]
status: testing
priority: P1
appetite: 2d
created: 2026-11-26
started: 2026-11-26
completed: null
agent_session: ses-claude-20261126-141007-ed72
depends_on: []
blocked_by: []
references: []
---

# TASK-1135: refactor(rules): one owner per rule — bodies to skills, one pointer line in AGENTS.md, no .codex/rules

**Outcome (one sentence):** Each rule is stated in exactly one file and reaches both agents; findings C2, D2, D3 of the [audit § Duplication](../engineering/harness-loading-audit-2026-11.md#duplication-single-source) and L1, L2 of [§ Claude loading](../engineering/harness-loading-audit-2026-11.md#claude-loading) are closed with a measured before/after count per profile (L3 moved to TASK-1141).

**Starts after TASK-1136:** L1's re-render is only correct once refresh_stack_rules uses D1's hash baseline.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a baseline taken with `cos doctor --tokens` in META and a fresh scaffold at task start, **When** it is re-run at close, **Then** always-on text is lower in both and no rule body appears in two always-on files.
- **Given** Codex in a scaffold, **When** `codex debug prompt-input` runs, **Then** every rule is reachable as a skill or an AGENTS.md line, and no .codex/rules dir exists.
- **Given** a META Claude session, **When** skills are listed, **Then** none come from tests/golden.

## Work Log
- 2026-11-26 [claude]: PLAN (graph refs + literal greps). Doc anchor: docs/engineering/rules-loading.md (stale; rewrite to the new…
- 2026-11-26 [claude]: commit 5939787c94 — refactor(rules): one owner per rule; Codex gets rule bodies from the core-rules skill
- 2026-11-26 [claude]: MEASURED (bytes of always-on files; doctor --tokens reads 7-day transcripts only: META median session baseline 77,019…
- 2026-11-26 [claude]: Bytes always-on, META before→after: Claude 65,594→58,892; Codex 23,204→21,164; .codex/rules 49,018→0.
- 2026-11-26 [claude]: Bytes always-on, scaffold (claude,codex fastapi) before→after: Claude 49,171→48,927; Codex 12,277→12,033;…
- 2026-11-26 [claude]: doctor --tokens reads 7-day transcripts only: META median session baseline 77,019 both runs; a fresh scaffold has no…
- 2026-11-26 [claude]: Review round 1: L3 moved to TASK-1141; publish clause added; settings.local.json out of goldens; guard tests for…
- 2026-11-26 [claude]: Scaffold .codex/rules 36,708→0 B. Fresh scaffold has no transcripts for doctor --tokens.
- 2026-11-26 [claude]: Hook text removed: primer card 1,202 B per session boundary; compact/resume rule list ~900 B.
- 2026-11-26 [claude]: Round-1 guard tests: no golden .claude dir; no rule paragraph repeated in AGENTS.md.
- 2026-11-26 [claude]: commit f92969ab12 — fix(rules): publishing needs a yes in the Codex rule line; golden guards and no local settings
