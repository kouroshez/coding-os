<!-- domain:OPS | layer:runbook | ssot:true | updated:{{DATE}} -->
# Runbook — <Alert / Incident Type>

Purpose: Step-by-step remediation when <trigger> fires. Optimized for an on-call engineer at 3am, not a leisurely read.
Read when: <Alert name> fires, OR a user reports symptom matching this runbook.
Skip when: The fault is upstream of this service — escalate per §6.
Read next: [post-mortem-template.md](./post-mortem-template.md), [<related runbook>](./<related>.md)

> Nav: [Runbooks Index](../../../ops/runbooks/00-index.md)

---

## 1. Trigger

- **Alert name:** `<exact alert id from monitoring system>`
- **Source:** `<dashboard / alertmanager / sentry / on-call queue>`
- **Severity ladder:** `P1: …` · `P2: …` · `P3: …`
- **Symptom phrasing (for user reports):** "<what user sees>"

## 2. Pre-conditions

Before executing the steps below, verify:

- [ ] You have <permission set> (e.g. prod read on the database).
- [ ] No deployment is in flight (`<deploy dashboard link>`).
- [ ] Active incident channel does not already own this alert.

If any pre-condition fails → §6 Escalation.

## 3. Steps

> Run in order. Each step has a verification gate; do not advance without it.

### Step 1 — <Identify the failing component>

```bash
<exact command>
```

**Verify:** <what output proves it worked>.
**If empty / different:** stop, escalate (this runbook does not apply).

### Step 2 — <Stabilize>

```bash
<exact command>
```

**Verify:** <metric returns to baseline within N minutes>.
**Rollback:** `<one-line revert command>`.

### Step 3 — <Confirm recovery>

- Check `<dashboard URL>` — <metric> below threshold for ≥5 minutes.
- Run `<smoke test command>`; expect `<output>`.

## 4. Verification

- [ ] Alert is acknowledged AND auto-resolved within 10 minutes.
- [ ] No follow-on alerts in the same family fired within 30 minutes.
- [ ] User-reported symptoms (if any) confirmed gone.

## 5. Rollback

If steps 1–3 fail or made things worse:

1. `<exact rollback command>` — restores previous known-good state.
2. Notify `<channel>` with rollback timestamp.
3. Open a P1 ticket linking this runbook + observed failure mode.

## 6. Escalation

| Symptom | Escalate to |
|---|---|
| Database is the root cause | DBA on-call (`<channel>`) |
| Upstream provider degradation | Vendor support (`<contact>`) |
| Code regression suspected | Service owner (`<owner>`) |
| Security indicators | Security on-call (`<channel>`) |

## 7. Aftermath

- If incident lasted >15 minutes OR caused user-visible impact → write a post-mortem within 48 hours using [post-mortem-template.md](./post-mortem-template.md).
- If this runbook missed a step → file a PR updating it the same week.
- If the alert was false-positive → tune threshold per [alerting-policy.md](../../engineering/alerting-policy.md).

---

> Last drilled: <YYYY-MM-DD> — runbooks are stale unless practiced. Re-drill quarterly or after any structural change to the underlying system.
