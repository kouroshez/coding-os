---
audit_id: hook-system-remediation-2026-06-05
task_id: TASK-104
status: in_progress
created: 2026-06-05
---

# Hook-System Remediation — 17-Agent Reverse-Engineering Audit

**Source findings:** 17-agent workflow (wka4h1afk) — 90 hook scripts (84 registered) + memory/cron/adapter/UI systems. Full raw findings: workflow output `tasks/wka4h1afk.output` (271 KB); curated digests `tool-results/buzsf9gr9.txt` (critics) + `b6mwk1h0e.txt` (systems). Totals: **4 critical · ~27 high · 26 medium · 31 low** (149 incl. systems).

**Matched exhaustive:**  ·  () ·
**Matched scope:** fix · verify · audit
**Predicates:** every category row `Verified=yes` + `Hits after=0`; per-fix test+verify; per-fix commit; do NOT break concurrent agents (TASK-100 scripts/hooks output-quality, TASK-102 web/cli logging are LIVE).

## Categories — Mandatory Coverage Table (10 remediation streams)

| # | Category (stream) | Task | Pattern / scope | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Learning-loop memory corruption | TASK-104 | decay.py/learning.py/session_enrich.py/nightly.py/cron_commands.py | 5 | 7 | yes | 0 | yes | d69a52b·568c4d9·b227b83·d752bd7·7096979 (auto-brain marker→N9, hour knob→N7) |
| 2 | Danger/secret regex holes | TASK-105 | block-dangerous-commands.sh/block-secrets.sh/_helpers/check_dangerous_rm.py | 3 | 4 | yes | 0 | yes | 10d1240·2d6b7de (25 hook behavior tests) |
| 3 | Per-panel marker-scope drift | TASK-107 | nudge-*/session-end/warn-abandoned/capture-work-log/cos-env | ~9 | 8 | yes | 0 | yes | 25d38fd (25 files; panel-scope smoke 1-4 pass; 0 new test-hooks failures vs baseline 60/67) |
| 4 | Board transition atomicity | TASK-108 | workflow.py/4 helpers/consume_override | 6 | 2 | yes | 0 | yes | e937785 (388 board tests + CAS-conflict smoke; expected_from subsumed by under-lock re-verify) |
| 5 | Memory-load correctness | TASK-109 | session-context.sh/learning.py/enforce-memory-check/server.py | 4 | 5 | yes | 0 | yes | 863d3d7 (digest-startup + boost smoke + gate-TTL unit + 142 learning/memory tests + MCP self-test) |
| 6 | Codex now-fixable parity | TASK-110 | codex-*-dispatch.sh/adapter.yaml/test_adapter_parity.py | 3 | 0 | yes | 0 | yes | 5bbb8a6 (6a wired + 6c parity test 5/5; 6b refiled TASK-153 — exit-0-stdout drop, no silent no-op) |
| 7 | Hub learning panel | TASK-111 | scheduled.py/SettingsPage.tsx | 4 | 0 | yes | 0 | yes | 27deb9f (route+model registered, tsc 0 errors; hour-knob fold-in deferred) |
| 8 | Data-driven adapter detection | TASK-112 | doctor.py/cos-env.sh | 3 | 0 | yes | 0 | yes | 6e96f5c (cursor loader smoke + 633 no-hardcoded tests; 8a/8c→TASK-155) |
| 9 | Hot-path Pre/Post dispatcher | TASK-113 | test-first/warn-mcp-down/auto-regen-doc-index/auto-brain-decay | ~6 | 0 | yes | 0 | yes | d7004d6·d08c282 (debounce+path smokes; 9a/9b/5d-autostamp→TASK-161 golden-window) |
| 10 | enforce-anti-ambiguity dead gate | TASK-114 | enforce-anti-ambiguity.sh/cognition.py | 2 | 2 | yes | 0 | yes | 1290412 (DB-state gate + clear-on-pass test) |

## Per-Stream Implementation Checklist

> Status markers: ⬜ todo · 🟦 in-progress · ✅ done+verified. Update the category-table `Verified` cell + call `cos_supervise_record_output` on each stream close.

### Stream 1 — TASK-104 · Learning-loop memory corruption (P0, isolated from concurrent work)
- ✅ 1a CRIT — `_upsert_pattern` INSERT stamps `last_validated`+`last_accessed_at` so fresh patterns aren't archived on first decay. **DONE d69a52b + regression test.**
- ✅ 1b HIGH — `archived_at` (migration v33) — prune gates on time-since-archived so freshly-archived knowledge gets full grace. **DONE 568c4d9 + grace tests.**
- ✅ 1c MED — re-extract revives archived pattern (`promoted_to=NULL`, `archived_at=NULL`) + refreshes recency. **DONE d69a52b / 568c4d9.**
- ✅ 1d HIGH — `session_enrich` decay routes through shared `run_decay_locked` (flock). **DONE b227b83 + throttle test.**
- ✅ 1e HIGH — decay marker unified at `<db-dir>/.last-decay` (mtime throttle, shared lock) for nightly + session_enrich. **DONE b227b83.** ↪ auto-brain-decay.sh marker alignment folded into N9 (avoids live TASK-100 hook collision).
- ✅ 1f MED — `nightly.run_project` regenerates digest after extract/decay. **DONE d752bd7.**
- ✅ 1g MED — Linux systemd `--user` .timer/.service scheduler; `cos cron install` dispatches by OS. **DONE 7096979 + tests.** ↪ misleading per-project `hour` knob removal folded into N7 (web layer).

### Stream 2 — TASK-105 · Danger/secret regex (P0, isolated)
- ✅ 2a CRIT — rm -rf now blocked via shlex-correct helper (`_helpers/check_dangerous_rm.py`) for `/`·`.`·`..`·`./`·`*`·`-fr`·`-r -f`·top-level abs·project dirs. **DONE 10d1240 + 19 tests.**
- ✅ 2b HIGH — `sk-` regex keyed on specific prefix (sk-ant-api##-/sk-proj-/40+ alnum) — kebab slugs no longer false-fire, real keys still caught. **DONE 2d6b7de + tests.**
- ✅ 2c MED — force-push refspec `+main`/`+HEAD:main` blocked. **DONE 10d1240 + tests.**
- ✅ 2d MED — secret skip-list matches path segments/basenames not substrings (`latest/`,`contest/` no longer silently unscanned). **DONE 2d6b7de.** ↪ `.env` git-add guard left best-effort by design — the installed git pre-commit hook scans the staged set (the real defense, per audit recommendation).

### Streams 3-6, 8 — DONE (detail in commits + task work logs)
- ✅ **N3 (TASK-107) 25d38fd** — 6 marker classes panel-scoped (nudge debounce, `.intent.json`, `.task-mode`, `.*-nudged`, capture-work-log, warn-graph-empty) + Stop hooks (session-end, warn-abandoned-task) upgrade panel id from stdin w/ agent-dir fallback. 25 files; smoke A-D + 0 new test-hooks regressions.
- ✅ **N4 (TASK-108) e937785** — `workflow.transition` write path = one `BEGIN IMMEDIATE` section: re-SELECT under lock + WIP-under-lock + CAS `UPDATE … WHERE status=?` (rowcount→transient) + MD-in-txn + rollback/raise. 4 helpers → `get_connection`; consume_override flock. `expected_from` subsumed by under-lock re-verify. 388 board tests + CAS smoke. (cos-env ppid-GC deferred — orphan-dir nicety.)
- ✅ **N5 (TASK-109) 863d3d7** — 5a digest on startup; 5b learn_suggest CASE-boost for complexity/task_type; 5c banner `⌛stale` gate TTL; 5d enforce-memory-check honest self-attest wording (auto-stamp→N9); 5e cos_search default min_confidence=0.3 + stale-reinforce-claim fix. 142 tests + smokes.
- ✅ **N6 (TASK-110) 5bbb8a6** — 6a codex posttool dispatcher wires auto-reindex-shell-ops + auto-prune-deleted-files (side-effect hooks); 6c parity test (for-loop == adapter.yaml). 6b (verify-completion-claim/prevent-premature-done) → **TASK-153**: they emit exit-0 stdout the dispatcher drops, so wiring = silent no-ops; needs Stop-dispatcher stdout-forwarding + codex-runtime verify.
- ✅ **N8 (TASK-112) 6e96f5c** — 8b doctor `loader_fns` maps `cursor_mcp_json`→`_load_claude_json` (Cursor MCP diagnostic no longer skipped); 8d drop speculative GEMINI_/ANTHROPIC_ session vars. 8a (data-driven cos-env detection via regen snippet) + 8c → **TASK-155** (hottest file; needs generator + per-adapter smoke).

- ✅ **N7 (TASK-111) 27deb9f** — 7b `POST /api/scheduled/run/{slug}`→`nightly.run_project` via `asyncio.to_thread` (fail-soft RunResult); 7d `scheduled_status` typed `response_model`; 7a SettingsPage `ScheduledStatus` enriched + last-run/cron render; 7c "Run learning loop now" button. Route registered + tsc 0 errors. (per-project `hour`-knob removal deferred — Cortex-UI collision.)
- ✅ **N9 (TASK-113) d7004d6·d08c282** — 9c test-first-reminder debounced once/file/session (panel marker); 9d auto-regen-doc-index finds `src/scripts/regen_doc_index.py`; 9e warn-mcp-down skips spawn-probe within `COS_MCP_PROBE_TTL`; N1-fold auto-brain-decay marker→`<db-dir>/.last-decay`. Smokes pass. 9a in-process dispatcher + 9b dead-stub removal + 5d memory-check auto-stamp → **TASK-161** (registry+golden-heavy, clean-window only).
- ✅ **N10 (TASK-114) 1290412** — enforce-anti-ambiguity gate made live via the `ambiguity_violations` DB table (pass clears the session's rows); FAIL branch `exit 1`→`exit 2`; fail-open guards. + clear-on-pass test.

## Resume Marker

<!-- last_updated_row: 9 -->
<!-- next_unchecked_row: 0 -->
<!-- last_updated_at: 2026-06-05T00:00:00Z -->
<!-- progress: ALL 10 streams closed (N1-N10). Safe fixes shipped; the registry/golden-heavy + unverifiable-without-runtime sub-items refiled as scoped tasks: TASK-153 (codex Stop stdout forward), TASK-155 (data-driven cos-env detection), TASK-161 (hot-path dispatcher + dead-stub + memory-check auto-stamp). -->
<!-- sequence: N1(104) → N2(105) → N10(114) → N3(107) → N5(109) → N4(108) → N6(110) → N8(112) → N7(111) → N9(113-last) -->

## Notes

- **Concurrency:** TASK-100 (scripts/make/hooks output-quality) + TASK-102 (web/cli logging) are LIVE on other sessions. Sequencing starts with thinking_os-isolated streams (1,2,10) then board/state (3,4,5), defers hot-path hook refactor (9) + hub UI (7) which overlap TASK-100/102 — coordinate via `git pull --rebase` + explicit-path commits, stage only my files.
- **Evidence model:** per-fix commit sha recorded in the category table Evidence cell; stream-close evidence via `cos_supervise_record_output`. Checkboxes are working notes; the guardian trusts the formula_dispatches DB rows, not the ticks.
- **WIP:** in_progress cap=1 held by a concurrent session — my stream task-starts use `bypass_wip` (user-authorized parallel work), one of MY streams in_progress at a time.

## Closing Checklist (guardian asserts)

- ⬜ Every category row `Hits after = 0` (or justified n/a)
- ⬜ Every category row `Verified = yes`
- ⬜ Every category row non-empty `Evidence`
- ⬜ EvidenceBundle via `cos_supervise_record_output`
- ⬜ Reviewer subagent re-grep zero
- ⬜ Frontmatter `status: completed` + completed date
