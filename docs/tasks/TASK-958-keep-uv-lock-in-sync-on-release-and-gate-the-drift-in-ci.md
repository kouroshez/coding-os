---
id: TASK-958
title: "Keep uv.lock in sync on release and gate the drift in CI"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-13
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-958: Keep uv.lock in sync on release and gate the drift in CI

**Outcome (one sentence):** Every release commit carries a uv.lock whose coding-os version equals pyproject.toml's, and CI fails on any divergence.

## Read First
- docs/governance/release-process.md
- release-please-config.json
- .github/workflows/ci.yml

## Repro Steps
On main at v0.3.14: pyproject.toml says 0.3.14, uv.lock says 0.3.13. `uv lock --check` exits 1, `uv sync --locked` exits 1. CI never catches it because all 8 `uv sync` calls omit --locked/--frozen and silently re-resolve, so the drift has survived since 0.3.12.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** release-please bumps the version in pyproject.toml
  **When** it opens or refreshes the standing release PR
  **Then** uv.lock's `coding-os` version is bumped in that same PR.

- **Given** a tree whose uv.lock disagrees with pyproject.toml
  **When** CI runs
  **Then** the Lint job fails on `uv lock --check`.

- **Given** main after this change
  **When** `uv lock --check` runs
  **Then** it exits 0.

## Work Log
- 2026-08-13 [claude]: Edit release-please-config.json
- 2026-08-13 [claude]: Edit ci.yml
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit release-process.md
- 2026-08-13 [claude]: Edit ci.yml
- 2026-08-13 [claude]: commit 912f9025d0 — fix(release): bump uv.lock with pyproject.toml and gate the drift in CI
- 2026-08-13 [claude]: extra-files toml updater + `uv lock --check` above every uv sync; both halves verified locally
- 2026-08-13 [claude]: commit 912ccd7c3c — chore(board): record TASK-958 for the uv.lock release sync
- 2026-08-13 [claude]: commit 6fa4869942 — docs(insights): record why a gate below a self-healing command is a no-op
- 2026-08-13 [claude]: Status transitioned to complete via cos task-done.
