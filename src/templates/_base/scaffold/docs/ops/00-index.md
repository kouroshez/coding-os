<!-- domain:OPS | layer:index | ssot:true | updated:{{DATE}} -->
# Operations — Index

Purpose: Navigation hub for operational runbooks and procedures.
Read when: Deploying, debugging production, responding to an incident, or onboarding to ops.
Skip when: The task is purely development-time (no production impact).
Read next: The specific runbook relevant to your situation.

> Nav: [Docs Index](../00-index.md)

## Suggested Runbooks

Populate as the project matures:

- `monitoring.md` — Alerts, dashboards, on-call rotation
- `backup-recovery.md` — Backup schedule, restore procedure, RTO/RPO
- `zero-downtime-deploy.md` — Blue/green or rolling deploy procedure
- `secrets-rotation.md` — How to rotate API keys, passwords, tokens
- `staging-refresh.md` — How to refresh staging from production (anonymized)
- `incident-response.md` — Severity levels, escalation, post-mortem template
- `go-live-checklist.md` — Pre-launch verification checklist
- `database-migrations.md` — How to safely apply schema migrations in production

## Format

Each runbook follows this structure:

```markdown
# Runbook Title

## When to use this

(symptom or trigger)

## Prerequisites

(access, tools, credentials needed)

## Procedure

1. Step 1
2. Step 2
3. Verify: (how to confirm success)

## Rollback

(how to undo if step N fails)

## Post-procedure

(notification, documentation, follow-up)
```

## Authoring Rules

- Runbooks must be testable. Run them in staging before adding to ops/.
- Never reference secret values inline. Use environment variable names.
- Each runbook lists prerequisites explicitly — no "obvious" assumptions.
- Update the runbook immediately after any incident reveals a missing step.
