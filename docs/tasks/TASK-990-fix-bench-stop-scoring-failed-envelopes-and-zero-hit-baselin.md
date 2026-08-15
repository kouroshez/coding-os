---
id: TASK-990
title: "fix(bench): stop scoring failed envelopes and zero-hit baselines as savings"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 2h
created: 2026-08-15
started: 2026-08-15
completed: 2026-08-15
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-990: fix(bench): stop scoring failed envelopes and zero-hit baselines as savings

**Outcome (one sentence):** The third-party bench never publishes a saving it cannot measure: a fail() envelope and a probe whose symbol has no corpus hits are both reported incomplete instead of scoring ~100%, and the mined ablation task set covers every closed task rather than the 15% still labelled complete.

## Read First
- docs/engineering/third-party-token-bench.md
- docs/engineering/ablation-protocol.md

## Repro Steps
1. Call `_coverage.read()` on a `fail()` envelope (no `data` key) — e.g. any uid the backend cannot resolve.
2. Observe `tokens=1`, `total_count=0`, `walk_truncated=False`, so `resolve_complete` settles immediately and classifies it `complete`.
3. `_probe_rows` then scores `savings_pct = (1 - 1/baseline) * 100` ≈ 99.99% and the row enters the published median.
4. Separately: `baseline_characters` returns 0 for a symbol absent from the corpus; `max(1, 0 // 4)` floors the baseline at 1 token and produces a savings_pct near -80,000%.
5. Separately: `eval_taskset.py` filters on `"status: complete"`, which skips the 824 closed-and-archived task files (`status: archive`, all carrying a `completed:` date).
Expected: an unmeasurable probe is reported incomplete and excluded; the miner reads every closed task.
Actual: an unmeasurable probe is scored as a near-100% saving; the miner samples 15% of the closed corpus.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a graph tool that returns a fail() envelope, **When** the bench resolves its coverage, **Then** the probe is classified incomplete and excluded from the median.
- **Given** a probe symbol absent from the corpus, **When** the baseline is measured, **Then** the probe is skipped rather than scored against a 1-token baseline.
- **Given** the ablation miner runs, **Then** `uv run --extra graph_os pytest src/core/graph_os/tests/test_bench_honesty.py -q` passes and closed-and-archived tasks are mined too.

## Work Log
- 2026-08-15 [claude]: Edit _coverage.py
- 2026-08-15 [claude]: Edit _coverage.py
- 2026-08-15 [claude]: Edit _coverage.py
- 2026-08-15 [claude]: Edit _coverage.py
- 2026-08-15 [claude]: Edit _coverage.py
- 2026-08-15 [claude]: Edit _coverage.py
- 2026-08-15 [claude]: Edit third_party.py
- 2026-08-15 [claude]: Edit third_party.py
- 2026-08-15 [claude]: Edit third_party.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit rule_audit.py
- 2026-08-15 [claude]: Edit rule_audit.py
- 2026-08-15 [claude]: Edit rule_audit.py
- 2026-08-15 [claude]: Edit context_budget.py
- 2026-08-15 [claude]: Edit context_budget.py
- 2026-08-15 [claude]: Edit test_chat_port.py
- 2026-08-15 [claude]: Edit context-budget.md
- 2026-08-15 [claude]: Edit context-budget.md
- 2026-08-15 [claude]: Edit README.md
- 2026-08-15 [claude]: Edit README.md
- 2026-08-15 [claude]: Edit test_bench_honesty.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit ablation-protocol.md
- 2026-08-15 [claude]: Coverage gate now marks a fail()/unparseable envelope unreadable so it is never scored (was a ~100% saving from an…
- 2026-08-15 [claude]: commit 91d5b2dc5b — fix(bench): never score an envelope the harness could not read
- 2026-08-15 [claude]: Status transitioned to complete via cos task-done.
