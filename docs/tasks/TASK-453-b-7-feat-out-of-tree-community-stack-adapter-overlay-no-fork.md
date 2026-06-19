---
id: TASK-453
title: "B-7 feat: out-of-tree community stack/adapter overlay (no-fork plugin path, PLUG-1)"
swimlane: cli
kind: feature
epic: null
labels: [modularity-audit-pass3, plugin-dx, PLUG-1, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-19
started: 2026-06-19
completed: null
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-453: B-7 feat: out-of-tree community stack/adapter overlay (no-fork plugin path, PLUG-1)

**Outcome (one sentence):** A third party adds a stack ($COS_USER_TEMPLATES_DIR/<id>/stack.yaml) or adapter ($COS_USER_ADAPTERS_DIR/<id>/adapter.yaml, default ~/.coding-os/{templates,adapters}) and the registries discover it WITHOUT forking the repo — mirroring the existing community-skill model. load_stack_registry + load_adapter_registry gained overlay_dirs (defaults to the resolved user dir, empty unless it exists so CI is a no-op); a community id may NOT shadow a bundled one (bundled kept), and a malformed community adapter fails SOFT (skipped, never crashing the CLI). stack_lint opts out (lints only bundled stacks). Closes the make-or-break gap for the community-plugin goal. Deferred (noted, not built per Raptor — zero consumers yet): trust-tier/consent + security-scan like community skills.

## Read First
- src/cli/_resources.py
- src/cli/stack_registry.py
- src/cli/adapter_registry.py
- src/cli/skill_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a stack/adapter in a tmp overlay dir **When** the registry loads with overlay_dirs **Then** it is discovered alongside the bundled ones. - **Given** a community id colliding with a bundled one **When** loaded **Then** the bundled profile is kept + a no-shadow warning. - **Given** $COS_USER_TEMPLATES_DIR set and overlay_dirs unset **When** loaded **Then** the env dir resolves automatically. - **Given** a malformed community adapter **When** loaded **Then** it is skipped, not raised. - **Given** the 32 registry tests **When** run **Then** all pass.

## Work Log
- 2026-06-19 [claude]: commit 567b1d3384 — feat(cli): out-of-tree community stack/adapter overlay — no-fork plugins (PLUG-1)
