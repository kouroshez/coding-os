---
id: TASK-559
title: "materialize_makefile_targets dirties the meta-repo's tracked Makefile \u2014 only wire -include when a stack contributes targets"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-154810-74c2
depends_on: []
blocked_by: []
references: []
---
# TASK-559: materialize_makefile_targets dirties the meta-repo's tracked Makefile — only wire -include when a stack contributes targets

**Outcome (one sentence):** cos update / cos init stop dirtying a no-stack-target project's hand-authored Makefile. materialize_makefile_targets wires the `-include .coding-os/Makefile.stacks` line only when world.makefile_targets is non-empty (the include appears exactly when a stack first contributes a target), so the meta-repo (meta stack = zero targets) keeps a clean tracked Makefile across every update. General fix, no meta-repo special-case. The gitignored .coding-os/Makefile.stacks placeholder is still written.

## Read First
- src/cli/_init_helpers.py
- src/cli/renderer.py
- tests/test_makefile_materialize.py

## Repro Steps
`cos update` (NOT `make sync` — adapter install.sh never materializes) calls materialize_makefile_targets(project=coding-os). _ensure_stacks_include (_init_helpers.py:495,500-510) appends `-include .coding-os/Makefile.stacks` to the hand-authored root Makefile even though the meta stack contributes zero targets (render_makefile_targets returns the "No stack-contributed" placeholder when world.makefile_targets is empty), surfacing as a persistent `M Makefile` dirty tree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project whose aggregated world has NO stack-contributed make targets (meta-repo / meta stack), **When** materialize_makefile_targets runs, **Then** the tracked Makefile is NOT mutated (no `-include` appended) and only the gitignored .coding-os/Makefile.stacks placeholder is written.
**Given** a project whose world HAS stack targets (e.g. fastapi), **When** materialize runs, **Then** the `-include .coding-os/Makefile.stacks` line is wired in (behavior unchanged).
**Given** the meta-repo's locally-polluted Makefile, **When** I git restore it and re-run the fixed materialize, **Then** the working tree stays clean (no re-pollution).

## Work Log
- 2026-06-24 [claude]: Edit _init_helpers.py
- 2026-06-24 [claude]: Edit test_makefile_materialize.py
- 2026-06-24 [claude]: commit 2235b835ce — fix(cli): materialize wires Makefile -include only when a stack contributes targets
- 2026-06-24 [claude]: Root-caused the M Makefile dirty tree: NOT make sync (adapter install.sh never materializes — verified) but cos…
