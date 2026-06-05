<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Severity, On-Call, Comms, Lifecycle

> P: Run an incident from detection to postmortem with a clear severity scale and roles.
> R: During an incident, or designing the on-call/runbook process before launch.
> S: Instrumentation that detects the incident — that's [observability](../../observability/SKILL.md).
> N: [SKILL.md](../SKILL.md), [incident-checklist.md](../assets/incident-checklist.md)

> Nav: [Skill](../SKILL.md)

The postmortem and runbook *document templates* are co-shipping SSOT — use them,
don't recreate: [post-mortem-template.md](../../../../docs/governance/_templates/post-mortem-template.md),
[runbook-template.md](../../../../docs/governance/_templates/runbook-template.md).
This reference is the *process*.

## Severity scale (tune per org)

| SEV | Meaning | Response |
|---|---|---|
| 1 | core down for many users / data loss / security breach | page now, incident commander, status page, all-hands |
| 2 | major degradation or core down with a workaround | page, dedicated responder, fix in hours |
| 3 | partial / minor impact | ticket + owner, normal hours |
| 4 | cosmetic / negligible | backlog |

`scripts/classify_severity.py` turns impact facts into a level so there's no
debate mid-incident. Data loss and security breach are **always** SEV1.

## Roles (even a 2-person team needs the split)

- **Incident Commander** — owns the response, makes calls, not hands-on-keyboard.
- **Operations** — the one making changes (one person touches prod, to avoid collisions).
- **Communications** — updates stakeholders/status page so the IC isn't interrupted.

For a small team one person may wear two hats — but name them, so nothing falls
through the gap.

## Lifecycle

1. **Detect** — an alert (symptom-based, links a runbook) or a report.
2. **Triage** — classify severity, declare the incident, assign roles.
3. **Mitigate first, diagnose later** — stop the bleeding (rollback is the most
   common and fastest mitigation — see [deployment-cicd](../../deployment-cicd/SKILL.md));
   root cause can wait until users are unblocked.
4. **Communicate** — regular updates on a cadence, even "still investigating".
5. **Resolve** — confirm recovery via the same telemetry that detected it.
6. **Postmortem** — blameless, within days, using the template. Action items have
   owners + dates, or they don't exist.

## Blameless postmortem

The question is "what about the system let this happen?", never "who messed up".
A human error that a system allowed is a system gap — add the guardrail (a test,
an alert, a check) so the next person can't make it. Track action items to done.
