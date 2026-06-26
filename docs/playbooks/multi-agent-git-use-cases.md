<!-- domain:META | layer:playbook | ssot:true | updated:2026-06-26 -->
# Playbook — Multi-Agent Git: Layered Defense & Real-World Use Cases

Purpose: One place that answers "is the git base safe for many agents on one repo, and which mode do I pick for *my* project?" It captures the **layered-defense model** (why client-side hooks are fast-feedback, not the wall), the **pre-publish GitHub setup**, and a **validated matrix of 10+ real-world project archetypes** with the recommended mode and the breakpoints each one hits.

Read when: deciding trunk-vs-pr for a consumer repo, publishing a repo that AI agents will work on, or reasoning about what actually stops a misaligned agent.
Read next: [pr-workflow.md](pr-workflow.md) · [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md) · [git-workflow.md](../../src/core/rules/git-workflow.md)

> Nav: [Docs Index](../00-index.md)

## 1. The layered-defense model (the load-bearing idea)

A client-side git hook is **fast feedback, never a security boundary** — any client hook can be bypassed (`--no-verify`, a `core.hooksPath` override, shell indirection, or simply a human / `Codex.app` / plain `git`). This is not a coding-os limitation; it is true of every client-side hook (git's own docs and the wider ecosystem say the same). So coding-os defends in layers, and the *authoritative* layer is the forge, not the agent:

| Layer | Mechanism | Bypassable? | What it buys |
|---|---|---|---|
| **L0 — Server wall** | GitHub **ruleset / branch protection** on the integration branch: require a PR, required status checks, block direct pushes, block force-push, (optional) required reviews + merge queue | **No** — enforced server-side regardless of any client trick | Broken / unreviewed / un-CI'd code **cannot** land on `main`. This is the real wall. |
| **L1 — Capability preflight** | `cos pr preflight` (remote + `gh` + required-check probe); emits an `unprotected_integration` warning when L0 is missing | n/a (advisory) | The operator *sees* whether the wall exists before trusting it. |
| **L2 — Agent guards** | PreToolUse hooks: `branch-guard` (+ indirection recovery), `block-dangerous-commands` (+ policy-file write guard), `block-secrets`, `enforce-commit-message` | Yes (client-side) | Fast feedback — the agent fails *early and locally* instead of after a rejected push; closes the obvious + many non-obvious bypass shapes. |
| **L3 — Isolation** | worktree-per-agent (separate checkout + `index.lock`), `gc.auto=0`, worktree lock, the owner-independent reaper | n/a | Concurrent agents never overwrite each other's working tree; a crashed agent's worktree is GC'd without losing work. |

**Consequence for the holes hardened in the `git-foundation-hardening` epic** (indirection bypass, policy-file write, `update-ref HEAD`): they all live in **L2**. On a repo with L0 set up, their blast radius is bounded — the server rejects the resulting push regardless. They bite *fully* only on a remote with **no** branch protection (which L1 now warns about). Hardening L2 is defense-in-depth + better agent ergonomics, **not** the thing standing between an agent and `main`.

## 2. Choosing a mode (the one decision a consumer makes)

| Repo reality | Mode | Why |
|---|---|---|
| Local-only (no remote), solo / beginner | **trunk** (default) | Zero-config; a worktree + manual merge is pure overhead when there is no forge and one author. Multi-agent still works (commits serialize on `main`). |
| Remote, but **no** branch protection | **trunk**, or **pr `draft`** + set up L0 | Without L0 the client guard is the only barrier (L1 warns). Prefer adding the ruleset, then pr. |
| Protected remote (require-PR + required checks) + multi-agent | **pr** (`draft` → `auto_merge` once trusted) | Worktree isolation + branch→PR→CI→merge. The only correct path when L0 blocks direct pushes. |
| Protected remote but **no CI / GitHub-only-forge gap** | **pr `local`** rung | Agent commits in a worktree; a **human** integrates (`git merge --no-ff`) — the agent is branch-guard-blocked from merging the shared checkout, by design. |
| coding-os itself | **trunk** (permanent) | The mother repo dogfoods pr-mode only through a consumer fixture (ADR-0013); enabling pr is hard-blocked on the `coding-os` slug. |

There is intentionally **no auto-detector** that flips trunk↔pr per capability (the `auto` mode was evaluated and **deferred** under Rule-of-Three — L1's warning already gives the legibility; revisit if the manual-toggle footgun recurs).

## 3. Pre-publish GitHub setup (do this BEFORE agents touch a published repo)

This is L0 — the only non-bypassable layer. Treat the agent as an **untrusted contractor** (least privilege + mandatory review), the 2025-2026 consensus for autonomous PRs:

- **Ruleset → integration branch (`main`):** require a pull request · required status checks = your CI job · block direct pushes · block force-pushes · (optional) enable the **merge queue** · CI must also trigger on `merge_group`.
- **Ruleset → protected branch (`production`):** restrict updates to owners (agents NOT on the bypass list) · block force-push · block deletion.
- **Agent token (least privilege):** `Contents: read/write` · `Pull requests: read/write` · `Metadata: read`. **No** bypass of the integration/protected rulesets.
- **CODEOWNERS** for sensitive paths (note the known auto-merge interaction — §5, TASK-592).
- **Auto-merge** + **auto-delete head branches** enabled (so `gh pr merge --auto` and cleanup work).

## 4. Validated use-case matrix (10+ real-world archetypes)

Each row is an end-to-end multi-agent run with the epic's L2 hardening applied. "Breakpoints" are real gaps surfaced by adversarial validation; each links its follow-up task.

| # | Archetype | Profile | Mode | Verdict & breakpoints |
|---|---|---|---|---|
| 1 | **Mobile (RN / Flutter)** | 4 devs, GitHub + EAS/Fastlane CI, protected `main`, 3 parallel agents, large iOS/Android binaries | pr `draft`→`auto_merge` | Sound. **Breakpoint:** worktree has no `node_modules`/`Pods`/`.env` → first `npm run validate` fails (→ TASK-593). Large binaries inflate each worktree (disk). |
| 2 | **Web SaaS (Next monorepo)** | 8 devs, Vercel + required CI + CODEOWNERS, 5 parallel agents, frequent same-file edits | pr `auto_merge` | Sound. Same-file edits handled by `cos pr conflicts` (advisory) + rebase-at-submit + merge queue. **Breakpoint:** worktree bootstrap (TASK-593); CODEOWNERS auto-merge deadlock (TASK-592). |
| 3 | **Infra (Terraform / k8s)** | platform team, required `plan`+OPA, protected `main`+`production`, agents must never touch prod | pr `draft` | Sound — `protected_branches=['production']` + integration=`main` holds; the agent token has no prod access (L0). **Breakpoint:** required-check identity (only `plan` required ≠ OPA) — echo check names (TASK-586 follow-up). |
| 4 | **OSS w/ external contributors** | maintainers + drive-by + agents, fork-based PRs, required reviews, CODEOWNERS | pr `draft` (maintainer-agent) | Works for maintainer agents on same-repo `agents/*`. **Breakpoint:** fork-based contributor PRs are unmodeled (`origin`=canonical assumed); required-reviews>0 → auto-merge deadlock (TASK-592). External-fork flow: documented out-of-scope for now. |
| 5 | **Solo beginner (local-only)** | 1 person, `git init`, no GitHub yet, 1-2 agents | **trunk** | The 99% start. Correct and friction-free. On the day they `git remote add` + add a ruleset, they flip to pr — smooth (worktrees + PR become available; L1 confirms readiness). |
| 6 | **Regulated / finance** | required reviews from teams, signed commits, merge queue, separation-of-duties | pr `draft` | Sound — `draft` already enforces separation-of-duties (agent authors, human merges); audit trail = git history + board. **Breakpoint:** required-reviews deadlock if `auto_merge` (TASK-592); signed-commits ruleset vs agent commits → documented limitation. |
| 7 | **Data / ML pipeline** | notebooks + DVC/large data, expensive training as a required check | pr `draft` (or `local` if no CI gate wanted) | Sound. **Breakpoint:** worktree bootstrap for large gitignored datasets (TASK-593); expensive required-check × auto-merge = cost — keep `draft` + human gate, or a cheap required check. |
| 8 | **Microservices polyrepo** | 30 repos, each own ruleset, agents hop repos | pr per-repo | Sound — per-repo `<root>/.coding-os/hub-settings.json` + per-repo worktree slug + `COS_PROJECT_ROOT` keep state correct across repos on one machine; misroute is now banner-surfaced (TASK-585b). |
| 9 | **Game / Unity (LFS)** | huge repo, Git-LFS binaries, non-mergeable scene files, Windows devs | pr `draft` (or `local`) | Worktrees share the LFS object store (fetched into the worktree). **Breakpoint:** non-mergeable binary conflicts are advisory-only (`cos pr conflicts`); Windows = §11. |
| 10 | **Enterprise monorepo** | 500 devs, mandatory merge queue, thousands of checks, 20+ agents | pr `auto_merge` | Mostly sound. **Breakpoint:** `COS_PR_MAX_OPEN=5`/session is a per-session cap (fine); 20 worktrees of a huge monorepo = disk pressure; merge-queue (`merge_group`) arming nuance (`_rollup_state` lacks a QUEUED branch) — follow-up. |
| 11 | **Windows dev box** | native Windows, no bash hooks, no `pgrep` | trunk (agent guards limited) | Degrades sanely: `pr_commands.py` guards `fcntl` import (reaper lock no-ops); but Bash PreToolUse hooks don't fire natively → L2 is thin on Windows. Rely on L0 (server wall). Documented limitation. |

## 5. Known breakpoints → tracked follow-ups (not yet fixed)

| Breakpoint | Severity | Task |
|---|---|---|
| Worktree dependency/secret bootstrap (no `node_modules`/`.env` → validate fails) | critical | [TASK-593](../tasks/TASK-593-worktree-dependency-secret-bootstrap-cos-pr-open-creates-a-f.md) |
| CODEOWNERS / required-reviews auto-merge deadlock | high | [TASK-592](../tasks/TASK-592-pr-mode-auto-merge-deadlock-on-codeowners-required-reviews-h.md) |
| test-governor lock redesign (PostToolUse-release) | medium | [TASK-590](../tasks/TASK-590-redesign-test-governor-concurrency-lock-host-global-pgrep-f-.md) |
| Reaper liveness (skip live-but-idle via lock-reason pid) | medium | [TASK-591](../tasks/TASK-591-reaper-liveness-skip-age-reaping-a-live-but-idle-agent-via-t.md) |
| Merge-queue arming + `_rollup_state` QUEUED branch · non-required checks inflating heal · fork PRs · LFS/signed-commits/Windows | low–medium | documented limitations (Rule-of-Three: file when a consumer hits them) |

## See also

- [pr-workflow.md](pr-workflow.md) — the operational pr-mode contract (the L2/L3 detail).
- [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md) — why consumer-only.
- [src/core/rules/git-workflow.md](../../src/core/rules/git-workflow.md) — trunk discipline + the mode table.
