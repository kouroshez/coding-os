---
id: TASK-921
title: "cos init refuses piped stdin: non-TTY guard breaks the agent prompt and reddens the nightly suite"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-09
started: 2026-08-09
completed: 2026-08-09
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-921: cos init refuses piped stdin: non-TTY guard breaks the agent prompt and reddens the nightly suite

**Outcome (one sentence):** cos init accepts piped stdin for the agent prompt (echo claude | cos init -d DIR works), truly-empty stdin still exits 2, and tests/test_cli_init_interactive.py passes.

## Read First
- src/cli/main.py
- tests/test_cli_init_interactive.py
- src/core/commands/new-project.md

## Repro Steps
1. `mkdir /tmp/p && printf 'claude\n0\ny\n' | cos init --no-git -d /tmp/p`
2. Observe the agent prompt never consumes the piped answer.
Expected: exit 0, `/tmp/p/.coding-os.yaml` created (the pipe carries the answer).
Actual: exit 2, "ERROR: non-interactive shell — pass --agent ...". Same failure
reddened `nightly slow suite` in CI run 31246768706 via
`tests/test_cli_init_interactive.py::TestInteractivePrompts::test_prompts_agent_when_missing`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** stdin is a pipe carrying "claude"
  **When** cos init runs without --agent
  **Then** the agent prompt consumes it and init succeeds (exit 0)
- **Given** stdin is closed/empty and --agent is absent
  **When** cos init runs
  **Then** it exits 2 with a clear message and never guesses
- **Given** the slow suite
  **When** tests/test_cli_init_interactive.py runs
  **Then** all tests pass

## Work Log
- 2026-08-09 [claude]: Edit main.py
- 2026-08-09 [claude]: Edit ci.yml
- 2026-08-09 [claude]: Edit ci.yml
- 2026-08-09 [claude]: Edit ci-gates.md
- 2026-08-09 [claude]: Edit ci-gates.md
- 2026-08-09 [claude]: Edit ci-gates.md
- 2026-08-09 [claude]: Edit GOVERNANCE.md
- 2026-08-09 [claude]: Edit third-party-token-bench.md
- 2026-08-09 [claude]: Edit main.py
- 2026-08-09 [claude]: Edit parser.py
- 2026-08-09 [claude]: Edit parser.py
- 2026-08-09 [claude]: Edit board_commands.py
- 2026-08-09 [claude]: Edit board_commands.py
- 2026-08-09 [claude]: Edit board_commands.py
- 2026-08-09 [claude]: Edit board_commands.py
- 2026-08-09 [claude]: Edit ci.yml
- 2026-08-09 [claude]: Edit test_frontmatter_repair.py
- 2026-08-09 [claude]: Edit test_frontmatter_repair.py
- 2026-08-09 [claude]: Edit db-reset.md
- 2026-08-09 [claude]: Status transitioned to complete via cos task-done.
