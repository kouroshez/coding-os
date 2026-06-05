---
name: agent-memory
tier: workflow
domain: [universal]
description: Mechanical recipes for writing to and reading from agent memory (cross-session patterns, decisions, failure modes) via the cos_observation_record / cos_search / cos_learn_* tool family. Use when capturing a breakthrough, replaying a past pattern in a new session, tuning confidence scores, or composing the learn-extract → learn-suggest → learn-validate loop. Pairs with src/core/rules/memory.md (policy), thinking_os (when in the Cognitive Cycle to invoke), and search (which retrieval layer to hit first).
last_reviewed: "2026-05-11"
---

# agent-memory

Purpose: turn the policy in [src/core/rules/memory.md](../../rules/memory.md) into mechanical recipes the agent can execute. The rule answers *when* and *what*; this skill answers *how* — exact tool signatures, argument shapes, when to compose them, what return envelopes look like.

Read when: writing to memory (`cos_observation_record`, `cos_learn_extract`), reading from memory (`cos_search`, `cos_learn_suggest`, `cos_timeline`, `cos_details`), or running the learning loop. Also read when tuning decay / confidence behavior.

Skip when: the query target is current code (use [graph-explorer](../graph-explorer/SKILL.md)) or current docs (use `cos_doc_search` per [search](../search/SKILL.md)). Memory is the third-priority retrieval layer.

## The Decision Gate — before any memory call

```
Question                                  → Layer + Tool
─────────────────────────────────────────────────────────
"Where is function X defined?"            → graph    cos_graph_query
"What does spec Y say?"                   → docs     cos_doc_search
"What's in flight / blocked?"             → tasks    cos_task_board
"Have I seen this pattern before?"        → memory   cos_search
"Why did we choose approach Z?"           → memory   cos_search (memory_type=decision)
"Which patterns apply to TASK-NNN?"       → memory   cos_learn_suggest(task_id=...)
"What changed in the last N days?"        → memory   cos_timeline(scope="recent")
"Not sure which layer"                    → router   cos_retrieve(query, hint="auto")
```

If the gate routes elsewhere, **stop reading this skill** and go to the right layer. Memory is expensive (decay + confidence ranking); over-use pollutes ranking for everyone.

## Write Recipes

### 1. Record an observation (the most common write)

```python
# Generic
cos_observation_record(
    title="Short, searchable title — 5-10 words",
    body="Body of the observation. Why does it matter? When does it apply? Anti-pattern? 1-3 short paragraphs max.",
    memory_type="pattern",         # pattern | workflow | error | decision | discovery
    domain="BACKEND",              # optional; BACKEND/FRONTEND/META/OPS/...
    swimlane="meta",               # optional; matches Scrumban swimlanes
    confidence=0.5,                # 0.0-1.0; default 0.5; raise to 0.7+ only after second confirming use
    impact_score=0.3,              # 0.0-1.0; "how much does knowing this save?"
    tags_csv="indexing,migration", # comma-separated, lowercase, kebab-case
    task_id="TASK-042",            # optional; links observation to the task that surfaced it
)
```

### 2. When to pick each `memory_type`

| Type | What it captures | Example title |
|---|---|---|
| `pattern` | Reusable approach to a recurring problem | "Expand-contract pattern for adding NOT NULL column" |
| `workflow` | Sequence of steps, not a one-off insight | "Verify migration safety: write → backfill → switch → drop" |
| `error` | Bug → root cause → fix | "Cookie SameSite=None requires Secure=true (FastAPI default leaks)" |
| `decision` | Trade-off chosen + reason | "SQLite + PRAGMA tuning over a second graph store: p99 < 30 ms on 5-hop @ 1M nodes makes the abstraction overhead unjustified" |
| `discovery` | Surprising fact about the system | "FastMCP doesn't accept `list[str]` args across all runtimes; use CSV" |

### 3. Confidence calibration (the lever that decides ranking)

Default 0.5. **Raise only after evidence**:

| Confidence | When |
|---|---|
| 0.5 (default) | First time seeing this pattern; one session of evidence |
| 0.7 | Two independent sessions confirmed the pattern still applies |
| 0.85 | Three+ sessions; pattern is load-bearing for the project |
| 0.95 | Cited in current docs / rules; effectively SSOT |

**Lower** after evidence-against:
- 0.5 → 0.3 if a session showed the pattern was wrong / no longer applies (also consider deleting via `cos_audit_log_record(action="deleted")`).

Inflated confidence = ranking pollution. Treat 0.7+ as a promise to the next session.

### 4. Learn-extract (post-task auto-extraction)

Use after a non-trivial task completes to harvest patterns automatically:

```python
cos_learn_extract(
    task_id="TASK-042",
    work_log_summary="<one paragraph of what was done>",
    decisions_made_csv="chose sqlite + PRAGMA tuning over a second graph store; backfill before NOT NULL",
)
```

This generates candidate observations (NOT auto-recorded). Review each, then `cos_learn_validate(observation_id=..., status="accepted" | "rejected")` to commit. **Always validate** — auto-extraction without validation = hallucinated patterns in memory.

## Read Recipes

### 1. Search by free-text query (most common read)

```python
cos_search(
    query="cookie samesite",
    limit=5,                       # 1-20, default 5
    memory_type="",                # optional filter
    min_confidence=0.3,            # drop low-trust patterns; 0.3 = floor for useful, 0.0 = include all (noisy)
    since_days=180,                # cap age; 0 = no cap; 90-180 for "recent" queries
)
```

Returns ranked rows. Iterate, call `cos_details(id=...)` for full body of the top 1-2.

### 2. Task-aware suggestion

```python
cos_learn_suggest(
    task_id="TASK-042",            # optional; otherwise uses .task-current
    k=5,                           # top-K patterns ranked for this task's signals
)
```

Rank uses task domain + swimlane + kind + recency + confidence + impact. Better than raw `cos_search` when you have a task in flight.

### 3. Timeline view (what changed recently)

```python
cos_timeline(
    scope="recent",                # "recent" | "task" | "domain"
    since_days=14,
    limit=20,
)
```

Use when the question is "what's new" rather than "what's known about X". Surfaces fresh observations + new task completions + recent failure patterns.

### 4. Drill into one record

```python
cos_details(
    id="obs-1234",                 # from cos_search / cos_learn_suggest results
)
```

Returns full body, source task, access count, last verified date.

## The Learning Loop (extract → suggest → validate → feedback)

```
┌─────────────────────────────────────────────────────┐
│  Task complete                                      │
│    │                                                │
│    ▼                                                │
│  cos_learn_extract(task_id=..., work_log=...)       │
│    │                                                │
│    ▼ candidate observations (NOT recorded yet)      │
│  Agent reviews, decides accept/reject               │
│    │                                                │
│    ▼                                                │
│  cos_learn_validate(obs_id=..., status=...)         │
│    │                                                │
│    ▼ committed to memory with confidence=0.5        │
│  Next session opens similar task                    │
│    │                                                │
│    ▼                                                │
│  cos_learn_suggest(task_id=new_task)                │
│    │                                                │
│    ▼ top-K including the new pattern                │
│  Agent uses pattern, work-log mentions it           │
│    │                                                │
│    ▼                                                │
│  cos_learn_feedback(obs_id=..., outcome="useful")   │
│    │                                                │
│    ▼ confidence ticks up 0.5 → 0.6                  │
└─────────────────────────────────────────────────────┘
```

**The skipped step is always validate.** Agents that call `cos_learn_extract` without `cos_learn_validate` poison memory with hallucinated patterns. Mechanical rule: **never call extract without queuing the validate step in the same response.**

## Cross-session verification

Before recommending an action based on a memory hit, verify the named symbols / paths still exist (per [src/core/rules/memory.md](../../rules/memory.md)):

- Memory says "function `foo` does X" → `cos_graph_query("foo")` to confirm it exists.
- Memory says "file `src/core/X.py`" → `Read` it to confirm.
- If gone or renamed: update memory via `cos_audit_log_record(action="deleted")` and re-record under the new name.

A memory recommendation that names a vanished symbol is worse than no memory — it's confidently wrong.

## Decay + auto-deprioritization

The ranking already factors in:
- `access_count` (popular patterns surface more)
- `last_verified_at` (stale patterns sink)
- `confidence` (trust-weighted)
- `since_days` filter applied (caller-controlled)

You don't tune these directly. You tune confidence (write side) and pass `min_confidence` + `since_days` (read side). The ranking is the contract.

## Audit log boundary

Two separate stores. Don't conflate:

| Concern | Store | Tool |
|---|---|---|
| "What did an agent learn?" | Operational memory | `cos_observation_record` |
| "Who changed what + when (immutable)?" | Audit log | `cos_audit_log_record` |
| "What patterns emerged from learning?" | Operational memory | `cos_learn_*` |
| "Forensic trail for compliance" | Audit log | `cos_audit_log_query` / `cos_audit_log_timeline` |

A permission change → audit log. A pattern about reviewing permissions → operational memory.

## Privacy + Compliance

- **No PII** in observation title/body — emails, names, customer-identifying strings. Hash if context truly needs it.
- **No secrets** — even masked. Memory is long-lived and replicated.
- **Sensitive findings** (security incidents, financial decisions) → record metadata + link to the postmortem doc, don't inline.

## Anti-patterns (reject in review)

- **Calling `cos_learn_extract` without `cos_learn_validate`** — hallucination farm.
- **Confidence inflation** at write time to make pattern surface faster — pollutes ranking.
- **Recording current-session task state** — that's `.task-current` + work log, not memory.
- **Recording code facts** — that's the graph (`cos_graph_*`). Memory is for *cross-code* patterns.
- **Recording PII / secrets** — long-lived store; compliance breach.
- **Reading without `min_confidence`** — top-K full of decayed noise.
- **Trusting memory without verification** when the memory names a specific symbol/path.

## Tooling

Validate an observation before recording (confidence range, no PII/secrets):
`python3 scripts/check_observation.py --file obs.json`

## Composition pointers

- [references/memory-recipes.md](references/memory-recipes.md) — the `cos_*` write/read/learn-loop sequences.
- [assets/memory-checklist.md](assets/memory-checklist.md) — the write/read gate.

- Cognitive cycle entry: [thinking_os](../thinking_os/SKILL.md) — Orient phase routes to memory.
- Layer routing: [search](../search/SKILL.md) decision gate (memory vs docs vs graph vs file).
- Policy + 4-layer model: [src/core/rules/memory.md](../../rules/memory.md) — the *why*.
- Audit log surface: [security-web](../security-web/SKILL.md) §A09, [observability](../observability/SKILL.md) audit-log section.
- Task linkage: [task-driver](../task-driver/SKILL.md) — task_id stamps observations.
