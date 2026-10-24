---
id: TASK-1071
title: "fix(hooks): helpers that need yaml or a coding-os package run under bare python3 and silently no-op"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P0
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1071: fix(hooks): helpers that need yaml or a coding-os package run under bare python3 and silently no-op

**Outcome (one sentence):** Every hook helper that imports PyYAML or a coding-os package (board_os, thinking_os, graph_os, …) runs under the cos interpreter, so the graph-context gate, the skill primer, task-frontmatter validation and the other helper-backed checks actually run in coding-os and in consumers.

## Read First
- docs/engineering/hooks-reference.md

## Repro Steps
1. `python3 src/core/hooks/_helpers/graph_context_match.py .coding-os/rag-config.yaml src/core/thinking_os/tools/tasks.py` → `no`; with the cos interpreter → `yes`.
2. `.hooks.log`: every `[enforce-graph-context]` line in coding-os (7) and streamos (21) is `[skip]`.
3. skill_primer.py → 0 chars under python3, 2849 under cos; validate_task_frontmatter.py → "board_os import failed".

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the system python3 has no PyYAML **When** enforce-graph-context sees an edit to a file matching graph.enforce_context_on **Then** the helper answers yes and the hook warns or blocks
- **Given** a SessionStart **When** session-skill-primer runs **Then** it emits the primer context instead of nothing
- **Given** `cos` is not installed **When** a hook resolves its interpreter **Then** it falls back to python3 exactly as before

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
