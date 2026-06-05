---
id: TASK-109
title: "Fix memory-load correctness — digest-on-compact, learn_suggest relevance, marker≠search, banner TTL staleness"
swimlane: core
kind: bug
epic: hook-remediation
labels: [memory, session, hooks, banner, audit-n5, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-109: Fix memory-load correctness — digest-on-compact, learn_suggest relevance, marker≠search, banner TTL staleness

**Outcome (one sentence):** Digest injected on startup too (not only compact/resume); learn_suggest uses complexity+task_type as ranking boosts; banner reflects the gate's 120-min TTL instead of showing an expired gate as valid; enforce-memory-check claim wording is honest; cos_search defaults to a sane min_confidence.

## Read First
- src/core/hooks/session-context.sh
- src/core/thinking_os/tools/learning.py
- src/core/hooks/enforce-memory-check.sh
- src/core/thinking_os/tools/memory.py

## Repro Steps
1. Fresh `SessionStart startup`: status message promises "Loading memory digest" but the digest block is gated `SOURCE == compact || resume` → a brand-new session inherits NO digest.
2. `cos_learn_suggest(domain=..., complexity=..., task_type=...)`: only `domain` reaches the SQL WHERE; `complexity`/`task_type` are accepted then ignored → recall is relevance-blind.
3. Long session (>120 min): banner `_read_state` returns the gate value with no TTL check → banner shows `gate=COMPLICATED 4` while the gate is actually expired and will BLOCK on the next edit.
Expected: digest on all three sources; complexity/task_type bias ranking; banner marks a stale gate.
Actual: digest compact/resume-only; params ignored; banner hides gate staleness.

## Acceptance (G/W/T)
- **Given** a fresh `SessionStart startup`, **When** session-context runs, **Then** the `[Agent Digest]` block is regenerated and emitted (digest no longer compact/resume-only).
- **Given** `learn_suggest(complexity=X, task_type=Y)`, **When** patterns are ranked, **Then** patterns whose concepts/pattern text match X or Y rank above equally-confident non-matches (boost, never exclude).
- **Given** a gate older than `COS_GATE_TTL_SECONDS` (default 7200s), **When** the banner renders, **Then** the gate field is flagged stale rather than shown as valid.
- **Given** enforce-memory-check, **When** it passes on the marker, **Then** the wording reflects that the marker is self-attested (authentic auto-stamp folded into N9).

## Work Log
- 2026-06-05 [claude]: 5a digest now injects on startup (not only compact/resume); 5b learn_suggest CASE-boosts complexity/task_type matches; 5
