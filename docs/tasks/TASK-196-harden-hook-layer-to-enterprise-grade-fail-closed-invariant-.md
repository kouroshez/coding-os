---
id: TASK-196
title: "Harden hook layer to enterprise-grade \u2014 fail-closed invariant + hook latency/fan-out budget + display signal-to-noise"
swimlane: core
kind: feature
epic: observability-eye
labels: [hooks, observability, enterprise, fail-closed, audit-exhaustive, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-196: Harden hook layer to enterprise-grade — fail-closed invariant + hook latency/fan-out budget + display signal-to-noise

**Outcome (one sentence):** Every enforcement/safety hook fails CLOSED on helper crash / missing critical dep, guarded by a regression test; cos_log_hook captures per-invocation duration so the hook layer has a real latency SLI; a CI guard caps PreToolUse fan-out width to prevent death-by-a-thousand-hooks; the hook activity panel defaults to decision-states. All changes verified green via the hook + thinking_os matrix commands.

## Read First
- docs/engineering/observability-eye.md
- src/core/hooks/registry.yaml
- src/core/hooks/cos-env.sh
- src/core/hooks/branch-guard.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** no JSON parser (jq + python3) is on PATH and a dangerous payload (`git push --force main`, `git add .env`, `rm -rf /`)
- **When** the matching PreToolUse Bash gate fires
- **Then** the gate exits 2 (BLOCK) and captures the reason via cos_say — never exits 0 (allow). Proven by `tests/test_hooks_fail_closed.py`.
- **Given** a hook runs to any `cos_log_hook` emit point
- **When** the line is written to `.hooks.log`
- **Then** it carries a `dt=<ms>` field measuring wall-time since hook entry (sub-second), and `tests/test_hook_fanout_budget.py` asserts PreToolUse Bash fan-out ≤ 12.
- **Given** the user runs `cos hooks-log`
- **When** no `--all`/`--verbose` flag is passed
- **Then** only decision-states (fire/block/warn/paths/reminded/full/debounced/skip) are shown; lifecycle rows (enter/ok) are hidden behind `--all`.

Audit artifact: docs/tasks/audits/audit-hook-fail-closed-hardening.md

## Work Log
- 2026-06-06 [claude]: Hardened 9 PreToolUse gates to fail-closed (cos_require_parser+cos_json_field; helper-missing→exit2), added dt= latency 
