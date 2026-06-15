---
id: TASK-387
title: "Brownfield adopt \u2014 `cos adopt` overlays coding-os onto an existing repo incrementally"
swimlane: cli
kind: feature
epic: H-lifecycle
labels: [backlog, onboarding-program, ready]
status: in_progress
priority: P2
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-387: Brownfield adopt — `cos adopt` overlays coding-os onto an existing repo incrementally

**Outcome (one sentence):** `cos adopt` (or init --adopt) layers .coding-os state, adapters and docs onto an existing codebase without touching user code, detecting stack(s) and proposing anatomy mapping.

## Read First
- src/cli/main.py (init flow + _detect_existing_install)
- src/cli/_init_helpers.py
- src/cli/registry.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an existing non-empty repo without .coding-os, **When** `cos adopt --agent claude --yes` runs, **Then** .coding-os/, adapter dirs and AGENTS.md are added and NO pre-existing user file is modified or deleted (test asserts before/after content hashes of seeded user files).
- **Given** stack detection, **When** package.json / pyproject.toml / go.mod markers are present, **Then** the detected stacks are proposed (non-interactive: echoed) and the confirmed list lands in .coding-os.yaml — no anatomy relocation of existing user code is ever attempted.
- **Given** a repo that already has coding-os, **When** adopt runs, **Then** it pivots to the idempotent sync path (same as re-init) instead of double-installing.
- **Given** the matrix, **When** the targeted adopt test class in tests/test_cli.py runs, **Then** green.

## Work Log
