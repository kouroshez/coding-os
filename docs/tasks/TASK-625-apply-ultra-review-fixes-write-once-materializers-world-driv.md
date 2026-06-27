---
id: TASK-625
title: "apply ultra-review fixes: write-once materializers + world-driven dockerfiles + CI install gaps"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260626-165558-a565
depends_on: []
blocked_by: []
references: []
---
# TASK-625: apply ultra-review fixes: write-once materializers + world-driven dockerfiles + CI install gaps

**Outcome (one sentence):** The ultra-review's confirmed findings on the stack-factory-v2 CLI diff are fixed — materialize_ci_workflow/dockerfiles never clobber consumer edits (write-once, the `ensure_*` idiom), materialize_dockerfiles is world-driven (overlay + relocation aware via `world.anatomy` + `world.verify_rows`, so bare/exempt backends like go-plain get none), `_CI_LANGUAGE_INSTALL` covers ruby/rust/java/csharp/dart, the glob-root split is guarded, and the promoted stack-lint repo-root check no longer hard-fails under a non-editable install.

## Read First
- src/cli/_init_helpers.py
- src/cli/renderer.py
- src/cli/stack_lint.py

## Repro Steps
1. `cos init --profile full -t django` then edit `.github/workflows/ci.yml` (add a deploy job) and `src/backend/Dockerfile` (change CMD).
2. Run `cos update` → observe both files are silently overwritten back to the generated skeleton (consumer edits lost).
3. `cos init --profile full -t rails` with cicd on → the generated ci.yml ruby leg runs `bundle exec rubocop` with no prior `bundle install` → CI red.
4. A go-plain backend (exempt, no verify row) gets a Dockerfile whose `go build ./cmd/api` targets a non-existent dir.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a consumer-edited ci.yml or Dockerfile, **When** `cos update` runs, **Then** the existing file is preserved (write-once — only absent files are written).
**Given** a rails consumer with the cicd module on, **When** CI runs, **Then** the ruby leg runs `bundle install` before `bundle exec`.
**Given** go-plain (exempt, no verify row), **When** init runs, **Then** no Dockerfile is generated.
**Then** `uv run pytest tests/test_cli.py -q` is green and TestDockerfile / TestCiWorkflow / TestStackBundleLint pass.

## Work Log
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit _init_helpers.py
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit subsystems.yaml
- 2026-06-27 [claude]: Edit main.py
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit test_cli.py
- 2026-06-27 [claude]: Edit test_cli.py
- 2026-06-27 [claude]: Applied 9 ultra-review findings: (#1/#2) both materializers now write-once (ensure_* idiom) — cos update never…
- 2026-06-27 [claude]: committed d206735e · 6 files
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
