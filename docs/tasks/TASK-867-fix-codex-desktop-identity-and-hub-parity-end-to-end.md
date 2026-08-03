---
id: TASK-867
title: "Fix Codex Desktop identity and Hub parity end to end"
swimlane: adapters
kind: bug
epic: null
labels: [codex, desktop, adapter, hub, hooks, skills, mcp, parity, dogfood, ready]
status: complete
priority: P0
appetite: 3d
created: 2026-08-03
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-codex-019fc9ac-216e-7211-a224-dad139ff5712
depends_on: []
blocked_by: []
references: []
---
# TASK-867: Fix Codex Desktop identity and Hub parity end to end

**Outcome (one sentence):** Codex Desktop is identified as Codex across hooks, MCP writes, state, board, sessions, Hub UI, and installed configuration, with documentation and live proof.

## Read First
- AGENTS.md
- README.md
- docs/adapters/codex.md
- docs/engineering/state-files.md
- docs/engineering/hub-architecture.md
- src/adapters/codex/adapter.yaml
- src/core/hooks/cos-env.sh

## Repro Steps
Run Codex Desktop in this repository with CODEX_SESSION_ID, CODEX_AGENT_DIR, and CODEX_HOME absent. Observe .coding-os/.agent=claude, active presence under .coding-os/claude, Hub showing agent=claude with model gpt-5.6-sol, and TASK-866 work-log entries labeled [claude].

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Codex Desktop invokes hooks without CODEX_* environment markers
- **When** any Codex lifecycle or direct hook runs
- **Then** state and presence are written under .coding-os/codex with ses-codex-* identity.

- **Given** Codex calls board MCP tools
- **When** tasks or work logs mutate
- **Then** explicit caller attribution is Codex and Hub board/session surfaces render Codex rather than Claude.

- **Given** the meta-project dogfoods Claude and Codex
- **When** configuration is rendered and installed
- **Then** both adapters are declared, hooks and skills are current, and generated/install drift checks pass.

- **Given** a fresh real Codex Desktop session
- **When** Hub APIs and UI are inspected
- **Then** header, Sessions, history, board, work logs, and traces consistently identify Codex.

- **Given** the implementation is complete
- **When** relevant README and adapter/Hub/state docs are audited
- **Then** setup, limitations, verification, and troubleshooting are current.

## Work Log
- 2026-08-03 [codex]: Implemented adapter-owned Codex identity for rendered hooks, shell subprocesses, MCP, SessionEnd presence,…
- 2026-08-03 [codex]: Verification passed: adapters 52, CLI 277, doctor identity/drift 3, renderer 8, verify-hooks, docs-lint, Ruff,…
- 2026-08-03 [claude]: committed 12a8bb65 · 25 files
- 2026-08-03 [codex]: Attribution correction: commit 12a8bb65 was executed by the already-open Desktop task before project shell config…
