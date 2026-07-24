Run a Scrumban retrospective for the period specified by $ARGUMENTS (default: 14 days).

Steps:
1. Resolve period: if `$ARGUMENTS` is a number → days; if `$ARGUMENTS` is `week|month|quarter` → 7|30|90 days; if empty → 14 days.
2. Call MCP tool `cos_task_retro(since="Nd")` (canonical aggregation of completed + blocked + failure patterns; `since` is a duration string like "14d").
3. Call `cos_failure_pattern_query(limit=20)` to surface recurring failure modes (frequency-ranked `root_cause` categories from `backtrack_events`; treat count ≥ 2 as recurring — filter client-side).
4. Call `cos_metric_trend(metric="time_to_solution", window_days=N)` to detect process drift.
5. Read `$COS_PANEL_DIR/.clear1-bypass-log` (if present): each line is a self-issued `CLEAR 1` enforcement-bypass plus its justification. Report the count + justifications — a rising count means the discipline is being routed around, not internalized.
6. Promotion candidates: call `cos_learn_suggest(limit=20)` and filter client-side to **Trusted, not yet promoted** lessons (`confidence ≥ 0.7 AND times_validated ≥ 3`; suggest already excludes promoted rows). For each candidate propose a destination (an existing rule file section, or a skill) and show the draft from `cos_promote(pattern_id, target)` — **apply NOTHING without explicit user approval**. On approval, write the returned content to the agreed destination (governance edit — needs the task marker); the tool already stamped `promoted_to`, which removes the row from digest/suggest.
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
