---
id: TASK-957
title: "Extend script smoke coverage to src/scripts/dev and add its verification matrix row"
swimlane: infra
kind: test
epic: null
labels: [docs-update, ready]
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
# TASK-957: Extend script smoke coverage to src/scripts/dev and add its verification matrix row

**Outcome (one sentence):** The entrypoint smoke test covers every script under src/scripts including the dev subdirectory, using one path-based import mechanism that needs no package marker, and AGENTS.md carries a Verification Matrix row so a script edit has a documented command.

## Read First
- tests/test_script_entrypoints.py
- AGENTS.md
- src/core/rules/test-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** eight scripts under src/scripts/dev, two of which the Makefile invokes, that the smoke test does not reach
**When** the discovery walks the tree recursively and non-argparse scripts are loaded by file path rather than as scripts.<name>
**Then** every script under src/scripts is smoke-tested without adding a package marker, a floor guard fails if discovery collapses, and AGENTS.md names the command that runs this suite.

## Work Log
- 2026-08-12 [claude]: Edit test_script_entrypoints.py
- 2026-08-12 [claude]: Edit test_script_entrypoints.py
- 2026-08-12 [claude]: Edit test_script_entrypoints.py
- 2026-08-12 [claude]: Edit AGENTS.md
- 2026-08-12 [claude]: commit 08f1fb13d3 — test(scripts): smoke every script under src/scripts, dev subtree included
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
