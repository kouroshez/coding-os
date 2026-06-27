---
id: TASK-611
title: "(post-backfill) promote stack-lint runtime-manifest/lint-config/reference-integrity SOFT to HARD"
swimlane: cli
kind: chore
epic: stack-factory-v2
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260626-165558-a565
depends_on: [TASK-605, TASK-606, TASK-607, TASK-608, TASK-599]
blocked_by: []
references: []
---
# TASK-611: (post-backfill) promote stack-lint runtime-manifest/lint-config/reference-integrity SOFT to HARD

**Outcome (one sentence):** After bootable + skill backfill closes the gaps, flip the T3 (TASK-598) SOFT checks — runtime-manifest, lint-config-where-commanded, reference-integrity — to HARD/blocking so a future stack can never regress below the v2 bar. Deliberately left SOFT until now to avoid turning CI red across 8 stacks at once (the staged promotion the adversarial critic insisted on).

## Work Log
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit test_template_scaffold.py
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit stack-factory-v2-epic.md
- 2026-06-27 [claude]: Done: promoted 3 stack-lint Factory-v2 checks SOFT->HARD (reference-integrity rule+DOMAIN_ROUTES, runtime-manifest,…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-27 [claude]: committed d59a071a · 3 files
