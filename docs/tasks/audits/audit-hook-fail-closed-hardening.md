---
audit_id: hook-fail-closed-hardening
task_id: TASK-196
intent_detected_at: 2026-06-05T00:00:00Z
matched_exhaustive: ["", ""]
matched_scope: ["fix"]
predicates: ["all_safety_gates_fail_closed", "hook_latency_measurable", "fanout_budget_guarded"]
status: completed
created: 2026-06-05
completed: 2026-06-06
---

# Audit: Hook layer enterprise-grade hardening — fail-closed invariant + latency SLI + fan-out budget + display signal-to-noise

## Source Intent

**User prompt (paraphrased — no verbatim leak):** write a grouped executable
checklist for all items and do all of it deeply and in detail, fix completely,
and test + verify the changes and check outputs.

**Matched exhaustive vocabulary:**  ·
**Matched scope verbs:** fix
**Predicates to satisfy:** every safety/enforcement gate fails CLOSED on
parser/helper unavailability · the hook layer has a measurable per-invocation
latency SLI · PreToolUse fan-out width is guarded by a regression test · the
hook activity surface defaults to decision-states.

## Background (doc anchor)

[docs/engineering/observability-eye.md](../../engineering/observability-eye.md)
§ I3 / E6 already specifies the contract: a security/enforcement hook that
cannot evaluate must **DENY** (fail-closed) and capture the failure — never
silently ALLOW. This audit implements that contract plus the two measurement
gaps (latency, fan-out budget) and the display gap.

## Categories — Mandatory Coverage Table

| # | Category | Pattern (grep/AST/spec) | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|
| A1 | Irreversible/integrity-harm gates fail OPEN when jq missing (empty extraction → exit 0 allow) | `jq -r .*\|\| echo ""` in block-secrets, block-dangerous-commands, block-protected-files, branch-guard, enforce-task-transition | 5 | 10 | yes | 0 | yes | All 5 gates: `cos_require_parser` + `cos_json_field`; sweep `grep -nE 'jq -r .*(\|\| echo ""\|\| echo allow)'` over the 9 gates → 0 hits |
| A2 | Harm gates: helper/parser-missing → ALLOW | `reason=helper-missing` + `\|\| exit 0` + `\|\| echo allow` on a security decision | branch-guard:59, enforce-task-transition:67, block-dangerous-commands:58 | 3 | yes | 0 | yes | branch-guard.sh helper-missing → exit 2; enforce-task-transition.sh helper-missing → exit 2; block-dangerous-commands.sh RM_VERDICT=error → scoped block on recursive rm |
| A3 | Quality gates fail OPEN when jq missing | `jq -r .*\|\| echo ""` in block-bad-patterns, block-migration-conflict, block-uv-heredoc, block-hardcoded-literals | 4 | 14 | yes | 0 | yes | All 4 gates: `cos_require_parser` + `cos_json_field`; smoke: block-bad-patterns no-parser sandbox → exit 2 |
| B1 | No per-hook latency captured (cos_log_hook second-resolution ts, no duration) | `dt=` field absent from cos_log_hook emit; ts is `%H:%M:%SZ` | src/core/hooks/cos-env.sh | 1 | yes | 0 | yes | cos-env.sh: `COS_HOOK_T0=$EPOCHREALTIME` + `cos_hook_elapsed_ms` integer-µs math; smoke log line emits `dt=10ms` |
| B2 | No fan-out budget regression guard | `grep -L fanout tests/` → test absent | tests/ | 1 | yes | 0 | yes | tests/test_hook_fanout_budget.py (4 tests, Bash≤12 + Write\|Edit≤28); `pytest` green |
| C1 | hooks-log surface shows lifecycle noise (enter/ok) by default | no decision-state default filter in `cos hooks-log` | src/cli/main.py | 1 | yes | 0 | yes | `cos hooks-log` default hides `[enter]`/`[ok]`; `--all`/`--verbose` restores; verified via fixture log |

> Hits-after semantics: A1/A2/A3 are removals (target 0 un-guarded fail-open
> extractions). B1/B2/C1 are additive (target 0 = gap closed, evidenced by a
> green test / present instrumentation).

## Groups (the executable checklist)

### Group A — Fail-closed invariant (Tier 1, the security fix)
- [x] A0. Add `cos_require_parser <hook_id>` + `cos_json_field <path...>` to `cos-env.sh` (jq fast-path → python3 fallback → block-if-neither). New helper `_helpers/json_field.py`.
- [x] A1. Convert the 5 harm gates' `jq … || echo ""` extractions to `cos_json_field` + guard with `cos_require_parser`.
- [x] A2. Fix the 3 helper-missing fail-opens to DENY + `cos_say` capture.
- [x] A3. Convert the 4 quality gates' extractions to `cos_json_field`.
- [x] A4. Regression test `tests/test_hooks_fail_closed.py` — each harm gate exits 2 (not 0) when no JSON parser is on PATH and the payload is a dangerous action.

### Group B — Measurement (Tier 2)
- [x] B1. Stamp `COS_HOOK_T0=$EPOCHREALTIME` on cos-env.sh source; emit `dt=<ms>` on every `cos_log_hook` line (pure-bash integer µs math).
- [x] B2. `tests/test_hook_fanout_budget.py` — assert PreToolUse Bash fan-out ≤ budget (cap 12; current 8) and no single event/matcher exceeds it.

### Group C — Display signal-to-noise (Tier 3)
- [x] C1. `cos hooks-log` defaults to decision-states (fire/block/warn/paths/reminded/full/debounced/skip); `--all`/`--verbose` restores lifecycle rows.

## Resume Marker

<!-- last_updated_row: 6 -->
<!-- next_unchecked_row: 0 -->
<!-- last_updated_at: 2026-06-06T01:40:00Z -->

## Notes

- python3 is a hard dependency of coding-os (MCP server, every `_helpers/*.py`,
  the `cos` CLI). So the realistic degraded case is "jq missing, python3
  present" → the parser fallback keeps the gate FUNCTIONING. Only the
  impossible-in-practice "neither parser" case fails closed (blocks). This is
  strictly better than both the old fail-open and a naive block-everything.
- Bootstrap escape: `COS_ALLOW_MISSING_DEPS=1` lets a human install jq/python3
  when both are absent (documented in cos-env.sh).
- Out of scope by design (intentional fail-open, workflow nudges not security
  gates): enforce-doc-anchor, enforce-skill, enforce-graph-context,
  enforce-graph-first-read, enforce-rename-plan, enforce-memory-check,
  enforce-zoom — these WARN by design so the agent discovers the workflow layer;
  fail-open there skips a process step, not an irreversible/security action.

## Closing Checklist (the guardian asserts these)

- [x] Every category row has non-empty `Files scanned`
- [x] Every category row has `Hits after = 0` (or explicit `n/a` with justification in Notes)
- [x] Every category row has `Verified = yes`
- [x] Every category row has a non-empty `Evidence` cell
- [x] EvidenceBundle submitted via `cos_supervise_record_output`
- [x] Reviewer subagent re-grep produced zero hits
- [x] Frontmatter `status` updated to `completed` and `completed` date filled
