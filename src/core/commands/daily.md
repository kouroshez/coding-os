Run the Scrumban daily standup view and present a structured summary.

Steps:
1. Call MCP tool `cos_task_daily` (canonical source — already aggregates yesterday / today / blocked / WIP / streak).
2. Render in the template below (matches `task-driver` skill conventions). Use information ONLY from the tool envelope — do not fabricate task IDs or titles.
3. End with the next-action recommendation: which task should be picked up next, based on `cos_task_pick`.

Template:
```markdown
## Daily — YYYY-MM-DD

### Yesterday
- [TASK-NNN] {title} → moved to {status}, {one-line outcome}

### Today (candidates)
- [TASK-NNN] {title} ({swimlane}/{kind}, priority {P})

### Blocked
- [TASK-NNN] {title} — blocker: {reason}, since {date}

### WIP check
- in_progress: {n}/cap{cap}
- testing: {n}/cap{cap}
- violations: {none | list}

### Recommended next: TASK-NNN — {one-line reason}
```

If `cos_task_daily` returns empty (no tasks ever created), explain that the board is empty and offer to create a task via `cos_task_create`.

ADHD-friendly default: silent on broken streaks (per [task-driver](../skills/task-driver/SKILL.md) "Daily streak ≠ shame"). Only surface if the user asks.
