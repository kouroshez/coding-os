---
name: pr-mode-driver
tier: workflow
domain: [infra]
description: Drive the pr-mode autonomous git loop for a consumer repo (COS_GIT_WORKFLOW=pr). Use after `cos pr submit` to poll CI and act on the result. Triggers — "drive the PR", "CI is red", "is the PR merged", "retry the failing check", "pr-mode loop", any turn waiting on an agent PR's CI.
phase: L
last_reviewed: "2026-06-24"

---

# pr-mode Driver Skill

You are driving the **pr-mode autonomous loop** for a consumer repo (`COS_GIT_WORKFLOW=pr`). One agent owns one task → one `agents/*` branch → one worktree → one PR. After `cos pr submit`, your job is to poll CI and act — never merge by hand, never spin in-process.

> Skip entirely in trunk mode (coding-os itself, and any default repo — pr-mode is consumer-only, default OFF). Full spec: [pr-workflow.md](../../../docs/playbooks/pr-workflow.md) §§ 4–10.

## The one signal

```bash
cos pr status --branch "$BRANCH" --json    # → {"ci_rollup": "merged|red|queued|pending|passing|passing-unarmed|closed|none"}
```

`ci_rollup` collapses `gh`'s `statusCheckRollup` + PR state + whether auto-merge is actually armed into one value. Branch on it — nothing else; the STOP decision needs no memory of the prior `cos pr submit`.

## The loop — ONE pass per turn (never busy-wait)

| `ci_rollup` | Action |
|---|---|
| `merged` | `cos pr cleanup --task "$TASK"` — removes the worktree + branch. **Done.** |
| `red` | Heal (below). |
| `passing` | Green AND auto-merge is armed — it will land itself. Re-poll next turn; do nothing else. |
| `passing-unarmed` | Green but nothing will auto-land it (autonomy=draft, no required check, or a draft PR). **STOP** — needs a human merge (below). |
| `pending` | Checks still running. Re-poll next turn. |
| `queued` | In the GitHub merge queue — the queue will land it (or eject it) on its own. Re-poll next turn; do **not** re-submit or re-arm. An ejected PR surfaces as `red` (only that PR is healed; followers keep merging). |
| `none` | No PR yet → `cos pr submit` (or `cos pr open` if there's no worktree). |
| `closed` | Closed unmerged (human/abandoned). Stop and surface to the user; do not auto-reopen. |

**`passing-unarmed` → STOP, don't spin.** The signal itself says nothing will land this PR on its own — you do NOT need to recall the prior `cos pr submit`, so this holds across `/clear`, `/compact`, and a reaper-recovered fresh session. Do NOT re-poll — at autonomy=draft that would loop forever. Stop and tell the user: *"PR #N is green and needs a human merge (auto-merge isn't armed — autonomy=draft, or no required status check on the integration branch) — merge it, or set autonomy_level=auto_merge with a required check in Hub Config→Git."*

`passing` / `pending` / `queued` mean **yield the turn and check again later**, not sleep-loop. Hooks and the turn loop drive this, not a daemon (Rule 21).

## Heal — the red branch

```bash
cos pr heal --task "$TASK"     # charges the self-heal budget; escalates to `blocked` when spent
```

1. Run `cos pr heal`. If it reports the budget is **spent / escalated**, STOP — the task is now `blocked` with the failure recorded; do not retry.
2. Diagnose: read the failing check (`gh pr checks "$BRANCH"`, `gh run view <id> --log-failed`) and reproduce with the repo's own validate command **inside the worktree**.
3. Fix in the worktree, then re-publish with `cos pr submit` (it rebases onto the integration head, lease-pushes, and CI re-runs).
4. Next turn: poll `cos pr status --branch` again.

A check that **cannot** run (quota exhausted, no runner — see `cos pr preflight`) is not a red to heal forever: surface it and stop.

## Invariants (never violate)

- Never `gh pr merge` by hand or push to the integration/protected branch — branch-guard blocks it; auto-merge lands a green PR itself.
- Never `cos pr cleanup` a non-merged branch without `--force` — it refuses, to protect unmerged work (TASK-530).
- Never loop in-process waiting on CI — one status check per turn.
- While your session is alive you own cleanup; the reaper only GCs a worktree whose owner has died.

## See also

- [pr-workflow.md](../../../docs/playbooks/pr-workflow.md) — the full loop, branch-guard policy, reaper, self-heal budget.
- `cos pr preflight` — capability gate (remote · gh · required check) before relying on auto-merge.
