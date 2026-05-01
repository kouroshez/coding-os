<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-01-01 -->
# Task Lifecycle Policy

Purpose: Canonical lifecycle for creating, executing, and closing tasks in the documentation-driven workflow.
Read when: Creating a task, updating task status, or aligning task scripts/templates.
Skip when: The task is already in progress and its lifecycle is clear.
Read next: `../tasks.md`, `templates/task-detail.md`, and `agent-workflow.md`

> Nav: [Docs Index](../00-index.md) | [Tasks Index](../tasks.md)

## Status Flow

- `- [ ]` → open and not started
- `[/]` → active work in progress
- `- [x]` → completed and logged
- `(BLOCKED: reason)` → cannot continue without external resolution

## Required Artifacts

- index entry in `docs/tasks.md`
- primary detail file at `docs/tasks/TASK-###-slug.md` once work starts
- optional companion reference docs only when the primary task file would exceed the size limit
- dated entry in `changes.log` when complete

## Execution Rules

- Mark the task `[/]` before substantial implementation work.
- Complexity Gate runs in Classify phase (before Orient) for all request types. For tasks, the Classify output (Dimension Map + Read List) informs the Orient and Plan phases. See AGENTS.md § Core Loop.
- Keep the primary task file updated with read-first refs, requirements, definition of done, verification, and files changed.
- Use `Given / When / Then` language for completion criteria.
- Mark `- [x]` only after verification succeeds or the remaining risk is explicitly logged.
- Search the repo before creating any file, pattern, or rule.
- All code changes must pass domain-appropriate linting, type-checking, and tests before marking [x].
- Error paths must be tested — a task with untested error handling is not complete.

## Primary Task File Contract

Required sections (in order):

- `## Goal`
- `## Read First` (REF codes annotated with what to look for)
- `## Source of Truth` (which docs are authoritative pre- and post-implementation)
- `## Scope` (In / Out subsections)
- `## Requirements` (minimum 3 numbered acceptance criteria; Given/When/Then format recommended)
- `## Dependencies` (annotated with what each dependency provides)
- `## Open Questions` ("None." if no unknowns — never delete this section)
- `## Verification`

Optional section:

- `## Notes` (working notes, findings, checkpoints)

`## Read First` should prefer `REF:*` codes from `docs/foundation-map.md`. Raw relative links are still allowed for task-local companion docs.

## Index and Status Rules

- Backlog tasks may remain `- [ ]` in `docs/tasks.md` without a detail file until execution begins.
- Active, blocked, and completed tasks must have a primary detail file.
- Task status is tracked only in `docs/tasks.md`. Task detail files do not contain status.

## Script Contract

### Core Commands

- `make task-create NUM=<num> TITLE="<title>"` scaffolds a task file and active index entry
- `make task-start TASK=<num>` creates the detail file if missing, marks `[/]` in `docs/tasks.md`, then loads context
- `make task-done TASK=<num> TYPE=<type> MSG="title" WHAT="impact" FILES="a.sh"` marks `[x]` in `docs/tasks.md`, appends structured entry to `changes.log`
- `make task-block TASK=<num> REASON="why"` marks `(BLOCKED: reason)` in `docs/tasks.md`, logs question to `docs/questions.md`
- `make task-context TASK=<num>` prints the task title, file, read-first refs, latest changes, verification, and any task-system warnings
- `make task-next` shows the next open task by file order in `docs/tasks.md`

### Standardized Output Format

All scripts use consistent output prefixes:

| Prefix | Meaning | Behavior |
| ------ | ------- | -------- |
| `OK: <message>` | Success | stdout |
| `ERROR: <message>` | Fatal error | stderr, exits with code 1 |
| `WARN: <message>` | Non-fatal warning | stderr |
| `INFO: <message>` | Informational | stdout |

## Outcome Tracking (Thinking OS)

After task completion or blocking, record outcome to `coding-os.db`:

| Field | Values | Source |
| ----- | ------ | ------ |
| outcome | success / rework / partial / blocked | agent assessment |
| duration_min | integer | session elapsed time |
| model | haiku / sonnet / opus | active model |
| skills_used | JSON array | skills invoked during task |

Outcomes feed the Learning Loop (runs every 10 tasks) which extracts patterns and suggests rule updates. See `agent-workflow.md` § Memory & Learning.
