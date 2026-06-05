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
| 6 | Codex now-fixable parity | TASK-110 | codex-*-dispatch.sh/adapter.yaml/hook_renderer.py | 3 | 3 | no | 3 | no | (pending) |
| 7 | Hub learning panel | TASK-111 | scheduled.py/SettingsPage.tsx/MemoryPage.tsx/api-types | 4 | 4 | no | 4 | no | (pending) |
| 8 | Data-driven adapter detection | TASK-112 | cos-env.sh/doctor.py/test_no_hardcoded_stacks.py | 3 | 4 | no | 4 | no | (pending) |
| 9 | Hot-path Pre/Post dispatcher | TASK-113 | registry.yaml/hook_renderer.py/test-first/auto-regen-doc-index/dead stubs | ~6 | 6 | no | 6 | no | (pending) |
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

### Stream 3 — TASK-107 · Per-panel marker-scope drift (P1) — ✅ DONE 25d38fd
- ✅ 3a — nudge-thinking-os/.zoom-prompt-suggested + nudge-docs-first/.docs-first-nudged → `${COS_PANEL_DIR:-$COS_AGENT_DIR}` (matches session-context panel-scope clear).
- ✅ 3b — nudge-graph-os/.graph-nudge + nudge-task-discovery/.task-nudge + track-discovery/.last-discovery-reminder → panel-dir; `.graph-nudge`/`.task-nudge` dirs + `.last-discovery-reminder` + `.intent.json` added to session-context SessionStart clear.
- ✅ 3c — session-end + warn-abandoned-task now read stdin → `cos_panel_upgrade_from_payload` → seeded `$COS_SESSION_FILE`, with stdin-session_id + agent-dir fallbacks (no more empty-session silent no-op). Smoke A/B/C/D pass.
- ✅ 3d — capture-work-log.sh:34 → `${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current`.
- ✅ 3e — `.intent.json` panel-first in producer (extract_intent.py `_intent_file_path`) + 4 consumers (prevent-premature-done, enforce-count-grounding, enforce-subagent-delegation, enforce-audit-artifact) + task_analyzer.py + intent-primer clears BOTH scopes; `.intent.json` + 3 `.*-nudged` added to COS_PER_PANEL_FILES; guardian already panel-first. Smoke: panel .intent.json written, cos_state_path routes all 4 basenames.
- ✅ 3f — `.task-mode` per-panel: writer (classify-task-mode upgrades panel id) + 6 readers (session-context banner, nudge-docs-first, enforce-task-start, enforce-zoom, enforce-memory-check, enforce-skill) all panel-first w/ agent fallback; warn-graph-empty marker → panel; sync-task-current upgrades panel id pre-write; write-state.sh comment corrected.

### Stream 4 — TASK-108 · Board transition atomicity (P1) — ✅ DONE e937785
- ✅ 4a — `workflow.transition` write path restructured into one `BEGIN IMMEDIATE` critical section: re-SELECT status under the lock (catches a peer that moved the row during the lock-free gate I/O), WIP count moved inside the lock (count→write race closed), CAS UPDATE `WHERE task_id=? AND status=?` with `rowcount!=1 → transient`, MD write inside the txn (rolls back the DB on failure), history INSERT, commit; `except: rollback; raise`. `mcp_tools.py` `expected_from`: NOT plumbed — the under-lock re-verify is strictly stronger than a caller-asserted pre-state the agent rarely supplies, so adding the param (2 signature layers) would be redundant churn. Verified: 388 board tests + CAS-conflict smoke (happy commit; expected_from-mismatch→transient).
- ✅ 4b — work_log_append.py / wip_limit_check.py / transition_gates_cli.py / _helpers/task_sync.py now open via `thinking_os.database.get_connection` (WAL + 5s busy_timeout) with a `sqlite3.connect(timeout=5)+PRAGMA busy_timeout` fallback when the import path is unavailable.
- ✅ 4c — consume_override.py now wraps the read-modify-write of the one-shot override JSON in an exclusive `fcntl.flock` (best-effort fallback + logged flock-unavailable). ↪ cos-env heartbeat-before-panel-upgrade transient-ppid-dir cleanup DEFERRED: it is an orphan-dir GC nicety (not a correctness bug — production hooks resolve the panel from stdin session_id), and cos-env.sh is sourced by every hook/adapter so a change there needs dedicated multi-panel testing out of this stream's blast radius.

### Stream 5 — TASK-109 · Memory-load correctness (P1) — ✅ DONE 863d3d7
- ✅ 5a — Agent-digest block split out of the compact/resume `if` and now runs on `startup|compact|resume`; a fresh session inherits the working-memory digest (the startup matcher's "Loading … memory digest" status is now true). Recovery-text + state-snapshot stay compact/resume-only (nothing to recover on fresh start). Smoke: `[Agent Digest]` emitted on SOURCE=startup.
- ✅ 5b — learn_suggest: `complexity`+`task_type` were accepted then ignored (no per-pattern column). Added a CASE-based relevance BOOST (matches concepts/pattern text, never excludes) → matching pattern outranks equally-confident non-match. Smoke: task_type=migration boosts the migration pattern to top.
- ✅ 5c — banner now applies the gate's 120-min TTL (`COS_GATE_TTL_SECONDS`, default 7200s): an expired gate renders `⌛stale` instead of looking valid. `_read_state` only checked session-ownership; staleness is checked on the gate's mtime. Unit: fresh not flagged, 3h-old flagged, env override honored. (Task/skill keep session-ownership semantics — no fabricated timer.)
- ✅ 5d — enforce-memory-check header + block message now state the marker is a SELF-ATTESTED good-faith claim (presence+freshness only, not proof of a real cos_search); the authentic PostToolUse auto-stamp on the cos_search/cos_learn_suggest MCP tool is folded into N9 (one coordinated registry+golden regen).
- ✅ 5e — cos_search default `min_confidence` 0.0→0.3 (skips decayed noise; fresh patterns at 0.5 still pass); `since_days` stays 0 (age opt-in so a valuable old decision isn't silently hidden — deliberately NOT 180). Confirmed raw search does NOT reinforce (that is `_boost_access` via cos_details); fixed the stale "updates access_count/confidence" docstring+annotation. 142 learning/memory tests + MCP self-test green.

### Stream 6 — TASK-110 · Codex now-fixable parity (P1, infra)
- ⬜ 6a HIGH — codex-posttool-dispatch.sh adds auto-reindex-shell-ops + auto-prune-deleted-files (drift vs adapter.yaml → graph staleness/zombie rows).
- ⬜ 6b HIGH — codex-stop-dispatch.sh adds verify-completion-claim + prevent-premature-done (3-layer intent half-wired).
- ⬜ 6c MED — generate dispatcher for-loops from adapter.yaml::delegates OR parity test asserting set-equality (kills future drift).

### Stream 7 — TASK-111 · Hub learning panel (P1, infra — coordinate w/ TASK-102 logging in web)
- ⬜ 7a HIGH — SettingsPage `ScheduledStatus` type + render cron_a + per-project run-logs (last_run_at/tasks/failures).
- ⬜ 7b HIGH — POST `/api/scheduled/run` (calls nightly.run_project / learn_extract) — ~15 lines.
- ⬜ 7c HIGH — 'Run learning loop now' button wired to the POST.
- ⬜ 7d MED — scheduled_status Pydantic response_model so api-types isn't `unknown` (structural drift fix).

### Stream 8 — TASK-112 · Data-driven adapter detection (P2, infra)
- ⬜ 8a HIGH — cos-env.sh:78-96 reads adapter.yaml::runtime_env_markers (not hardcoded if/elif).
- ⬜ 8b HIGH — doctor.py:1207 loader_fns generalized/registered (Cursor MCP diagnostic silently skipped today).
- ⬜ 8c MED — test_no_hardcoded_stacks extended to src/core/hooks/*.sh.
- ⬜ 8d LOW — remove speculative GEMINI_* literals (cos-env.sh:126/146/193); cursor adapter.yaml misleading camelCase comment.

### Stream 9 — TASK-113 · Hot-path Pre/Post dispatcher (P2, FULL refactor — high blast radius, do LAST, coordinate w/ TASK-100)
- ⬜ 9a — single PreToolUse + single PostToolUse Write|Edit dispatcher (parse stdin once, fan out in-process) — cuts ~42 spawns/edit.
- ⬜ 9b — delete dead stubs verify-changed-file + doc-sync-reminder + registry entries + regen.
- ⬜ 9c HIGH — test-first-reminder debounced (no `find . -maxdepth 6` ×2 over ~6.2k files per edit).
- ⬜ 9d HIGH — auto-regen-doc-index.sh path resolves src/scripts/regen_doc_index.py (currently dead).
- ⬜ 9e MED — warn-mcp-down debounce + lightweight probe (don't spawn full MCP server on compact/resume).

### Stream 10 — TASK-114 · enforce-anti-ambiguity dead gate (P1)
- ✅ 10a CRIT — gate made live via the canonical DB (more reliable than a producer-written file, which has the MCP-panel-resolution flaw): cos_ambiguity_check clears the session's prior `ambiguity_violations` each check (pass→none); the hook queries the table for the session. **DONE 1290412 + clear-on-pass test.**
- ✅ 10b HIGH — FAIL branch now `exit 2` (was `exit 1`); fail-open guards for missing sqlite3/DB/session. **DONE 1290412.**

## Resume Marker

<!-- last_updated_row: 4 -->
<!-- next_unchecked_row: 6 -->
<!-- last_updated_at: 2026-06-05T00:00:00Z -->
<!-- progress: N1✅ N2✅ N10✅ N3✅ N5✅ N4✅ (e937785). NEXT: N6 (TASK-110) codex parity. Then N8,N7,N9. -->
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
