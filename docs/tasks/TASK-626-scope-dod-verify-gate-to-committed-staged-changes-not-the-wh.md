---
id: TASK-626
title: "Scope DoD verify-gate to committed+staged changes, not the whole shared dirty tree"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: blocked
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: null
agent_session: ses-claude-20260627-161919-30e5
depends_on: []
blocked_by: []
references: []
---
# TASK-626: Scope DoD verify-gate to committed+staged changes, not the whole shared dirty tree

**Outcome (one sentence):** enforce-verify.sh computes required suites from this completion's deliberate changes (committed-unpushed + staged) instead of the entire working tree, so a concurrent sibling session's UNCOMMITTED edits in the shared trunk checkout can no longer force an unrelated heavy suite at task-done. Fail-open to the full dirty tree when the upstream base is unresolvable (fresh clone / no remote).

## Read First
- src/core/hooks/enforce-verify.sh
- src/core/board_os/verify_suites_cli.py
- src/core/board_os/verify-suites.yaml

## Repro Steps
Dogfooded 2026-06-27 (TASK-622 close): a docs/chore task-close demanded the 762s test-cli suite purely because a sibling session's uncommitted src/cli/renderer.py sat in the shared working tree; enforce-verify.sh:90 reads `git diff --name-only HEAD` (whole tree) and matched it to test-cli. COS_VERIFY_OVERRIDE was needed to close.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a sibling session has an uncommitted modification to src/cli/renderer.py in the shared checkout AND my docs-only task has its work committed **When** I run `cos task-done` for the docs task **Then** enforce-verify requires only docs-lint (not test-cli), because the unstaged sibling file is outside the committed+staged scope. - **Given** no `@{upstream}`/`origin/main` ref exists **When** the gate runs **Then** it falls back to the current `git diff HEAD` behavior (no regression, fail-open). - **Given** my own task committed a src/cli change **When** I close **Then** test-cli is still required (committed work stays gated).

## Work Log
- 2026-06-27 [claude]: Edit enforce-verify.sh
- 2026-06-27 [claude]: Investigated + REVERTED. Probed two scopings against the live tree: (a) committed+staged via origin/main..HEAD…
