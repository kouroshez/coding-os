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
cos pr status --branch "$BRANCH" --json    # → {"ci_rollup": "merged|red|pending|passing|closed|none"}
```

`ci_rollup` collapses `gh`'s `statusCheckRollup` + PR state into one value. Branch on it — nothing else.

## The loop — ONE pass per turn (never busy-wait)

| `ci_rollup` | Action |
|---|---|
| `merged` | `cos pr cleanup --task "$TASK"` — removes the worktree + branch. **Done.** |
| `red` | Heal (below). |
| `passing` + auto-merge armed | Green; auto-merge will land it. Re-poll next turn — do nothing else. |
| `passing` + **not** armed (draft / degraded-no-required-check) | **STOP** — needs a human merge (below). |
| `pending` | Checks still running. Re-poll next turn. |
| `none` | No PR yet → `cos pr submit` (or `cos pr open` if there's no worktree). |
| `closed` | Closed unmerged (human/abandoned). Stop and surface to the user; do not auto-reopen. |

**Green but no auto-merge → STOP, don't spin.** When `ci_rollup=passing` AND the last `cos pr submit` reported `merge_status` in {`draft`, `degraded-no-required-check`} (i.e. `auto_merge_armed=false`), nothing will land the PR on its own. Do NOT re-poll — at autonomy=draft that loops forever. Stop and tell the user: *"PR #N is green and needs a human merge (autonomy=draft) — merge it, or set autonomy_level=auto_merge in Hub Config→Git."*

`passing` / `pending` mean **yield the turn and check again later**, not sleep-loop. Hooks and the turn loop drive this, not a daemon (Rule 21).

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
