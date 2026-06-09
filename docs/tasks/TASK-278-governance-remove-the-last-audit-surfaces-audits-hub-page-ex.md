---
id: TASK-278
title: "governance: remove the last audit surfaces \u2014 Audits hub page + exhaustive_evidence cognition formula"
swimlane: core
kind: refactor
epic: hub-redesign
labels: [ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-09
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-278: governance: remove the last audit surfaces — Audits hub page + exhaustive_evidence cognition formula

**Outcome (one sentence):** Zero audit residue: the Audits hub page (route+page+nav) and the exhaustive_evidence cognition formula (preset + schema + dispatch branch + CLI audit-mode + pre-commit ref + tests) are removed, goldens regenerated, and the full suite stays green.

## Read First
- src/core/web/server.py + App.tsx + routes/audits.py + pages/AuditsPage.tsx — Audits page
- src/core/thinking_os/presets/registry.yaml + cognition_schemas.py + tools/cognition.py — exhaustive_evidence formula
- src/cli/cognition.py + src/core/hooks/_helpers/pre_commit_batch.py — audit-mode + pre-commit ref
- tests/golden/** — stale goldens still carry the removed hooks/rules

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the hub, **When** the user navigates, **Then** there is no Audits page/route/nav and server.py no longer registers an audits router.
- **Given** the cognition system, **When** an agent calls cos_supervise_record_output, **Then** there is no exhaustive_evidence formula/preset/schema/branch and the CLI has no trace-replay audit-mode — other formulas still work.
- **Given** the full suite + goldens, **When** verified, **Then** thinking_os + cli + golden-parity + UI tsc + docs-lint are all green.

## Work Log
- 2026-06-09 [claude]: committed e0a17fbd: src/cli/cognition.py, src/core/board_os/mcp_tools.py, src/core/board_os/tests/test_reviewer_hint.py,
- 2026-06-09 [claude]: Zero audit residue achieved. A: Audits hub page (route/page/nav/router) removed. B: exhaustive_evidence formula removed 
