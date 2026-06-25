---
id: TASK-570
title: "On-touch thin the top-5 comment-dense files (graph.py/server.py/database.py/test_cli.py/test_hooks.py) \u2014 never bulk"
swimlane: core
kind: refactor
epic: null
labels: [comments, tech-debt, deferred, on-touch]
status: archive
priority: P3
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: ses-claude-20260624-214606-5dfd
depends_on: []
blocked_by: []
references: []
---
# TASK-570: On-touch thin the top-5 comment-dense files (graph.py/server.py/database.py/test_cli.py/test_hooks.py) — never bulk

**Outcome (one sentence):** Reduce the imitation gradient (TASK-568 diagnosis R4): TASK-538 thinned only 2 of 557 files, leaving the densest neighbors the harness 'match surrounding density' force pulls toward — graph.py (993 comment-lines), server.py (879), database.py (410), test_cli.py (426, #1 densest test file), test_hooks.py (152). Thin internal-helper docstrings + what-comments to near-zero WHY-only ON THE NEXT TASK THAT TOUCHES EACH FILE — never a bulk 20k-line sweep (massive review/merge-conflict blast radius, would trip test-discipline/governance gates). This is a standing on-touch practice, closed file-by-file as each is next edited.

## Read First
- src/core/skills/clean-code/SKILL.md
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a future task edits one of the 5 listed files, **When** the edit lands, **Then** that file's internal-helper docstrings + code-restating comments are thinned to WHY-only as part of the same change (no separate churn).
- **Given** any of these files, **When** thinning, **Then** module/@mcp.tool one-line docstrings are preserved (Rule 12 exception) and no bulk cross-file rewrite is committed.

## Work Log
