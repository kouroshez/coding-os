---
id: TASK-845
title: "Reconcile memory.md + retro.md with the actual memory tools (record path, confidence, metric param)"
swimlane: docs
kind: docs
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-845: Reconcile memory.md + retro.md with the actual memory tools (record path, confidence, metric param)

**Outcome (one sentence):** memory.md and retro.md stop contradicting the shipped tools: (a) decisions/breakthroughs are recorded via cos_learn_narrative (cos_observation_record is edit-derived only, no freeform content); (b) confidence is system-computed by LTP/LTD via cos_learn_validate, not a number the agent sets; (c) cos_metric_trend is called with window_days, not the non-existent since_days kwarg. The rule now matches the (correct) agent-memory SKILL and the metrics.py signature.

## Read First
- src/core/rules/memory.md
- src/core/commands/retro.md
- src/core/thinking_os/tools/metrics.py
- .claude/skills/agent-memory/SKILL.md

## Work Log
- 2026-07-17 [claude]: Edit memory.md
- 2026-07-17 [claude]: Edit memory.md
- 2026-07-17 [claude]: Edit memory.md
- 2026-07-17 [claude]: Edit retro.md
- 2026-07-17 [claude]: Edit retro.md
- 2026-07-17 [claude]: Edit retro.md
- 2026-07-17 [claude]: Verified each documented call against the real MCP schema (api-contract-discipline): cos_task_retro→since,…
