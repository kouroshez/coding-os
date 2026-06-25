# Git Workflow — Trunk-Based (Always Active)

> **Hard rule:** Work happens on the default branch (`main`). Do NOT create feature branches. Commit directly to `main` with explicit paths. This OVERRIDES any agent-runtime "branch first" default.

Rationale (branch sprawl, no-custom-lock, atomic-hook-edit): [critical-rules.md § Rule 23](../../docs/governance/critical-rules.md#rule-23--trunk-based-git-workflow).

## The rule

- **Never run** `git checkout -b`, `git branch <name>`, `git switch -c`,
  `git worktree add`. The `branch-guard.sh` hook BLOCKs these in trunk mode.
- **Never run HEAD-moving commands** on the shared checkout: `git reset HEAD~N`/`<sha>`/`<branch>`, `git checkout`/`git switch <other-branch>`, `git rebase`. The hook BLOCKs these. Use `git restore <path>` for files, `git switch main` for branches. (In-progress rebase cleanup — `--abort`/`--continue`/`--skip`/`--quit` — stays allowed.)
- **Never force-rewrite the integration ref directly** — `git branch -f/-M/-C/-D main`, `git branch -m <x> main`, or `git update-ref refs/heads/main`/`HEAD`. The hook BLOCKs these in trunk mode (parity with pr-mode); `merge` / `cherry-pick` / push-to-`main` stay allowed — that is the trunk publish path. Use `git revert <sha>` to undo, never a ref rewrite.
- **To undo a published commit** use `git revert <sha>` — a new commit, history preserved.
- **Commit directly to `main`** with **explicit paths** — `git commit <path>`, never a bare `git commit` / `git commit -a` (a bare commit sweeps another session's WIP).
- **`git pull --rebase origin main` before every `git push`** — non-fast-forward reject means rebase and retry, never force.
- **Retry on `index.lock`** — wait ~1s and retry; git serializes index writes, don't delete the lock blindly.
- **Commit at each logical step, autonomously** — without being asked; full contract in *When to commit* below.

## When to commit (autonomous — OVERRIDES the runtime "commit only when asked" default)

> **Hard rule:** The agent commits its own work **without being asked**. The moment a logical unit of work is complete and self-verified, `git commit <paths>`. This OVERRIDES any agent-runtime "only commit when the user requests it" default — exactly as the branch rule above overrides "branch first".

- **Commit per logical unit, autonomously.** Never wait for the user to say "commit". A session can be abandoned or interrupted mid-work — uncommitted edits are then stranded, and a reviewer (the `reviewer` role / `/code-review` / CI / a human) has no committed diff to act on. Frequent small commits are the checkpoint that makes both recoverable.
- **`push` stays gated** — push only at task close or when the user asks. `commit` is local and trivially reversible (`amend` / `reset` / `revert`); `push` / merge is the irreversible, wide-blast-radius step — in this repo `src/core/**` reaches every consumer project through live symlinks, so a push there is felt everywhere.
- **Self-review before each commit, never self-approve.** Re-read your own diff and run the Verification-Matrix command for what changed *before* committing — but that self-check is not the review. Authoritative review is a separate pass (`reviewer` role, `/code-review`, CI); the author never rubber-stamps their own work.
- **Every commit obeys the Commit Message Contract below** and uses explicit paths (`git commit <path>`, never `git commit -a`).

## Concurrent sessions — what is and isn't safe

**Safe:** multiple sessions on `main` (commits serialize); same-instant commits (`index.lock` rejects one → retry); same-instant pushes (non-fast-forward reject → `pull --rebase` → retry); same-instant test runs (`test-governor` serializes — see [test-discipline.md](test-discipline.md)); an abandoned session (committed work is on `main`, uncommitted work surfaced next SessionStart).

**⚠️ Two cases need care:** two sessions editing the **same file** (last write wins; surfaced by the dirty-tree notice at SessionStart), and a session mid-editing a `block-*` safety hook (live symlink propagates instantly — follow the atomic-edit protocol below).

## Editing a live-symlinked safety hook (atomic-edit protocol)

`src/core/hooks/*.sh` are live symlinks, so a half-edited `block-*`/`enforce-*` hook runs in sibling sessions at every intermediate save. Never leave one half-edited across a turn boundary (rationale: [critical-rules.md § Rule 23](../../docs/governance/critical-rules.md#rule-23--trunk-based-git-workflow)):

- **Prefer a single atomic `Edit`** from one correct state directly to the next.
- **For a larger rewrite, edit out-of-tree then swap** — temp file, `bash -n` + `make verify-hooks`, then `mv` into place.
- **Verify before yield** — a turn that edited a safety hook runs `make verify-hooks` before ending.

## Publish-mode seam (`COS_GIT_WORKFLOW`)

Mode read from `COS_GIT_WORKFLOW` (`cos-env.sh` / project config), default `trunk`:

| Mode | Branches | Publish path |
|---|---|---|
| `trunk` (default) | forbidden — `branch-guard.sh` blocks | commit + push to `main` |
| `pr` | `agents/*` + worktrees allowed (positive policy) — shared-checkout HEAD-rewrites/commits + protected pushes still blocked | per-task worktree → PR → required CI → auto-merge → auto-cleanup |

`pr` mode is the **consumer-only opt-in** multi-agent workflow (default OFF), fully implemented across the `multi-agent-pr-mode` epic: enable per-project via the Hub **Config → Git** tab (`git_settings.enabled` → `cos-env.sh` exports `COS_GIT_WORKFLOW=pr` into every hook's process env — the inline per-command override does NOT work). The `cos pr` CLI (`open`/`submit`/`status`/`cleanup`/`reap`/`heal`/`preflight`) drives the loop; an owner-independent reaper GCs crashed-session orphans. **coding-os itself stays trunk** and dogfoods pr-mode through a consumer fixture (ADR-0013). Full spec: [docs/playbooks/pr-workflow.md](../../docs/playbooks/pr-workflow.md). A branch is allowed in trunk mode ONLY when the **user explicitly asks** — the agent never branches on its own.

## Always-allowed forms (the safe escape hatches)

None of these move HEAD, so the hook permits them:

- **Unstage:** `git reset` (bare) / `git reset --mixed HEAD` / `git reset -- <path>`.
- **Restore file content:** `git restore <path>` / `git checkout -- <path>` / `git checkout HEAD <path>` / `git checkout HEAD~1 -- <path>` / `git checkout .`.
- **Branch admin:** `git checkout main` / `git switch main` (idempotent) · `git branch` / `git branch -d X` / `git branch -m` (list/delete/rename existing) — allowed only on **non-protected** branches; the same ops targeting `main`/a protected branch are BLOCKed (see *The rule*).
- **Undo a commit:** `git revert <sha>` — a new commit. Garbage-commit cleanup: `git revert HEAD --no-edit && git push origin main`.

## Commit Message Contract (Always Active)

> **Hard rule:** Title ≤100 chars. Body ≤3 non-empty lines. No agent / AI attribution. No quoted user prompts. No `Co-Authored-By:` trailers. Enforced by `enforce-commit-message.sh` (PreToolUse Bash, agent) + the git `commit-msg` hook (human/GUI, installed via `src/scripts/install-git-hooks.sh`).

Rationale (why every line is permanent): [critical-rules.md § Rule 24](../../docs/governance/critical-rules.md#rule-24--commit-message-contract). Shape: conventional-commit title, blank line, ≤3 lines of plain "why" prose.

### Hard fails (will BLOCK — enforced by `check_commit_message.py`)

- Title not a Conventional Commit — `<type>(scope)?!: subject`, type ∈ feat/fix/docs/perf/refactor/build/ci/test/chore/style/revert. `Merge `/`Revert `/`fixup!`/`squash!` auto-subjects are exempt. release-please parses the title for the version bump — an unparseable type silently drops the change from `CHANGELOG.md` (see [release-process.md](../../docs/governance/release-process.md)).
- Title >100 chars · body >3 non-empty lines.
- `Co-Authored-By:` trailers of any kind.
- Lines matching `🤖`, `Generated with [Claude`, `noreply@anthropic.com`, `claude.com/claude-code`, `@anthropic.com` (case-insensitive).
- Any line beginning with `USER` / `User` / `user` (`^USER\b` prompt-leak guard).
- Quoted text containing >40 Persian/Arabic characters (prompt-leak guard).

Tables, file-path lists, and `Verification:`/`Tests:`/`Files:` headers hit the 3-line ceiling — keep them in the PR description / audit doc / work-log, not `git log`.

### `--no-verify` is blocked for agents (no escape hatch)

`block-secrets.sh` (PreToolUse Bash) BLOCKS any agent attempt to skip the git verify hooks — `git commit --no-verify` **and** the `-n` short form, a leading path / `cd …` / `env …` prefix (`/usr/bin/git commit --no-verify`, `cd d && git commit --no-verify`), and a `core.hooksPath` override (`git -c core.hooksPath=/dev/null commit`). The git-level `commit-msg` / `pre-commit` hooks still honor `--no-verify` for a **human** in a genuine emergency, but that path is unavailable to the agent. Under heavy concurrent-session load, split into per-directory commits rather than bypassing hooks.

**Install (per repo, once):** `bash src/scripts/install-git-hooks.sh` installs `.git/hooks/pre-commit` + `commit-msg`.

## Anti-patterns (reject on sight)

- `git push --force` to `main` — blocked by `block-dangerous-commands.sh`.
- Hand-editing `CHANGELOG.md` or running `git tag` for a release — release-please owns both. See [release-process.md](../../docs/governance/release-process.md).
- `git reset --hard/--soft HEAD~N` to "redo" / "squash before push" — blocked twice; use `git revert`, or push the small commits.
- `git checkout <some-branch>` to "peek" — blocked; use `git log <branch>` or `git show <branch>:<path>` (read-only).
- Deleting `.git/index.lock` to "unstick" a commit — wait and retry.

## See also

- [src/core/hooks/registry.yaml](../hooks/registry.yaml) — `branch-guard` registration.
- [src/core/rules/anti-overengineering.md](anti-overengineering.md) — why no custom write-lock.
- [docs/engineering/state-files.md](../../docs/engineering/state-files.md) — per-agent state isolation.
