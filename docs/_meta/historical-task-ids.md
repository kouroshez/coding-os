<!-- domain:META | layer:reference | ssot:false | updated:2026-05-20 -->
# Historical TASK IDs (pre-public)

Purpose: explain why some commit messages reference `TASK-NNN` files
that do not exist under `docs/tasks/` in the public history.

Read when: you read a commit message like
`feat(graph-os): S5 React SPA scaffold (TASK-037)` and try to find
`docs/tasks/TASK-037-*.md` — it is not there, and you want to know
why.

Skip when: you are not curious about commit-message archeology.

> Nav: [Docs Index](../00-index.md) | [CHANGELOG](../../CHANGELOG.md)

## What happened

During pre-public development the project ran on a private Scrumban
board with ~200 task files under `docs/tasks/TASK-NNN-slug.md`.
Commit messages referenced those tasks by id, the way most
issue-tracker-driven workflows do.

Before the first public release the task corpus was archived (it
contained internal client-coupled details that had no value to
public contributors) and **only the four foundational tasks
TASK-001 .. TASK-004 were retained** as worked examples of the
Scrumban template. The pre-public history with the full task corpus
is still available locally on the `archive/full-history` branch and
the `archive/pre-public-2026-05-20` tag.

The result: commit messages on `main` still reference TASK ids in
the 005–200 range that no longer exist under `docs/tasks/`. The
work the commit describes is real and merged; the *task file* is
not.

## How to navigate

| You see in a commit                | Try these in order                                              |
| ---------------------------------- | --------------------------------------------------------------- |
| `(TASK-001..004)`                  | `docs/tasks/TASK-00{1,2,3,4}-*.md` — these still exist.         |
| `(TASK-005..200)`                  | The task file is archived. Read the commit body for context.    |
| `audit-<slug>.md` in commit body   | `docs/tasks/audits/audit-<slug>.md` — these were retained.      |

For any historical TASK id, you can also dig the archive locally:

```bash
git checkout archive/full-history -- docs/tasks/TASK-NNN-*.md
# inspect, then either keep the file or `git restore --staged --worktree docs/tasks/`
```

This works as long as the archive branch and tag haven't been
deleted (they are intentionally kept indefinitely).

## Why we didn't rewrite the commit messages

Three reasons:

1. **The commits themselves are an artifact** of how the project
   was built. Rewriting messages would mask the actual evolution
   (which had real Scrumban discipline) and replace it with a
   sanitized version that pretends contributors arrived at the
   final state directly.
2. **History rewrite costs SHAs.** Every commit hash would change,
   breaking any external reference (links from past PR threads,
   blame digs by future contributors).
3. **The relevant content is in the commit body.** The TASK id was
   a pointer; the *what* and *why* live in the commit body, which
   survives.

## What to expect in the public Scrumban board

Going forward, new tasks start fresh at **TASK-005** and only the
ones genuinely useful to public contributors get committed. The
board is back to its design intent: a small set of in-flight tasks
with `Outcome + Read First + Acceptance + Work Log` bodies, not a
historical archive.

## See also

- [`AGENTS.md`](../../AGENTS.md) § Tool Routing — current Scrumban CLI.
- [`docs/governance/task-lifecycle.md`](../governance/task-lifecycle.md) — task states + transitions.
- [`CHANGELOG.md`](../../CHANGELOG.md) — public release history.
