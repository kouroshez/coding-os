---
id: TASK-345
title: "Hook chain latency budget: every Bash call pays 9 PreToolUse + 9 PostToolUse spawns (~p50 92ms each); verify-ish commands pay +1.2s"
swimlane: core
kind: refactor
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-345: Hook chain latency budget: every Bash call pays 9 PreToolUse + 9 PostToolUse spawns (~p50 92ms each); verify-ish commands pay +1.2s

**Outcome (one sentence):** Median wall-clock overhead per ordinary Bash tool call from coding-os hooks drops below 250ms total (measured via .hooks.log dt), by giving every Bash-matcher hook a first-line cheap fast-path (string match before any python3/jq spawn) and consolidating duplicate stdin parses — without changing any enforcement semantics.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/record-verify-auto.sh
- src/core/hooks/enforce-verify.sh
- src/core/hooks/test-governor.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a no-op Bash command (e.g. ls), **When** the full hook chain runs, **Then** summed dt across its Pre+Post hooks ≤ 250ms (today: ~9×40-90ms each side).
- **Given** verify-ish commands, **When** gated, **Then** record-verify-auto + enforce-verify + test-governor combined ≤ 600ms (today ~610+269+350ms).
- **Given** make verify-hooks + make test-hooks, **When** run, **Then** green.

## Work Log
