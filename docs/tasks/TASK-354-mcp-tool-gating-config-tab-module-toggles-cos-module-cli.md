---
id: TASK-354
title: "MCP tool gating + Config-tab module toggles + `cos module` CLI"
swimlane: "thinking_os"
kind: feature
epic: G-modularity
labels: [wave-3, onboarding-program, ready]
status: icebox
priority: P1
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: [TASK-349]
blocked_by: []
references: []
---

# TASK-354: MCP tool gating + Config-tab module toggles + `cos module` CLI

**Outcome (one sentence):** Tools of a disabled module return fail('module_disabled') with an enable hint instead of tool-not-found; Hub Config tab gains module toggle UI wired to settings API; `cos module enable/disable/list` regenerates dependent artifacts.

## Read First
- src/core/thinking_os/tools/_shared.py
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- docs/engineering/mcp-error-envelope.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the tasks module disabled, **When** any cos_task_* tool is invoked, **Then** it returns the Rule-13 envelope fail(category='module_disabled') naming the module and the enable command — never an unhandled error or tool-not-found.
- **Given** the Hub Config tab, **When** a non-kernel module is toggled, **Then** the change persists via the settings API, the UI reflects state on reload, and kernel modules render as locked (no toggle).
- **Given** `cos module disable docs`, **When** it completes, **Then** AGENTS.md/hook templates are regenerated automatically and `cos module list` shows per-module state with dependencies.
- **Given** the matrix, **When** thinking_os pytest + MCP self-test + `uv run pytest tests/test_cli.py -q` run, **Then** green with gating tests for at least one tool per gated family.

## Work Log
