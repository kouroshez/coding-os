---
id: TASK-538
title: "Thin comment-dense legacy in most-imitated src/core files (on-touch tech-debt: impact.py 75%, _shared.py 20%, graph_os/types.py)"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, comments, dogfood]
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

# TASK-538: Thin comment-dense legacy in most-imitated src/core files (on-touch tech-debt: impact.py 75%, _shared.py 20%, graph_os/types.py)

**Outcome (one sentence):** Remove the imitation SOURCE the harness "match surrounding density" instruction feeds on: bring the most-imitated comment-dense exemplars toward Rule-12-target density on touch — strip/condense internal-helper docstrings and what-restating comments in src/core/thinking_os/impact.py, src/core/thinking_os/tools/_shared.py, and the docstring-heavy graph_os/types.py contracts — keeping only non-obvious-WHY comments. Opportunistic/on-touch, never a big-bang diff. No behavior change.

## Read First
- src/core/thinking_os/impact.py
- src/core/thinking_os/tools/_shared.py
- src/core/graph_os/types.py
- src/core/skills/clean-code/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
Given a top comment-dense src/core file is touched for other work, When this task is applied to it, Then internal-helper docstrings are removed or condensed to a single non-obvious-WHY line per Rule 12, what-restating comments are deleted, and the file's comment density materially drops.
Given the edits, When the matching Verification-Matrix suite runs (thinking_os / graph_os), Then it stays green with zero behavior change.
Given the imitation loop, When an agent later reads the thinned file, Then "match surrounding density" no longer pulls it toward over-commenting.

## Work Log
