<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-08 -->
# Task Lifecycle Policy

> P: Canonical lifecycle for creating, executing, and closing tasks under the Scrumban model (`src/core/board_os/`).
> R: Creating a task, transitioning status, or aligning task scripts and templates.
> S: Reading existing task content unrelated to lifecycle change.
> N: [docs-system.md](docs-system.md), [agent-workflow.md](agent-workflow.md), [_templates/task-detail.md](_templates/task-detail.md)

> Nav: [Governance Index](./00-index.md) | [Docs Index](../00-index.md)

## SSOT and Mirrors

- `docs/tasks/TASK-###-slug.md` — **canonical detail file**. One per active or completed task. File frontmatter and body are the source of truth.
- `src/core/board_os/db.py` (table `tasks`) — **derived mirror**. Mtime-incremental sync from the detail files; never edited by hand.
- `cos board` / `cos board --web` — **live view** rendered from the DB.

There is no flat `docs/tasks.md` index. Status is read from frontmatter, not from a top-level checkbox file.

## Status States

`icebox → in_progress → testing → complete`, plus `blocked` reachable from any state (and `emergency` / `archive` for the incident and retirement lanes).

Transitions go through `cos task-*` (or the equivalent MCP tool). The CLI writes the detail-file frontmatter and the DB row atomically; manual edits to one side without the other create drift that the doctor will flag.

## Required Artifacts

For any task that is `in_progress`, `testing`, `blocked`, or `complete`:

- A primary detail file at `docs/tasks/TASK-###-slug.md` authored from `src/templates/task-detail.md`.
- A non-empty Work Log section once execution starts (transition gates check this).
- An Outcome line at the top, plus Read First, Acceptance (Given/When/Then), and Rollback sections.
- Optional companion reference docs only when the primary file would exceed the size cap (warn ≥1.5 k tokens, block ≥3 k — Rule 14).

Backlog entries that are not yet started may live in `cos board` (icebox status) without a detail file. Detail file becomes required at the moment of first transition out of icebox.

## Execution Rules

- **Pull from icebox requires the `ready` label.** With `workflow_policy.require_ready_label` (default on), `icebox → in_progress` is blocked until the task is marked pullable — `cos task-ready TASK-NNN` (or create with `--ready`). The `emergency` fast lane is exempt. This separates "groomed idea" from "raw idea": the content DoR gate proves the task is well-formed, the `ready` label proves it was deliberately scheduled.
- Move the task to `in_progress` before any substantial Write/Edit. Hooks block code edits without an active task marker.
- Complexity Gate (AGENTS.md § Core Loop) runs in Classify before Orient. The gate's Dimension Map and Read List inform the rest of the loop and are recorded in the task's Notes when non-trivial.
- Keep Work Log up to date as you go — one bullet per meaningful checkpoint. The CLI's `cos work-log TASK-NNN "note"` is preferred so the DB cache (`work_log_last_5`) stays fresh.
- Use `Given / When / Then` for Acceptance criteria.
- Move to `complete` only after Verification Matrix tests for the changed surface pass. Untested error paths fail the gate.
- **Direct `in_progress → complete` is blocked by default.** With `workflow_policy.block_in_progress_to_complete` (default on), the shortcut is rejected — route `in_progress → testing → complete` so the Verification Matrix runs. The state-machine edge stays legal (`force=True` / `cos task-move --force` overrides for genuine trivial work, and is audited). When the policy knob is off, `workflow.transition` falls back to the legacy soft warning instead of blocking.
- Search the repo and the graph before creating any new file, pattern, or rule. Reuse beats reinvention.

## Primary Task File Contract

Required sections in this order (template lives at `src/templates/task-detail.md`):

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
| `kind` | yes | one of `feature · bug · chore · spike · docs · refactor · test · security` |
| `status` | yes | `icebox · in_progress · testing · blocked · complete · emergency · archive` |
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

## The `make task-*` wrappers

`cos task-*` is the canonical task interface. `src/templates/_base/Makefile.base` keeps a few `make task-*` targets purely as muscle-memory wrappers — each shells straight out to `cos`:

| Wrapper | Delegates to |
|---|---|
| `make task-start TASK=098` | `cos task-start TASK-098` |
| `make task-done TASK=098` | `cos task-done TASK-098` |
| `make task-block TASK=098 REASON="…"` | `cos task-block TASK-098 --reason "…"` |
| `make task-create` | prints the `cos task-create` usage (it needs `--swimlane` / `--kind`) |

The legacy file-based task system — the `task-*.sh` scripts and the flat `docs/tasks.md` index — has been removed. `make task-*` provides nothing that `cos task-*` does not; new code and docs should always call `cos task-*` directly.

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
