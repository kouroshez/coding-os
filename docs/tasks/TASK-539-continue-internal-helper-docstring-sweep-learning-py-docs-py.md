---
id: TASK-539
title: "Continue internal-helper docstring sweep \u2014 learning.py, docs.py (thinking_os), board_os/mcp_tools.py, graph_os hot helpers"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, comments, dogfood, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-539: Continue internal-helper docstring sweep — learning.py, docs.py (thinking_os), board_os/mcp_tools.py, graph_os hot helpers

**Outcome (one sentence):** Finish the Rule-12 internal-helper-docstring cleanup begun in TASK-538: remove or condense the remaining `def _helper` docstrings the imitation audit flagged — learning.py (19/25), docs.py (9/11) under src/core/thinking_os/tools, src/core/board_os/mcp_tools.py (29/53), and the graph_os hot helpers — converting genuine non-obvious WHY to a single terse comment, deleting what-restating docstrings, keeping @mcp.tool one-liners and module docstrings. Behavior-neutral.

## Read First
- src/core/thinking_os/tools/learning.py
- src/core/thinking_os/tools/docs.py
- src/core/board_os/mcp_tools.py
- src/core/skills/clean-code/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the remaining hot tool files (learning.py, docs.py, board_os/mcp_tools.py, graph_os helpers), **When** the sweep is applied, **Then** an AST check reports zero internal-helper (`def _name`) docstrings except genuine non-obvious WHY condensed to one terse line, and @mcp.tool/module docstrings are untouched.
**Given** the edits, **When** the matching Verification-Matrix suites run (thinking_os + board_os + graph_os), **Then** all stay green with zero behavior change.
**Given** an agent later reads these files, **When** it calibrates comment density, **Then** "match surrounding density" no longer pulls it toward over-commenting.

## Work Log
