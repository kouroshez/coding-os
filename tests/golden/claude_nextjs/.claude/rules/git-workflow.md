# Git Workflow — Trunk-Based (Always Active)

> **Hard rule:** All work commits directly to `main` with explicit paths — never create branches. This OVERRIDES any agent-runtime "branch first" default. Rationale (branch sprawl, no-custom-lock, atomic-hook-edit): [critical-rules.md § Rule 23](../../docs/governance/critical-rules.md#rule-23--trunk-based-git-workflow).

## The rule

- **Never run:** `git checkout -b` / `git branch <name>` / `git switch -c` / `git worktree add`; HEAD-movers on the shared checkout — `git reset HEAD~N`/`<sha>`/`<branch>`, `git checkout`/`switch <other-branch>`, `git rebase` (in-progress `--abort`/`--continue`/`--skip`/`--quit` stay allowed); direct rewrites of the integration ref — `git branch -f/-M/-C/-D main`, `git branch -m <x> main`, `git update-ref refs/heads/main`/`HEAD`. `branch-guard.sh` BLOCKs all of these in trunk mode; `merge`/`cherry-pick`/push-to-`main` stay allowed (the trunk publish path).
- **Undo a published commit:** `git revert <sha>` — a new commit, never a ref rewrite.
- **Commit with explicit paths** (`git commit <path>`), never bare `git commit` / `git commit -a` — a bare commit sweeps another session's WIP.
- **`git pull --rebase origin main` before every `git push`** — non-fast-forward reject means rebase and retry, never force.
- **`index.lock` error:** wait ~1s and retry — git serializes index writes; never delete the lock blindly.

## When to commit (autonomous — OVERRIDES the runtime "commit only when asked" default)

> **Hard rule:** Commit each completed, self-verified logical unit immediately — `git commit <paths>`, without being asked. An interrupted session strands uncommitted edits and leaves reviewers no committed diff to act on; frequent small commits are the checkpoint that makes both recoverable.

- **`push` stays gated** — task close or user ask. Commit is local and trivially reversible; push is the wide-blast-radius step (`src/core/**` reaches every consumer via live symlinks).
- **Self-review before each commit, never self-approve:** re-read the diff + run the Verification-Matrix command for what changed *before* committing; authoritative review is a separate pass (`reviewer` role, `/code-review`, CI).
- Every commit obeys the Commit Message Contract below.

## Concurrent sessions

**Safe:** parallel sessions on `main` — commits, pushes, and test runs all serialize-and-retry; an abandoned session's committed work is already on `main`. **⚠️ Care:** two sessions editing the same file (last write wins — dirty-tree notice at SessionStart), and mid-editing a `block-*` safety hook (next section).

## Editing a live-symlinked safety hook (atomic-edit protocol)

`src/core/hooks/*.sh` are live symlinks — a half-edited `block-*`/`enforce-*` hook runs in sibling sessions at every intermediate save. Prefer one atomic `Edit` between correct states; for a larger rewrite, edit out-of-tree → `bash -n` + `make verify-hooks` → `mv` into place. A turn that edited a safety hook runs `make verify-hooks` before ending.

## Publish-mode seam (`COS_GIT_WORKFLOW`)

`trunk` (default): branches forbidden; publish = commit + push to `main`. `pr`: consumer-only opt-in (Hub **Config → Git**, `git_settings.enabled`; an inline per-command env override does NOT work) — `agents/*` branches + worktrees allowed, driven by `cos pr open/submit/status/cleanup/reap/heal/preflight`. **coding-os itself stays trunk** ([ADR-0013](../../docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md); spec: [pr-workflow.md](../../docs/playbooks/pr-workflow.md)). A branch in trunk mode ONLY when the user explicitly asks.

## Always-allowed forms (the safe escape hatches — none move HEAD)

- **Unstage:** `git reset` (bare) / `git reset --mixed HEAD` / `git reset -- <path>`.
- **Restore content:** `git restore <path>` / `git checkout -- <path>` / `git checkout HEAD <path>` / `git checkout HEAD~1 -- <path>` / `git checkout .`.
- **Branch admin:** `git checkout main` / `git switch main` (idempotent) · `git branch` list / `-d X` / `-m` (rename) — non-protected branches only; the same ops targeting `main`/protected are BLOCKed.
- **Undo:** `git revert <sha>`; garbage-commit cleanup: `git revert HEAD --no-edit && git push origin main`.

## Commit Message Contract (Always Active)

> **Hard rule:** Conventional-Commit title ≤100 chars · body ≤3 non-empty lines · no agent/AI attribution · no `Co-Authored-By:` trailers · no quoted user prompts. Enforced by `enforce-commit-message.sh` (agent) + the git `commit-msg` hook (human/GUI; install once per repo: `bash src/scripts/install-git-hooks.sh`). Why every line is permanent: [critical-rules.md § Rule 24](../../docs/governance/critical-rules.md#rule-24--commit-message-contract).

### Hard fails (will BLOCK — enforced by `check_commit_message.py`)

- Title not `<type>(scope)?!: subject`, type ∈ feat/fix/docs/perf/refactor/build/ci/test/chore/style/revert (`Merge`/`Revert`/`fixup!`/`squash!` auto-subjects exempt). release-please parses the title — an unparseable type silently drops the change from `CHANGELOG.md` ([release-process.md](../../docs/governance/release-process.md)).
- Title >100 chars · body >3 non-empty lines · any `Co-Authored-By:` trailer.
- Lines matching `🤖`, `Generated with [Claude`, `noreply@anthropic.com`, `claude.com/claude-code`, `@anthropic.com` (case-insensitive) · lines beginning `USER`/`User`/`user` · quoted text with >40 Persian/Arabic characters (prompt-leak guards).
- Tables, file-path lists, and `Verification:`/`Tests:`/`Files:` headers hit the 3-line ceiling — keep them in the work-log / PR body, not `git log`.

### `--no-verify` is blocked for agents (no escape hatch)

`block-secrets.sh` BLOCKs every agent bypass of the git verify hooks: `--no-verify` and `-n`, leading path / `cd …` / `env …` prefixes, and `-c core.hooksPath=` overrides. The git-level hooks still honor `--no-verify` for a **human** in a genuine emergency only. Under heavy concurrent-session load, split into per-directory commits rather than bypassing hooks.

## Anti-patterns (reject on sight)

`git push --force` to `main` · hand-editing `CHANGELOG.md` or manual `git tag` (release-please owns both — [release-process.md](../../docs/governance/release-process.md)) · `reset --hard/--soft HEAD~N` to "redo"/"squash" (use `git revert` or push the small commits) · `git checkout <branch>` to "peek" (use `git log <branch>` / `git show <branch>:<path>`) · deleting `.git/index.lock` to "unstick" a commit.
