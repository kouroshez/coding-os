---
audit_id: task-lifecycle-integrity
task_id: TASK-210
intent_detected_at: 2026-06-05T00:00:00Z
matched_exhaustive: ["all", "every", "each", "until done", "", ""]
matched_scope: ["fix", "audit", "verify", "sweep"]
predicates: ["counts_after_zero", "every_category_verified", "reviewer_pass"]
status: completed
created: 2026-06-05
completed: 2026-06-06
---

# Audit: Task-Lifecycle Integrity — Enforce Clean Closure

**Tracker:** TASK-210 · **Epic:** task-lifecycle-integrity · **Mode:** autonomous overnight (user delegated decision authority).

## Source Intent

User: agents repeatedly abandon tasks — create a task, do the work, session
ends, task never moved to complete; tasks rot in `icebox`; tasks stuck in
`in_progress`/`testing` forever. Directive: fix EVERY one down to the last,
enterprise-grade, with tests + verify + per-fix commits — no superficial fixes.

**Matched exhaustive vocabulary:** all / every / each / until done /  /
**Matched scope verbs:** fix / audit / verify / sweep
**Predicates to satisfy:** counts_after = 0 per category · every row Verified=yes · reviewer subagent re-grep passes

## Evidence basis

Two independent deep audits (this session's 61-agent workflow `wf_94fb08b0-d38`
+ a sibling 25-agent audit recorded in memory `project-multiagent-concurrency-audit`)
converged on the same root causes. 49/51 candidate gaps survived adversarial
verification. 7 root causes (RC1-RC7); RC5 (no time dimension) is the generative
cause beneath RC3/RC4/RC6.

## Root causes (SSOT for the fix map)

- **RC1** (crit) Closure has no enforcement event — START blocked, FINISH free, session DEATH runs nothing (`SessionEnd` has 0 hooks).
- **RC2** (crit) The one block-class Stop guardian enforces exhaustive-AUDIT evidence, not task lifecycle; names hide this.
- **RC3** (crit) `testing` is the protocol resting state AND the least-protected status (reclaim/warn/daily all `in_progress`-only).
- **RC4** (crit) Recovery is event-coupled to forward progress, never time-driven — the board self-heals only while already healthy.
- **RC5** (high, GENERATIVE) The board has no time dimension — `_task_card` carries zero timestamps; rot is unobservable everywhere.
- **RC6** (high) Icebox is pure inflow, zero automated outflow; the only "terminate" verbs feed it; `cos task-archive` is a docstring lie.
- **RC7** (high) Inherited zombies surfaced weakly, never acted on; ownership never expires; resume scans only audit files.
- **MISS-1** (crit) Hub web UI (`POST /board/move`) mutates the board with ZERO hooks — actor-type-agnostic recovery required.

## Decisions on open questions (user delegated; override-able)

1. Lease model → derived dwell-age, NO schema column, NO read-time mutation (sweeps mutate, reads observe).
2. Closure block → `COS_ENFORCE_TASK_CLOSURE=off|warn|strict`, default `warn`; meta-repo dogfoods `strict`.
3. Icebox max-age → label-stale+warn default (`icebox_stale_days=30`); auto-archive opt-in (`icebox_auto_archive_days=0`).
4. testing zombie destination → `in_progress`+ready (preserve near-done work); in_progress/emergency → icebox+ready.
5. Death-aware path → DROPPED PID-death (sibling-refuted, cross-host unsafe); timestamp-only, testing 6h / in_progress 24h.
6. Global WIP ceiling → deferred (low value per refutation; SessionStart+nightly sweep is the cure).

## Categories — Mandatory Coverage Table

Every row must end `Verified=yes` and `Hits after=0` (or justified `n/a`).

| # | Category (RC) | Pattern (grep/AST/spec) | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence (commit / file:line) |
|---|---|---|---|---|---|---|---|---|
| 1 | RC5 time-dim missing | `_task_card` returns no timestamp/dwell field | board_os/mcp_tools.py | 1 | yes | 0 | yes | 2d728d6b — dwell+SLA stale on board/daily; 397 board_os tests green |
| 2 | RC3 reclaim in_progress-only | `status = 'in_progress'` in reclaim row query | board_os/mcp_tools.py | 1 | yes | 0 | yes | 581523c7 — IN (in_progress,testing,emergency); testing→in_progress; per-status windows; 401 tests |
| 3 | RC3 warn-abandoned in_progress-only | `status = 'in_progress'` in warn-abandoned-task.sh | hooks/warn-abandoned-task.sh | 1 | yes | 0 | yes | 452b113d — IN (in_progress,testing); bash -n + golden byte-verified |
| 4 | RC4 no SessionStart reclaim | SessionStart hook invoking reclaim sweep | hooks/registry.yaml | 0 | yes | 1 | yes | 452b113d — reclaim-sweep.sh registered SessionStart startup+resume |
| 5 | RC4 no nightly reclaim | reclaim/sweep task in nightly.py | scheduled/nightly.py | 0 | yes | 1 | yes | 308e1084 — _run_reclaim wired (Task 4.5); dry-run reclaim→ok; 26 nightly tests |
| 6 | RC1/RC2 no ordinary-closure guardian | intent-independent task-status read in guard_completion | thinking_os/completion_guardian.py | 0 | yes | 1 | yes | 9cb85ab6 — _closure_gaps via panel .task-current ∩ DB; strict block, warn default; 28 tests |
| 7 | RC6 task-archive missing | `task-archive` registered click command | cli/board_commands.py | 0 | yes | 1 | yes | 394a9126 — task_archive_cmd registered; live --help OK |
| 8 | RC6 cancel feeds icebox | task-cancel default destination | cli/board_commands.py | 1 | yes | 0 | yes | 394a9126 — cancel→archive for terminal-eligible; --park keeps soft |
| 9 | RC6 no icebox hygiene | daily/sweep surfaces+drains icebox stale | board_os/mcp_tools.py | 0 | yes | 1 | yes | 2d728d6b (daily surface) + 95bf8796 (_archive_stale_sweep opt-in) |
| 10 | MISS-1 hub hookless move | actor-agnostic reclaim covers human/hub sessions | board_os/mcp_tools.py | 0 | yes | 1 | yes | 56cf62a8 — covered by F2a+F2b (no-presence owner = reclaimable); regression test |
| 11 | RC7 resume observe-only | resume surfaces board zombies + dwell-age + auto-reclaim | hooks/_helpers/wip_lines.py | 0 | yes | 1 | yes | 72d94e11 (dwell-age) + 452b113d (SessionStart auto-reclaim); session-context already lists board zombies |
| 12 | RC2 docs hide scope | scope-boundary section distinguishes audit-vs-task completion | rules/auto-mode-vs-exhaustive.md | 0 | yes | 1 | yes | 308e1084 — "Scope boundary" admonition added at top of rule |
| 13 | RC5 scaffold no hygiene knobs | consumer scaffold ships lifecycle knobs | templates/_base/scaffold/.coding-os/scrumban-config.yaml | 0 | yes | 6 | yes | 98f068de — 6 tunable knobs documented in _base scaffold; 38 scaffold tests |

## Resume Marker

<!-- last_updated_row: 13 -->
<!-- next_unchecked_row: none — all 13 verified -->

## Closing Checklist

- [x] Every category row Verified=yes / Hits after=0
- [x] Matrix verification green per changed layer
- [x] Reviewer subagent re-grep returns 0 (independent Explore agent: 13/13 PASS)
- [x] EvidenceBundle submitted via cos_supervise_record_output (formula_id=exhaustive_evidence)
