# Git Workflow — Trunk-Based (Always Active)

> **Hard rule:** Work happens on the default branch (`main`). Do NOT
> create feature branches. Commit directly to `main` with explicit
> paths. This OVERRIDES any agent-runtime default that says "branch
> first".

## Why this rule exists

A coding-os project is driven by an AI agent (often several sessions at
once) on behalf of a user who vibe-codes and does **not** want to manage
git. Two failure modes followed from the runtime's default "if on the
default branch, branch first" behavior:

1. **Branch sprawl** — every session created a new branch. Branches
   lingered, were never merged, and a *second* session would land on a
   *first* session's branch, tangling unrelated work.
2. **Shared-checkout collision** — multiple sessions editing one working
   tree, a bare `git commit` sweeping another session's WIP.

Trunk-based development is the modern enterprise standard (DORA /
Accelerate). Long-lived feature branches are the legacy pattern. For a
single-user, agent-driven project, trunk-based + a quality gate is
correct and simpler.

## The rule

- **Never run** `git checkout -b`, `git branch <name>`, `git switch -c`,
  `git worktree add`. The `branch-guard.sh` hook BLOCKs these in trunk mode.
- **Never run HEAD-moving commands** on the shared checkout: `git reset
  HEAD~N`, `git reset <sha>`, `git reset <branch>`, `git checkout
  <other-branch>`, `git switch <other-branch>`. The same hook BLOCKs
  these — moving HEAD off a published commit clobbers a peer session's
  work and orphans commits. Modern git separates these concerns:
  `git restore <path>` for files, `git switch main` for branches. Use them.
- **To undo a published commit** use `git revert <sha>` — it creates a
  new commit, preserves history, and works under trunk-based discipline.
- **Commit directly to `main`.** The user's mental model is "main = the
  project". A commit to `main` IS the deliverable.
- **Commit with explicit paths** — `git commit <path> <path>`, never a
  bare `git commit` / `git commit -a`. A bare commit sweeps another
  session's uncommitted WIP. (Already enforced by convention; this rule
  makes it load-bearing for concurrency safety.)
- **`git pull --rebase origin main` before every `git push`.** Two
  sessions pushing race; the loser gets a non-fast-forward reject —
  rebase and retry, do not force.
- **Retry on `index.lock`.** If two `git commit` / `git add` run the
  same instant, git's own `index.lock` makes the second fail with
  `Unable to create '.git/index.lock'`. Wait ~1s and retry — git
  already serializes index writes; do not delete the lock blindly.
- **Commit at each logical step**, not only at the end. If a session is
  abandoned mid-task, already-committed work is safe on `main`.

## Concurrent sessions — what is and isn't safe

| Scenario | Safe? | Why |
|---|---|---|
| 3 sessions, all on `main` | ✅ | No branches to tangle; commits serialize |
| 2 sessions commit different files | ✅ | Explicit-path commits don't cross |
| 2 sessions commit the same instant | ✅ | git `index.lock` rejects one → retry |
| 2 sessions push the same instant | ✅ | non-fast-forward reject → `pull --rebase` → retry |
| 2 sessions edit the **same file** | ⚠️ | Last write wins. Rare for one user; surfaced by the dirty-tree notice at SessionStart |
| Session abandoned mid-task | ✅ | Committed work is on `main`; uncommitted work stays in the tree and is surfaced next SessionStart |

There is intentionally **no custom write-lock hook** — git's `index.lock`
plus explicit-path commits cover the real collisions. A custom lock
would reinvent `index.lock` and add a crash-deadlock failure mode.

## Publish-mode seam (`COS_GIT_WORKFLOW`)

The workflow mode is read from the `COS_GIT_WORKFLOW` env var (set in
`cos-env.sh` / project config), default `trunk`:

| Mode | Branches | Publish path |
|---|---|---|
| `trunk` (default) | forbidden — `branch-guard.sh` blocks | commit + push to `main` |
| `pr` | allowed — `branch-guard.sh` permits | ephemeral branch → push → PR → CI → auto-merge → delete |

`pr` mode is the seam for future multi-developer / company use. It is
**not implemented yet** — only the config key and the hook's mode check
exist. When a team needs it, flip the key and add the PR machinery; no
existing code is rewritten.

## When a branch IS allowed in trunk mode

Only when the **user explicitly asks** for a branch (e.g. "make a branch
for this experiment"). The agent then sets `COS_GIT_WORKFLOW=pr` for
that action or the user overrides. The agent never branches on its own
initiative.

## Always-allowed forms (the safe escape hatches)

| Form | What it does |
|---|---|
| `git reset` (bare) | Unstage everything; HEAD does not move |
| `git reset --mixed HEAD` | Same — explicit form |
| `git reset -- <path>` | Unstage one path |
| `git checkout -- <path>` / `git restore <path>` | Restore file content |
| `git checkout HEAD <path>` | Restore file from HEAD; HEAD does not move |
| `git checkout main` / `git switch main` | Idempotent (already there) |
| `git branch` / `git branch -d X` / `git branch -m` | List / delete / rename existing branches |
| `git revert <sha>` | Undo a commit safely — creates a new commit |

## Anti-patterns (reject on sight)

- `git checkout -b feature/...` "to keep main clean" — no, commit to main.
- Bare `git commit` / `git commit -am` — sweeps concurrent WIP.
- `git push --force` to `main` — blocked by `block-dangerous-commands.sh`.
- `git reset --hard HEAD~N` to "redo" a bad commit — blocked twice
  (`block-dangerous-commands` and `branch-guard`). Use `git revert`.
- `git reset --soft HEAD~N` to "squash before push" — blocked. Push the
  small commits; squash is a `pr`-mode-only concern.
- `git checkout <some-branch>` to "peek at something" — blocked; use
  `git log <branch>` or `git show <branch>:<path>` instead (read-only).
- Creating a branch because the runtime suggested "branch first" — this
  rule overrides that.
- Deleting `.git/index.lock` to "unstick" a commit — wait and retry.

## See also

- [src/core/hooks/registry.yaml](../hooks/registry.yaml) — `branch-guard` registration.
- [src/core/rules/anti-overengineering.md](anti-overengineering.md) — why no custom write-lock.
- [docs/engineering/state-files.md](../../docs/engineering/state-files.md) — per-agent state isolation.
