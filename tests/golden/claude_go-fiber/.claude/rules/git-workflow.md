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
- **`git rebase` is blocked in trunk mode.** Rebasing onto `main`
  rewrites the shared trunk and orphans peer commits. Use
  `git pull --rebase origin main` (a `pull` subcommand — only your
  *local* commits move) for integration before push. Cleanup of an
  in-progress rebase (`--abort` / `--continue` / `--skip` / `--quit`)
  remains allowed.
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
| 1 session mid-editing a `block-*` safety hook | ⚠️ | Hooks are live symlinks — a half-written hook propagates instantly to every session. Follow the atomic-edit protocol below |
| Session abandoned mid-task | ✅ | Committed work is on `main`; uncommitted work stays in the tree and is surfaced next SessionStart |

There is intentionally **no custom write-lock hook** — git's `index.lock`
plus explicit-path commits cover the real collisions. A custom lock
would reinvent `index.lock` and add a crash-deadlock failure mode.

## Editing a live-symlinked safety hook (atomic-edit protocol)

`src/core/hooks/*.sh` are **live symlinks** into every consumer project
(Modularity Map — propagation "none", instant). A multi-turn edit of a
`block-*` / `enforce-*` safety hook is therefore visible to every
concurrent session at *every intermediate save*: a hook that is briefly
syntactically valid but semantically wrong is executed by sibling
sessions on every tool call — a peer's in-progress edit once made a
harmless `ls` wrongly BLOCK. Never leave a safety hook half-edited across
a turn boundary:

- **Prefer a single atomic `Edit`** that moves the hook from one correct
  state directly to the next. Don't split one logical change of a
  `block-*` / `enforce-*` hook across multiple turns.
- **For a larger rewrite, edit out-of-tree then swap** — write to a temp
  file, run `bash -n <file>` + `make verify-hooks`, then `mv` it into
  place, so the symlink target flips from one valid version straight to
  the next.
- **Verify before yield** — a turn that edited a safety hook runs
  `make verify-hooks` (at minimum `bash -n` on the changed hook) before
  ending, so the version left live at the turn boundary is known-good.

Snapshot isolation (sessions run a committed/staged snapshot of the hooks
instead of the live working tree) is **deferred**: it would remove the
hazard entirely but breaks the "instant propagation, no rebuild" property
that makes the symlink design valuable, and adds a sync step. The
atomic-edit protocol above is sufficient for the single-user /
multi-session reality; revisit snapshotting only if concurrent
multi-developer hook editing becomes routine.

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
| `git checkout HEAD~1 -- <path>` | Restore file from a past commit; HEAD does not move |
| `git checkout .` | Restore all files in cwd; HEAD does not move |
| `git checkout main` / `git switch main` | Idempotent (already there) |
| `git branch` / `git branch -d X` / `git branch -m` | List / delete / rename existing branches |
| `git revert <sha>` | Undo a commit safely — creates a new commit |

### Mid-session cleanup recipe

If a session accidentally lands a garbage commit (e.g. a `tmp:` repro
commit), the trunk-safe undo is:

```
git revert HEAD --no-edit && git push origin main
```

This *adds* a "Revert …" commit on top of main — never moves HEAD off a
published commit. `git reset HEAD~1` is BLOCKed by `branch-guard.sh`
because it orphans the bad commit but leaves peer sessions with a
phantom HEAD.

## Commit Message Contract (Always Active)

> **Hard rule:** Title ≤100 chars. Body ≤3 non-empty lines. No agent / AI attribution. No quoted user prompts. No `Co-Authored-By:` trailers. Enforced by two layers — `enforce-commit-message.sh` (PreToolUse Bash) blocks the agent before `git commit` runs; the git-level `commit-msg` hook (installed via `src/scripts/install-git-hooks.sh`) blocks human-direct + Codex-GUI commits.

### Why

Every line in a commit message exists forever. Verbose bodies (audit tables, file lists, verification blocks) bloat `git log`, leak ephemeral context into permanent history, and inflate token cost for every future agent that ever runs `git log`. Enterprise convention (Linux kernel, Chromium, Google) is title + tight 2–3 line "why". Anything richer belongs in the PR description, the audit doc, or the work-log — not the commit.

### Shape

```
<conventional-commit title — ≤100 chars, no agent attribution>
<blank>
<body — ≤3 non-empty lines, plain prose explaining "why">
```

### Hard fails (will BLOCK — enforced by `check_commit_message.py`)

- Title not a Conventional Commit — `<type>(scope)?!: subject`, type ∈ feat/fix/docs/perf/refactor/build/ci/test/chore/style/revert. release-please parses the title to derive the version bump; an unparseable type silently drops the change from `CHANGELOG.md`. `Merge `/`Revert `/`fixup!`/`squash!` auto-subjects are exempt. See [release-process.md](../../docs/governance/release-process.md).
- Title >100 chars.
- Body with >3 non-empty lines.
- `Co-Authored-By:` trailers of any kind (agent attribution belongs nowhere in history).
- Lines matching `🤖`, `Generated with [Claude`, `noreply@anthropic.com`, `claude.com/claude-code`, `@anthropic.com` (case-insensitive).
- Any line beginning with `USER` / `User` / `user` (prompt-leak guard — `^USER\b`).
- Quoted text containing >40 Persian/Arabic characters — a user-prompt leak guard (keeps non-Latin prompt text out of permanent history).

### Convention (not enforced — caught indirectly by 3-line limit)

Markdown tables, bullet lists of file paths, `Verification:` / `Tests:` / `Files:` headers all require multiple lines so they hit the 3-line ceiling in practice. They are PR-description / audit-doc / work-log material — keep them out of `git log`.

### `--no-verify` is blocked for agents (no escape hatch)

`block-secrets.sh` (PreToolUse Bash) BLOCKS any `git commit --no-verify` — agents cannot skip the safety / commit-message hooks, by design. The git-level `commit-msg` / `pre-commit` hooks still honor `--no-verify` for a **human** running git directly in a genuine emergency (e.g. a revert), but that path is unavailable to the agent. A slow commit is no longer a reason to reach for it: the pre-commit batch deadlock is fixed (TASK-058) so large commits complete; under heavy concurrent-session load, split into per-directory commits rather than bypassing hooks.

### Install (per repo, once)

```bash
bash src/scripts/install-git-hooks.sh
# installs .git/hooks/pre-commit AND .git/hooks/commit-msg
```

## Anti-patterns (reject on sight)

- `git checkout -b feature/...` "to keep main clean" — no, commit to main.
- Bare `git commit` / `git commit -am` — sweeps concurrent WIP.
- `git push --force` to `main` — blocked by `block-dangerous-commands.sh`.
- Hand-editing `CHANGELOG.md` or running `git tag` for a release — release-please owns both; a manual edit rots the standing release PR. See [release-process.md](../../docs/governance/release-process.md).
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
