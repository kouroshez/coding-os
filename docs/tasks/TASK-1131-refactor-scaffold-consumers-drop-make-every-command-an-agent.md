---
id: TASK-1131
title: "refactor(scaffold): consumers drop make; every command an agent is told to run starts with cos"
swimlane: templates
kind: refactor
epic: null
labels: [docs-update, governance, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-11-25
started: 2026-11-25
completed: null
agent_session: ses-claude-20261125-165238-7b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-1131: refactor(scaffold): consumers drop make; every command an agent is told to run starts with cos

**Outcome (one sentence):** A consumer project ships no Makefile.base or Makefile.stacks, and its AGENTS.md, rules, skills and docs name only cos commands, with the stack's lint and test reachable through cos.

## Read First
- src/templates/_base/Makefile.base
- src/cli/renderer.py
- src/cli/_init_phase.py
- src/cli/update.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold, **When** its files are listed, **Then** there is no .coding-os/Makefile.base or Makefile.stacks and no Makefile written by cos.
- **Given** the shipped AGENTS.md, rules, skills and docs, **When** grepped for `make <target>`, **Then** nothing matches outside a user-owned file.
- **Given** a stack with lint/test commands in stack.yaml, **When** the agent runs the cos command named in AGENTS.md, **Then** those commands run.
- **Given** an existing project whose Makefile includes Makefile.base, **When** `cos update` runs, **Then** the include lines and cos-owned files are removed and the user's own targets are kept.

## Work Log
- 2026-11-26 [claude]: commit 8ee11c7714 — docs(anatomy): consumers ship no Makefile; stack commands run through cos run
- 2026-11-26 [claude]: makefile_targets->commands (28 stacks, schema); init writes none of Makefile/Makefile.base/.stacks;…
- 2026-11-26 [claude]: commit 7673bfe255 — refactor(scaffold): consumers ship no Makefile; stack commands run through cos run
- 2026-11-26 [claude]: commit e0655ced53 — docs(anatomy): cos update rewrites the make commands it wrote into AGENTS.md
- 2026-11-26 [claude]: commit 114be5f23c — docs(tasks): TASK-1131 work log
- 2026-11-26 [claude]: green: lint, size, docs-lint, verify-hooks, golden+fail_closed+rules_fresh 34 (after golden-capture), unit 99, rag 5,…
- 2026-11-26 [claude]: commit 1203b572e5 — fix(scaffold): cos doc-lint satisfies the docs-lint gate; add/remove-stack keep cos run in step
- 2026-11-26 [claude]: r1 rework 1203b572: suite aliases (docs-lint=cos doc-lint|make docs-lint), cos-aware matcher+recorder,…
- 2026-11-26 [claude]: commit 92421678fe — fix(scaffold): exact cos match for verify suites; migrate legacy task/log make names
- 2026-11-26 [claude]: Rework round 2 committed 92421678: exact cos-segment match for verify suites (cos doc-lint <file>/--help no longer…
