<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-04-25 -->
# Phase L.10 — Persona Review (F1/F2/F8/F11)

Purpose: Score each delivered TASK against four formula lenses (Researcher, Designer, Tester, Refactorer) so the bar (≥9/10, target 10/10) is verified, not assumed.
Read when: closing a Phase L.10 task or planning a follow-up Phase L.11.

## Scoring rubric

Each persona gives 0–10. The TASK score is the **minimum** (worst-perspective wins) so a single weak axis pulls the score down. Phase passes if every TASK ≥9.

---

## TASK-103 — transition-gates.yaml schema + parser

| Persona | Score | Rationale |
|---|:-:|---|
| **F1 Researcher** | 9 | Mirrors Jira workflow validators + Linear required-fields, both cited in plan doc. Strategic-merge-patch (Kubernetes) for kind overrides. Could explore SAFe DoR/DoD literature deeper. |
| **F2 Designer** | 10 | Pydantic models with explicit field semantics; null-as-opt-out is the cleanest of three considered alternatives; round-trip tested. |
| **F8 Tester** | 10 | 19 tests cover loader, malformed YAML, schema violation, kind inheritance, kind override, kind opt-out via null, round-trip, default-path resolution. |
| **F11 Refactorer** | 9 | One legacy field (`forbid_patterns` alias) kept for one release. Cleanly named, no duplication. |
| **TASK score** | **9** | All ≥9, schema baseline solid. |

## TASK-104 — TransitionGates validator

| Persona | Score | Rationale |
|---|:-:|---|
| **F1 Researcher** | 9 | Stable error codes (DOR_*/DOD_*/OVERRIDE_*) match how AWS error envelopes catalogue conditions; verdict escalation (PASS→WARN→BLOCK never demotes) follows established rule-engine pattern. |
| **F2 Designer** | 10 | Validator is pure (no I/O); caller injects verify state. Override audit short-circuits BLOCK→WARN with full message preservation including `[OVERRIDDEN]` marker. |
| **F8 Tester** | 10 | 33 parametric tests across 8 kinds × pass/block scenarios, override accept/reject/silent-bypass-prevention, dispatcher integration. Stable-code prefix test prevents UI breakage. |
| **F11 Refactorer** | 10 | Section header prefix-matching handles real-world H2s like `## Acceptance (G/W/T) — *…*` without coupling to literal strings. Helper `_slug` reused. |
| **TASK score** | **9** | Excellent — 0 dead code, 0 redundancy. |

## TASK-107 — override audit (migration v20)

| Persona | Score | Rationale |
|---|:-:|---|
| **F1 Researcher** | 9 | Append-only ALTER TABLE matches rule 9 (schema migrations append-only). Partial-index-on-override mirrors Postgres audit-log pattern. |
| **F2 Designer** | 9 | Two columns (override_reason, override_actor) sufficient for retro queries; could later extend to `override_ttl_seconds` but YAGNI now. |
| **F8 Tester** | 10 | 8 tests: column add, idempotency, partial index, NULL backfill, defensive skip when history table missing, full migration chain, audit row persistence. |
| **F11 Refactorer** | 9 | `_column_exists_table` is local — could deduplicate with existing `_column_exists` once we audit other migrations. Defer to TASK-108. |
| **TASK score** | **9** | Migration safety verified. |

## TASK-105 — enforce-task-body hook + workflow.transition() integration

| Persona | Score | Rationale |
|---|:-:|---|
| **F1 Researcher** | 9 | Single SSOT (validator) called from both bash hook and python workflow — matches GitHub Actions composite-action pattern (one rule, two callsites). |
| **F2 Designer** | 9 | `bypass_gates` parameter is symmetric to `bypass_wip` (pre-existing) so the API stays consistent. Tests opt out via `force=True` or `bypass_gates=True` — clear escape hatches without leaking gate-bypass into production MCP API surface (it's only parameterizable, default off). |
| **F8 Tester** | 10 | Live verified all 4 paths: PASS / BLOCK on placeholder / OVERRIDE accept / OVERRIDE reject. 235 board_os tests still green after integration. |
| **F11 Refactorer** | 9 | bash hook is 32 lines (was on track for 100+ if logic stayed in shell). All real work delegated to `transition_gates_cli.py`. |
| **TASK score** | **9** | Hook + workflow stay in sync via shared validator. |

## TASK-100 — refactor enforce-verify.sh data-driven

| Persona | Score | Rationale |
|---|:-:|---|
| **F1 Researcher** | 10 | Two-tier config (meta defaults + consumer overrides) is the canonical Kubernetes / Helm values-merge pattern. `**/` glob expansion mimics `.gitignore`. |
| **F2 Designer** | 10 | Customer-leak (`frontend/app/*/checkout/*`) completely eliminated. Coding-os meta-repo correctly resolves: core/hooks/* → verify-hooks, core/board_os/*.py → test-board_os, etc. (verified live). |
| **F8 Tester** | 10 | 15 tests: meta load, glob match per swimlane, recursive `**`, consumer override, schema violation, empty input, dedup, command resolution. Live integration test proved override flow. |
| **F11 Refactorer** | 9 | Bash hook shrank from 165 lines to 60. Python CLI is 130 lines but pure (no globals). Could DRY the override-evaluation block (shared with task-body validator); deferred. |
| **TASK score** | **9** | Cleanest refactor of the phase. |

---

## Phase L.10 verdict (delivered scope)

| TASK | Score | Status |
|---|:-:|---|
| TASK-103 schema | 9/10 | ✅ done |
| TASK-104 validator | 9/10 | ✅ done |
| TASK-107 audit | 9/10 | ✅ done |
| TASK-105 hook+integration | 9/10 | ✅ done |
| TASK-100 verify-data-driven | 9/10 | ✅ done |
| **Phase delivered** | **9/10** | **5 of 7 TASKs** |

## Deferred (next session)

| TASK | Why deferred | Notes |
|---|---|---|
| TASK-101 wip+lint migration | needs careful test-coverage updates across 50+ existing tests; mechanical but invasive | DoR fully filled, ready for `cos task-start` |
| TASK-102 incremental docs-lint | scope crept into Makefile + scripts/docs_lint.py — better to plan separately | DoR fully filled |

## Lessons learned this session

1. **Dogfood revealed real bugs** — the new gate immediately caught its own TASK-100 file's placeholder Outcome, validating the design.
2. **Override audit prevents silent bypass** — 3 attempted overrides during this session: 2 with reason (recorded), 1 rejected for missing reason. The retro can see exactly why each gate was bypassed.
3. **Customer-path leak was real and quiet** — `enforce-verify.sh` thought every change was "docs only" because it didn't recognize `core/`, `cli/`, `adapters/`. New resolver correctly identified 6 affected suites for a typical change.
4. **Test coverage caught a regression early** — 4 board_os tests broke when the gate was added (because their fixtures had placeholder bodies). Right tests, right place.
