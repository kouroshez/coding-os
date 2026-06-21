---
id: TASK-508
title: "Golden fixtures stale: codex role-* commands + hooks absent \u2192 test_golden_parity RED on main"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-508: Golden fixtures stale: codex role-* commands + hooks absent → test_golden_parity RED on main

**Outcome (one sentence):** test_golden_parity passes again by recapturing the 8 stack goldens so they reflect the codex adapter's role-* commands + hooks that were added after the last capture, with no unintended content drift.

## Read First
- tests/test_golden_parity.py
- tests/golden/claude_base/.codex/commands/
- src/adapters/codex/adapter.yaml
- docs/engineering/modularity-audit-2026-06.md

## Repro Steps
Run `COS_TEST_FORCE=1 uv run pytest tests/test_golden_parity.py -q`. Expected: pass. Actual: 6 failed (claude_base/django/nextjs, codex_base/django/nextjs) — the rendered output carries .codex/commands/role-*.md and .codex/hooks/*.sh that the goldens (captured before the role commands shipped) lack; the assertion `assert not [extra files]` at test_golden_parity.py:151 trips. Pre-existing on main, independent of the pass-6 doc-gating change.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the meta-repo at HEAD **When** `uv run pytest tests/test_golden_parity.py -q` runs **Then** all fixtures pass; the recaptured tests/golden/<adapter>_<stack>/ trees contain the codex role-* commands + hooks, and a diff of the recapture shows ONLY those additive role/hook files (no surprise content drift in unrelated docs).

## Work Log
