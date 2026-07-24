---
id: TASK-538
title: "Thin comment-dense legacy in most-imitated src/core files (on-touch tech-debt: impact.py 75%, _shared.py 20%, graph_os/types.py)"
swimlane: core
kind: refactor
epic: null
labels: [tech-debt, comments, dogfood, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-538: Thin comment-dense legacy in most-imitated src/core files (on-touch tech-debt: impact.py 75%, _shared.py 20%, graph_os/types.py)

**Outcome (one sentence):** Remove the imitation SOURCE the harness "match surrounding density" instruction feeds on: bring the most-imitated comment-dense exemplars toward Rule-12-target density — strip/condense internal-helper docstrings and what-restating comments in src/core/thinking_os/impact.py, src/core/thinking_os/tools/_shared.py, and graph_os/types.py — keeping genuine non-obvious-WHY comments and public-API one-liners. No behavior change.

## Read First
- src/core/thinking_os/impact.py
- src/core/thinking_os/tools/_shared.py
- src/core/graph_os/types.py
- src/core/skills/clean-code/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a top comment-dense src/core file, **When** this task is applied, **Then** internal-helper docstrings are removed or condensed to a single non-obvious-WHY line per Rule 12, what-restating comments and provenance IDs are deleted, and the file's comment density materially drops.
**Given** the edits, **When** the matching Verification-Matrix suite runs (thinking_os / graph_os), **Then** it stays green with zero behavior change.
**Given** the imitation loop, **When** an agent later reads the thinned file, **Then** "match surrounding density" no longer pulls it toward over-commenting.

## Work Log
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit impact.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Edit memory.py
- 2026-06-24 [claude]: Tranche 1 done + verified. memory.py: 9/9 internal-helper docstrings → terse WHY comments (recency half-life, drift…
- 2026-06-24 [claude]: commit 52b1dd2d88 — refactor(thinking_os): thin internal-helper docstrings + what-comments (impact.py, memory.py)
