---
id: TASK-343
title: "Docs frontmatter debt: 32 docs fail the SSOT header contract + CLAUDE.md exact-count drift (hallucination seeds)"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 4h
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-343: Docs frontmatter debt: 32 docs fail the SSOT header contract + CLAUDE.md exact-count drift (hallucination seeds)

**Outcome (one sentence):** make docs-lint reports zero frontmatter errors (32 files get honest domain/layer/updated headers derived from their git last-commit date), and CLAUDE.md stops carrying exact artifact counts that drift (hooks '88/82' vs real 89/83, CLI '36' vs 40) — replaced with SSOT pointers.

## Work Log
