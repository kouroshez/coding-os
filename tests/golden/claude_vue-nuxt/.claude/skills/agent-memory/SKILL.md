---
name: agent-memory
tier: workflow
domain: [universal]
description: Mechanical recipes for reading agent memory and running the learning loop (cross-session patterns, decisions, failure modes) via the cos_search / cos_details / cos_timeline / cos_learn_* tool family, plus how observation capture actually works (automatic, edit-derived). Use when recalling a past pattern in a new session, running the extract → suggest → validate loop, or understanding why you cannot hand-author a freeform observation. Pairs with src/core/rules/memory.md (policy), thinking_os (when in the Cognitive Cycle to invoke), and search (which retrieval layer to hit first).
last_reviewed: "2026-06-05"
---

# agent-memory

Purpose: turn the policy in [src/core/rules/memory.md](../../rules/memory.md) into mechanical recipes the agent can execute. The rule answers *when* and *what*; this skill answers *how* — the exact tool signatures, what is automatic vs explicit, and what the return envelopes look like. Every signature here is verified against [src/core/thinking_os/server.py](../../thinking_os/server.py); a CI drift-guard test fails if any drifts.

Read when: recalling from memory (`cos_search`, `cos_details`, `cos_timeline`, `cos_learn_suggest`), running the learning loop (`cos_learn_extract` / `cos_learn_validate` / `cos_learn_feedback`), or understanding how observations get captured.

Skip when: the query target is current code (use [graph-explorer](../graph-explorer/SKILL.md)) or current docs (use `cos_doc_search` per [search](../search/SKILL.md)). Memory is the third-priority retrieval layer.

## The mental model — writes are automatic, you mostly READ

The single most important fact: **you do not hand-author observations.** Memory is written automatically by PostToolUse capture hooks — every `Write`/`Edit`/`MultiEdit` derives a sanitized, deduped, impact-scored observation ([capture.py](../../thinking_os/capture.py)), and separate hooks capture tool failures, completion gaps, and session events. Confidence on learned patterns is **system-computed** by brain-inspired LTP/LTD formulas, not a number you set. The agent's job is to **read** memory in the Orient phase and **reinforce** patterns via the learn loop. There is no freeform `record(title, body, confidence)` tool — by design.

## The Decision Gate — before any memory call

```
Question                                  → Layer + Tool
─────────────────────────────────────────────────────────
"Where is function X defined?"            → graph    cos_graph_query
"What does spec Y say?"                   → docs     cos_doc_search
"What's in flight / blocked?"             → tasks    cos_task_board
"Have I seen this pattern before?"        → memory   cos_search
"Why did we choose approach Z?"           → memory   cos_search (memory_type=decision)
"Which patterns apply to my task?"        → memory   cos_learn_suggest(domain=, complexity=)
"What changed in the last N days?"        → memory   cos_timeline(days=N)
"How does X work / who calls X / rename"  → graph    cos_graph_* (graph/code FIRST)
"Not sure which layer"                    → default to graph/code; memory only for cross-session recall
```

If the gate routes elsewhere, **stop reading this skill** and go to the right layer. Memory is expensive (decay + confidence ranking); over-use pollutes ranking for everyone.

## Read Recipes (the agent's primary memory interaction)

### 1. Search by free-text query (most common read)

```python
cos_search(
    query="cookie samesite",
    limit=5,                       # 1-20, default 5
    memory_type="",                # optional filter: pattern|workflow|error|decision|discovery
    min_confidence=0.3,            # drop low-trust patterns; 0.3 = floor for useful, 0.0 = include all (noisy)
    since_days=90,                 # cap age; 0 = no cap; 90-180 for "recent" queries
)
```

Returns ranked rows `[{id, title, confidence, impact_score, memory_type, source_table}]`. Drill into the top 1-2 with `cos_details`.

### 2. Drill into one record

```python
cos_details(
    pattern_id=1234,               # the integer id from a cos_search / cos_learn_suggest row
    source="learned_patterns",     # which table: observations | learned_patterns | task_outcomes
)
```

Match `source` to the `source_table` field of the row you are drilling into — `cos_search` returns rows from both `observations` and `learned_patterns`.

### 3. Task-aware suggestion

```python
cos_learn_suggest(
    domain="BACKEND",              # task domain; optional
    complexity="COMPLICATED",      # Cynefin classification; optional
    task_type="feat",             # optional
    limit=5,                       # top-K, 1-20, default 5
)
```

Ranks learned patterns for the current task context and includes spaced repetition — fading patterns (0.2-0.4 confidence) that were once validated resurface for re-validation. Better than raw `cos_search` when you have a task in flight.

### 4. Timeline view (what changed recently)

```python
cos_timeline(
    days=14,                       # lookback window, 1-365, default 30
    domain="",                     # optional domain filter
    limit=20,                      # 1-50, default 20
)
```

Use when the question is "what's new" rather than "what's known about X". Surfaces recent task outcomes + observations.

## How memory is WRITTEN (mostly automatic)

### 1. Automatic capture (the default — you do nothing)

A PostToolUse hook calls [capture.py](../../thinking_os/capture.py) after every `Write`/`Edit`/`MultiEdit`: it derives `title` (`Modified <path>` / `Created <path>`), `narrative`, `memory_type` (auto-detected from the path), `impact_score`, and `concepts` from the file and tool, runs them through the write sanitizer (rejects injection, truncates over-length), dedups within a 30s window, and inserts. Tool failures, completion gaps, and session events are captured by their own hooks. **The agent supplies nothing.**

### 2. Explicit single-file capture (rare)

```python
cos_observation_record(
    file_path="src/core/thinking_os/database.py",
    tool_name="Edit",             # Write | Edit | MultiEdit; default "Edit"
)
```

This triggers the **same** auto-capture machinery for one file. Use it only when the PostToolUse hook did not fire — e.g. under a runtime without PostToolUse coverage (Codex), or to force-capture a specific file. It does **not** accept a title, body, confidence, or impact — those are derived. There is no other write path.

### 3. What each `memory_type` means (for reading + filtering)

`memory_type` is auto-detected at capture; this table is for understanding what a stored row represents when you read or filter on it.

| Type | What it captures |
|---|---|
| `pattern` | Reusable approach to a recurring problem |
| `workflow` | Sequence of steps, not a one-off insight |
| `error` | Bug → root cause → fix |
| `decision` | Trade-off chosen + reason |
| `discovery` | Surprising fact about the system |

## The Learning Loop (extract → suggest → validate → feedback)

The loop distills patterns from the corpus of task outcomes and lets the N-th session reuse them — the killer feature. Confidence moves automatically: a pattern that held gets reinforced (LTP), one that didn't decays (LTD).

```
cos_learn_extract(min_occurrences=3)        # scan task_outcomes corpus → mint learned_patterns
        │                                     #   (domain_rework / skill_correlation / complexity_mismatch)
        ▼
cos_learn_suggest(domain=, complexity=)     # surface ranked patterns for the active task
        │
        ▼  agent uses a pattern, notes the outcome
cos_learn_validate(pattern_id, was_helpful) # reinforce (LTP) or decay (LTD) its confidence
        │
        ▼  persistent rework on a domain+skill cluster
cos_learn_feedback(min_rework=3)            # draft feedback files for human review (not auto-applied)
```

```python
cos_learn_extract(min_occurrences=3)               # corpus-wide; NOT per-task
cos_learn_suggest(domain="BACKEND", complexity="COMPLICATED", limit=5)
cos_learn_validate(pattern_id=42, was_helpful=True)  # integer id + boolean
cos_learn_feedback(min_rework=3)                    # returns drafts; caller writes + human confirms
```

`cos_learn_extract`/`feedback` are corpus scans (no task argument). `cos_learn_validate` is how confidence changes — there is no write-time confidence knob.

## Cross-session verification

Before recommending an action based on a memory hit, verify the named symbols / paths still exist (per [src/core/rules/memory.md](../../rules/memory.md)):

- Memory says "function `foo` does X" → `cos_graph_query("foo")` to confirm it exists.
- Memory says "file `src/core/X.py`" → `Read` it to confirm.
- If gone or renamed: the memory is stale — re-verify against the code and trust the code, not the record.

A memory recommendation that names a vanished symbol is worse than no memory — it's confidently wrong. Every `cos_search` row carries the record timestamp; re-verify when it predates the file's last change.

## Decay + auto-deprioritization

Ranking already factors in `access_count` (popular patterns surface), `last_verified_at` (stale sinks), `confidence` (trust-weighted), and the caller's `since_days` filter. You don't tune these at write time — you influence confidence through the learn loop (`cos_learn_validate`) and control reads via `min_confidence` + `since_days`. The ranking is the contract.

## Audit log boundary

Two separate stores. Don't conflate:

| Concern | Store | Tool |
|---|---|---|
| "What did an agent learn?" | Operational memory | automatic capture + `cos_learn_*` |
| "Who changed what + when (immutable)?" | Audit log | `cos_audit_log_record` |
| "Forensic trail for compliance" | Audit log | `cos_audit_log_query` / `cos_audit_log_timeline` |

A permission change → audit log. A pattern about reviewing permissions → operational memory.

## Privacy + Compliance

The write sanitizer rejects injection and truncates over-length text at capture, but content discipline is still yours:

- **No PII** in files you edit if it would land in a narrative — emails, names, customer-identifying strings.
- **No secrets** — even masked. Memory is long-lived and replicated.
- **Sensitive findings** (security incidents, financial decisions) → keep details in the postmortem doc; let capture record only the edit.

## Anti-patterns (reject in review)

- **Expecting a freeform `cos_observation_record(title=, body=, confidence=)`** — it does not exist; capture is edit-derived.
- **Setting confidence by hand** — confidence is computed by the learn loop, not supplied.
- **Calling `cos_learn_extract` per task with a task_id** — it is a corpus scan keyed by `min_occurrences`.
- **Recording code facts** — that's the graph (`cos_graph_*`). Memory is for *cross-code* patterns.
- **Reading without `min_confidence`** — top-K full of decayed noise.
- **Trusting memory without verification** when the memory names a specific symbol/path.

## Composition pointers

- [references/memory-recipes.md](references/memory-recipes.md) — the `cos_*` read + learn-loop sequences.
- [assets/memory-checklist.md](assets/memory-checklist.md) — the read + learn-loop gate.
- Cognitive cycle entry: [thinking_os](../thinking_os/SKILL.md) — Orient phase routes to memory.
- Layer routing: [search](../search/SKILL.md) decision gate (memory vs docs vs graph vs file).
- Policy + 4-layer model: [src/core/rules/memory.md](../../rules/memory.md) — the *why*.
- Task linkage: [task-driver](../task-driver/SKILL.md) — task outcomes feed the learn loop.
