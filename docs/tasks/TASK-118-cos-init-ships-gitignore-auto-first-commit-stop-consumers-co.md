---
id: TASK-118
title: "cos init ships .gitignore + auto first commit — stop consumers committing the mutating runtime DB"
swimlane: cli
kind: feature
epic: doc-system
labels: [docs-system, dogfood, git, audit-d6-f1, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-118: cos init ships .gitignore + auto first commit — stop consumers committing the mutating runtime DB

**Outcome (one sentence):** Every cos init creates a .gitignore (excludes .coding-os/*.db, traces/, panels/, *.db-wal/shm) AND an initial 'chore: scaffold coding-os project' commit, so docs are tracked from line one and the binary runtime DB + agent-memory PII never enter git history. Skips both when nested in an existing repo.

## Read First
- src/cli/_init_helpers.py
- src/cli/main.py
- src/templates/_base/scaffold/

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos init` runs on a fresh, non-nested directory with git available
- **When** the scaffold is generated
- **Then** a `.gitignore` is written excluding `*.db`/`*.db-wal`/`*.db-shm` + `.coding-os/*` (carving back the 3 config files), AND exactly one baseline `chore: scaffold coding-os project` commit tracks the configs + .gitignore but NOT the runtime DB / traces / panels; nested-in-an-existing-repo skips both git-init and the commit. Verified by tests/test_cli.py::test_creates_gitignore, ::test_baseline_commit_excludes_runtime_db, and tests/test_cli_init_flags.py::test_git_init_skipped_when_nested.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
