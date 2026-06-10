<!-- domain:XXX | layer:playbook | ssot:true | updated:2026-05-21 -->
# Playbook — <Workflow Name>

Purpose: Repeatable procedure for <task>. Optimized so a competent agent or engineer can execute end-to-end without reading sibling docs.
Read when: <Trigger condition — "before merging X", "when adding a new Y", etc.>
Skip when: <Negative trigger — "if it's just a typo fix", "if there's already a runbook">.
Read next: <1–3 most relevant sibling docs>

> Nav: [Playbooks Index](../00-index.md)

---

## When to use

- ✅ <Concrete situation 1>
- ✅ <Concrete situation 2>
- ❌ Not for: <out-of-scope situation>

## Inputs

| Name | Type | Source | Required |
|---|---|---|---|
| `<input>` | `<type>` | <where it comes from> | ✅ / ❌ |
| `<input>` | `<type>` | <…> | ✅ / ❌ |

## Pre-conditions

- [ ] <Permission / access ready>
- [ ] <Dependency in place>
- [ ] <Branch / state requirement>

## Steps

> Each step states the change, the verification gate, and the rollback. Don't advance without verification.

### Step 1 — <Action verb + target>

```bash
<exact command>
```

**Why:** <one-line rationale referencing a rule/spec/ADR>.
**Verify:** <observable check>.
**Rollback:** <single command>.

### Step 2 — <next action>

…

### Step N — <Final action>

…

## Verification (full procedure done)

- [ ] <Test command + expected pass>
- [ ] <Lint / type-check passes>
- [ ] <Doc updated / reference added>
- [ ] <Trace event present in logs>

## Failure Modes & Recovery

| Symptom | Likely cause | Action |
|---|---|---|
| <error message> | <root> | <fix or escalate path> |
| <hang / timeout> | <root> | <fix> |
| <silent no-op> | <root> | <fix> |

## Out-of-scope

- <Things this playbook deliberately does NOT cover, with pointer to where they live>

## Related

- ADR: <link>
- Runbook: <if there's an alert form>
- Spec: <if this implements a contract>

---

> Stale playbooks are worse than missing ones. If a step here no longer matches reality, fix it the same day you discover the drift.
