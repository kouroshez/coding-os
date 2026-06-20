---
id: TASK-459
title: "Integrity & surface cleanup \u2014 doc-drift guard, graph health, hook dedup"
swimlane: infra
kind: chore
epic: audit-remediation-2026-06
labels: [governance, audit-remediation, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-459: Integrity & surface cleanup — doc-drift guard, graph health, hook dedup

**Outcome (one sentence):** Repo SSOT stops contradicting itself (stack count generated/linted, not a stale literal), the agent-trusted graph is healthy (phantom cursor nodes + stale paths purged) and gated in CI, and src/core/hooks/ contains only runtime hooks (record-verify near-duplicate merged, test harnesses relocated). This is the 'stop lying / clean the surface' batch from the strategic audit (group A).

## Work Log
- 2026-06-20 [claude]: Edit AGENTS.md
- 2026-06-20 [claude]: Edit doc-system-overhaul-roadmap.md
- 2026-06-20 [claude]: commit 2e5534a55b — docs: remove stale '8 stacks' SSOT literal (AGENTS.md + overhaul roadmap)
- 2026-06-20 [claude]: DONE: A2 graph purged via cos_graph_doctor(fix=true) → healthy:true (70 phantom cursor + 1103 external + 5 stale…
- 2026-06-20 [claude]: committed 1de45092 · 1 file
