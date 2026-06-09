---
id: TASK-277
title: "governance: remove the exhaustive-intent/audit enforcement layer \u2014 board+task system is enough"
swimlane: core
kind: refactor
epic: hub-redesign
labels: [ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-277: governance: remove the exhaustive-intent/audit enforcement layer — board+task system is enough

**Outcome (one sentence):** The exhaustive-intent/audit-checklist layer is fully removed — its 8 hooks, the banner audit= field, the SessionStart intent/resume cards, the completion-guardian exhaustive branch, the rules/docs and the audit-*.md artifacts — leaving the board+task system as the single workflow, with all docs realigned and the suite green.

## Read First
- src/core/hooks/registry.yaml — the 8 layer hooks
- src/core/hooks/session-context.sh — audit= banner field (~485)
- src/core/thinking_os/completion_guardian.py — exhaustive branch vs task-closure
- src/core/rules/auto-mode-vs-exhaustive.md, docs/engineering/intent-vocabulary.md, docs/_meta/audit-checklist-template.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session, **When** any prompt uses exhaustive vocabulary, **Then** no .intent.json is written, no audit-*.md is required, no Stop-guardian exhaustive gate fires, and the banner has no audit= field.
- **Given** the hook registry, **When** adapter templates are regenerated and installed, **Then** none of the 8 layer hooks render and verify-hooks + the board/thinking_os matrix suites stay green.
- **Given** the docs, **When** the layer is removed, **Then** auto-mode-vs-exhaustive.md / intent-vocabulary.md / audit templates are gone and CLAUDE.md/AGENTS.md no longer reference the layer (task-closure via warn-abandoned-task + reclaim stays intact).

## Work Log
- 2026-06-08 [claude]: Exhaustive-intent/audit layer functionally REMOVED + green: 8 hooks deleted from registry+scripts (detect-exhaustive-int
- 2026-06-09 [claude]: Dead-code pass complete: deleted completion_guardian.py + its test + the orphaned extract_intent.py helper; removed the 
