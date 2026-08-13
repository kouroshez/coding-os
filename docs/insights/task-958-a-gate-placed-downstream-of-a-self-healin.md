<!-- domain:INFRA | layer:reference | ssot:false | source:outcome_history#1037 | updated:2026-08-13 -->
# TASK-958: A gate placed downstream of a self-healing command tests the repair, not the tree — before trusting any check, run it against a deliberately broken input and confirm it goes red (same class as a matrix row exiting "no tests ran"). Corollary: release-please's toml updater no-ops silently when its jsonpath stops matching, so a config-driven bump needs an independent gate or it rots invisibly.

**Date:** 2026-08-13  
**Domain:** INFRA  
**Source task:** [TASK-958](../tasks/TASK-958-keep-uv-lock-in-sync-on-release-and-gate-the-drift-in-ci.md)

## Key Insight

A gate placed downstream of a self-healing command tests the repair, not the tree — before trusting any check, run it against a deliberately broken input and confirm it goes red (same class as a matrix row exiting "no tests ran"). Corollary: release-please's toml updater no-ops silently when its jsonpath stops matching, so a config-driven bump needs an independent gate or it rots invisibly.

## What Failed

Placing `uv lock --check` after the job's `uv sync` step, next to the other lint checks. Proven by experiment to be a no-op gate: a bare `uv sync` rewrites a stale lockfile and exits 0 silently, so the check then inspects a file the runner just repaired and passes on a genuinely divergent tree.

## What Worked

`uv lock --check` as the first step after uv setup, above every `uv sync`, plus a release-please `extra-files` toml updater ($.package[?(@.name.value=='NAME')].version) so the release PR bumps the lock in the same commit as pyproject.toml. Verified the updater output is byte-identical to `uv lock`, and the release PR cleared the new gate.

## Links

- Pattern: `learned_patterns#367` — retrievable via `cos_details`
- History: `outcome_history#1037`
