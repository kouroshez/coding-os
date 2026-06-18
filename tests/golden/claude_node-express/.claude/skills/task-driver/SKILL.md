---
name: task-driver
tier: workflow
domain: [governance]
description: Use when creating, modifying, or transitioning Scrumban tasks in docs/tasks/. Triggers on "create a task", "move task", "start task X", "what's blocked", "daily standup", "retro", or any edit to docs/tasks/TASK-*.md.
phase: L
last_reviewed: "2026-05-11"

---

# Task Driver Skill — Scrumban

You are in task-management mode. Apply these rules mechanically.

## Mandatory intake loop (run for every implementation request)

1. **Reconcile existing tasks first.** Check whether the user request maps to:
   - an explicit task id (`TASK-###`), or
   - an existing open/in_progress/testing task in the same area.
2. **If a matching task exists:** use it (do not create a duplicate).
3. **If no matching task exists and work is non-trivial: create it fully
   formed in ONE call.** When you already know the scope (you almost always
   do — you just analyzed the work), the SAME `cos_task_create` call carries
   `outcome=`, `acceptance=`, `read_first=` **and** `ready=True` (`--ready`).
   Creating a skeleton "to fill in later" is a defect, not a shortcut: the
   create envelope echoes `data.dor` — a non-empty `gaps` list or
   `ready: false` you did not intend is YOUR bug; fix it before proceeding.
   CLI flag trap: `--read-first` / `--labels` are **comma-separated single
   flags** — repeating the flag silently keeps only the last value.
4. **Before `in_progress`: the task body gate must already hold.** Outcome
   (one measurable sentence), Read First (minimal links), Acceptance (G/W/T).
   Step 3 done right makes this a no-op; the icebox→in_progress gate blocks
   placeholders regardless.
5. **Then execute through statuses:** `in_progress` → `testing` → `complete`.
6. **If blocked at any time:** move to `blocked` and record the concrete blocker.

## Golden rules

1. **Prefer MCP tools over hand-written YAML.** Always call `cos_task_create`
   instead of writing the frontmatter yourself. Always call `cos_task_move`
   to transition — not an `Edit` on the MD file.

2. **Rule 15 — tasks are pointers, not specs.** Never inline content from
   `docs/**`, `src/core/rules/**`, `CLAUDE.md`, or `AGENTS.md`. If you find
   yourself writing >800 tokens of task body: stop, find the doc to link,
   or create a new doc (Documenter role) and link to it.

3. **Acceptance = Definition of Done.** G/W/T are the tests. When all pass,
   task is Done — not "perfect", Done. Scope creep ⇒ create a new task via
   `cos_task_create(kind="bug"|"chore"|...)`.

4. **One Outcome sentence — measurable, concrete.** Bad: "improve auth".
   Good: "users log in with email+OTP, P95 <500ms, on iOS+Android+web".

5. **WIP=1 per session by default.** The `in_progress` cap is counted per
   `agent_session` (`workflow_policy.per_session_wip`) — concurrent sessions
   don't block each other, but YOUR session still does one task at a time.
   Need a second `in_progress` in the same session? Ask first. Never
   silently `COS_WIP_OVERRIDE=1`.
6. **`in_progress → complete` is blocked.** Route through `testing` so the
   verification matrix runs (`workflow_policy.block_in_progress_to_complete`).
   `force` is the only override and is audited.

## The four axes (memorize)

| Axis | Field | Examples |
|---|---|---|
| Domain | `swimlane` | `graph_os`, `backend`, `vpn-core` (from scrumban-config) |
| Type | `kind` | `feature`, `bug`, `chore`, `spike`, `docs`, `refactor`, `test`, `security` |
| Initiative | `epic` | `phase-l`, `mvp`, `oncall-q2` |
| Tags | `labels` | `indexing`, `perf`, `experimental` (must NOT contain kind values) |

## Bug found mid-session

Create a task immediately with `cos_task_create(kind="bug", priority="P0"|"P1")`
then continue your current work. Don't interrupt the current task to fix
the bug unless the user asks.

## Required status choreography

0. **Mark ready** — a task needs the `ready` label before it can leave
   `icebox`: `cos task-ready TASK-NNN` (or create with `--ready` / `ready=True`).
   `icebox → in_progress` is BLOCKED otherwise (the `emergency` lane is exempt).
1. `cos task-start TASK-NNN` before substantive edits, then **commit each logical unit autonomously as you implement** (`git commit <paths>` — never wait to be asked; [git-workflow.md](../../rules/git-workflow.md) § When to commit).
2. If dependency/policy/tooling blocks progress:
   `cos_task_move(task_id=..., to="blocked")` and log the blocker.
3. After implementation: `cos_task_move(task_id=..., to="testing")` —
   move to `testing` FIRST, then run verification. `in_progress → complete`
   is BLOCKED, so don't run tests while still `in_progress`.
4. Run verification commands tied to changed files.
5. If green: append one short work-log note (token-lean), commit, then `cos task-done` (push to `main` at close).
6. If red: keep in `testing` or move back to `in_progress` with a short reason.

## Work Log (append-only, 120 char cap)

- **Claude:** `capture-work-log.sh` appends automatically on Write/Edit.
- **Codex:** MUST call `cos_work_log_append(task_id, summary)` explicitly
  after any significant edit — no PostToolUse hook delivers for Codex.
- NEVER rewrite or reformat existing Work Log lines.
- Keep entries short and factual (what changed, result, blocker if any).

## Session start ritual

1. Run `cos daily` → see yesterday's progress + today's candidates + blockers.
2. Reconcile the new user request against existing tasks (`cos_task_board` / `cos task-show`).
3. If no suitable task exists: create one, fill Outcome/Read First/Acceptance.
4. `cos task-start TASK-NNN` → enforces WIP + sets `.task-current`.
4. Do work — **commit each logical unit autonomously**. `capture-work-log` auto-records. Status visible via `cos_task_board`.
5. Move to `testing`, run checks, then `cos task-done TASK-NNN` when G/W/T pass.

## MCP outage fallback (R-L-28)

If `cos_task_move` returns `fail("transient", retryable=True)`:
1. Wait 2s, retry once.
2. On second failure: fall back to `Edit` on the task MD file directly.
   The `validate-task-frontmatter.sh` hook still enforces enum + cycle rules.
3. On next reachable MCP, re-sync via `cos task-sync`.

## Surface stale tasks to the human

If a task has been in `in_progress` for >3 days OR >2× its `appetite`,
surface this observation to the user — don't silently assume progress.
Daily/retro outputs already flag these.

## Daily streak ≠ shame

If `cos daily` shows a broken streak: DO NOT pressure the user. This is
observability only. ADHD-friendly default is silence; the user asks if
they care.

## WIP enforcement (hard caps)

| Status | Cap | What happens if exceeded |
|---|---|---|
| `in_progress` | 1 **per agent_session** (configurable via `scrumban-config.yaml::wip_limits.in_progress`) | `cos task-start` refuses for THIS session; other sessions are unaffected (`per_session_wip`). Idle in_progress tasks of dead sessions are freed by `cos task-reclaim` |
| `testing` | 3 (board-global) | Warns; doesn't block (testing can stack while verification runs) |
| `emergency` | 2 (board-global) | Hard block — emergency lane only for SEV-1/2 incidents |

Override is by the user via `--wip-override` flag, never by the agent silently. Document why the override is justified in the work log of the over-cap task.

## Daily standup template (paste-ready)

When the user says "daily" / "standup" / "what's the state":

```
## Daily — YYYY-MM-DD

### Yesterday
- [TASK-NNN] {title} → moved to {status}, {one-line outcome}
- (repeat for each task touched yesterday)

### Today (candidates)
- [TASK-NNN] {title} ({swimlane}/{kind}, priority {P})
- (top 3 from `cos task-pick`)

### Blocked
- [TASK-NNN] {title} — blocker: {one-line reason}, since {date}
- (action: {who/what unblocks})

### WIP check
- in_progress: {n}/cap{cap}
- testing: {n}/cap{cap}
- violations: {none | list}

### Notable
- {anything stale > 3 days, anything > 2× appetite, anything new from MCP discovery}
```

Source the data from `cos_task_daily` (canonical) — don't reconstruct from `cos_task_board` if `daily` is available.

## Retro template (paste-ready)

When the user says "retro":

```
## Retro — YYYY-MM-DD (period: {N days})

### What shipped
- [TASK-NNN] {title} → complete, {date}
- (every task moved to complete in the period)

### What broke / blocked
- [TASK-NNN] {title} — blocked for {days}; root cause: {category}
- (every task that hit `blocked` or rolled back)

### Patterns (from `cos_failure_pattern_query`)
- {recurring failure category}: {N occurrences}; suggested mitigation: {action}

### Action items (with owners + due dates)
- [ ] {description} — @owner — due YYYY-MM-DD
```

Source from `cos_task_retro` (canonical), which already aggregates the completed/blocked/failure-pattern signals. Add owner + due-date columns by asking the user; the data is human input.

## Blocked-task escalation pattern

A task moved to `blocked` is not a finished state. Escalation ladder:

| Days blocked | Action |
|---|---|
| Day 0 | Move to blocked, record blocker, ask the user once. |
| Day 1-2 | Daily output highlights the blocker. Agent does NOT re-prompt. |
| Day 3 | Agent surfaces "TASK-NNN has been blocked 3 days — still relevant?" once. |
| Day 7 | Agent suggests `cos_task_move(to="archived")` with a brief note. |
| Day 14 | Auto-archive (configurable). The task body still exists, but it's off the active board. |

**Never** silently archive without surfacing to the user first. Lost work is worse than visible blocked work.

## Swimlane routing — discover from config, never hardcode

Swimlanes are **project-specific**, defined ONLY in
`.coding-os/scrumban-config.yaml` (`swimlanes:`). They differ per stack
(django: `backend/frontend/ai-service/shared/docs/infra`; nextjs:
`frontend/api/e2e/design/docs/infra`; the meta-repo:
`core/thinking_os/graph_os/board_os/adapters/templates/cli/docs/infra`).
There is **no universal list** — do not memorize or guess one.

**Discover the valid lanes (don't guess):**

- `cos_task_create` with an unknown swimlane fails with `valid: [...]` —
  that list IS this project's source of truth.
- `cos board-config` prints the full config (swimlanes + colours).

**Map the work to the closest existing lane by domain concept:**
server / API / DB → the backend-ish lane · UI / components → the
frontend-ish lane · `src/core|cli|adapters|templates` in the meta-repo →
the matching subsystem lane · docs-only → `docs` · CI / deploy / infra →
`infra` (or `ops`). The lane *names* always come from config, not from a
fixed table here.

**Need a domain that doesn't exist yet?** Add it to
`.coding-os/scrumban-config.yaml::swimlanes` (`id` + `label` + `color`).
Config is re-read live on every call — no restart, and concurrent
sessions pick it up immediately. Only add a lane when no existing one
genuinely fits; prefer reuse (anti-overengineering).

Ambiguous? Pick the broadest existing lane (commonly `infra` or `shared`
when present) — the user can re-route.

## `kind` (task type) — when to pick which

- `feat` — net-new capability. Adds user-visible behavior.
- `fix` — repair existing broken behavior. Pair with a regression test.
- `chore` — internal work, no user-visible change (dependency bumps, cleanup).
- `refactor` — code structure change, no behavior change. Tests must still pass.
- `docs` — docs-only change. Lint applies; code doesn't.
- `test` — adds tests to existing code. Often paired with `fix` or `feat`.
- `spike` — time-boxed research; produces a decision doc, not a feature.
- `security` — security fix or hardening. Often pairs with private disclosure.

The `kind` choice drives commit message prefix (`feat:`, `fix:`, …) and changelog grouping.

## Composing with other skills

This skill is the entry point for **process**. For **content** of the task, compose with:

- `thinking_os` → for the Cynefin classification recorded in the gate before any code edit on a COMPLICATED+ task.
- `search` → for "is there already a task for this?" via `cos_task_search` before creating.
- `graph-explorer` → for blast-radius scoping when the task says "rename X" or "refactor Y".
- `clean-code` → mandatory secondary on any code-touching task.
- domain skills (e.g. `python-meta-server`, `nextjs-react`) → primary on the implementation phase.

The order is fixed: **task-driver lifecycle → thinking_os classify → domain skill → clean-code → search/graph as needed → implementation.**

## See also

- [Rule 14 — Tasks are pointers](../../../docs/governance/critical-rules.md#rule-14--tasks-are-pointers-not-specs).
- [Rule 18 — Task reconciliation mandatory](../../../docs/governance/critical-rules.md#rule-18--task-reconciliation-is-mandatory-before-implementation).
- [docs/governance/task-lifecycle.md](../../../docs/governance/task-lifecycle.md) — canonical lifecycle spec.
- [thinking_os](../thinking_os/SKILL.md) — Complexity Gate before any code change.
- [search](../search/SKILL.md) — `cos_task_search` for reconciliation.
- [src/scripts/task-lint.sh](src/scripts/task-lint.sh) — lint TASK-*.md files (frontmatter + sections + Rule 14 size cap).
