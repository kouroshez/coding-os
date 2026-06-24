<!-- domain:META | layer:playbook | ssot:true | updated:2026-06-22 -->
# Playbook — PR-Mode Multi-Agent Git Workflow (Consumer-Only)

Purpose: The operational contract for `COS_GIT_WORKFLOW=pr` — per-task git worktree → PR → required-CI → auto-merge → auto-cleanup, so 5+ agents work one consumer repo concurrently without collision and broken code never reaches the integration branch.
Read when: Implementing or operating any pr-mode piece (branch-guard policy, `cos pr` CLI, the reaper, self-heal budget, Hub `git_settings`), or enabling pr-mode on a consumer.
Skip when: Working in coding-os itself or any trunk-mode repo — pr-mode is OFF by default and the mother repo never switches (see [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md)).
Read next: [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md) · [git-workflow.md](../../src/core/rules/git-workflow.md) · [state-files.md](../engineering/state-files.md)

> Nav: [Docs Index](../00-index.md)

## 0. Two modes — never mixed in one repo

`COS_GIT_WORKFLOW` is read from `cos-env.sh` (project config / env), default `trunk`.

| Mode | Branches | Worktrees | Publish path |
|---|---|---|---|
| `trunk` (default) | forbidden — `branch-guard.sh` blocks | forbidden | commit + push to `main` |
| `pr` (consumer opt-in) | `agents/*` allowed | required, outside the repo | worktree → PR → required CI → auto-merge → cleanup |

A repo is one mode or the other. coding-os is permanently `trunk` (Rule 23). pr-mode is for consumer projects that opt in.

## 1. Enablement — the only switch that turns pr-mode on

pr-mode is **default OFF**. It activates only when a consumer sets, in its **own** per-project state:

```jsonc
// $COS_STATE_DIR/hub-settings.json   (per-project — each repo has its own)
{ "git_settings": { "enabled": true, "integration_branch": "main", "protected_branches": ["production"] } }
```

`cos-env.sh` reads `git_settings.enabled` and, when true, **exports `COS_GIT_WORKFLOW=pr` session-wide**. This is mandatory because **the inline form does not work**: `branch-guard.sh` reads its own process env *before* a command's `VAR=val cmd` prefix, so `COS_GIT_WORKFLOW=pr git …` is silently ignored. The toggle must persist into the adapter-injected environment exactly like `model_routing`. With the toggle off, nothing in this playbook fires and there is zero behavioural or token-cost difference.

## 2. Naming & paths (the slug contract)

```bash
# Branch (board task):   agents/<task-slug>/<id>
# Branch (no task):      agents/adhoc/<session-id>
# Repo slug:             <repo-basename>-<sha8(realpath)>   (readable AND collision-free)
#                        /Users/x/Project/foo  ->  foo-1a2b3c4d
# Worktree root:         ${COS_WORKTREE_ROOT:-~/.coding-os/worktrees}/<repo-slug>
# Worktree path:         <root>/<task-slug>-<session>
```

- `<session>` is the agent's session id (from the **atomic board claim** `cos_task_claim_next` → unique `agent_session`), **not** a wall-clock timestamp (same-second agents collide). Implemented by `cos pr` (src/cli/pr_commands.py): `cos pr open [--task | --adhoc]` isolates, `cos pr submit` publishes, `cos pr cleanup` GCs.
- Worktrees live in **one central per-repo root outside every repo**. Never inside the repo (§Alternatives in ADR-0013: bundlers/watchers break on a second on-disk checkout). Never `../agent-worktrees` (resolves to the same parent for 100 repos).

## 3. The `$HOME` hard-stop fix (foundation — TASK-515)

Worktrees under `~/.coding-os/` would hit `cos-env.sh::_cos_find_project_root`'s `$HOME` break and bind all state/DB/board/presence to the **global hub** instead of the worktree's repo. The dispatch layer therefore **exports `COS_PROJECT_ROOT=<main-repo>` for every command run inside a worktree**, so all worktrees of one repo share that repo's single `$COS_STATE_DIR` (this also unfragments `test-governor`'s `pgrep -f pytest` run-lock across worktrees).

## 4. The autonomous loop (per task — driven by the agent's turn loop, not a daemon)

```bash
# (0) PREFLIGHT — capability gate. Missing remote / gh-auth / required-CI => degrade to trunk, do NOT half-work.
cos pr preflight || { echo "pr-mode unavailable — staying trunk"; exit 0; }

# (1) ISOLATE
cos pr open --task "$TASK"        # or: cos pr open --adhoc   (no board task — see §6)
#   => git fetch origin <integration>; git worktree add -b agents/<task>/<id> <wt> origin/<integration>
#      exports COS_PROJECT_ROOT=<main-repo> into the worktree shell

# (2) WORK + VALIDATE with the repo's OWN check (stack-agnostic)
<edit files in the worktree>
<repo validate cmd>               # npm run validate --if-present | make verify | the repo's declared command

# (3) COMMIT + REBASE onto FETCH_HEAD (never the shared moving ref) + PUSH (lease, never bare force)
git add -A && git commit -m "<conventional msg>"
git fetch origin <integration> && git rebase FETCH_HEAD
git push --force-with-lease --force-if-includes -u origin HEAD

# (4) PR + AUTO-MERGE (auto-merge OFF until proven stable — TASK-513)
gh pr create --base <integration> --head "$(git branch --show-current)" --title "…" --body "agent task <task>/<id>"
gh pr merge --auto --squash       # merges itself once required CI is green; CI red => PR simply does not merge

# (5) CLEANUP on merge (this is what prevents orphans)
cos pr cleanup --task "$TASK"     # MERGE-GATED: refuses while the PR is still OPEN, or
                                  # when the branch has local commits not on origin,
                                  # unless --force. On a merged/closed PR (or a fully
                                  # pushed branch): worktree remove + branch -D + prune.
```

`gc.auto=0` is set in each worktree: worktrees share objects/refs/packed-refs, so background gc during a peer's rebase is unsafe.

## 5. Branch-guard in pr-mode — positive policy, not guard-kill (TASK-516)

Replacing `exit 0`, pr-mode is a **positive allow-list**, keeping the guards that still matter:

- **Allow:** `git worktree add`, branch create/checkout of `agents/*`, `push --force-with-lease` to `agents/*`.
- **Still BLOCK — the protected wall, every bypass shape, not just the obvious one:**
  - **HEAD-rewrites** — `reset` / `rebase` / `merge` / `cherry-pick` — on the **shared integration checkout**; allowed only when the op is **worktree-scoped** (a worktree advances its own `agents/*` HEAD, never the integration line). `merge --abort` / `cherry-pick --continue` and the other in-progress cleanup flags are safe and pass.
  - any **push** to an `integration_branch` / `protected_branches` entry, in **every refspec form** — bare (`origin main`), fully-qualified (`origin HEAD:refs/heads/main`), force (`+main` / `+refs/heads/main`), delete (`origin :refs/heads/main`), and `--mirror` / `--all`.
  - any **direct ref rewrite** of a blocked branch — `git branch -f/-D/-m/-c <blocked>` or `git update-ref refs/heads/<blocked>` (incl. `--stdin`) — blocked **regardless of worktree**: refs are shared across every worktree via the common dir, so worktree scope is no protection here.
  - bare `--force` push.
- **Edit-isolation:** in pr-mode, `git commit` / Write / Edit against the **shared integration checkout** is blocked — every code change must happen in a worktree (so even no-task work isolates; see §6).

## 6. No-task work still isolates

A consumer may say "fix X, don't make a task." pr-mode still isolates the change: `cos pr open --adhoc` creates `agents/adhoc/<session-id>` + a worktree, because the unit of isolation is **a code change**, not a board task. The shared integration checkout is edit-blocked (§5), so there is no path to mutate it directly.

## 7. Orphan reaper — owner-independent GC (TASK-519)

The dying agent cannot be trusted to clean up (the exact Rule-21 failure mode). A reaper runs **independently of the worktree's owner** — on `SessionStart` and/or cron — and GCs dead-agent worktrees / local branches / abandoned PRs. It **never touches a worktree whose owner is still live**, so liveness must be judged on *positive death evidence*, not the soft idle pill: a session is reaped only when its presence record sets `ended_at` **or** its recorded `pid` is no longer alive on this host. `presence.py`'s `session_presence()=="offline"` is **not** used as the death oracle — it also fires for a PID-alive agent merely idle >30min (a long build or model turn), and reaping that would destroy live uncommitted work. A no-presence-record orphan ("unknown") is GC'd only once its worktree is idle past `COS_PR_ORPHAN_MAX_AGE` (default 24h), measured by the **newest file mtime anywhere in the tree** (the top-level dir mtime alone is blind to nested `src/**` edits).

## 8. Bounded self-heal + circuit-breaker (TASK-520)

Autonomy is capped so a stuck agent cannot loop forever or flood the remote:

- **Cap open PRs per session** (refuse to open the N+1th).
- **CI-runnable probe** before relying on auto-merge — auto-merge is armed (`gh pr merge --auto --squash`) **only when a required status check exists** on the integration branch. With no required check GitHub silently no-ops `--auto`, so `cos pr submit` does NOT arm it: it emits an explicit `merge_status: degraded-no-required-check` naming the missing check (never a silent open PR). Autonomous merge with no CI gate is opt-in via `autonomy_level` (TASK-533).
- **Escalate-to-blocked** after N self-heal attempts on the same red PR: move the board task to `blocked` with the failure, stop retrying.

## 9. Capability preflight & degrade (CLI lives in `src/cli`, never `src/core`)

`cos pr preflight` checks: remote configured · `gh` installed + authenticated · a required CI check exists on the integration branch. Any miss → **degrade to trunk** with a one-line reason. `gh` is invoked only from `src/cli` (P2/P8: `src/core/**` symlinks reach every consumer and must stay agent/host-agnostic).

## 10. Defense in depth (why broken code can't reach integration, why nothing orphans)

1. **Isolation** — per-task worktree = separate `index.lock` + separate checkout → no commit contention, no file overwrite.
2. **Hook guards** — branch-guard positive policy (§5) blocks HEAD-rewrites on shared tree + protected-branch writes.
3. **CI gate** — required status check + merge queue ("two pass alone, break together" caught before merge); broken code never merges.
4. **Autonomy safety** — self-heal budget + circuit-breaker (§8).
5. **Cleanup** — live cleanup on merge (§4.5, merge-gated: `cos pr cleanup` refuses to destroy an OPEN-PR / unpushed worktree without `--force`) + owner-independent reaper (§7).
6. **Protected wall + default-OFF** — `protected_branches` never agent-writable; whole engine inert until the consumer opts in (§1).

## 11. One-time consumer repo setup

- **GitHub → Pull Requests:** Allow auto-merge ✅ · Auto-delete head branches ✅.
- **Ruleset → integration branch (`main`):** require a PR · required approvals **0** · require status checks (the CI job) · block direct pushes · block force pushes · enable **merge queue**.
- **Ruleset → protected branch (`production`):** restrict updates to the owner only (agents not on bypass) · block force pushes · block deletion.
- **Agent token:** `Contents: read/write`, `Pull requests: read/write`, `Metadata: read`. No access to protected branches.
- CI fires on `pull_request: [<integration>]` + `merge_group`; the repo's own validate command is the single source of truth.

## See also

- [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md) — why consumer-only, why the reaper makes Rule 21 and pr-mode compatible.
- [src/core/rules/git-workflow.md](../../src/core/rules/git-workflow.md) — trunk discipline + the `COS_GIT_WORKFLOW` mode table.
- [docs/engineering/state-files.md](../engineering/state-files.md) — `COS_STATE_DIR` / `COS_PROJECT_ROOT` resolution the §3 fix depends on.
- [docs/engineering/hub-architecture.md](../engineering/hub-architecture.md) — the per-project `hub-settings.json` that holds `git_settings` (§1).
