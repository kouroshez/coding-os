<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-08 -->
# Task Lifecycle Policy

> P: Canonical lifecycle for creating, executing, and closing tasks under the Scrumban model (`core/board_os/`).
> R: Creating a task, transitioning status, or aligning task scripts and templates.
> S: Reading existing task content unrelated to lifecycle change.
> N: [docs-system.md](docs-system.md), [agent-workflow.md](agent-workflow.md), [templates/task-detail.md](templates/task-detail.md)

> Nav: [Governance Index](./00-index.md) | [Docs Index](../00-index.md)

## SSOT and Mirrors

- `docs/tasks/TASK-###-slug.md` — **canonical detail file**. One per active or completed task. File frontmatter and body are the source of truth.
- `core/board_os/db.py` (table `tasks`) — **derived mirror**. Mtime-incremental sync from the detail files; never edited by hand.
- `cos board` / `cos board --web` — **live view** rendered from the DB.

There is no flat `docs/tasks.md` index. Status is read from frontmatter, not from a top-level checkbox file.

## Status States

`open → in_progress → testing → complete`, plus `blocked` reachable from any state.

Transitions go through `cos task-*` (or the equivalent MCP tool). The CLI writes the detail-file frontmatter and the DB row atomically; manual edits to one side without the other create drift that the doctor will flag.

## Required Artifacts

For any task that is `in_progress`, `testing`, `blocked`, or `complete`:

- A primary detail file at `docs/tasks/TASK-###-slug.md` authored from `templates/task-detail.md`.
- A non-empty Work Log section once execution starts (transition gates check this).
- An Outcome line at the top, plus Read First, Acceptance (Given/When/Then), and Rollback sections.
- Optional companion reference docs only when the primary file would exceed the size cap (warn ≥1.5 k tokens, block ≥3 k — Rule 14).

Backlog entries that are not yet started may live in `cos board` (icebox swimlane) without a detail file. Detail file becomes required at the moment of first transition out of icebox.

## Execution Rules

- Move the task to `in_progress` before any substantial Write/Edit. Hooks block code edits without an active task marker.
- Complexity Gate (AGENTS.md § Core Loop) runs in Classify before Orient. The gate's Dimension Map and Read List inform the rest of the loop and are recorded in the task's Notes when non-trivial.
- Keep Work Log up to date as you go — one bullet per meaningful checkpoint. The CLI's `cos work-log TASK-NNN "note"` is preferred so the DB cache (`work_log_last_5`) stays fresh.
- Use `Given / When / Then` for Acceptance criteria.
- Move to `complete` only after Verification Matrix tests for the changed surface pass. Untested error paths fail the gate.
- Search the repo and the graph before creating any new file, pattern, or rule. Reuse beats reinvention.

## Primary Task File Contract

Required sections in this order (template lives at `templates/task-detail.md`):

- `## Outcome` — single sentence describing the externally visible result.
- `## Read First` — annotated list of files and refs the executor should load before editing.
- `## Acceptance` — numbered list, Given/When/Then format.
- `## Work Log` — append-only bullets, newest at the bottom.
- `## Rollback` — one-paragraph plan for backing the change out.

Optional sections:

- `## Notes` — working notes, findings, dimension maps for COMPLICATED+ tasks.
- `## Dependencies` — only when the task is gated by other tasks; mirrored in the `depends_on` frontmatter.

## Frontmatter Fields

| Field | Required | Notes |
|---|---|---|
| `id` | yes | matches the file name slug |
| `title` | yes | one line, no trailing punctuation |
| `swimlane` | yes | agent-defined; common: `infra`, `frontend`, `docs`, `research` |
| `kind` | yes | one of `feat · fix · refactor · docs · test · infra · spike · chore` |
| `status` | yes | `open · in_progress · testing · blocked · complete` |
| `priority` | yes | `P1 · P2 · P3` |
| `appetite` | yes | shape-up budget, e.g. `30m · 2h · 1d · 2w` |
| `epic`, `labels` | no | grouping helpers |
| `depends_on`, `blocked_by` | no | task IDs |
| `references` | no | doc paths the task points at |
| `created`, `started`, `completed` | auto | written by the CLI on transitions |
| `agent_session` | auto | fingerprint of the agent that started the task |

## CLI and MCP Surface

| Action | CLI | MCP |
|---|---|---|
| View board | `cos board` / `cos board --web` | `cos_task_board` |
| Create | `cos task-create --title "…" --swimlane … --kind …` | `cos_task_create` |
| Start | `cos task-start TASK-NNN` | `cos_task_move` → `in_progress` |
| Move to testing | `cos task-move TASK-NNN --to testing` | `cos_task_move` → `testing` |
| Complete | `cos task-done TASK-NNN` | `cos_task_move` → `complete` |
| Block | `cos task-move TASK-NNN --to blocked` | `cos_task_move` → `blocked` |
| Append work log | `cos work-log TASK-NNN "note"` | `cos_work_log_append` |
| Daily standup | `cos daily` | `cos_task_daily` |
| WIP check | `cos wip` | `cos_task_wip_check` |
| Pick next | `cos task-pick` | `cos_task_pick` |

## Migration from `make task-*` to `cos task-*`

The legacy `make task-*` targets (defined in `templates/_base/Makefile.base`) remain as thin aliases for back-compat with consumer projects that have not yet adopted the `cos` CLI. They shell out to the same `cli/board_commands.py` code path as the `cos` CLI, so behavior is identical.

| Legacy | Preferred | Notes |
|---|---|---|
| `make task-create NUM=098 TITLE="…"` | `cos task-create --title "…" --swimlane … --kind …` | `cos` requires swimlane + kind; `make` infers defaults. |
| `make task-start TASK=098` | `cos task-start TASK-098` | Identical. |
| `make task-done TASK=098 …` | `cos task-done TASK-098` | `cos` reads metadata from frontmatter; `make` needs explicit args. |
| `make task-block TASK=098 REASON="…"` | `cos task-move TASK-098 --to blocked` | `cos` records the reason in Work Log. |
| `make task-list STATUS=wip` | `cos board` / `cos task-by-filter --status wip` | `cos` is the only surface that reads from the DB cache. |

New consumer projects should not use `make task-*`. The targets will be removed from `Makefile.base` once two release cycles have passed with `cos` as the default — track the deprecation under the next icebox audit task. Existing projects that still rely on `make task-*` can keep using them; the aliases are stable for the duration of v0.2.x.

## Script Output Convention

| Prefix | Meaning | Stream |
|---|---|---|
| `OK:` | success | stdout |
| `ERROR:` | fatal | stderr, exit 1 |
| `WARN:` | non-fatal | stderr |
| `INFO:` | progress / context | stdout |

## Outcome Tracking

After every transition into `complete` or `blocked`, the workflow records an outcome row to `coding-os.db` for the Learning Loop:

| Field | Values | Source |
|---|---|---|
| outcome | `success · rework · partial · blocked` | agent assessment |
| duration_min | integer | session elapsed time |
| model | active model id | dispatcher |
| skills_used | JSON array | skill enforcement hook |

Outcomes feed pattern extraction every N completions. See [agent-workflow.md](agent-workflow.md) § Memory & Learning.
