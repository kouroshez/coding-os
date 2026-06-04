---
id: TASK-060
title: "Workflow-integrity follow-ups: capture-audit hook, cos web merge, docs-first-protocol alignment"
swimlane: core
kind: chore
epic: workflow-integrity
labels: [cleanup, hooks, documentation]
status: complete
priority: P3
appetite: "1d"
created: 2026-06-02
started: 2026-06-02
completed: 2026-06-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-060: Workflow-integrity follow-ups: capture-audit hook, cos web merge, docs-first-protocol alignment

**Outcome (one sentence):** Close the 3 items deferred from TASK-059: (1) add capture-audit.sh PostToolUse hook to auto-fire cos_audit_log_record on docs/** Write/Edit (fact-capture symmetry with capture-observation.sh); (2) merge cos web into cos hub start --foreground and drop the duplicate launcher; (3) align docs/governance/docs-first-protocol.md to teach semantic ops (cos_classify_prompt for gate, cos task-start for doc-anchor) instead of raw write-state.sh, matching Rule 25.

## Work Log
- 2026-06-02 [claude]: All 3 deferred items landed — capture-audit.sh hook (523b85a), cos web merged into `cos hub start --foreground` (5701930), docs-first-protocol Rule 25 alignment (c39d5dd).
