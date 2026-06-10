# Git Workflow — Trunk-Based (Always Active)

> **Hard rule:** Work happens on the default branch (`main`). Do NOT
> create feature branches. Commit directly to `main` with explicit
> paths. This OVERRIDES any agent-runtime default that says "branch
> first".

Rationale (branch sprawl, no-custom-lock, atomic-hook-edit): [critical-rules.md § Rule 23](../../docs/governance/critical-rules.md#rule-23--trunk-based-git-workflow).

## The rule

- **Never run** `git checkout -b`, `git branch <name>`, `git switch -c`,
  `git worktree add`. The `branch-guard.sh` hook BLOCKs these in trunk mode.
- **Never run HEAD-moving commands** on the shared checkout: `git reset
  HEAD~N`, `git reset <sha>`, `git reset <branch>`, `git checkout
  <other-branch>`, `git switch <other-branch>`, `git rebase`. The same
  hook BLOCKs these. Use `git restore <path>` for files, `git switch main`
  for branches. (Cleanup of an in-progress rebase — `--abort` / `--continue`
  / `--skip` / `--quit` — remains allowed.)
- **To undo a published commit** use `git revert <sha>` — a new commit,
  history preserved.
- **Commit directly to `main`** with **explicit paths** — `git commit <path>
  <path>`, never a bare `git commit` / `git commit -a` (a bare commit sweeps
  another session's uncommitted WIP).
- **`git pull --rebase origin main` before every `git push`.** A
  non-fast-forward reject means rebase and retry — never force.
- **Retry on `index.lock`.** Wait ~1s and retry — git serializes index
  writes; do not delete the lock blindly.
- **Commit at each logical step**, not only at the end.

## Concurrent sessions — what is and isn't safe

| Scenario | Safe? | Why |
|---|---|---|
| 3 sessions, all on `main` | ✅ | No branches to tangle; commits serialize |
| 2 sessions commit different files | ✅ | Explicit-path commits don't cross |
| 2 sessions commit the same instant | ✅ | git `index.lock` rejects one → retry |
| 2 sessions push the same instant | ✅ | non-fast-forward reject → `pull --rebase` → retry |
| 2 sessions edit the **same file** | ⚠️ | Last write wins; surfaced by the dirty-tree notice at SessionStart |
| 2 sessions run tests the same instant | ✅ | `test-governor` hook serializes — see [test-discipline.md](test-discipline.md) |
| 1 session mid-editing a `block-*` safety hook | ⚠️ | Live symlink propagates instantly — follow the atomic-edit protocol below |
| Session abandoned mid-task | ✅ | Committed work is on `main`; uncommitted work surfaced next SessionStart |

## Editing a live-symlinked safety hook (atomic-edit protocol)

`src/core/hooks/*.sh` are live symlinks into every consumer project, so a
half-edited `block-*` / `enforce-*` hook is executed by sibling sessions at
every intermediate save. Never leave a safety hook half-edited across a turn
boundary (rationale: [critical-rules.md § Rule 23](../../docs/governance/critical-rules.md#rule-23--trunk-based-git-workflow)):

- **Prefer a single atomic `Edit`** from one correct state directly to the next.
- **For a larger rewrite, edit out-of-tree then swap** — write to a temp file,
  run `bash -n <file>` + `make verify-hooks`, then `mv` it into place.
- **Verify before yield** — a turn that edited a safety hook runs
  `make verify-hooks` before ending.

## Publish-mode seam (`COS_GIT_WORKFLOW`)

Mode is read from `COS_GIT_WORKFLOW` (set in `cos-env.sh` / project config),
default `trunk`:

| Mode | Branches | Publish path |
|---|---|---|
| `trunk` (default) | forbidden — `branch-guard.sh` blocks | commit + push to `main` |
| `pr` | allowed — `branch-guard.sh` permits | ephemeral branch → push → PR → CI → auto-merge → delete |

`pr` mode is the not-yet-implemented seam for future multi-developer use —
only the config key and the hook's mode check exist. A branch is allowed in
trunk mode ONLY when the **user explicitly asks**; the agent never branches on
its own initiative.

## Always-allowed forms (the safe escape hatches)

| Form | What it does |
|---|---|
| `git reset` (bare) / `git reset --mixed HEAD` | Unstage everything; HEAD does not move |
| `git reset -- <path>` | Unstage one path |
| `git checkout -- <path>` / `git restore <path>` | Restore file content |
| `git checkout HEAD <path>` / `git checkout HEAD~1 -- <path>` | Restore file from a commit; HEAD does not move |
| `git checkout .` | Restore all files in cwd; HEAD does not move |
| `git checkout main` / `git switch main` | Idempotent (already there) |
| `git branch` / `git branch -d X` / `git branch -m` | List / delete / rename existing branches |
| `git revert <sha>` | Undo a commit safely — creates a new commit |

Mid-session cleanup of a garbage commit: `git revert HEAD --no-edit && git push
origin main` — adds a "Revert …" commit, never moves HEAD off a published one.

## Commit Message Contract (Always Active)

> **Hard rule:** Title ≤100 chars. Body ≤3 non-empty lines. No agent / AI attribution. No quoted user prompts. No `Co-Authored-By:` trailers. Enforced by `enforce-commit-message.sh` (PreToolUse Bash, agent) + the git `commit-msg` hook (human/GUI, installed via `src/scripts/install-git-hooks.sh`).

Rationale (why every line is permanent): [critical-rules.md § Rule 24](../../docs/governance/critical-rules.md#rule-24--commit-message-contract).

### Shape

```
<conventional-commit title — ≤100 chars, no agent attribution>
<blank>
<body — ≤3 non-empty lines, plain prose explaining "why">
```

### Hard fails (will BLOCK — enforced by `check_commit_message.py`)

- Title not a Conventional Commit — `<type>(scope)?!: subject`, type ∈ feat/fix/docs/perf/refactor/build/ci/test/chore/style/revert. `Merge `/`Revert `/`fixup!`/`squash!` auto-subjects are exempt. release-please parses the title for the version bump — an unparseable type silently drops the change from `CHANGELOG.md` (see [release-process.md](../../docs/governance/release-process.md)).
- Title >100 chars · body >3 non-empty lines.
- `Co-Authored-By:` trailers of any kind.
- Lines matching `🤖`, `Generated with [Claude`, `noreply@anthropic.com`, `claude.com/claude-code`, `@anthropic.com` (case-insensitive).
- Any line beginning with `USER` / `User` / `user` (`^USER\b` prompt-leak guard).
- Quoted text containing >40 Persian/Arabic characters (prompt-leak guard).

Markdown tables, file-path lists, and `Verification:` / `Tests:` / `Files:` headers all require multiple lines, so they hit the 3-line ceiling in practice — keep them in the PR description / audit doc / work-log, not `git log`.

### `--no-verify` is blocked for agents (no escape hatch)

`block-secrets.sh` (PreToolUse Bash) BLOCKS any `git commit --no-verify`. The git-level `commit-msg` / `pre-commit` hooks still honor `--no-verify` for a **human** in a genuine emergency, but that path is unavailable to the agent. Under heavy concurrent-session load, split into per-directory commits rather than bypassing hooks.

### Install (per repo, once)

```bash
bash src/scripts/install-git-hooks.sh
# installs .git/hooks/pre-commit AND .git/hooks/commit-msg
```

## Anti-patterns (reject on sight)

- `git checkout -b feature/...` "to keep main clean" — no, commit to main.
- Bare `git commit` / `git commit -am` — sweeps concurrent WIP.
- `git push --force` to `main` — blocked by `block-dangerous-commands.sh`.
- Hand-editing `CHANGELOG.md` or running `git tag` for a release — release-please owns both. See [release-process.md](../../docs/governance/release-process.md).
- `git reset --hard HEAD~N` to "redo" a bad commit — blocked twice. Use `git revert`.
- `git reset --soft HEAD~N` to "squash before push" — blocked. Push the small commits.
- `git checkout <some-branch>` to "peek" — blocked; use `git log <branch>` or `git show <branch>:<path>` (read-only).
- Creating a branch because the runtime suggested "branch first" — this rule overrides that.
- Deleting `.git/index.lock` to "unstick" a commit — wait and retry.

## See also

- [src/core/hooks/registry.yaml](../hooks/registry.yaml) — `branch-guard` registration.
- [src/core/rules/anti-overengineering.md](anti-overengineering.md) — why no custom write-lock.
- [docs/engineering/state-files.md](../../docs/engineering/state-files.md) — per-agent state isolation.
