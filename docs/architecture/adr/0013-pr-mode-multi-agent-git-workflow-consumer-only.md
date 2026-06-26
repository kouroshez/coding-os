<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-22 -->
# ADR-0013: PR-mode multi-agent git workflow is consumer-only; coding-os stays trunk

> Nav: [ADR Index](./00-index.md)

## Status

Accepted (2026-06-22, epic `multi-agent-pr-mode`) — the architecture (consumer-only, default-OFF, reaper-backed) is firm and built now; *enablement* of auto-merge on any repo stays gated behind TASK-513 (CI green + Actions quota).

- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** pr-mode, worktree, multi-agent, dogfood, rule-21, rule-23, COS_GIT_WORKFLOW

## Context

coding-os ships a **stubbed** `COS_GIT_WORKFLOW=pr` seam: [branch-guard.sh](../../../src/core/hooks/branch-guard.sh) line 43 is `if [[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]]; then exit 0; fi`. That is not a workflow — it is a **global guard-kill** that, when reached, disables every branch/HEAD-move/protected-branch check at once. Three traps were verified by red-team before this ADR (do not re-discover them):

1. **`$HOME` hard-stop.** Worktrees under `~/.coding-os/` hit `cos-env.sh::_cos_find_project_root`'s `$HOME` break in the upward walk → all state/DB/board/presence bind to the **global hub**, not the worktree's repo.
2. **Inline override is dead.** `COS_GIT_WORKFLOW=pr git …` does not work: branch-guard reads its own process env *before* the command's env-prefix. pr-mode is reachable only by exporting the var session-wide.
3. **Guard-kill, not policy.** `exit 0` allows everything — including `reset`/`rebase`/HEAD-rewrites on the shared integration checkout and pushes to protected branches.

The **consumer need** that justifies finishing the seam: a non-git-savvy consumer wants **5+ AI agents working one repo concurrently** without clobbering each other and without broken code reaching the integration branch. The mechanism that delivers this is well-understood — a per-task **git worktree** (separate `index.lock` → no commit contention, separate checkout → no file overwrite) feeding a **PR gated on required CI** (broken code cannot enter the always-green integration line). The agent does the git housekeeping autonomously because the consumer will not.

Two governance tensions block a naive "just turn it on":

- **The dogfood horn (P5 vs Rule 23).** P5 says coding-os dogfoods everything it ships. But coding-os's own git discipline is **trunk-based** (Rule 23): it is a single-developer repo whose `src/core/**` reaches every consumer through **live symlinks**, so linear, reviewable history *is* the safety property. Adopting pr-mode repo-wide *here* would fork the very discipline the meta-repo teaches and buy nothing (no concurrent external developers, no merge-conflict pressure to relieve).
- **Rule 21 looks like it bans worktrees.** Rule 21 forbids `isolation:"worktree"` on the **Agent/subagent tool**. Read literally it seems to forbid the pr-mode worktree too. It does not — it bans a *different* mechanism with a *different* failure mode.

## Decision

**Finish the seam as a consumer-only, default-OFF, reaper-backed workflow. coding-os itself stays trunk. The capability is produced here and dogfooded through a consumer fixture, never by switching the mother repo's own mode.**

1. **pr-mode is consumer opt-in, default OFF.** The engine (branch-guard policy, `cos pr` CLI, reaper, self-heal budget, Hub knobs) is built now but **inert** until a consumer sets `git_settings.enabled=true` in its *own* per-project `$COS_STATE_DIR/hub-settings.json`. coding-os's Rule 23 (trunk) is unchanged. With the toggle off there is zero behavioural or token-cost difference (the `model_routing` precedent).

2. **Rule 21 and the pr-mode worktree are distinct mechanisms — keep both.** They differ on every axis that matters:

   | Axis | Rule 21 — banned Agent-tool `isolation:"worktree"` | pr-mode worktree (this ADR) |
   |---|---|---|
   | Owner | an ephemeral **subagent** spawned mid-turn | the **main-loop** session itself |
   | Lifetime | dies with the subagent's single turn | spans one board task / adhoc unit |
   | Cleanup owner | the **dying parent** — which often never runs it → orphan | an **owner-independent reaper** keyed on `presence` offline |
   | Failure mode | orphaned worktrees nobody GCs (the reason for the ban) | reaped automatically; live session also cleans on merge |

   The reaper is exactly the missing piece that made Rule 21 necessary. pr-mode supplies it, so the ban on subagent worktrees stays in force *and* durable main-loop worktrees become safe. **The two rules do not conflict.**

3. **Dogfood through a consumer fixture, not the mother repo.** Per ADR-0012 (break the monoculture by running the loop on a real consumer), pr-mode is validated on a consumer fixture / lighthouse repo whose CI exercises the full isolate→PR→CI-green→merge→cleanup loop. No agent ever switches coding-os's own checkout to pr-mode.

4. **Degrade, never half-work.** pr-mode requires a remote + `gh` (authenticated) + a required CI check. A capability preflight runs before any worktree is created; if a prerequisite is missing, the agent falls back to trunk behaviour with a clear message rather than producing a branch+PR that can never merge. `gh` stays out of `src/core/**` (P2/P8 — symlinks reach all consumers); it lives in `src/cli` with the preflight + degrade path.

## Consequences

- **Positive:** the stubbed seam becomes a real, safe workflow; consumers get true concurrent-agent isolation with an always-green integration line; coding-os keeps its linear-history safety untouched.
- **Positive:** Rule 21's orphan failure mode finally has a concrete answer (the presence-keyed reaper) — reusable beyond pr-mode.
- **Negative / cost:** two git disciplines now coexist in the codebase (trunk for the mother, pr for consumers). That is more surface and more docs to keep coherent — the explicit coherence tax is paid by TASK-522.
- **Negative / risk:** pr-mode's correctness depends on remote + `gh` + required-CI being present and on auto-merge being trustworthy. Auto-merge therefore stays **OFF until proven stable** (enablement gated by TASK-513); GitHub Actions billing (macOS 10×, quota) is a real operating cost surfaced to the consumer.
- **Deferred:** only **two** branch roles ship now — `integration` + `protected`. A third `testing` role is deferred until three real call sites need it (Rule of Three).
- **Limitation — GitHub-only forge:** the push/PR/merge automation is 100% the GitHub `gh` CLI (`gh pr create` / `gh pr merge --auto` / `gh pr list`). A GitLab / Gitea / Forgejo / Bitbucket / self-hosted consumer therefore cannot use the push/PR rungs (`draft` / `auto_merge` / `autonomous`) at all — its only supported autonomy rung today is **`local`** (the agent commits in the worktree, never pushes, and a human integrates the `agents/*` branch). This is a runtime limitation, not a bug: the worktree isolation, branch-guard, reaper, and `local` rung are all forge-agnostic; only the publish path is GitHub-coupled. A future forge-adapter layer (a `gh`/`glab`/`tea` shim behind the `cos pr` publish step) is **deferred** until a non-GitHub consumer needs it (Rule of Three).
- **Limitation — Codex shared-tree edit-isolation gap:** the §5 edit wall (`block-shared-tree-edit.sh`, a Write/Edit BLOCK) fires only on a runtime that hooks Write/Edit — **Claude Code does, Codex (Bash-only hooks) does not** — so a Codex agent can edit the shared integration checkout directly. This is **partially mitigated**: `branch-guard.sh` runs on Bash for Codex, so a shared-tree `git commit` onto the integration line is still blocked. The edit lands in the working tree but cannot be committed onto the integration branch — defense narrows from "no edit" to "no commit," still keeping broken/unreviewed code off the integration line. Framed as a runtime-capability limitation (parity is bounded by `adapter.yaml::hook_capabilities`), not a bug.
- **Limitation — enforcement is agent-PreToolUse-only:** `branch-guard.sh` and `block-shared-tree-edit.sh` are PreToolUse hooks, so the branch/worktree/protected-push policy binds only the **agent** runtime (Claude Code; Codex on Bash). A **human**, `Codex.app`, or any plain `git` invocation is NOT constrained — `install-git-hooks.sh` wires only the content + `commit-msg` `.git/hooks`, with no branch/worktree/HEAD-rewrite guard. pr-mode's branch policy is therefore an agent-layer guarantee (surfaced as a static note in the Config→Git tab); a parallel git-level guard for human commits is **deferred** until a consumer needs it (Rule of Three). The `enabled` toggle is also guarded at the edge: enabling pr-mode requires a confirm step in the Hub and is **hard-blocked on the meta-repo slug** (`coding-os` stays trunk).
- **Limitation — settings durability is best-effort-local:** `git_settings` lives in the bound project's `<root>/.coding-os/hub-settings.json` (resolved per `/api/p/<slug>/` request, never the Hub process's global `COS_STATE_DIR`); the route writes it atomically (temp + `os.replace`) under a flock and refuses to overwrite a present-but-unparseable file. When `cos-env.sh` cannot parse a present `git_settings` (corrupt file / no jq+python3) it runs **trunk** and warns once on stderr rather than silently downgrading.

## Alternatives Considered

1. **Switch coding-os itself to pr-mode (full repo-wide dogfood).** Rejected: breaks Rule 23's linear-history safety for the `src/core/**` symlink blast radius, adds PR ceremony a single-developer repo gains nothing from, and forks the discipline taught to consumers. Dogfood is satisfied by the consumer fixture instead.
2. **Commit-lock / serialize to one agent at a time.** Rejected: defeats the 5+ concurrent-agent goal and reintroduces the custom write-lock anti-overengineering already rejects. Worktrees give lock-free isolation natively.
3. **Worktrees inside the repo (`.agent-worktrees/`).** Rejected: bundlers/watchers/test-runners scan the folder and see two copies of every file → haste-map collisions and infinite rebuilds; `.gitignore` does not save you (tools read disk, not git). The central per-repo root `~/.coding-os/worktrees/<slug>/` is the only layout isolated from tooling *and* organized per project.
4. **Relax Rule 21 to allow Agent-tool worktrees.** Rejected: Rule 21's failure mode (orphans owned by a dying subagent) is real. pr-mode answers it with a reaper rather than by lifting the ban; the ban stays.

## See also

- [docs/playbooks/pr-workflow.md](../../playbooks/pr-workflow.md) — the operational spec every downstream pr-mode code change traces to (Rule 0/19).
- [src/core/rules/git-workflow.md](../../../src/core/rules/git-workflow.md) — trunk discipline + the `COS_GIT_WORKFLOW` publish-mode seam this ADR completes.
- [ADR-0012](0012-lighthouse-consumer-breaks-the-dogfood-monoculture.md) — dogfood-through-a-real-consumer, the precedent for validating pr-mode on a fixture not the mother repo.
- [docs/governance/critical-rules.md](../../governance/critical-rules.md) — Rule 21 (Agent-tool worktree ban) and Rule 23 (trunk-based git) the ADR reconciles.
- Memory `multi-agent-pr-mode-refactor` — the confirmed traps and task backlog behind this decision.
