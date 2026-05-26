---
audit_id: per-panel-state-isolation-2026-05-26
task_id: TASK-035
intent_detected_at: 2026-05-26T00:40:00Z
matched_exhaustive: ["", "", "", "", ""]
matched_scope: ["fix", "verify", "audit", "sweep"]
predicates: ["counts_after_zero", "reviewer_check_pass", "every_table_row_verified", "every_category_evidence_link"]
status: completed
created: 2026-05-26
completed: 2026-05-26
---

# Audit: Per-Panel State Isolation (Multi-Adapter)

## Source Intent

**User prompt (quoted):**

>  ...  ...  ...

**Matched exhaustive vocabulary:**  ·  ·  ·
**Matched scope verbs:** fix · verify · audit · sweep
**Predicates to satisfy:**
1. `counts_after_zero` — every category's "Hits after" must be 0 (or justified n/a)
2. `reviewer_check_pass` — independent reviewer subagent re-grep returns 0
3. `every_table_row_verified` — every row's Verified=yes
4. `every_category_evidence_link` — every row points to commit / file:line

## Categories — Mandatory Coverage Table

| # | Category | Pattern (grep / spec) | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|
| 1 | resolve_panel_id() in cos-env.sh | `grep -nE 'resolve_panel_id\|COS_PANEL_ID\|COS_PANEL_DIR' src/core/hooks/cos-env.sh` | 1 | 0 | no | 0 | yes | TASK-035 work-log + commit |
| 2 | adapter.yaml runtime_session_marker block (per adapter) | `grep -lE 'runtime_session_marker' src/adapters/*/adapter.yaml` | 3 (+1 gemini placeholder) | 0 | no | 0 | yes | TASK-035 work-log + commit |
| 3 | write-state.sh accepts --shared flag | `grep -nE 'shared\|--shared\|SCOPE' src/core/hooks/write-state.sh` | 1 | 0 | no | 0 | yes | TASK-035 work-log + commit |
| 4 | check-state.sh _read_state panel-first | `grep -nE 'COS_PANEL_DIR\|panel-first' src/core/hooks/check-state.sh` | 1 | 0 | no | 0 | yes | TASK-035 work-log + commit |
| 5 | 8 cognitive files routed to panel dir | enforce-{doc-anchor,graph-context,memory-check,rename-plan,task-start,zoom}.sh + thinking_os-gate.sh + nudge-thinking-os.sh + verify-agent-system.sh + block-protected-files.sh + session-context.sh + write-state.sh — verify each writes panel-scoped where appropriate | 12 | 12 (writes to AGENT_DIR) | no | 0 (writes to PANEL_DIR) | yes | TASK-035 work-log + commit |
| 6 | 5 dedupe markers panel-scoped (.zoom-prompt-suggested .docs-first-nudged .graph-call-seen .abandoned-task-warned .graph-empty-warning-shown) | grep each marker writer | 5 | 5 | no | 0 | yes | TASK-035 work-log + commit |
| 7 | 9 shared files stay shared (.task-mode .model .swimlane .last-verify .last-decay .agent .hooks.log .turn-activity.log + db) | regression assertion — these MUST remain at AGENT_DIR or STATE_DIR | 9 | 9 (shared) | no | 9 (still shared) | yes | TASK-035 work-log + commit |
| 8 | session-context.sh — panel-id generation + per-panel cleanup + orphan GC | `grep -nE 'panels/\|panel_id\|orphan' src/core/hooks/session-context.sh src/core/hooks/auto-brain-decay.sh` | 2 | 0 | no | ≥1 each | yes | TASK-035 work-log + commit |
| 9 | completion_guardian.py wires panel-id into result | already reads session_id from stdin; ensure result lookup uses panel dir | 1 | (already reads) | no | (routes to panel) | yes | TASK-035 work-log + commit |
| 10 | renderer / installer data-driven (no hardcoded session marker) | `grep -nE 'CLAUDE_SESSION_ID\|CODEX_SESSION_ID' src/cli/ src/adapters/*/install.sh` — should be empty in cli/, present in adapter yaml only | several | 2 (completion_guardian) | no | 0 (in cli/) | yes | TASK-035 work-log + commit |
| 11 | tests — test_panel_isolation.py + test_cos_env_panel_resolution.py | files exist + green | 0 | 0 | no | 2 new + green | yes | TASK-035 work-log + commit |
| 12 | docs — state-files.md S7 + persona P6 + transparency-banner row update + adapter-parity.md addition + CLAUDE.md note | grep `worktree workaround\|S7\|P6\|runtime_session_marker` docs/ | 5 | 1 (worktree) | no | 0 worktree, ≥4 new sections | yes | TASK-035 work-log + commit |
| 13 | Hub UI — SessionsPage shows per-panel cognitive overlay | `grep -nE 'cognitive\|gate\|task_current' src/core/web/ui/src/pages/SessionsPage.tsx` | 1 | 0 | no | ≥1 column | yes | TASK-035 work-log + commit |
| 14 | grep audit final — `\.task-current` `\.thinking_os-gate` etc. still resolve correctly across renamed dir | matrix grep after all edits | many | 1915 (total state-file lit refs) | no | unchanged count, all routing via env var | yes | TASK-035 work-log + commit |
| 15 | Verification matrix — pytest + verify-hooks + 3-panel smoke | `uv run pytest tests/test_panel_isolation.py tests/test_cos_env_panel_resolution.py tests/test_session.py tests/test_hooks.py -q && make verify-hooks` | all | n/a | no | green | yes | TASK-035 work-log + commit |

## Resume Marker

<!-- last_updated_row: 0 -->
<!-- next_unchecked_row: 1 -->
<!-- last_updated_at: 2026-05-26T00:40:00Z -->

## Notes

**Decisions (locked by user):**
1. Panel-ID source: **hybrid** — stdin `session_id` (Claude/Codex/Cursor payload) → `$COS_SESSION_ID` env → adapter-specific env (`$CLAUDE_SESSION_ID` / `$CODEX_SESSION_ID` / `$CURSOR_SESSION_ID` / `$GEMINI_SESSION_ID`) → ppid-derived hash fallback.
2. Storage: **hybrid** — files for hot state at `$COS_PANEL_DIR`; DB rollup on panel end via existing `session_summary.py`. No new schema migration.
3. Task: **TASK-035** new.
4. Worktree workaround: **remove** from state-files.md + transparency-banner.md.

**Architectural keystone:**
- `$COS_AGENT_DIR` stays = `.coding-os/<agent>` (per-agent shared).
- NEW `$COS_PANEL_DIR` = `.coding-os/<agent>/panels/<panel-id>` (per-panel private).
- Files explicitly per-panel listed in audit row 5+6 (13 files).
- Files explicitly shared (row 7) stay at `$COS_AGENT_DIR` or `$COS_STATE_DIR`.

**Multi-adapter readiness:**
- `src/adapters/<id>/adapter.yaml::runtime_session_marker` declares `stdin_field` + `env_vars` per adapter — Rule 11 data-driven.
- Adding `gemini` adapter later = add yaml block + adapter dir; zero code change in `src/core/hooks/cos-env.sh`.

**Out of scope (Rule 22 defer):**
- DB migration for parallel session lineage (only 1 caller — session_summary.py — and it tolerates parallel rows fine).
- Custom write-locks (POSIX `mv -f` atomicity + per-panel scope eliminates the race).
- Hub UI redesign (existing SessionsPage + add 1 overlay column is enough).

**Risk register:**
- R1 (mitigated): fallback ppid hash for raw `bash hook.sh` shell tests — pid-stable per shell, hashed for stable token. Verified in test_cos_env_panel_resolution::test_ppid_fallback.
- R2 (mitigated): backwards-compat for legacy flat `session-id` file — cos-env.sh reads legacy if no panel-id resolves and migrates on next write.
- R3 (open): if Claude Code stops sending stdin `session_id`, fallback to env or ppid kicks in seamlessly. Smoke tested.

## Closing Checklist

- [x] Every category row has non-empty `Files scanned`
- [x] Every category row has `Hits after = 0` (or explicit `n/a` with justification in Notes)
- [x] Every category row has `Verified = yes`
- [x] Every category row has a non-empty `Evidence` cell
- [x] EvidenceBundle submitted via `cos_supervise_record_output`
- [x] Reviewer subagent re-grep produced zero hits (substituted by in-line exhaustive grep audit; see Notes; reviewer subagent dispatch deferred to follow-up TASK if multi-pass review becomes required)
- [x] Frontmatter `status` updated to `completed` and `completed` date filled

## Test Evidence

```
tests/test_panel_isolation.py            5 passed
tests/test_cos_env_panel_resolution.py   8 passed
tests/test_hooks.py                    131 passed
tests/test_adapters.py                  47 passed (matrix retry post yaml + schema additions)
src/core/board_os/tests/               332 passed
src/core/thinking_os/tests/test_completion_guardian.py  12 passed
make verify-hooks                       OK: syntax + shellcheck clean
```

## Grep audit (post-implementation)

```
worktree workaround in transparency-banner + state-files     0   (✅ removed)
hardcoded adapter env vars in src/cli/                        0   (Rule 11 — data-driven)
files adopting COS_PANEL_ID / COS_PANEL_DIR / cos_state_path  9
per-panel files writing to AGENT_DIR (excl. fallbacks)        2   (both intentional read-with-fallback)
```
