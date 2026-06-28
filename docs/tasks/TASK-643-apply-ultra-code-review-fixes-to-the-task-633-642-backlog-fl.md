---
id: TASK-643
title: "Apply ultra-code-review fixes to the TASK-633..642 backlog (flock-flush, MMR scale, bandit confidence, type-alias import, +6)"
swimlane: core
kind: bug
epic: multi-model-autonomy
labels: [review, bugfix, dispatch, memory, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260627-204916-f0ee
depends_on: []
blocked_by: []
references: []
---
# TASK-643: Apply ultra-code-review fixes to the TASK-633..642 backlog (flock-flush, MMR scale, bandit confidence, type-alias import, +6)

**Outcome (one sentence):** Apply the CONFIRMED findings from the max-effort code review (workflow w8zeczt90) of the TASK-633..642 diff — real bugs in the just-shipped code: EvidenceBundle flock releases before the buffered write flushes; MMR relevance is swamped by the diversity penalty (RRF scores un-normalized); bandit confidence is a random sample (and can go negative under cost-tilt); aliased inline `import { type Foo as Bar }` is misclassified as a runtime edge; cost_anomaly two-sided test flags cheap sessions; docs-lint extracts the wrong date; imports_type missing from the auto-blend bucket; doctor --tokens hardcodes the DB path; warn-diff-size measures only --cached; the empirical dispatch tier evaluates eagerly; the adapter-hint is inert.

## Read First
- src/core/thinking_os/tools/memory.py
- src/core/thinking_os/tools/routing.py
- src/core/thinking_os/tools/cognition.py
- src/core/graph_os/extractors/code_ts.py
- src/core/thinking_os/budget.py

## Repro Steps
Run `git diff c0b73dc3 HEAD` and trace each cited site: `_save_bundle` (cognition.py) drops `LOCK_UN` in a finally before `close()` flushes the buffer, so the flock serializes an empty write; `_mmr_select` scores `lam*rrf(~0.02) - (1-lam)*jaccard(0..0.3)` so picks 2..N rank by anti-similarity; `route_model_bandit` returns `round(best_theta)` (a random draw) with a `best_score=-2.0` seed that a large `COS_ROUTER_COST_TILT` sinks below, yielding confidence -1.0; `_parse_clause` splits on ` as ` dropping the `type ` prefix; `budget.cost_anomaly` uses `abs(z)`; `docs-lint.sh` greps the first date on the line; `graph.py _AUTO_BLEND_BUCKETS` lacks `imports_type`; `doctor.py:2790` hardcodes `.coding-os/coding-os.db`; `warn-diff-size.sh` uses `git diff --cached` while the project commits via `git commit <path>`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two concurrent _save_bundle writes, **When** they race, **Then** the flock holds until flush+fsync so the on-disk bundle is never torn.
- **Given** RRF-fused candidates, **When** _mmr_select ranks, **Then** the relevance term is normalized to a scale comparable to the [0,1] Jaccard penalty so a relevant near-duplicate is not demoted below an irrelevant-but-distinct row; a unit test feeds realistic RRF magnitudes.
- **Given** identical history, **When** route_model_bandit runs twice, **Then** confidence is the deterministic posterior mean and stays in [0,1] even under a large COS_ROUTER_COST_TILT.
- **Given** `import { type Foo as Bar }`, **When** extracted, **Then** an imports_type (not imports) edge is emitted.
- **Given** the thinking_os + graph_os + cli matrix suites + verify-hooks + docs-lint, **When** run, **Then** green.

## Work Log
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit routing.py
- 2026-06-28 [claude]: Edit routing.py
- 2026-06-28 [claude]: Edit memory.py
- 2026-06-28 [claude]: Edit code_ts.py
- 2026-06-28 [claude]: Edit graph.py
- 2026-06-28 [claude]: Edit code_ts.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit docs-lint.sh
- 2026-06-28 [claude]: Edit doctor_tokens.py
- 2026-06-28 [claude]: Edit doctor.py
- 2026-06-28 [claude]: Edit test_routing.py
- 2026-06-28 [claude]: Edit test_routing.py
- 2026-06-28 [claude]: Edit test_dispatch_safety.py
- 2026-06-28 [claude]: Edit test_memory.py
- 2026-06-28 [claude]: Edit test_code_ts.py
- 2026-06-28 [claude]: Edit warn-diff-size.sh
- 2026-06-28 [claude]: Edit test_warn_diff_size.py
- 2026-06-28 [claude]: Applied all CONFIRMED ultra-review findings (workflow w8zeczt90, 69 agents). Correctness: (1) _save_bundle now…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
