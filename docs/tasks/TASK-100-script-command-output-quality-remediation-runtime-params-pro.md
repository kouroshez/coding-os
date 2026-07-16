---
id: TASK-100
title: "Script/command output-quality remediation \u2014 runtime params, progress, error-handling, stdout/stderr discipline across make+cos+scripts+hooks+tests"
swimlane: infra
kind: chore
epic: null
labels: [scripts, output-quality, audit, tech-debt, ci-trust, ready]
status: archive
priority: P1
appetite: 3d
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-06
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-100: Script/command output-quality remediation — runtime params, progress, error-handling, stdout/stderr discipline across make+cos+scripts+hooks+tests

**Outcome (one sentence):** Every make target, cos CLI command, standalone script, hook, and test obeys the 7 script-output non-negotiables (runtime args, fail-closed, idempotent, observable progress, stdout=result/stderr=narration, algo-honest, header). Headline bugs fixed first: make-verify greenwash + the src/-reorg stale-path cluster.

## Work Log
- 2026-06-07 [claude]: Completion review (reclaimed zombie): 7/8 batches verified real — greenwash gates (test-mcp now exit-gated), stale src/
