---
id: TASK-061
title: "Hot-path hook perf: convert python file_path extraction to jq in PreToolUse Write|Edit hooks"
swimlane: core
kind: chore
epic: workflow-integrity
labels: [performance, hooks]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-02
started: 2026-06-02
completed: 2026-06-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-061: Hot-path hook perf: convert python file_path extraction to jq in PreToolUse Write|Edit hooks

**Outcome (one sentence):** Measured: 23 PreToolUse Write|Edit hooks cost ~1007ms per edit even on a no-op file. 4 hooks (enforce-graph-context, validate-task-frontmatter, enforce-wip-limit, enforce-task-transition) spawn python3 -c only to extract tool_input.file_path (~30ms each) before deciding applicability — convert to jq (the pattern the other 19 hooks already use) to cut ~120ms off every edit. Mechanical, no enforcement-logic change, verified by re-timing + smoke tests + verify-hooks.

## Work Log
- 2026-06-02 [claude]: Status transitioned to complete via cos task-done.
