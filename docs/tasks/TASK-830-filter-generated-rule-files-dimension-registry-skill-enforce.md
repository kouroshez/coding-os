---
id: TASK-830
title: "Filter generated rule files (dimension-registry, skill-enforcement) to installed stacks in consumer renders"
swimlane: core
kind: spike
epic: null
labels: [context-economy, regen-pipeline, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-07-16
started: 2026-08-02
completed: 2026-08-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-830: Filter generated rule files (dimension-registry, skill-enforcement) to installed stacks in consumer renders

**Outcome (one sentence):** dimension-registry.md (8.3K) + skill-enforcement.md (9.8K) inject all ~20 stacks into every session even where one stack is installed; in the meta-repo all templates count as installed so the win needs analysis: decide whether the regen pipeline should emit per-project filtered variants (consumers get only their stack; meta keeps meta + actively-edited template) and implement if the token saving justifies it. Caveat from audit: when editing src/templates/<stack>/ the agent may legitimately need that stack's rows.

## Work Log
- 2026-07-17 [claude]: Scope correction before pickup: install-adapter.sh already EXCLUDES dimension-registry.md + skill-enforcement.md from…
- 2026-07-17 [claude]: committed e0dc8f82 · 1 file
- 2026-08-02 [claude]: Spike resolved by inspection+execution: consumer renders NEVER ship dimension-registry/skill-enforcement (golden…
