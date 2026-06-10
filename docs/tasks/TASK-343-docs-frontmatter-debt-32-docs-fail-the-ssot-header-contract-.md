---
id: TASK-343
title: "Docs frontmatter debt: 32 docs fail the SSOT header contract + CLAUDE.md exact-count drift (hallucination seeds)"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 4h
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-112852-603a
depends_on: []
blocked_by: []
references: []
---
# TASK-343: Docs frontmatter debt: 32 docs fail the SSOT header contract + CLAUDE.md exact-count drift (hallucination seeds)

**Outcome (one sentence):** make docs-lint reports zero frontmatter errors (32 files get honest domain/layer/updated headers derived from their git last-commit date), and CLAUDE.md stops carrying exact artifact counts that drift (hooks '88/82' vs real 89/83, CLI '36' vs 40) — replaced with SSOT pointers.

## Work Log
- 2026-06-10 [claude]: Edit AGENTS.md
- 2026-06-10 [claude]: Edit branch-guard.sh
- 2026-06-10 [claude]: Edit AGENTS.md
- 2026-06-10 [claude]: Edit enforce-commit-message.sh
- 2026-06-10 [claude]: Edit enforce-verify.sh
- 2026-06-10 [claude]: Edit test-governor.sh
- 2026-06-10 [claude]: Edit search-enforce-inventory.sh
- 2026-06-10 [claude]: Edit nudge-task-discovery.sh
- 2026-06-10 [claude]: commit 763b6376ab — docs(governance): add SSOT front-matter headers to 32 docs; exclude task-detail template
- 2026-06-10 [claude]: commit 7eea75faa9 — docs(meta): replace drifted hook/CLI counts with SSOT pointers
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
