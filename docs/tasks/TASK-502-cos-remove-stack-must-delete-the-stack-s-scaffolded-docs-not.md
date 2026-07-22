---
id: TASK-502
title: "cos remove-stack must delete the stack's scaffolded docs, not just rules (modularity DOC-5)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-21
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-502: cos remove-stack must delete the stack's scaffolded docs, not just rules (modularity DOC-5)

**Outcome (one sentence):** cos remove-stack go also removes the stack's scaffold-doc outputs (docs/engineering/go-rules.md, docs/playbooks/go-service.md), backup-guarded and ref-counted, so no stale stack guidance survives removal.

## Read First
- src/cli/remove_stack.py
- src/cli/main.py
- src/templates/go/scaffold/docs/playbooks/go-service.md
- docs/engineering/modularity-audit-2026-06.md

## Repro Steps
1. In a consumer, `cos add-stack go`, then `cos remove-stack go`.
2. Inspect docs/engineering/ and docs/playbooks/ for go-rules.md / go-service.md.
Expected: removed (or .bak'd) along with the rest of the stack cascade.
Actual: remove_stack.py:224 deletes only `<rules_dir>/<stack>-*.md`; the scaffolded docs/ outputs survive as orphaned, stale stack guidance (§8.1 "full cascade" over-claim recurs at the docs axis).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a consumer with the go stack installed (go-rules.md + go-service.md scaffolded)
**When** cos remove-stack go runs
**Then** go-rules.md and go-service.md are removed or .bak'd, AND a doc also contributed by a remaining stack is preserved, AND a user-modified doc is skipped not clobbered, AND the removal is manifest-driven (never glob-guessed).

## Work Log
- 2026-06-21 [claude]: Edit remove_stack.py
- 2026-06-21 [claude]: Edit remove_stack.py
- 2026-06-21 [claude]: Edit remove_stack.py
- 2026-06-21 [claude]: Edit remove_stack.py
- 2026-06-21 [claude]: Edit remove_stack.py
- 2026-06-21 [claude]: Edit test_remove_stack.py
- 2026-06-21 [claude]: Edit verify_doc502.py
- 2026-06-21 [claude]: Added _remove_stack_docs (manifest-driven from stack scaffold/docs, backup-before-delete, ref-counted vs…
- 2026-06-21 [claude]: Edit config.py
- 2026-06-21 [claude]: Edit config.py
- 2026-06-21 [claude]: Edit ConfigPage.tsx
