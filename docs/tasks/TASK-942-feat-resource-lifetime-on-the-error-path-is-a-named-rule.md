---
id: TASK-942
title: "feat: resource lifetime on the error path is a named rule"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-942: feat: resource lifetime on the error path is a named rule

**Outcome (one sentence):** Every acquired resource — connection, transaction, file handle, lock, subprocess — has one owner and one release path that also runs when the body raises, stated as a rule the agent reads before writing the acquisition.

## Read First
- src/core/skills/clean-code/SKILL.md
- src/core/skills/clean-code/references/error-handling.md
- src/core/graph_os/backends/_sqlite_write.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the clean-code skill **When** an agent opens a resource **Then** the rule names the context-manager obligation and the failure it prevents. **Given** the sqlite write-lock incident **When** the rule is written **Then** it cites that concrete failure rather than an abstract principle. **Given** the rule lands **Then** make docs-lint passes.

## Work Log
- 2026-08-12 [claude]: Edit SKILL.md
- 2026-08-12 [claude]: Edit error-handling.md
- 2026-08-12 [claude]: commit d26fd8f3b7 — docs(clean-code): name resource lifetime on the failing path as a rule
- 2026-08-12 [claude]: SKILL.md 1d + references/error-handling.md 1d (py+ts pairs) citing the sqlite write-lock incident; docs-lint OK;…
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-12 [claude]: Edit block-bad-patterns.sh
- 2026-08-12 [claude]: Edit block-bad-patterns.sh
- 2026-08-12 [claude]: Edit test_hooks_file_size.py
- 2026-08-12 [claude]: Edit test_hooks_file_size.py
- 2026-08-12 [claude]: commit 03223e2ed0 — feat(hooks): make the documented 300-line budget visible at write time
