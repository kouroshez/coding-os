---
id: TASK-518
title: "Hub git_settings (minimal, settings-gated, default-OFF): enabled + integration_branch + protected_branches"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, hub, settings]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-22
started: null
completed: null
agent_session: null
depends_on: [TASK-516]
blocked_by: []
references: []
---

# TASK-518: Hub git_settings (minimal, settings-gated, default-OFF): enabled + integration_branch + protected_branches

**Outcome (one sentence):** A settings-gated Git control surfaced as a new **"Git" sub-tab inside ConfigPage** (Config → stacks·skills·mcp·hooks·modules·**git**), reusing the SubNav pattern and the hub-settings.json backend — NOT a section in SettingsPage (model_routing stays in Diagnostics→Settings; Git lives in Config because it is project-structure config and that is where consumers look). Mirrors model_routing's settings-gated discipline (off by default = zero behavioral/cost change). `enabled` persists COS_GIT_WORKFLOW=pr into the adapter-injected agent env (the REAL enforcement seam — the inline per-command override is confirmed broken); `integration_branch` + `protected_branches` feed the branch-guard policy (P2/TASK-516) and the cos pr executor (P3/TASK-517); plus a read-only git-state health row (remote/gh/CI/required-check). _DEFAULTS + _PatchBody added in the SAME commit to avoid 422-ing the whole settings round-trip. Defers auto-push toggle, testing-role, and worktree-root override (anti-overengineering).

## Read First
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/ui/src/pages/SettingsPage.tsx
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** git_settings.enabled=false (default), **When** the agent works, **Then** behavior is byte-identical to current trunk (zero diff). **Given** the operator opens Config → Git and sets enabled=true + integration_branch + protected_branches (PATCH /api/settings), **When** the next agent session starts, **Then** COS_GIT_WORKFLOW=pr is present in the agent runtime env and branch-guard honors the protected list. **Given** the new Git sub-tab renders in ConfigPage (SubNav), a tests/test_hub_settings_git copy of the model_routing test, and `make docs-lint` with hub-architecture.md updated, **Then** green.

## Work Log
