<!-- domain:OPS | layer:postmortem | ssot:true | updated:2026-01-01 -->
# Post-Mortem — <YYYY-MM-DD> <Incident Title>

Purpose: Blameless retrospective for <incident>. Records what happened, why, and what changes prevent recurrence.
Read when: Investigating a similar failure, or onboarding to incident response in this domain.
Skip when: Looking for the runbook (use [runbook-template.md](./runbook-template.md) family).
Read next: [risk-register.md](../risk-register.md), <related ADR>

> Nav: [Post-Mortems Index](../postmortems/00-index.md)

---

## Summary

- **What happened:** <one sentence>
- **User impact:** <one sentence with concrete numbers — N users, X minutes, $Y revenue>
- **Status:** Resolved · Mitigated · Investigating
- **Severity:** P1 / P2 / P3
- **Detected by:** monitoring · user report · internal · audit

## Timeline (UTC)

| Time | Actor | Event |
|---|---|---|
| HH:MM | system | <metric crosses threshold> |
| HH:MM | <person> | acknowledges alert |
| HH:MM | <person> | identifies root cause |
| HH:MM | <person> | applies mitigation |
| HH:MM | system | metric returns to baseline |
| HH:MM | <person> | declares resolved |

Total user impact window: HH:MM → HH:MM.
Total response time: <minutes from detection to resolution>.

## Impact

- **Users affected:** <number / cohort / region>
- **Requests failed:** <number or %>
- **Data integrity:** <none lost · N records replayed · <other>>
- **Revenue / SLA:** <if applicable>
- **Internal cost:** <pages, hours, distraction>

## Root Cause

One paragraph. The technical cause, stated factually.

## Contributing Factors

- <Factor 1 — process, tooling, monitoring gap, etc.>
- <Factor 2>
- <Factor 3>

## What Went Well

- <Things that worked: alert fired, runbook covered, rollback fast>

## What Went Poorly

- <Things that didn't: detection latency, missing dashboard, paged the wrong person>

## Action Items

> Each action has an owner, a deadline, and a tracking ID. No "we should consider…" entries.

| ID | Action | Owner | Due | Status |
|---|---|---|---|---|
| AI-1 | <concrete change> | @user | YYYY-MM-DD | open |
| AI-2 | <concrete change> | @user | YYYY-MM-DD | open |
| AI-3 | <concrete change> | @user | YYYY-MM-DD | open |

## Lessons Learned

- <Generalizable insight 1>
- <Generalizable insight 2>

## Related Records

- ADR: <if a decision came out of this>
- Runbook: <created or updated>
- Risk register: <new entry id>
- Tracking task: TASK-NNN

---

> This is a **blameless** post-mortem. Names appear only in the timeline as actors, never as causes. Systems and processes fail; people work the systems.
