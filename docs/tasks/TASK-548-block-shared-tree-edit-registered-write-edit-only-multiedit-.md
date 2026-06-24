---
id: TASK-548
title: "block-shared-tree-edit registered Write|Edit only \u2014 MultiEdit bypasses edit isolation"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: null
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-548: block-shared-tree-edit registered Write|Edit only — MultiEdit bypasses edit isolation

**Outcome (one sentence):** block-shared-tree-edit fires on MultiEdit (the matcher most real Claude edits emit), so pr-mode worktree edit isolation can no longer be bypassed via MultiEdit.

## Read First
- src/core/hooks/registry.yaml
- src/adapters/claude/settings.template.json
- tests/test_golden_parity.py
- tests/test_adapter_parity.py

## Repro Steps
1. COS_GIT_WORKFLOW=pr; agent edits a shared-checkout file. Claude SDK emits MultiEdit (its default for most edits).
2. PreToolUse matchers run; block-shared-tree-edit is registered `Write|Edit` only.
Expected: MultiEdit on the shared tree is BLOCKED.
Actual: MultiEdit matcher misses → hook never fires → agent edits the shared checkout unblocked (hook body already handles MultiEdit; only the registration is wrong).
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_GIT_WORKFLOW=pr and an agent issuing a MultiEdit on a file in the shared integration checkout
- **When** the PreToolUse matcher is evaluated
- **Then** block-shared-tree-edit runs (registry matcher Write|Edit|MultiEdit) and BLOCKs the edit; adapter templates + golden fixtures are regenerated and parity tests pass

## Work Log
- 2026-06-24 [claude]: Edit registry.yaml
