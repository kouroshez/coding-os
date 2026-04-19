<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-18 -->
# Phase J — `cos_retrieve` Meta-Router

Purpose: Give agents a single entry point for "I want to know X" and let the runtime pick the correct retrieval layer (memory / docs / tasks / code-grep) instead of the agent choosing every time.
Read when: Starting any J.* sub-task, adjusting the query classifier, or wiring a new retrieval layer into the dispatch table.
Read next: [core/thinking-os/tools/memory.py](../core/thinking-os/tools/memory.py), [tools/docs.py](../core/thinking-os/tools/docs.py), [tools/tasks.py](../core/thinking-os/tools/tasks.py), [docs/phase-g-brain-hardening-plan.md](./phase-g-brain-hardening-plan.md) §G.7.1 (routing paragraph).

## Why

After Phase G.7.1 we documented the routing decision in `AGENTS.md` — agents now *know* that identifier queries go to Grep and conceptual queries to `cos_doc_search`. But **the decision is still manual**. That has three costs:

1. **Cognitive load.** Every retrieval costs a classification step inside the agent's prompt.
2. **Regression risk.** A new agent model / a tired reviewer may pick the wrong layer without detection.
3. **Metric opacity.** We can't easily measure "how often did the agent misroute?" without logging the chosen layer separately.

Phase J consolidates this into `cos_retrieve(query, hint="auto")` — a thin meta-router that:

- Classifies the query shape using the same rules documented in G.7.1
- Dispatches to the correct `cos_*` tool
- Returns a unified envelope with `meta.chosen_layer`, `meta.classifier_reason`
- Logs misroutes (agent overrides) so we can measure quality over time

## Principles

- **P-J-1: Additive, not replacement.** Existing `cos_search`, `cos_doc_search`, `cos_task_*` keep working. `cos_retrieve` is a convenience layer; agents remain free to call layers directly when they know the shape.
- **P-J-2: Rule-based first, ML later.** A regex + keyword classifier with explicit rules has honest failure modes. ML comes only after we have ground truth from usage.
- **P-J-3: Fan-out when uncertain, single-dispatch when confident.** Identifier query → single dispatch to code-hint. Conceptual query → fan-out memory+docs+tasks and rank by score within token budget.
- **P-J-4: Budget-aware.** Meta-router enforces `budget_tokens` across fan-out results; trims lowest-scoring layer first.
- **P-J-5: Fully telemetered.** Every call writes a row to a new `retrieval_router_log` table with query hash, chosen layer, fan-out size, agent override (if any). Feeds Phase G.11 precision tracker.

## Phase J Roadmap

| Slice | Scope | LOC | Ship gate |
|---|---|---|---|
| **J.1** | `tools/router.py` — pure classifier function `classify_query(q) -> Classification` with regex rules + keyword signals | ~150 | unit tests on 40+ queries |
| **J.2** | `tools/router.py::dispatch` — given a classification, call the right `cos_*` function(s); merge results with score normalization | ~180 | per-layer dispatch tests |
| **J.3** | Migration v12: `retrieval_router_log` table (query_hash, classification, chosen_layer, fanout_layers, bytes_returned, created_at) | ~40 | idempotent migration + append-only |
| **J.4** | `cos_retrieve` MCP tool registered in server.py | ~60 | envelope shape test + self-test green |
| **J.5** | Quality evaluation script — `scripts/evaluate_router.py` takes a CSV of (query, expected_layer) pairs → reports precision/recall per classification class | ~120 | baseline report on 50 sample queries |
| **J.6** | AGENTS.md + CLAUDE.md addendum: "You can call `cos_retrieve(q)` OR the specific layer. Use cos_retrieve when unsure" | 0 code | docs-lint |

**Execution order:** J.1 → J.2 → J.3 → J.4 → J.5 → J.6. J.5 is critical — without a measurable baseline we can't improve the classifier.

## J.1 — Query Classifier

**Classification enum:**

```python
class Classification(TypedDict):
    shape: Literal["identifier", "conceptual", "past_pattern",
                   "task_ref", "behavioral", "mixed"]
    confidence: float  # 0.0 - 1.0
    reason: str        # short human-readable trace
```

**Rules (ordered, first match wins):**

1. **Behavioral** — starts with "how should I", "how do I", "what's the rule for" → rule-file full-read, not retrieval. Confidence 0.9.
2. **Task ref** — regex `\bTASK[-_]\d+\b` present → tasks layer. Confidence 0.95.
3. **Identifier** — contains `[a-z_]{3,}\([a-z_]*\)` OR `CamelCase\w+` OR `` `backticked` `` OR starts with `/` or `src/` or `core/` → Grep hint. Confidence 0.85.
4. **Past pattern** — matches keywords `{"", "before", "had", "previously", "same as", "prior"}` → memory layer. Confidence 0.8.
5. **Conceptual** — none of the above AND length > 5 tokens → fan-out. Confidence 0.6.
6. **Mixed** — if multiple rules fire with similar confidence → flag `mixed`, caller decides.

**Training data (J.5 baseline):** 50 queries curated from real agent sessions, each hand-labelled with expected class. Stored at `docs/code-os-core-docs/router-eval.csv`.

## J.2 — Dispatch

**Single-dispatch cases:**

| Classification | Action |
|---|---|
| `behavioral` | return `{status: "noop", hint: "rule is always-active, re-read core/rules/*.md"}` |
| `task_ref` | call `cos_task_search(query)` — return as-is |
| `identifier` | return `{status: "noop", hint: "use Grep/Glob for identifier lookups"}` + suggested grep command |

**Fan-out cases (conceptual, past_pattern, mixed):**

```
budget = meta.budget_tokens (default 2500)
fetch cos_search(q, limit=5) → memory slice
fetch cos_doc_search(q, limit=5) → docs slice
fetch cos_task_search(q, limit=5) → tasks slice
normalize scores (min-max per slice)
merge, rank by normalized score, trim to budget
return unified list with original source_table + layer tag
```

## J.3 — Migration v12 (`retrieval_router_log`)

```sql
CREATE TABLE retrieval_router_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash      TEXT NOT NULL,       -- SHA256[:16] of query
    query_shape     TEXT NOT NULL,       -- Classification.shape
    confidence      REAL NOT NULL,
    chosen_layer    TEXT,                -- primary dispatch target
    fanout_layers   TEXT,                -- JSON list when fan-out
    bytes_returned  INTEGER,
    truncated       INTEGER DEFAULT 0,
    agent_override  TEXT,                -- if agent subsequently called a different layer
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_router_log_created ON retrieval_router_log(created_at);
CREATE INDEX idx_router_log_shape ON retrieval_router_log(query_shape);
```

Append-only (no UPDATE triggers required — unlike memory_audit, this isn't security-critical).

## J.4 — MCP Tool

```python
@safe_tool
def cos_retrieve(
    query: str,
    hint: Literal["auto", "memory", "docs", "tasks", "code"] = "auto",
    budget_tokens: int = 2500,
) -> str:
    """Unified retrieval with automatic layer dispatch.

    Use this when you're not sure which specific cos_* tool to call.
    Returns same envelope shape as specific layers, with extra meta:
      - meta.chosen_layer (single) or meta.fanout_layers (array)
      - meta.classifier_reason
      - meta.budget_used / meta.budget_remaining
    """
```

## J.5 — Evaluation

`scripts/evaluate_router.py`:

1. Read `docs/code-os-core-docs/router-eval.csv` (query, expected_class)
2. Run classifier on each
3. Confusion matrix per class + overall precision/recall
4. Report misclassifications with the full reason trace
5. Threshold gate for CI: overall precision ≥ 0.80

## J.6 — Docs Addendum

Small addendum under G.7.1 routing paragraph: "If in doubt, call `cos_retrieve(q)` and let the runtime pick. The response will tell you which layer answered — so you can build routing intuition over time."

## Risks & Mitigations

- **R-J-1: Classifier false positives.** Mitigation: rules ordered by specificity; evaluation gate in CI.
- **R-J-2: Fan-out doubles latency.** Mitigation: parallelize via `concurrent.futures` if measured median > 200ms.
- **R-J-3: Agents skip cos_retrieve because specific tools are faster.** Mitigation: log both usage paths; if specific-call ratio drops below 20%, consider making cos_retrieve the default.
- **R-J-4: Log table grows unbounded.** Mitigation: `cos doctor` adds a retention check; `cos-prune-logs` Make target trims to last 90 days.

## Ship Checklist

- [ ] Classifier passes 40+ unit tests across all classes
- [ ] Dispatch works for every classification
- [ ] Migration v12 idempotent; `retrieval_router_log` in `_TABLES` list
- [ ] `cos_retrieve` registered and emits correct meta shape
- [ ] Evaluation script baseline reported, CI gate enabled
- [ ] Addendum in AGENTS.md + CLAUDE.md
- [ ] G.11 precision tracker ingests router log alongside retrievals
