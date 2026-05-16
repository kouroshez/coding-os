Run a Scrumban retrospective for the period specified by $ARGUMENTS (default: 14 days).

Steps:
1. Resolve period: if `$ARGUMENTS` is a number → days; if `$ARGUMENTS` is `week|month|quarter` → 7|30|90 days; if empty → 14 days.
2. Call MCP tool `cos_task_retro(period_days=N)` (canonical aggregation of completed + blocked + failure patterns).
3. Call `cos_failure_pattern_query(since_days=N, min_count=2)` to surface recurring failure modes.
4. Call `cos_metric_trend(metric="time_to_solution", since_days=N)` to detect process drift.
5. Render in the template below. The action items are the only place the agent should *propose* content beyond the data — every line needs an owner placeholder + due-date placeholder (the user fills them in).

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

### Action items
- [ ] {action} — @owner — due YYYY-MM-DD
```

No-blame rule (per [incident-response](../skills/incident-response/SKILL.md)): describe the failing system, never the person.
