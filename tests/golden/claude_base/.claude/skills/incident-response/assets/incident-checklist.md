<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Incident Response Checklist

During an incident, in order.

## Declare
- [ ] Severity classified (`python3 scripts/classify_severity.py ...` — data loss/breach = SEV1).
- [ ] Incident declared in the agreed channel; roles assigned (Commander / Ops / Comms).
- [ ] Status page updated if user-facing.

## Mitigate (before diagnosing)
- [ ] Stop the bleeding — rollback the last deploy is the fastest common fix.
- [ ] Only ONE person changes prod (Ops) to avoid collisions.
- [ ] Mitigation confirmed via the telemetry that detected the issue.

## Communicate
- [ ] Stakeholder updates on a cadence (even "still investigating").
- [ ] Customer-facing comms if SLA/contract requires.

## Resolve & learn
- [ ] Recovery confirmed; incident closed.
- [ ] Blameless postmortem scheduled (use docs/governance/_templates/post-mortem-template.md).
- [ ] Action items have an owner + a date; tracked to done.
- [ ] A guardrail added (test/alert/check) so the same class can't recur.

## Pre-launch (design the process before you need it)
- [ ] On-call rotation + escalation defined.
- [ ] Runbooks written for known failure modes (docs/governance/_templates/runbook-template.md).
- [ ] Every alert links to a runbook and is actionable.
