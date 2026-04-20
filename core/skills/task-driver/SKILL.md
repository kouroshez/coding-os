---
name: task-driver
description: Use when creating, modifying, or transitioning Scrumban tasks in docs/tasks/. Triggers on "create a task", "move task", "start task X", "what's blocked", "daily standup", "retro", or any edit to docs/tasks/TASK-*.md.
phase: L
---

# Task Driver Skill — Phase L Scrumban

You are in task-management mode. Apply these rules mechanically.

## Golden rules

1. **Prefer MCP tools over hand-written YAML.** Always call `cos_task_create`
   instead of writing the frontmatter yourself. Always call `cos_task_move`
   to transition — not an `Edit` on the MD file.

2. **Rule 15 — tasks are pointers, not specs.** Never inline content from
   `docs/**`, `core/rules/**`, `CLAUDE.md`, or `AGENTS.md`. If you find
   yourself writing >800 tokens of task body: stop, find the doc to link,
   or create a new doc (Formula 4) and link to it.

3. **Acceptance = Definition of Done.** G/W/T are the tests. When all pass,
   task is Done — not "perfect", Done. Scope creep ⇒ create a new task via
   `cos_task_create(kind="bug"|"chore"|...)`.

4. **One Outcome sentence — measurable, concrete.** Bad: "improve auth".
   Good: "users log in with email+OTP, P95 <500ms, on iOS+Android+web".

5. **WIP=1 by default.** If you need a second `in_progress` task, ask the
   user first. Never silently `COS_WIP_OVERRIDE=1`.

## The four axes (memorize)

| Axis | Field | Examples |
|---|---|---|
| Domain | `swimlane` | `graph-os`, `backend`, `vpn-core` (from scrumban-config) |
| Type | `kind` | `feature`, `bug`, `chore`, `spike`, `docs`, `refactor`, `test`, `security` |
| Initiative | `epic` | `phase-l`, `mvp`, `oncall-q2` |
| Tags | `labels` | `indexing`, `perf`, `experimental` (must NOT contain kind values) |

## Bug found mid-session

Create a task immediately with `cos_task_create(kind="bug", priority="P0"|"P1")`
then continue your current work. Don't interrupt the current task to fix
the bug unless the user asks.

## Work Log (append-only, 120 char cap)

- **Claude:** `capture-work-log.sh` appends automatically on Write/Edit.
- **Codex:** MUST call `cos_work_log_append(task_id, summary)` explicitly
  after any significant edit — no PostToolUse hook delivers for Codex.
- NEVER rewrite or reformat existing Work Log lines.

## Session start ritual

1. Run `cos daily` → see yesterday's progress + today's candidates + blockers.
2. If no active task: `cos task-pick` → pick one.
3. `cos task-start TASK-NNN` → enforces WIP + sets `.task-current`.
4. Do work. `capture-work-log` auto-records. Status visible via `cos_task_board`.
5. `cos task-done TASK-NNN` when G/W/T all pass.

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
