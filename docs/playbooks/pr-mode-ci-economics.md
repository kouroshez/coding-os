<!-- domain:META | layer:playbook | ssot:true | updated:2026-06-27 -->
# Playbook — PR-Mode CI Economics (consumer cost guidance + reference workflow)

Purpose: pr-mode `autonomy_level=auto_merge`/`autonomous` + a GitHub merge queue multiplies CI runs (each PR runs CI, then each `merge_group` runs it again), so on a free **private** repo with a slow suite the 2000-min/mo Actions budget burns fast. This playbook gives the cost model, the fast-gate / full-suite split that keeps the autonomous loop affordable, and a copy-paste consumer CI workflow.
Read when: Enabling pr-mode auto-merge on a consumer repo, or a consumer's Actions minutes are running out.
Skip when: Working in coding-os itself (trunk, nightly-only CI — see [github-actions-cost note]) or any repo not on the autonomous loop.

> Nav: [Docs Index](../00-index.md) · pairs with [pr-workflow.md](pr-workflow.md) §11 (one-time setup) and §12 (live validation).

## 1. The cost model (know these before arming auto-merge)

- **Runner OS multiplier** (billed minutes = wall-minutes × multiplier): **Linux ×1**, **Windows ×2**, **macOS ×10**. Keep the required check Linux-only — a macOS leg on every PR + every merge-group is the fastest way to exhaust the budget.
- **Free Actions minutes:** private repo Free plan **2000 min/mo** (Pro 3000); **public repo = UNLIMITED**; **self-hosted runner = UNLIMITED** (self-hosted minutes are never billed against the quota).
- **Merge-queue multiplication:** with a merge queue, a single change can trigger CI on the PR *and* on one or more `merge_group` batches. Budget for ~2× the naive per-PR cost, more under heavy concurrency.
- **Quota-exhausted failure mode:** once minutes run out, workflows simply don't start — `cos pr status` reads `pending` forever and `cos pr preflight` should surface "no runner / quota". An autonomous loop then stalls silently; the fast-gate split below is what keeps you under the cap.

## 2. The fast-gate / full-suite split (the core economy)

Make the **required check fast** — only it gates merge, so only it runs on every PR + merge_group:

- **Fast required check** (gates merge, runs per-PR + per-merge_group): lint + **targeted tests** only. "Targeted tests" = the unit/contract layer that runs in a few minutes — explicitly NOT the slow/integration/e2e suite. This is the single status check the integration-branch ruleset requires.
- **Full suite** (does NOT gate merge): run on a **nightly `schedule` cron** (and optionally manual `workflow_dispatch`). Catches the slow/integration regressions off the hot path, on one run per day instead of one per PR.

A red nightly opens a normal issue/PR to heal; it never blocks the autonomous merge loop.

## 3. Reference consumer CI workflow (copy to `.github/workflows/ci.yml`)

Linux-only, fast required check on `pull_request` + `merge_group`, full suite on a nightly cron. Replace the `run:` lines with the repo's own commands (the repo's validate command is the SSOT — pr-workflow.md §4 step 2). This is a **reference**, not an auto-scaffolded file: pr-mode is opt-in, so the consumer copies and adapts it.

```yaml
name: ci
on:
  pull_request:
    branches: [main]
  merge_group:            # required so the merge queue's batched check reports status
  schedule:
    - cron: "0 4 * * *"   # nightly full suite (UTC) — does NOT gate merge
  workflow_dispatch:

jobs:
  # FAST required check — the ONLY job the integration ruleset requires.
  # Keep it lint + targeted tests so every PR + merge_group stays cheap.
  fast-check:
    if: github.event_name != 'schedule'
    runs-on: ubuntu-latest        # Linux ×1 — never macOS (×10) on the hot path
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - run: make lint             # replace with the repo's lint
      - run: make test-targeted    # replace with the repo's fast/unit suite

  # FULL suite — nightly only, never gates merge.
  full-suite:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - run: make test             # the slow/integration/e2e suite
```

Then in the integration-branch ruleset (pr-workflow.md §11) require **only** the `fast-check` job as the status check, and enable the merge queue. The nightly `full-suite` is intentionally **not** a required check.

## 4. Decision guidance (the consumer's call — EXTERNAL)

| Situation | Recommended runner / plan |
|---|---|
| Open-source / public repo | Public repo → Actions **unlimited**; use GitHub-hosted Linux freely. |
| Private repo, light suite | Free 2000 min/mo is plenty with the fast-gate split; Linux-only. |
| Private repo, heavy suite / many agents | **Self-hosted Linux runner** (unlimited) — the only way the autonomous loop scales without a minute cap. |
| Any | Never put macOS (×10) or Windows (×2) on the required check; reserve them for nightly/matrix if truly needed. |

The actual billing tier and runner choice is the consumer's decision — this playbook only documents the economics so that choice is informed.

## See also

- [pr-workflow.md](pr-workflow.md) — the pr-mode contract (§11 ruleset setup, §12 live validation).
- [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md) — why pr-mode is consumer-only.
