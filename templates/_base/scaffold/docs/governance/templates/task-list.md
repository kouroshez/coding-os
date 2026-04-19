<!-- domain:DOCS | layer:reference | ssot:true | updated:{{DATE}} -->
# Task List Template

Purpose: Canonical format for `docs/tasks.md` (the SSOT task index).
Read when: Adding a new task entry by hand or auditing the index format.
Skip when: Using `make task-create NUM=### TITLE="..."` (it formats automatically).

> Nav: [Docs Index](../../00-index.md)

## Format

```markdown
# Tasks

<!-- Status: [ ] open, [/] in-progress, [x] done, (BLOCKED: reason) -->

## Phase NN — <name>

- [ ] TASK-001: [DOMAIN] Verb + short description
- [/] TASK-002: [DOMAIN] Verb + short description
- [x] TASK-003: [DOMAIN] Verb + short description
- (BLOCKED: waiting on TASK-005) TASK-004: [DOMAIN] Verb + short description

## Phase NN+1 — <name>

- [ ] TASK-006: [DOMAIN] Verb + short description
```

## Rules

- Tasks are grouped by phase under H2 (`##`) headings matching `docs/roadmap.md`.
- Each task line follows the exact format `- <status> TASK-NNN: [DOMAIN] description`.
- Domain tag is uppercase in square brackets: `[BACKEND]`, `[FRONTEND]`, `[DOCS]`, `[INFRA]`, etc.
- Status markers: `[ ]` open, `[/]` in-progress, `[x]` done, `(BLOCKED: reason)`.
- Task numbers are monotonically increasing (3 digits, never reused even when archived).
- Description is imperative voice, 5-15 words: "Add user auth", "Fix payment retry bug".
- Detail file lives at `docs/tasks/TASK-NNN-slug.md` once the task is started.

## Anti-Patterns

- ❌ Long descriptions (move to detail file's Goal section)
- ❌ Status text inside task title ("- [ ] TASK-001 (in progress): ...")
- ❌ Missing domain tag
- ❌ Reusing task numbers
- ❌ Editing task status by hand (use `make task-start` / `task-done` / `task-block`)
