---
description: Memory vs SSOT boundary policy — when to use agent memory, when to use docs, when to use code.
globs: "**/*"
alwaysApply: true
last_reviewed: "2026-05-11"
---

# Memory Policy

> Source of truth for the canonical layering: [docs/governance/wrapper-derivation.md](../../docs/governance/wrapper-derivation.md). This rule states the operational policy in one place; the SSOT explains the *why*.

## The Four Layers (mandatory mental model)

Every fact in the project lives in exactly **one** of these four layers. Putting the same fact in two = drift bug waiting to happen.

| Layer | Tool | What lives there | Lifetime |
|---|---|---|---|
| **Code** | `Read` / `cos_graph_*` | Implementations, contracts in code | Until refactor |
| **Docs** | `cos_doc_search` | Specs, playbooks, ADRs, runbooks | Until superseded |
| **Tasks** | `cos_task_*` | What's in flight / queued / blocked / done | Until archived |
| **Agent memory** | `cos_search` / `cos_observation_record` / `cos_learn_*` | Cross-session patterns, breakthroughs, decisions, failure modes | Long-lived, decays |

**When unsure which layer:** default to the graph/code layer (`cos_graph_*`) for structural and "how does X work" questions; fall to memory only for cross-session recall. The four-layer table above is ordered by this precedence — code/graph first, memory last.

## When to write to agent memory (and when NOT to)

Use `cos_observation_record` / `cos_learn_extract` for:

- **Breakthroughs:** non-obvious insight discovered this session that would speed up a future session ("schema migration X needed a backfill before the NOT NULL constraint").
- **Failure modes:** specific bug → root cause → fix pattern, especially recurring ones.
- **Decisions:** trade-off + reasoning when the alternative was non-obvious.
- **Cross-session context:** a fact about the project that won't be obvious from reading the code (e.g., "the perf budget is set by the SLA contract, not by team preference").

**Do NOT save to memory** (it pollutes ranking + wastes tokens):

- Anything already in the code → use `cos_graph_*` / `Read`.
- Anything already in docs → use `cos_doc_search`.
- Anything in `git log` / `git blame` → use those.
- Current-session task state → use `cos_task_*` and `.task-current`.
- "I just did X" recap — that's the work log, not memory.

## When to read from agent memory

In the **Orient** phase of the Core Loop, after Classify but before Plan:

```
cos_search("query about past patterns / similar work", min_confidence=0.3, since_days=90)
cos_learn_suggest(domain="...", complexity="...")   # ranked patterns for the task context
cos_timeline(days=14)                                # what changed recently
```

If `cos_search` returns 0 hits with min_confidence=0.3 + since_days=90, the memory layer has no signal — fall through to docs (`cos_doc_search`) or code (`cos_graph_*`).

## Memory hygiene rules

1. **Every observation has a confidence + impact score.** Default confidence 0.5; raise to 0.8+ only after a second confirming session. Inflated confidence = ranking pollution.
2. **Decay is automatic.** Old low-confidence patterns are deprioritized in ranking — don't manually delete unless wrong-and-actively-misleading.
3. **Use `cos_search` with `min_confidence=0.3`** when you want only high-trust patterns.
4. **Use `since_days=90`** when the question implies "recent" (e.g., "how have we handled X lately").
5. **Tag with `domain` + `swimlane`** when known — narrows future retrieval.

## Cross-session reasoning (the killer feature)

Agent memory's value is **N-th session > 1st session**. Pattern:

- Session 1: encounter problem, solve it, record observation.
- Session 4: similar problem appears → `cos_search` finds the prior solution → 10× faster.

If sessions aren't getting faster on similar problems, the memory write step is being skipped. Audit via `cos_metric_trend(metric="time_to_solution", since_days=30)`.

## When code-vs-memory conflicts

**Always trust current code over memory.** Memory is frozen at write time. Code evolves. If recall says "function `foo` does X" but `Read` shows it doesn't, the memory is stale — update or delete the observation, then trust the code.

The `cos_search` response always includes the timestamp of the underlying record. If memory is older than the file's last-modified, re-verify.

## Audit log vs operational memory

- **Operational memory** (`cos_observation_record`) — what an agent learned. Decay applies. Confidence varies.
- **Audit log** (`cos_audit_log_record`) — who did what to which object when, immutable. No decay. Required for compliance.

Don't conflate. An auth permission change goes to the audit log; a pattern about how auth permissions are typically reviewed goes to operational memory.

## Privacy + compliance

- **Never** record PII in memory observations (emails, names, customer-identifying strings). Hash if needed.
- **Never** record secrets, even masked. Memory is a long-lived artifact.
- Sensitive design decisions (e.g., security-incident root cause) → record metadata + link to the postmortem doc, don't inline the sensitive details.

## See also

- [docs/governance/wrapper-derivation.md](../../docs/governance/wrapper-derivation.md) — SSOT for the four-layer model.
- [docs/governance/docs-system.md](../../docs/governance/docs-system.md) — docs layer rules.
- [docs/governance/agent-workflow.md](../../docs/governance/agent-workflow.md) — Core Loop integration.
- [src/core/skills/thinking_os/SKILL.md](../skills/thinking_os/SKILL.md) — when to invoke memory during the Cognitive Cycle.
- [src/core/skills/search/SKILL.md](../skills/search/SKILL.md) — `cos_search` vs `cos_doc_search` vs grep decision gate.
