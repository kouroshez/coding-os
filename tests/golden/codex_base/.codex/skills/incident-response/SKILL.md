---
name: incident-response
tier: workflow
domain: [infra]
description: Production incident handling — severity classification, runbook execution, communication, postmortem. Use when something is on fire (CHAOTIC quadrant), when designing a runbook before launch, after an incident to drive the postmortem, or to define the SEV scale + on-call rotation. Pairs with observability (alerts → runbook) and thinking_os (CHAOTIC routing) and deployment-cicd (rollback as the most-used incident action).
last_reviewed: "2026-05-11"
---

# Incident Response — Stop the Bleeding, Then Diagnose

A practical playbook for handling production incidents and learning from them. Aligned with Google SRE practices and the PagerDuty incident-response framework, refined for 2026 SaaS reality.

## When to Use This Skill

- **In an incident** — pages firing, users complaining, error rate spiked. Load this skill **first**, before diagnosing.
- **Before launch** — writing the runbook for a feature.
- **After an incident** — driving the postmortem.
- Designing the SEV classification.
- Defining the on-call rotation.
- Choosing tools (PagerDuty / Opsgenie / FireHydrant / incident.io).

If the user says "the API is down" / "users can't log in" / "we have an outage" — this skill, immediately.

## The Three-Phase Loop

```
   1. Stabilize        2. Diagnose        3. Resolve
   (5 min)             (30-90 min)        (variable)
   stop the bleeding    understand cause   actual fix
        │                  │                  │
        └──────────────────┴──────────────────┘
                 ↓
            Postmortem (within 5 business days)
```

The order is fixed. **Diagnosis before stabilization wastes the most time**, because users keep suffering while you read logs. Stabilize first — even if the fix is hacky — then diagnose.

## Phase 1 — Stabilize (the first 5 minutes)

When the page fires:

1. **Acknowledge the page.** Don't drop it on someone else's screen.
2. **Open the war room.** Slack thread, dedicated channel, Zoom — one place for the team.
3. **Declare a SEV.** Stops debate over urgency. See SEV scale below.
4. **Roll back, scale up, or feature-flag off.** In that order of preference.
   - Rollback the deploy if the timing matches.
   - Scale up if saturation is the signal.
   - Flip the feature flag off if a specific feature is broken.
5. **Communicate.** Status page, internal status, customer support team. "We're investigating an issue affecting X." Don't speculate on cause yet.

**Hard rule:** in the first 5 minutes you take **safe reversible actions only**. Rollback is reversible. `kubectl delete pod` is not.

## SEV Scale — Stop the Argument

| SEV | Definition | Examples | Response |
|---|---|---|---|
| **SEV-1** | Critical: full or near-full outage of a major function. Revenue or trust at risk. | Login down, payment processing failed, data corruption | Page on-call + secondary + manager. War room within 5 min. Status page update within 10 min. CEO briefed within 30 min. |
| **SEV-2** | Major: significant degradation. One important function broken; workaround may exist. | Search returning empty, exports failing, region-specific outage | Page on-call. War room within 15 min. Status page update within 30 min. |
| **SEV-3** | Minor: limited-scope issue, workaround clear. | Spelling error in production, slow endpoint not on critical path | Ticket + assign. Fix within next business day. |
| **SEV-4** | Cosmetic / non-urgent | UI alignment bug, log spam | Backlog. Fix when convenient. |

**SEV is set at acknowledgement** and can be re-classified as you learn more. Better to over-classify and downgrade than under-classify and miss the escalation window.

## Phase 2 — Diagnose (the next 30-90 minutes)

Now read logs, traces, metrics — using [observability](../observability/SKILL.md):

1. **Dashboards first.** Service dashboard with golden signals (latency / traffic / errors / saturation).
2. **Look at the deploy timeline.** If errors started at 14:32 and a deploy went out at 14:31, the deploy is your suspect. (You already rolled it back in Phase 1.)
3. **Trace a failing request.** `trace_id` from a recent error log → full trace shows which span broke.
4. **Compare to a known-good window.** "What changed in the last hour" is more informative than "what does the dashboard show now".
5. **Hypothesis-driven.** Form a hypothesis, look for confirming + disconfirming evidence. "Database connection pool exhausted because of the new endpoint" → look at pool depth metric AND the new endpoint's traffic.

Document everything in the war room thread. Future-you (writing the postmortem) will thank present-you.

## Phase 3 — Resolve

The resolve action is one of:

- **Rollback** — already done in Phase 1 if it was a deploy.
- **Patch** — small forward fix. Reviewed and deployed via the normal pipeline (don't skip CI even in an incident — you'll cause incident #2).
- **Scale** — add capacity, increase rate limits, raise quotas. Document the scale change so it's not forgotten.
- **Feature flag** — disable the offending feature.
- **Operate around** — sometimes the resolve is "shift traffic to the working region while we fix the broken one".

**Hard rule:** the resolve must include "how do we prevent this from re-firing in the next hour?" Not "how do we prevent it long-term" — that's the postmortem.

## Communication During an Incident

### Internal

- War room channel — running thread, append everything.
- Engineering channel — periodic summary every 30 min: "Status: investigating. Hypothesis: database pool saturation. ETA: unknown."
- Customer support — written summary they can paste to customers: "We're aware of intermittent login errors and are working on a fix."

### External (status page)

- Within 10 min of SEV-1: "Investigating reports of login errors."
- Update every 30 min even if no progress: "Still investigating. We'll update by HH:MM."
- Resolved post: include start time, end time, scope (% of users), and root cause (one sentence).

### Anti-patterns

- "Probably a database thing" — speculation creates rumors.
- Going silent for an hour — silence is worse than "still investigating".
- "Our engineers are working hard" — say what specifically.
- Apology theater without root-cause communication.

## On-Call Rotation — Sustainable Design

- **Rotation length:** 1 week. Shorter is more disruptive, longer is more burnout.
- **Pair primary + secondary.** Secondary covers if primary doesn't ack within 15 min.
- **Follow-the-sun if global.** No one on-call at 03:00 their time more than once per quarter.
- **Page budget:** target ≤ 2 pages per on-call week. More than that = alert hygiene work this quarter.
- **Compensation:** time-off-in-lieu for off-hours pages, even if you "didn't really do much".
- **No-blame culture.** The on-call who clicked the wrong rollback button isn't fired. They're given training and a better rollback button.

## Postmortem — within 5 business days

The postmortem is **not optional**. Every SEV-1 and SEV-2 gets one. Template:

```markdown
# Postmortem: <title>

**Severity:** SEV-1
**Date:** 2026-MM-DD
**Authors:** @owner, @secondary
**Status:** Draft | Reviewed | Approved

## Summary
One paragraph. What happened, who was affected, how long, root cause.

## Impact
- Users affected: ~X% / ~N users
- Duration: HH:MM to HH:MM UTC (Y minutes)
- Revenue impact: $X (if known)
- SLO impact: error budget consumed = Z%

## Timeline (UTC)
- 14:31 — Deploy of commit abc123 to production
- 14:33 — First Sentry alerts (payment.captured failures)
- 14:35 — On-call paged
- 14:37 — War room opened, SEV-1 declared
- 14:39 — Rollback initiated
- 14:42 — Error rate returns to baseline
- 14:50 — Status page updated to "monitoring"
- 15:10 — Status page resolved

## Root cause
Specific. "The new payment.capture endpoint did not handle Stripe's idempotency-key-conflict error. When deploy hit the production traffic mix, ~3% of captures returned a 4xx that the frontend treated as terminal."

## Resolution
What action ended the incident. (Rollback, in this case.)

## Five whys (or chain-of-causes)
1. Why did payment fail? Endpoint didn't handle idempotency conflict.
2. Why didn't it handle that? Test fixtures didn't cover that branch.
3. Why didn't test fixtures cover it? Stripe sandbox doesn't easily produce that error.
4. Why didn't we record-replay? Recording tooling wasn't set up for this endpoint.
5. Why? The pattern existed for other endpoints but wasn't generalized.

## What went well
- Rollback in 11 minutes from page to resolved.
- Status page updated on schedule.

## What went poorly
- Pre-merge testing didn't catch the idempotency case.
- Initial dashboard didn't show payment-specific error rate, only total 4xx rate.

## Action items (with owners + due dates)
- [ ] @alice — Add idempotency-conflict test case to payment.capture suite (due 2026-MM-DD)
- [ ] @bob — Generalize Stripe-error-replay fixture across endpoints (due 2026-MM-DD)
- [ ] @carol — Add payment-specific error-rate panel to service dashboard (due 2026-MM-DD)
- [ ] @dave — Add SLO + burn-rate alert for payment.capture (due 2026-MM-DD)

## Lessons learned (one-liners worth remembering)
- ...
```

**No-blame rule:** the postmortem names actions and systems, not people-as-failures. "@alice deployed the bad code" is wrong. "The pre-merge test suite did not cover the failing case" is right.

## Runbook — write before launch

Every service should ship with a runbook. One markdown file per service. Sections:

- **What this service does** (one paragraph)
- **Owner team + on-call rotation pointer**
- **Service SLO** (what we promise)
- **Dashboards** (link to golden signals)
- **Alerts → actions** (this alert means X, do Y)
- **Common issues + fixes** (the top 5 things that have gone wrong)
- **Rollback procedure** (one command, tested)
- **Escalation contacts**

Runbooks rot fast — quarterly refresh in the on-call rotation handoff.

## When the Incident Doesn't End

- **Hour 2:** swap primary on-call out. Fresh eyes catch things the tired ones miss.
- **Hour 4:** if SEV-1 still active, escalate to engineering leadership for support resources.
- **Hour 8:** if still active, that's a special incident — formally declare a "major incident" with daily executive comms.

## Anti-patterns

- **Heroes who solve incidents alone** — the team can't learn or recover sustainably.
- **No runbooks** — every incident is a from-scratch investigation.
- **Blame in the postmortem** — kills psychological safety, future incidents get hidden.
- **No action items from postmortems** — same incident in 3 months.
- **Action items without owners + due dates** — never done.
- **Skipping the postmortem because "it was small"** — every SEV-1/2 gets one.
- **Pre-incident testing of the rollback procedure missing** — first time you roll back is in the incident; the rollback fails.

## See also

- [observability](../observability/SKILL.md) — alerts come from here.
- [thinking_os](../thinking_os/SKILL.md) — CHAOTIC quadrant routes here (act → stabilize → then diagnose).
- [deployment-cicd](../deployment-cicd/SKILL.md) — rollback is the most-used incident action.
- [security-web](../security-web/SKILL.md) — when the incident is a security event, different playbook (containment, evidence preservation, comms differ).
