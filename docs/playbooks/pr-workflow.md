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
{ "git_settings": { "enabled": true, "integration_branch": "main", "protected_branches": ["production"], "autonomy_level": "draft" } }
```

`cos-env.sh` reads `git_settings.enabled` and, when true, **exports `COS_GIT_WORKFLOW=pr` session-wide** (alongside `COS_GIT_INTEGRATION_BRANCH`, `COS_GIT_PROTECTED_BRANCHES`, and `COS_GIT_AUTONOMY`). This is mandatory because **the inline form does not work**: `branch-guard.sh` reads its own process env *before* a command's `VAR=val cmd` prefix, so `COS_GIT_WORKFLOW=pr git …` is silently ignored. The toggle must persist into the adapter-injected environment exactly like `model_routing`. With the toggle off, nothing in this playbook fires and there is zero behavioural or token-cost difference.

`autonomy_level` (default `draft`) sets how far the agent acts unattended — the industry "Trust Spectrum" framing (§8). `cos pr submit`/`open` resolve `autonomy_level` + `integration_branch` themselves: an explicit `COS_GIT_AUTONOMY` / `COS_GIT_INTEGRATION_BRANCH` env var always wins, else the CLI **self-reads `git_settings` straight from the consumer's `hub-settings.json`**. The CLI validates the rung where it is consumed: an `autonomy_level` it does not recognize (e.g. written outside the Hub API edge) falls back to the safe `draft` with a warning, never silently behaving as draft while reporting the typo. This self-read is required because `cos-env.sh` exports the `COS_GIT_*` vars only into **hook** subprocesses — the agent's `cos pr` command shell carries none, so without it the saved rung/branch would be silently ignored (TASK-542). Inside a linked worktree the CLI resolves the **main** repo's settings file via `git rev-parse --git-common-dir`'s parent (§3), so every worktree of one repo honors the one shared config.

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

Worktrees under `~/.coding-os/` would hit `cos-env.sh::_cos_find_project_root`'s `$HOME` break and bind all state/DB/board/presence to the **global hub** instead of the worktree's repo. The dispatch layer therefore **exports `COS_PROJECT_ROOT=<main-repo>` for every command run inside a worktree**, so all worktrees of one repo share that repo's single `$COS_STATE_DIR` (this also unfragments `test-governor`'s `pgrep -f pytest` run-lock across worktrees). When that export is **not** inherited — a fresh hook subprocess, or a worktree at a custom `COS_WORKTREE_ROOT` that the raw-string gate never sees — `cos-env.sh` falls back to **git-native** detection: a linked worktree's `git rev-parse --show-toplevel` differs from the main checkout (`--git-common-dir`'s parent), so state still routes to the main repo regardless of where the worktree lives (gated on both fast-paths being absent, so a normal trunk hook never forks git). If even that is unresolvable, cos-env **refuses to write a worktree-local `.coding-os`** (which would otherwise be committed into the agent's own PR), binds to the hub instead, and surfaces a loud `COS_STATE_MISROUTE`.

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

# (2.5) PEERS — advisory only: spot a live peer editing your files BEFORE you push (§10.7)
cos pr conflicts                  # read-only; lists overlapping agents/* branches, never blocks

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
                                  # PRESERVE-BEFORE-DESTROY (TASK-561): when the resolved
                                  # worktree belongs to a DIFFERENT (drifted/peer) session
                                  # and its tree is dirty, bundles the uncommitted work
                                  # first; if the bundle fails, keeps the worktree.
```

**Session-id robustness (TASK-541).** `open` names the worktree/branch `<task>-<id>` / `agents/<task>/<id>` from the session id; `submit` and `cleanup` re-derive that name to find the worktree. When no session id resolves, the id falls back to `pid-<getpid>` — which differs across the separate `cos pr` processes of one unit of work, so a re-derive would miss the worktree. To prevent that, `submit`/`cleanup` first try the session-derived path (fast path, unchanged) and, only on a miss, resolve the worktree+branch **from disk** by the task slug — the same way the reaper derives the branch from the checkout (§7). An ambiguous match (two worktrees for one task slug) falls back to the computed pair rather than guess.

**Preserve before destroy under drift (TASK-561).** The single-candidate from-disk resolution above can hand `cleanup` a *peer's* worktree (same task slug, different session) — and the live-peer gate only refuses when that owner is *provably* live (a presence record with an alive same-host pid); a peer with **no** presence record reads as `unknown` and so passes the gate, exactly as a legitimate drifted-self does. The two are indistinguishable by session state, so `cleanup` cannot decide safety from liveness alone. Instead it borrows the reaper's `_preserve_reaped` (§7): when the resolved worktree belongs to a different session (`owner_session != session`) **and** its tree is dirty, it bundles the uncommitted work to `~/.coding-os/reaped/<repo-slug>/` **before** `worktree remove --force`; if that preservation fails, it keeps the worktree (refuses, like `_reap_one`'s `needs_attention`) rather than destroy the only copy. A non-drifted own-worktree cleanup is unchanged (no peer can lose work that is yours), so the merged-PR fast path stays a plain remove.

`gc.auto=0` is set in each worktree: worktrees share objects/refs/packed-refs, so background gc during a peer's rebase is unsafe.

## 5. Branch-guard in pr-mode — positive policy, not guard-kill (TASK-516)

Replacing `exit 0`, pr-mode is a **positive allow-list**, keeping the guards that still matter:

- **Allow:** `git worktree add` of an `agents/*` (or other non-blocked) branch, branch create/checkout of `agents/*`, a **worktree-scoped** `push --force-with-lease` (the worktree's HEAD is `agents/*` by construction).
- **Still BLOCK — the protected wall, every bypass shape, not just the obvious one:**
  - **HEAD-rewrites** — `reset` / `rebase` / `merge` / `cherry-pick` / `update-ref HEAD` (incl. `-d HEAD`) — on the **shared integration checkout**; allowed only when the op is **worktree-scoped** (a worktree advances its own `agents/*` HEAD, never the integration line). `merge --abort` / `cherry-pick --continue` and the other in-progress cleanup flags are safe and pass.
  - any **push** to an `integration_branch` / `protected_branches` entry, in **every refspec form** — bare (`origin main`), `heads/`-shorthand (`origin HEAD:heads/main`), fully-qualified (`origin HEAD:refs/heads/main`), force (`+main` / `+refs/heads/main`), delete (`origin :refs/heads/main`), and `--mirror` / `--all`. Ref shorthands are normalized (`refs/heads/` **and** `heads/` stripped) before the match, so no qualified form slips past. `protected_branches` accepts exact names and shell-style branch patterns such as `release/*`; UI chips and branch-guard enforcement use the same semantics.
  - a **bare or `HEAD`-only push from the shared integration checkout** (`git push`, `git push origin`, `git push -u origin HEAD`) — there the current branch IS the integration line, so an unnamed push advances it outside PR+CI. A push is allowed only when it is **worktree-scoped** OR names an **explicit non-blocked destination refspec** (`origin HEAD:agents/...`). The sanctioned `cos pr submit` always pushes from the worktree with the explicit `agents/*` branch named.
  - `git -c push.default=matching push` (and other unsafe `push.default` overrides) — a bare push under `matching` updates every same-name branch incl. the integration line, slipping the refspec check; refused outright in pr-mode.
  - any **direct ref rewrite** of a blocked branch — `git branch -f/-D/-m/-c <blocked>`, `git update-ref refs/heads/<blocked>` (incl. `--stdin`), or a force create/checkout `git checkout -B <blocked>` / `git switch -C <blocked>` — blocked **regardless of worktree**: refs are shared across every worktree via the common dir, so worktree scope is no protection here.
  - `git worktree add` (with `-b/-B <blocked>` or an existing blocked branch as the checkout target, e.g. `git worktree add <wt> main`) — a worktree may only be created on a non-blocked branch; checking the integration/protected line out into a worktree would let commits land on it through the worktree's own (otherwise-allowed) HEAD path.
  - bare `--force` push.
  - **shell-indirection** — a protected op hidden inside `eval '…'`, a pipe-into-`sh`/`bash`, a here-string `<<< '…'`, or `xargs git …` is **recovered** (the inner command string is un-glued by the shared parser, never interpreted) and re-evaluated against every rule above, so wrapping a push / HEAD-rewrite / branch-create in indirection no longer bypasses the guard. The same recovery feeds `block-dangerous-commands.sh`, so an `eval`-wrapped force-push-to-`main` is caught in trunk too.
- **Edit-isolation:** in pr-mode, `git commit` / Write / Edit against the **shared integration checkout** is blocked — every code change must happen in a worktree (so even no-task work isolates; see §6).
- **Policy-file integrity (defense-in-depth):** the mode switch itself is guarded — a Bash write / redirect / `tee` / `cp` / `mv` / `sed -i` / `python -c` whose resolved target is `<root>/.coding-os/hub-settings.json` is **blocked** (`block-dangerous-commands.sh`), closing the self-downgrade path where an agent rewrites `git_settings.enabled=false` to escape pr-mode and then pushes to `main` under trunk. If the file is present but unparseable (torn / corrupt write), `cos-env.sh` **fails closed to pr-mode** (the stricter posture) instead of silently dropping to trunk. Both are client-side fast-feedback; the authoritative wall stays server-side branch protection (§11).

**Adapter-parity caveat — Codex edit-isolation gap (runtime limitation, not a bug).** The Write/Edit half of the edit wall (`block-shared-tree-edit.sh`) fires only on a runtime that **hooks Write/Edit** — Claude Code does; **Codex (Bash-only hooks) does not** — so a Codex agent can edit the shared integration checkout directly. It is **partially mitigated**: `branch-guard.sh` runs on Bash for Codex, so a shared-tree `git commit` onto the integration line is still blocked. The edit lands in the working tree but cannot be committed onto the integration branch, so defense narrows from "no edit" to "no commit" and broken/unreviewed code still cannot reach the integration line. Parity is bounded by `adapter.yaml::hook_capabilities` (the renderer skips `{event, matcher}` pairs a runtime cannot fire) — this is a known capability gap, not a defect.

**Enforcement boundary — agent-PreToolUse only (not human/plain git).** All of §5 is enforced by PreToolUse hooks, so the branch/worktree/protected-push policy binds the **agent** runtime only. A **human**, `Codex.app`, or any plain `git` invocation is unconstrained — `install-git-hooks.sh` wires only the content + `commit-msg` `.git/hooks`, with no branch/worktree/HEAD-rewrite guard. pr-mode's branch policy is an agent-layer guarantee (the Config→Git tab states this in a static note); a git-level guard for human commits is **deferred** until a consumer needs it (Rule of Three). Enabling pr-mode requires a confirm step in the Hub and is hard-blocked on the `coding-os` slug (the meta-repo stays trunk).

## 6. No-task work still isolates

A consumer may say "fix X, don't make a task." pr-mode still isolates the change: `cos pr open --adhoc` creates `agents/adhoc/<session-id>` + a worktree, because the unit of isolation is **a code change**, not a board task. The shared integration checkout is edit-blocked (§5), so there is no path to mutate it directly.

## 7. Orphan reaper — owner-independent GC (TASK-519)

The dying agent cannot be trusted to clean up (the exact Rule-21 failure mode). A reaper runs **independently of the worktree's owner** — on `SessionStart` and/or cron — and GCs dead-agent worktrees / local branches / abandoned PRs. It **never touches a worktree whose owner is still live**, so liveness must be judged on *positive death evidence*, not the soft idle pill: a session is reaped only when its presence record sets `ended_at` **or** its recorded `pid` is no longer alive on this host. `presence.py`'s `session_presence()=="offline"` is **not** used as the death oracle — it also fires for a PID-alive agent merely idle >30min (a long build or model turn), and reaping that would destroy live uncommitted work. A no-presence-record orphan ("unknown") is GC'd only once its worktree is idle past `COS_PR_ORPHAN_MAX_AGE` (default 24h), measured by the **newest file mtime anywhere in the tree** (the top-level dir mtime alone is blind to nested `src/**` edits).

**Preserve before GC — the reaper never destroys work (TASK-535).** *When* to reap is owner-death; *what* the reaper may destroy is only a disposable artifact. The worktree is a re-creatable checkout, but the **branch commits and uncommitted changes are the work** and must survive. So `_reap_one` separates the two: it always removes the worktree directory, but before doing so it preserves the work whenever the branch is **not** already recoverable (`_branch_recoverable` — every commit reachable from an `origin`/integration ref) **or** the worktree is dirty. Preservation is gh-independent and offline-safe: capture uncommitted changes as a dangling commit (`git stash create`, no branch/hook mutation), then `git bundle create ~/.coding-os/reaped/<repo-slug>/<branch>-<ts>.bundle <branch> [<stash>]`. The local branch ref is deleted **only** once the work is safe — recoverable from origin **or** a bundle was confirmed written; if both preservation paths fail, the branch ref is kept (last-resort recovery) and the result flags `needs_attention`. This is the spec's `abandoned-preserved` lifecycle state (§6/§23): a reaped orphan with unique work lands in the quarantine bundle, never the void. (The interactive `cos pr cleanup` merge-gates the *committed* branch the same way and, since TASK-561, also preserves a drifted/peer worktree's *uncommitted* tree before destroying — closing the symmetric gap the reaper hardening left in the interactive path.)

## 8. Bounded self-heal + circuit-breaker (TASK-520)

Autonomy is capped so a stuck agent cannot loop forever or flood the remote:

- **Cap open PRs per session** (refuse to open the N+1th).
- **CI-runnable probe** before relying on auto-merge — auto-merge is armed (`gh pr merge --auto --squash`) **only when a required status check exists** on the integration branch. With no required check GitHub silently no-ops `--auto`, so `cos pr submit` does NOT arm it: it emits an explicit `merge_status: degraded-no-required-check` naming the missing check (never a silent open PR).
- **Autonomy level — the Trust Spectrum (TASK-533, TASK-540).** `git_settings.autonomy_level` (exported as `COS_GIT_AUTONOMY`, read by `cos pr submit`) is how far the agent acts unattended:
  - **`local`** (lowest rung, TASK-540) — submit commits in the worktree but **never pushes** and opens **no PR**; a human reviews the `agents/*` branch (`git diff <integration>..<branch>`) and integrates it. Works with **no remote at all** (beginner / solo / air-gapped) and short-circuits before the capability probe, so a missing remote is the intended mode, not a degrade. `merge_status: local`, `pushed: False`.
  - **`draft`** (default, safe) — submit opens the PR and **never** arms auto-merge, whatever the CI state; a human merges. `merge_status: draft`.
  - **`auto_merge`** — submit arms `gh pr merge --auto --squash` **when a required check exists** (else `degraded-no-required-check`); the PR merges itself once green.
  - **`autonomous`** — same arming as `auto_merge`, and additionally authorizes the driver loop (§ pr-mode-driver skill) to `cos pr cleanup` the worktree itself once the PR is merged.
  - Levels at/above `draft` still honor the required-check gate — autonomy widens *who merges* (human → agent) and, at `local`, *whether the agent pushes at all* — but **never** *whether CI gates the merge*. A consumer that wants full no-touch automation but has no CI must add a required check, not lower the gate; the no-CI consumer's path is `local` (human integrates) or `draft` (human merges).
- **Escalate-to-blocked** after N self-heal attempts on the same red PR: move the board task to `blocked` with the failure, stop retrying.
- **Drive the loop on the CI rollup (TASK-529, TASK-556).** `cos pr status --branch <branch>` returns one `ci_rollup` signal — `merged | red | pending | passing | passing-unarmed | closed | none` — distilled from `gh`'s `statusCheckRollup` **plus** whether auto-merge is armed (`isDraft` / `autoMergeRequest`), so the green-but-won't-auto-land case is derivable from the signal alone and needs no memory of the prior `cos pr submit` (survives `/clear` / `/compact` / reaper-handoff). The shipped `pr-mode-driver` skill encodes the poll→branch decision so a non-expert consumer's agent is *told* how to run the diagnose-fix-retry loop instead of remembering the blind heal counter: `merged` → `cos pr cleanup`; `red` → `cos pr heal` (charges the budget; escalates to `blocked` when spent) then fix in the worktree + re-`cos pr submit`; `pending`/`passing` (auto-merge armed) → wait and re-poll next turn; `passing-unarmed` (green, nothing will auto-land it) → **STOP** for a human merge; `none` → open/submit.

## 9. Capability preflight & degrade (CLI lives in `src/cli`, never `src/core`)

`cos pr preflight` checks: remote configured · `gh` installed + authenticated · a required CI check exists on the integration branch. Any miss → **degrade to trunk** with a one-line reason. `gh` is invoked only from `src/cli` (P2/P8: `src/core/**` symlinks reach every consumer and must stay agent/host-agnostic). When a remote IS configured but the integration branch has **no required check**, `cos pr preflight` and `cos pr submit` additionally emit an `unprotected_integration` warning (derived from the existing `remote && !required_check` probe — no extra round-trip): the client branch-guard is then the only barrier, so set up the §11 ruleset to put the wall server-side. This is **non-blocking legibility** (the client hooks are fast-feedback, not the security boundary), never a degrade or a hard fail.

The Hub **Config → Git** tab reads `GET /api/settings/git-state`, which returns the capability probe **and** the repo's real git-state (`branches`, `current_branch`, `remote_url`, from local git only — present even when `gh` is down). `integration_branch` renders as a dropdown and `protected_branches` as a multiselect sourced from that branch list, so a consumer cannot silently configure a non-existent branch (a stray value warns at save). The tab runs the probe even while pr-mode is disabled so a consumer sees branch, remote, `gh`, and required-check capability before enabling the workflow; the result is `staleTime`-cached so re-opening the tab does not re-round-trip (TASK-534).

The probe also **drives the autonomy dropdown data-driven (TASK-540)**: rungs the repo cannot support are disabled with a reason — when the probe reports no `remote` or no `gh`, only `local` is selectable (push/PR rungs need both), so the panel can never offer a mode that would degrade at submit. A currently-saved-but-now-unsupported value stays selectable (never silently rewritten) but is annotated. One non-blocking warning sharpens the choice without restricting it: `auto_merge` or `autonomous` on an integration branch with **no required check** warns that auto-merge will not arm and the PR will stay open for manual merge — add a required check (pr-workflow.md §8) to get hands-off merging, or use `local`/`draft` if you do not run CI (the CI-gate is never lowered to compensate). If a consumer ignores the warning and submits anyway, `cos pr submit` does not silently strand the open PR: a degraded `auto_merge`/`autonomous` submit with no required check **escalates the board task to `blocked`** (`board_blocked: true` in the emit) so a human is signalled to add the check, rather than leaving the deadlock to only a non-fatal stderr line.

**Forge support — GitHub only today (runtime limitation, not a bug).** The push / PR / merge automation is 100% the GitHub `gh` CLI (`gh pr create` / `gh pr merge --auto` / `gh pr list`, all in `src/cli/pr_commands.py`). A **GitLab / Gitea / Forgejo / Bitbucket / self-hosted** consumer therefore cannot use the push/PR rungs (`draft` / `auto_merge` / `autonomous`); its only supported autonomy rung is **`local`** — the agent commits in the worktree, never pushes, and a human integrates the `agents/*` branch (`git diff <integration>..<branch>` then `git merge --no-ff`). Everything else is forge-agnostic (worktree isolation, branch-guard, the reaper, the `local` rung); only the publish step is GitHub-coupled. A forge-adapter layer (a `gh`/`glab`/`tea` shim behind the publish step) is **deferred** until a non-GitHub consumer needs it (Rule of Three).

## 10. Defense in depth (why broken code can't reach integration, why nothing orphans)

1. **Isolation** — per-task worktree = separate `index.lock` + separate checkout → no commit contention, no file overwrite.
2. **Hook guards** — branch-guard positive policy (§5) blocks HEAD-rewrites on shared tree + protected-branch writes.
3. **CI gate** — required status check + merge queue ("two pass alone, break together" caught before merge); broken code never merges.
4. **Autonomy safety** — self-heal budget + circuit-breaker (§8).
5. **Cleanup** — live cleanup on merge (§4.5, merge-gated: `cos pr cleanup` refuses to destroy an OPEN-PR / unpushed worktree without `--force`) + owner-independent reaper (§7).
6. **Protected wall + default-OFF** — `protected_branches` never agent-writable; whole engine inert until the consumer opts in (§1).
7. **Conflict pre-detection (TASK-558)** — `cos pr conflicts` (read-only, advisory) reports when a live peer `agents/*` branch edits the same files (touched = `merge-base..branch` diff ∪ that worktree's uncommitted porcelain) — the early warning the merge queue (late, post-CI) doesn't give. It **never blocks**: two agents may legitimately edit one file in different places, and rebase-at-submit + the merge queue still catch a real conflict at land. Only branches that currently have a worktree appear, so it scopes to genuinely-concurrent agents.

> **Why there is no separate "frozen base snapshot".** An agent branch forks the integration head at `open`; `cos pr submit` re-pins it (`git fetch + rebase FETCH_HEAD`) and the merge queue rebases again at land, so base drift is *integrated* before merge rather than frozen. `cos pr conflicts` measures overlap from the `merge-base` fork-point, which a moving integration head does not distort. A dedicated base-snapshot store would add persistent state with no consumer — deferred under Rule-of-Three (anti-overengineering), not overlooked.

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
