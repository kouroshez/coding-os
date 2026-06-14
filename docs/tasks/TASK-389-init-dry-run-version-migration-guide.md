---
id: TASK-389
title: "Init dry-run + version migration guide"
swimlane: cli
kind: feature
epic: H-lifecycle
labels: [backlog, onboarding-program, ready]
status: in_progress
priority: P3
appetite: 1d
created: 2026-06-11
started: 2026-06-14
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-389: Init dry-run + version migration guide

**Outcome (one sentence):** `cos init --dry-run` previews the scaffold tree without writing; a migration guide documents upgrading pre-0.3 consumer projects.

## Read First
- src/cli/main.py (init flow; --dry-config from TASK-356 is the precedent)
- src/cli/_init_helpers.py
- docs/governance/release-process.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos init --template <x> --dry-run --yes`, **When** it runs, **Then** the would-be file tree (scaffold + links + composed configs) is printed (text and `--format json`) and ZERO writes occur anywhere (test asserts empty target + untouched registry).
- **Given** --dry-run combined with --preset, **When** it runs, **Then** the preset expansion is reflected in the preview.
- **Given** the migration guide, **When** `make docs-lint` runs, **Then** green; the guide covers pre-0.3 → current upgrade (cos update path, dangling-symlink repair, verify config refresh).
- **Given** the matrix, **When** the targeted dry-run test class in tests/test_cli.py runs, **Then** green.

## Work Log
