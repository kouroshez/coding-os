---
id: TASK-807
title: "Guard suite red: hardcoded claude-opus-4-8 in tools/routing.py fails test_no_hardcoded_anthropic (2 cases)"
swimlane: core
kind: bug
epic: null
labels: [ci, rule-11, ready]
status: archive
priority: P2
appetite: 2h
created: 2026-07-10
started: 2026-07-09
completed: 2026-07-09
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-807: Guard suite red: hardcoded claude-opus-4-8 in tools/routing.py fails test_no_hardcoded_anthropic (2 cases)

**Outcome (one sentence):** tests/test_no_hardcoded_anthropic.py passes fully: the inline 'claude-opus-4-8' literal in src/core/thinking_os/tools/routing.py (and its echo in tests/test_routing.py) is replaced by a data-driven source (DispatchRequest.model / role frontmatter / adapter.yaml) or, if the compatibility gate is genuinely intentional, the path is added to ALLOWED_MODEL_PATHS with a documented reason.

## Read First
- (no doc yet — exploratory)

## Repro Steps
Run: uv run pytest tests/test_no_hardcoded_anthropic.py -q → 2 failed (tools/routing.py, tests/test_routing.py), message: hardcoded model id 'claude-opus-4-8'. Introduced before 2026-07-09 (present at commit 76ea6f63).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** tests/test_no_hardcoded_anthropic.py, **When** run on a clean tree, **Then** all cases pass with no new ALLOWED_MODEL_PATHS entry lacking a documented reason.
- **Given** cos_route_model with no history, **When** cold-start defaults resolve, **Then** the default model comes from adapter.yaml, not an inline literal.

## Work Log
- 2026-07-10 [claude]: Edit routing.py
- 2026-07-10 [claude]: Edit test_routing.py
- 2026-07-10 [claude]: Edit no-parking-actionable-findings.md
- 2026-07-10 [claude]: commit 0ba07f272e — fix(core): drop hardcoded claude-opus-4-8 literals that broke the anthropic guard suite
- 2026-07-10 [claude]: Status transitioned to complete via cos task-done.
