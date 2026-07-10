---
id: TASK-809
title: "Resolve TodoWrite policy gap: fix dead track-discovery matcher + add in-turn-vs-Work-Log guidance"
swimlane: core
kind: docs
epic: null
labels: [governance, docs-update, ready]
status: complete
priority: P2
appetite: 2h
created: 2026-07-10
started: 2026-07-10
completed: 2026-07-10
agent_session: ses-claude-20260709-202023-30fe
depends_on: []
blocked_by: []
references: []
---
# TASK-809: Resolve TodoWrite policy gap: fix dead track-discovery matcher + add in-turn-vs-Work-Log guidance

**Outcome (one sentence):** The misleading dead TodoWrite reference in registry.yaml/track-discovery.sh is resolved (TodoWrite either added to the Claude PostToolUse hook_capabilities so discovery-scanning of todos actually fires, or dropped from the matcher so the SSOT stops declaring a matcher the renderer silently downgrades), adapter templates regenerated to match; and a one-line policy in thinking_os.md EXECUTE phase clarifies that persistent progress lives in the task Work Log (SSOT) while ephemeral TodoWrite is an allowed private in-turn scratchpad for a long multi-step EXECUTE — never a substitute for the Work Log. No parallel checklist/subtask subsystem is added (SSOT + Rule 22).

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/track-discovery.sh
- src/adapters/claude/adapter.yaml
- src/core/rules/thinking_os.md

## Work Log
- 2026-07-10 [claude]: Edit thinking_os.md
- 2026-07-10 [claude]: Edit track-discovery.sh
- 2026-07-10 [claude]: Edit registry.yaml
- 2026-07-10 [claude]: Edit no-parking-actionable-findings.md
- 2026-07-10 [claude]: commit e9b70b7f64 — fix(hooks): drop dead TodoWrite matcher from track-discovery, clarify Work-Log-vs-todo policy
- 2026-07-10 [claude]: Guide confirmed TodoWrite invalid+disabled matcher; dropped it from registry/hook, added Work-Log-vs-todo policy,…
- 2026-07-10 [claude]: Status transitioned to complete via cos task-done.
