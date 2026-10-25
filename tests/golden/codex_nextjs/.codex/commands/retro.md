Run a Scrumban retrospective for the period specified by $ARGUMENTS (default: 14 days).

Steps:
1. Resolve period: if `$ARGUMENTS` is a number → days; if `$ARGUMENTS` is `week|month|quarter` → 7|30|90 days; if empty → 14 days.
2. Call MCP tool `cos_task_retro(since="Nd")` (canonical aggregation of completed + blocked + failure patterns; `since` is a duration string like "14d").
5. Read `$COS_PANEL_DIR/.clear1-bypass-log` (if present): each line is a self-issued `CLEAR 1` enforcement-bypass plus its justification. Report the count + justifications — a rising count means the discipline is being routed around, not internalized.
6. Promotion candidates: read `.agents/memory/MEMORY.md`. A memory whose rule the period's failures or backtracks kept breaking is a candidate to become a mechanism — a hook, rule, gate or skill section. Propose the destination and the draft — **apply NOTHING without explicit user approval** (a governance edit needs the task marker).
7. Render in the template below. The action items are the only place the agent should *propose* content beyond the data — every line needs an owner placeholder + due-date placeholder (the user fills them in).

Template:
```markdown
## Retro — YYYY-MM-DD (period: {N} days)

### What shipped ({count})
- [TASK-NNN] {title} → complete, {date}

### What broke / blocked ({count})
- [TASK-NNN] {title} — blocked for {days}; root cause: {category}

### Patterns (from cos_failure_pattern_query)
- {recurring category}: {N occurrences}; suggested mitigation: {action}

### Trend (time_to_solution)
- median {Nm} (vs {Nm} previous period) — {improving | stable | regressing}

### Self-issued CLEAR-1 bypasses ({count})
- {justification} — what discipline was skipped, and was it warranted

### Promotion candidates (Trusted lessons → durable rules; {count})
- [#{pattern_id}] {lesson one-liner} — validated {N}×; proposed destination: {rule/skill path} — approve?

### Action items
- [ ] {action} — @owner — due YYYY-MM-DD
```

No-blame rule (per [incident-response](../skills/incident-response/SKILL.md)): describe the failing system, never the person.
