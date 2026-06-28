---
id: TASK-624
title: "apply ultra-review fixes: write-once materializers + world-driven dockerfiles + CI install gaps"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: null
completed: null
agent_session: ses-claude-20260626-165558-a565
depends_on: []
blocked_by: []
references: []
---
# TASK-624: apply ultra-review fixes: write-once materializers + world-driven dockerfiles + CI install gaps

**Outcome (one sentence):** The ultra-review's confirmed findings on the stack-factory-v2 CLI diff are fixed: materialize_ci_workflow/dockerfiles never clobber consumer edits (write-once, ensure_* idiom), materialize_dockerfiles is world-driven (overlay+relocation aware, skips bare/exempt backends), _CI_LANGUAGE_INSTALL covers ruby/rust/java/csharp/dart, the glob-root split is guarded, and the promoted stack-lint repo-root check no longer hard-fails under a non-editable install.

## Read First
- src/cli/_init_helpers.py
- src/cli/renderer.py
- src/cli/stack_lint.py
- src/cli/main.py
- src/cli/update.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
GIVEN cos update on a project with an edited ci.yml/Dockerfile WHEN it runs THEN the consumer's edits are preserved (write-once). GIVEN a rails consumer with cicd on THEN the ruby CI leg runs bundle install before bundle exec. GIVEN go-plain (exempt, no verify row) THEN no Dockerfile is generated. THEN uv run pytest tests/test_cli.py -q is green and TestDockerfile/TestCiWorkflow/TestStackBundleLint pass.

## Work Log
