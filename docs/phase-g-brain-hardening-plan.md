<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-18 -->
# Phase G — Brain Hardening & Retrieval Unification

Purpose: Close the memory-poisoning and envelope-drift gaps found in the v0.2.2 audit; make coding-os safe for 24/7 autonomous learning.
Read when: Starting any G.* sub-task, reviewing learning-loop safety, or wiring a new MCP tool.
Read next: [core/thinking_os/db.py](../core/thinking_os/db.py) for migration v7 reference; [core/thinking_os/tools/_shared.py](../core/thinking_os/tools/_shared.py) for envelope.

## Why (audit findings)

| # | Finding | Severity | Chain |
|---|---|---|---|
| A1 | Envelope ok/fail uniform across 21 tools | OK | — |
| A2 | Inner `data` shapes diverge (no common `meta` field: layer/tokens_est/truncated) | Med | agent can't reason about cost uniformly |
| A3 | No `provenance` — can't distinguish agent-self-written from user-directive/extracted | High | poisoning vector |
| A4 | No `trust_tier` — any caller can UPDATE/DELETE validated rules | High | catastrophic amnesia |
| A5 | Self-validation loop: `cos_search` +0.02 conf ∪ `cos_learn_validate(True)` LTP boost without throttle | High | agent self-reinforces wrong patterns |
| A6 | Narrative unsanitized — free-text `narrative`/`title`/`pattern` stored as-is | High | prompt-injection via memory |
| A7 | `learn_narrative` creates pattern with conf=0.7 impact=0.85 with zero verification | High | fabricated breakthroughs |
| A8 | No `memory_audit` — zero tamper-evidence | Med | can't detect manipulation |
| A9 | No token-budget enforcement per tool | Low-Med | context overflow on pathological data |
| A10 | No session throttle on `cos_learn_validate` | Med | extends A5 |
| A11 | No input-length caps on writes | Low | — |

Chain A3+A4+A5+A6+A7 forms a complete poisoning path — must be closed before any continuous-learning loop (Phase G.4+) ships.

## Principles

- **P-BH-1: Fail closed on validation.** Invalid provenance / trust_tier / oversized text → reject with `fail("validation", ...)` envelope, log audit row, do NOT write the record.
- **P-BH-2: Append-only.** Migrations, audit log, outcome_history all append. No in-place history rewrites.
- **P-BH-3: Write at the chokepoint.** Guards live at DB-write functions (`capture.py`, `learn_narrative`, `_upsert_pattern`, `memory_promote`), NOT duplicated across every caller. Hooks enforce at the outer boundary.
- **P-BH-4: Trust tier is monotonic w.r.t. protection.** Once a pattern is `locked`/`core`, it can only move DOWN via an explicit, audited admin path — never via `cos_learn_validate` with `was_helpful=False`.
- **P-BH-5: Provenance is immutable.** Set at insert, never altered.
- **P-BH-6: Agent-self writes are under suspicion.** `provenance='agent_self'` patterns capped at `trust_tier='volatile'` and cannot auto-promote to `validated` without an external confirmation signal (user validation OR ≥N outcome_history successes tied to the pattern).
- **P-BH-7: Data shape contract.** Every `cos_*` return payload is `ok({"results"|"record"|"status": ..., "meta": {...}})` with a uniform `meta` block (layer, tokens_estimated, truncated, query?). Additive — legacy fields preserved.

## Trust Tier Model

```
┌────────────┐  auto on >=10 validations AND 0 violations in 30d
│ volatile   │ ──────────────────────────► ┌───────────┐
└────────────┘                             │ validated │
     ▲                                     └─────┬─────┘
     │ LTD / violation / decay                   │ explicit promote via
     │                                           │ `cos_promote` (admin)
     │                                           ▼
     │                                     ┌──────────┐
     └─── UPDATE/DELETE NEVER permitted ───│  locked  │
                                           └─────┬────┘
                                                 │ governance write only
                                                 ▼
                                           ┌──────────┐
                                           │   core   │
                                           └──────────┘
```

- `volatile`: default for every new row. Decays, can be overwritten, influenced by agent-self writes.
- `validated`: auto-promoted; can still decay but only via real violations (not agent self-vote). Mutating confidence down requires `times_violated++` from actual outcome evidence.
- `locked`: human-promoted (via `cos_promote`). UPDATE/DELETE blocked by trigger. Confidence frozen at promotion value.
- `core`: governance-level (e.g. promoted rule file). Immutable by any agent path; only `governance-*` task marker can touch via a dedicated admin tool (not exposed via MCP).

Enforcement: SQLite trigger `trg_learned_patterns_protect` raises on UPDATE/DELETE where `old.trust_tier IN ('locked','core')` unless the session is in governance mode (checked via `$COS_TASK_CURRENT` readable through `PRAGMA user_version` or a session-bind variable; simpler: block all UPDATE/DELETE on those tiers from MCP code paths and expose a separate `admin_patch` helper not registered as MCP tool).

## Provenance Tags

| Value | Set by | Trust default |
|---|---|---|
| `agent_self` | observations via `capture.py`, pattern via `learn_narrative` | volatile only |
| `user_directive` | writes originating from explicit user instructions (hook flags) | volatile → validated possible |
| `extracted_from_outcome` | `learn_extract` mining over `task_outcomes` | volatile → validated with >=3 reinforcements |
| `promoted_from_rule` | `cos_promote` with target=rule | starts at `locked` |
| `imported` | initial bootstrap / external import | volatile; re-validate in-project |

## Data Shape Contract (envelope v2)

All `cos_*` tools after Phase G return:

```json
{
  "ok": true,
  "data": {
    "results":  [...],          // primary payload (or `record` / `status` / `entries`)
    "count":    N,              // present when `results` is a list
    "meta": {
      "layer":              "memory|docs|tasks|metrics|routing|graph|health|learning",
      "tokens_estimated":   347,
      "truncated":          false,
      "query":              "...",           // when applicable
      "source":             "fts5+semantic", // retrieval-only
      "filters_applied":    {"status":"wip"} // when applicable
    }
  }
}
```

Legacy fields in `data` are preserved for backward compat (no rename), only `meta` is added. `_shared.ok()` gains an optional `meta={}` kwarg; when caller supplies it, the helper merges it into `data.meta`.

## Phase G Roadmap

| Slice | Scope | LOC | Ship gate |
|---|---|---|---|
| **G.0** ✅ | Audit + contract spec | 0 code | doc review |
| **G.1** ✅ | Migration v7 — trust_tier, provenance (both tables), memory_audit table, protection trigger, helpers | ~150 | 23 migration tests green |
| **G.2** ✅ | Narrative sanitizer + length caps + wire into `capture.py` / `learn_narrative` / `_upsert_pattern` | ~120 | 44 sanitizer tests green |
| **G.3** ✅ | Envelope `meta` block — `_shared.ok()` + propagated through all 21+ tools | ~180 | 24 envelope tests green |
| **G.4** ✅ | Throttle `cos_learn_validate` per session (1h window) + locked/core short-circuit; migration v8 (`pattern_validations`) | ~100 | 6 throttle tests green |
| **G.5** ✅ | Token-budget enforcement on `ok()` — trims `results` tail, records `truncated_results_from/to` | (in G.3) | envelope tests cover overflow |
| **G.6** ✅ | `learn_narrative` → volatile/agent_self/0.3/0.5 defaults; `_upsert_pattern` stamps provenance from source mapping | ~30 | 4 G.6 tests green |
| **G.7.1** ✅ | `retrieval-routing.md.tmpl` fragment + `base.yaml` wiring + CLAUDE.md governance copy | ~60 | renderer tests pass |
| **G.7.3** ✅ | Migration v9 (`document_chunks_fts`) + `cos_doc_search(mode=auto\|semantic\|lexical)` + identifier-first heuristic | ~90 | `test_doc_search_fallback.py` |
| **G.8** ✅ | Migration v10 (`retrievals`) + `tools/retrieve.py` (log/cite/backfill/learn) + MCP `cos_retrieval_cite` + `cos_retrieval_learn` + task-done hook | ~250 | 22 retrieve tests green |
| **G.9** ✅ | `background.py` opt-in indexer (`COS_BACKGROUND_INDEX=1`) + `cos_health.background_indexer` surface + 3-failure disable | ~300 | 27 threading tests green |
| **G.10** ✅ | `digest.py` + `cos_digest_regenerate` MCP tool + `session-context.sh` wiring + `task-done.sh` refresh | ~250 | 11 digest tests green |
| **G.11** ✅ (scaffolding) | Migration v11 (`retrieval_quality`, `document_chunks.contextual_prefix/context_model`) + `retrieval_quality.py` + `cos_retrieval_quality` + `cos_retrieval_enrichment_check` | ~180 | 20 quality tests green — LLM enrichment deliberately stubbed |

**Ship gate for full Phase G:** `881 passed` in `core/thinking_os/tests/` + MCP self-test green at schema v11.
Pre-existing hook-test failures in `tests/test_hooks_phase_e.py` / `phase_f.py` (5+10) reflect a prior `COS_STATE_DIR` → `COS_AGENT_DIR` refactor and are **not caused by Phase G** — tracked separately.

**Order of execution (actual):** G.0 → G.1 → G.2 → G.3 → G.4 → G.6 → G.7.1 → G.7.3 → G.8 → G.9 → G.10 → G.11. Hardening slices (G.1–G.6) shipped before any extension path touched the retrieval / learning loop, per the original guarantee.

## G.1 — Migration v7 (this slice)

**Changes:**

1. `ALTER TABLE learned_patterns ADD COLUMN trust_tier TEXT NOT NULL DEFAULT 'volatile'`
2. `ALTER TABLE learned_patterns ADD COLUMN provenance TEXT NOT NULL DEFAULT 'agent_self'`
3. `ALTER TABLE observations ADD COLUMN provenance TEXT NOT NULL DEFAULT 'agent_self'`
4. `CREATE TABLE memory_audit` (append-only audit log)
5. `CREATE TRIGGER trg_learned_patterns_protect_update` — RAISE when `OLD.trust_tier IN ('locked','core')`
6. `CREATE TRIGGER trg_learned_patterns_protect_delete` — same
7. Helpers in `db.py`: `has_memory_audit_table`, `is_pattern_protected`, append `memory_audit` to `_TABLES`

**Audit row shape:**

```sql
CREATE TABLE memory_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    actor        TEXT NOT NULL,       -- component name e.g. 'capture.py', 'learn_narrative'
    action       TEXT NOT NULL,       -- insert|update|delete|reject
    source_table TEXT NOT NULL,
    source_id    INTEGER,
    old_value    TEXT,                -- JSON snippet (nullable)
    new_value    TEXT,                -- JSON snippet (nullable)
    reason       TEXT                 -- human-readable note / rejection cause
);
CREATE INDEX idx_memory_audit_table ON memory_audit(source_table, source_id);
CREATE INDEX idx_memory_audit_created ON memory_audit(created_at);
```

**Validation (Python-side, since SQLite CHECK on ADD COLUMN is version-fragile):**

```python
_VALID_TRUST = {"volatile", "validated", "locked", "core"}
_VALID_PROVENANCE = {"agent_self", "user_directive", "extracted_from_outcome", "promoted_from_rule", "imported"}
```

Guards in G.2 call these sets before write.

**Tests (added to `tests/test_db.py` and new `tests/test_brain_hardening.py`):**

1. `test_migration_v7_idempotent` — run twice, schema_version stays at 7
2. `test_learned_patterns_has_trust_tier_column`
3. `test_learned_patterns_has_provenance_column`
4. `test_observations_has_provenance_column`
5. `test_memory_audit_table_exists`
6. `test_default_trust_tier_is_volatile` — new insert gets `volatile`
7. `test_default_provenance_is_agent_self`
8. `test_protected_pattern_update_raises` — UPDATE on `trust_tier='core'` raises
9. `test_protected_pattern_delete_raises` — DELETE on `trust_tier='locked'` raises
10. `test_volatile_pattern_update_allowed` — baseline not broken
11. `test_memory_audit_append_only` — insert-only, no UPDATE trigger
12. `test_has_memory_audit_table_helper`

**Non-goals for G.1:**
- No validation at write-time (that's G.2)
- No envelope meta block (that's G.3)
- No throttling (that's G.4)

## G.11 — Precision tracker status (delivered as scaffolding)

- [core/thinking_os/precision.py](../core/thinking_os/precision.py) ships three public symbols:
  - `precision_snapshot(conn, *, lookback_days=30) -> PrecisionSnapshot`
  - `should_enable_contextual_enrichment(conn) -> (bool, reason, dict)`
  - `contextual_enrichment_stub(heading_path, content, doc_title="")` — **pure no-op** placeholder.
- Trigger rule: recommendation flips to `True` only when `precision < 0.70` **and** resolved-sample ≥ 30. Pre-v10 DBs return `(False, "pre_v10_no_signal", …)`.
- No LLM dependency introduced. Future activation (Phase G.12) swaps the stub body for an Anthropic Haiku call keyed by chunk mtime.
- Tests: [core/thinking_os/tests/test_precision.py](../core/thinking_os/tests/test_precision.py) — 16 cases covering empty DB, lookback window, threshold, pre-v10 tolerance, stub purity.

## G.2 — Sanitizer (next slice)

**Block patterns** (regex, case-insensitive, matched against narrative/title/pattern on write):

```
r"(?i)\bignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|directives?|prompts?)"
r"(?i)\bdisregard\s+(the\s+)?(above|prior|previous|system)"
r"(?i)\bfrom\s+now\s+on\s+(you|i|we)\s+(will|must|are)"
r"(?i)\byou\s+are\s+(now\s+)?(a\s+)?(different|new|unrestricted)"
r"(?i)\bsystem\s+prompt\b"
r"(?i)\boverride\s+(the\s+)?(default|system|safety)"
```

**Length caps:**
- `title`: 200 chars
- `narrative` (observations): 4000 chars
- `pattern` (learned_patterns): 500 chars
- `key_insight`: 500 chars

**Behavior on match:**
- If block pattern detected: reject write, log to `memory_audit` with `action='reject', reason='injection_pattern_matched:<pattern_index>'`. Return `fail("validation", "rejected: potential prompt injection")`.
- If over length: truncate with `… [truncated]` suffix, log to `memory_audit` with `action='truncate'`.

**Integration points:**
- `capture.py::capture_observation` — sanitize before INSERT
- `tools/learning.py::_upsert_pattern` — sanitize `pattern` field
- `tools/learning.py::learn_narrative` — sanitize `key_insight`, `what_failed`, `what_worked`
- `tools/memory.py::memory_promote` — sanitize promoted content

## Risks & Mitigations

- **R1: False positive on legitimate text** ("The rule says ignore comments" matches "ignore … previous"). Mitigation: regex uses boundary-word anchors + context words (`previous instructions`, not `previous comments`). Tests cover false positives explicitly.
- **R2: Sanitization breaks existing DB rows.** Mitigation: applied only at write-time. Existing rows remain; if suspect, tag via one-time backfill script (separate task, not in G.1/G.2).
- **R3: Trigger-based protection fires during legitimate governance edits.** Mitigation: Governance path uses direct SQL via a helper that first flips a temp `PRAGMA user_data` flag bypassable only from `admin_patch.py` (which is NOT MCP-exposed).
- **R4: Migration fails on older SQLite without ALTER TABLE ADD COLUMN WITH DEFAULT.** Mitigation: SQLite 3.6+ supports this. Minimum target is 3.37 (matches `sqlite3` stdlib on Python 3.11+). Test covered by migration test.

## Ship Checklist (per slice)

- [ ] Migration applies cleanly to fresh DB
- [ ] Migration applies cleanly to existing DB at v6
- [ ] Migration idempotent (re-running no-ops)
- [ ] All existing tests still pass
- [ ] New tests added and green
- [ ] `cos_health` returns expected schema_version
- [ ] Self-test (`python core/thinking_os/server.py --test`) passes
- [ ] Doc updated (this file)
