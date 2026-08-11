---
id: TASK-934
title: "governance: add algorithmic-efficiency and no-hardcoded-environment rules to the quality layer"
swimlane: docs
kind: docs
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-11
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-934: governance: add algorithmic-efficiency and no-hardcoded-environment rules to the quality layer

**Outcome (one sentence):** clean-code SKILL.md gains a section 8 on algorithmic efficiency and runtime cost plus a no-hardcoded-environment-values subsection, both wired into the Post-Code Checklist, the Critical Rules index in CLAUDE.md/AGENTS.md, and a warn-tier check in block-bad-patterns.sh; make verify-hooks and docs-lint pass.

## Read First
- src/core/skills/clean-code/SKILL.md
- src/core/rules/anti-overengineering.md
- src/core/hooks/block-bad-patterns.sh

## Work Log
- 2026-08-11 [claude]: Edit algorithmic-efficiency.md
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: Edit SKILL.md
- 2026-08-11 [claude]: Edit critical-rules.md
- 2026-08-11 [claude]: Edit critical-rules.md
- 2026-08-11 [claude]: Edit AGENTS.md
- 2026-08-11 [claude]: Edit check_runtime_cost.py
- 2026-08-11 [claude]: Edit block-bad-patterns.sh
- 2026-08-11 [claude]: Edit test_hooks_file_size.py
- 2026-08-11 [claude]: Edit check_runtime_cost.py
- 2026-08-11 [claude]: commit 6cb07efa44 — feat(rules): add Critical Rule 27 — runtime cost is correctness
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
