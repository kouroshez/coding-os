---
id: TASK-495
title: "Persist a 1-2 sentence value-deliberation in the work-log for COMPLICATED+ gates"
swimlane: core
kind: docs
epic: teach-why-alignment
labels: [teach-why, thinking-os, worklog, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: [TASK-491]
blocked_by: []
references: []
---

# TASK-495: Persist a 1-2 sentence value-deliberation in the work-log for COMPLICATED+ gates

**Outcome (one sentence):** The Record Gate captures complexity (CLEAR 1 / COMPLICATED 3) but never WHY a chosen approach is right against the project's values — yet the article's strongest data-efficiency result is that demonstrations+value-deliberation beat demonstrations alone (22%->3% vs 22->15%). For COMPLICATED+ gates ONLY, the Plan phase appends a 1-2 sentence "why this approach honors <constitution value>" to the work-log via the existing cos_work_log_append (no new tool). Light/CLEAR gates skip it so casual-work cost discipline is preserved. Makes deliberation a cheap, persisted, auditable artifact that also feeds the memory/learning loop. Codified as guidance in src/core/rules/thinking_os.md; NOT enforced by a new hook and NOT gating task-close (avoid rationale-theater).

## Read First
- src/core/rules/thinking_os.md
- src/core/skills/thinking_os/SKILL.md
- docs/governance/constitution.md
- src/core/rules/memory.md

## Work Log
