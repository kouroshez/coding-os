---
id: TASK-1029
title: "Nothing asserts the verification matrix --extra groups exist in pyproject"
swimlane: cli
kind: test
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-31
started: 2026-08-31
completed: 2026-08-31
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1029: Nothing asserts the verification matrix --extra groups exist in pyproject

**Outcome (one sentence):** A rename of a dependency-extras group in pyproject.toml fails a test instead of silently breaking every Verification-Matrix row that names it.

## Read First
- tests/test_verification_matrix.py
- AGENTS.md
- pyproject.toml

The matrix rows carry their own invocation, e.g. `uv run --extra rag pytest ...`.
That `rag` is a second copy of a name whose only authority is
`pyproject.toml::[project.optional-dependencies]`. Nothing checks the two agree:
`grep -oE '\-\-extra [a-zA-Z_-]+' AGENTS.md` yields `graph_os` and `rag`, and
`grep extra tests/test_verification_matrix.py` yields nothing. Rename the group in
pyproject and every row naming it breaks at run time, far from the edit.

Raised by a reader on r/AI_Agents (2026-08-31): a declaration inherits the diligence
of whoever last touched it, so move it somewhere already load-bearing or guard it.
Deriving the invocation is out of scope here; this guards the declaration, which is
the smaller half and the one that has a seam today (`_matrix_commands()` already
parses every matrix command for the existing zero-collection guard).


## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Verification-Matrix command naming `--extra <group>`
  **When** `tests/test_verification_matrix.py` runs
  **Then** the test fails unless `<group>` appears in `pyproject.toml::[project.optional-dependencies]`.
- **Given** the extras group is renamed in pyproject.toml only
  **When** the suite runs
  **Then** it goes red naming the group and both files (negative control must be executed, not assumed).
- **Given** py3.10 is the supported floor
  **When** the test reads pyproject.toml
  **Then** it parses by text, not `tomllib` (precedent: tests/test_wheel_packaging.py).

## Work Log
- 2026-08-31 [claude]: Added _declared_extras() + test_every_extra_group_in_the_matrix_is_declared to tests/test_verification_matrix.py,…
- 2026-08-31 [claude]: Status transitioned to complete via cos task-done.
