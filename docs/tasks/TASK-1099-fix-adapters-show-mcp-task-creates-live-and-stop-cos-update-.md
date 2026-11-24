---
id: TASK-1099
title: "fix(adapters): show MCP task creates live and stop cos update re-escaping settings.json"
swimlane: adapters
kind: bug
epic: null
labels: [adapters, hooks, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1099: fix(adapters): show MCP task creates live and stop cos update re-escaping settings.json

**Outcome (one sentence):** Every task create or move through the cos_task_* MCP tools shows its live line, and cos update and install.sh write byte-identical settings.json.

## Read First
- src/adapters/claude/adapter.yaml
- src/adapters/codex/adapter.yaml
- src/cli/hook_renderer.py
- src/cli/update.py
- src/core/rules/transparency-banner.md

## Repro Steps
Review of streamos sync diff: rendered settings.json had show-board-transition only under matcher mcp__coding-os__cos_task_move (adapter.yaml PostToolUse capabilities omit the other three), and HEAD had \ud83d escapes from src/cli/update.py json.dumps while install.sh wrote literal emoji, so the whole file churned.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the registry matcher for show-board-transition names cos_task_create, cos_task_move, cos_task_claim_next and cos_task_reclaim, **When** the Claude and Codex templates render, **Then** the PostToolUse group carries all four tokens.
- **Given** a consumer whose settings.json was written by install.sh, **When** cos update re-registers hooks, **Then** emoji stay literal and the file has no \u escapes.

## Work Log
- 2026-11-24 [claude]: Review of the streamos sync found two defects. (1) adapter.yaml PostToolUse capabilities listed only cos_task_move,…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
