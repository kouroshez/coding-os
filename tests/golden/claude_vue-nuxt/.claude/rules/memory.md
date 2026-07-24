# Memory Policy

> **Scope — `memory` module.** Active only when the `memory` subsystem is enabled. With it disabled, this policy is inert and the `cos_search` / `cos_observation_record` / `cos_learn_*` tools it references are gated (`module_disabled`); a lean profile unlinks this file entirely (defense-in-depth: the rule stays honest even in the mid-toggle window).
>
> Canonical layering SSOT (the *why*): [docs/governance/wrapper-derivation.md](../../docs/governance/wrapper-derivation.md). This rule is the operational policy.

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

Record a **reasoned insight** — a **breakthrough** (non-obvious insight that speeds a future session), a **failure mode** (bug → root cause → fix, especially recurring), a **decision** (trade-off + reasoning when the alternative was non-obvious), or **cross-session context** (a project fact not obvious from the code, e.g. "perf budget is set by the SLA, not preference") — with **`cos_learn_narrative`**: it files a searchable insight doc AND mints a belief. There is **no** freeform `record(title, body)` tool. `cos_observation_record` only force-captures a *file edit* (edit-derived, no content you supply) when the automatic PostToolUse hook didn't fire; `cos_learn_extract` is a corpus scan over task outcomes, not a per-insight record.

**Do NOT save** (it pollutes ranking + wastes tokens): anything already in code (`cos_graph_*`/`Read`), docs (`cos_doc_search`), `git log`/`git blame`, current-session task state (`cos_task_*`/`.task-current`), or "I just did X" recaps (that's the work log).

## When to read from agent memory

In the **Orient** phase (after Classify, before Plan): `cos_search(query, min_confidence=0.3, since_days=90)`, `cos_learn_suggest(domain, complexity)` for ranked patterns, `cos_timeline(days=14)` for recent change. 0 hits at those thresholds = no signal → fall through to docs (`cos_doc_search`) or code (`cos_graph_*`).

## Memory hygiene rules

1. **Confidence is system-computed, not hand-set.** Learned-pattern confidence moves by LTP/LTD only when you call `cos_learn_validate` — a second confirming session reinforces it toward Trusted; there is no tool that writes a confidence number. Validate patterns; don't assert scores (inflated confidence pollutes ranking, and by design you can't).
2. **Decay is automatic** — old low-confidence patterns deprioritize; don't manually delete unless wrong-and-actively-misleading.
3. **`min_confidence=0.3`** for high-trust patterns only; **`since_days=90`** when the question implies "recent".
4. **Tag `domain` + `swimlane`** when known — narrows future retrieval.

## Cross-session reasoning, conflicts, audit, privacy

- **Cross-session is the killer feature** — record in session 1, `cos_search` finds it in session 4. If similar problems aren't getting faster, the write step is being skipped (audit: `cos_metric_trend(metric="time_to_solution", window_days=30)`).
- **Code wins over memory.** Memory is frozen at write time; code evolves. If recall and `Read` disagree, the memory is stale — update or delete it, trust the code. `cos_search` returns each record's timestamp; older than the file's mtime → re-verify.
- **Git history ≠ operational memory.** Who-did-what-when lives in git (immutable, no decay); `cos_observation_record` is what an agent learned (decay + confidence). A permission *change* → a commit; a *pattern* about reviewing permissions → memory.
- **Privacy:** never record PII or secrets (memory is long-lived). Sensitive decisions (e.g. incident root cause) → record metadata + link the postmortem doc, don't inline.

## See also

[wrapper-derivation.md](../../docs/governance/wrapper-derivation.md) (four-layer SSOT) · [docs-system.md](../../docs/governance/docs-system.md) (docs layer) · [agent-workflow.md](../../docs/governance/agent-workflow.md) (Core Loop) · [thinking_os SKILL](../skills/thinking_os/SKILL.md) (when to invoke in the Cycle) · [search SKILL](../skills/search/SKILL.md) (`cos_search` vs `cos_doc_search` vs grep).
