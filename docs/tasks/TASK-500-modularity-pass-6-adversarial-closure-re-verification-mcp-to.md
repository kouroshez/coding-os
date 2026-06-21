---
id: TASK-500
title: "Modularity pass-6: adversarial closure re-verification + MCP tool-surface curation + docs-axis + Hub-parity decision"
swimlane: core
kind: spike
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-223048-0760
depends_on: []
blocked_by: []
references: []
---
# TASK-500: Modularity pass-6: adversarial closure re-verification + MCP tool-surface curation + docs-axis + Hub-parity decision

**Outcome (one sentence):** A verified pass-6 section appended to docs/engineering/modularity-audit-2026-06.md that (1) independently re-checks each FIXED/DONE closure claim against CURRENT code with real file:line evidence, flagging any regressions or over-claims; (2) resolves the tool-count truth (register says 87, grep finds 72) and delivers a concrete MCP tool-surface curation proposal addressing the owner's "too many tools → hallucination" complaint; (3) investigates the docs/related-files axis as a 6th module-disable dimension; (4) checks Hub config-tab ↔ core apply-path parity; (5) assesses the consumer-in-CI dogfood harness gap — plus DoR-complete follow-up tasks for every confirmed real gap and an owner decision table for deferred items.

## Work Log
- 2026-06-21 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-21 [claude]: committed c4dfb6bb · 1 file
- 2026-06-21 [claude]: Pass-6 done: 50-agent adversarial workflow re-verified the FIXED/DONE closure set against current HEAD — 35/36…
