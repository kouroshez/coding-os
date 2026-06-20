---
id: TASK-460
title: "Dedup record-verify hooks + relocate test harnesses out of src/core/hooks"
swimlane: infra
kind: refactor
epic: audit-remediation-2026-06
labels: [audit-remediation, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-460: Dedup record-verify hooks + relocate test harnesses out of src/core/hooks

**Outcome (one sentence):** src/core/hooks/ contains only runtime hooks. record-verify.sh (manual 2-arg CLI, referenced by 2 hooks) is merged into / superseded by record-verify-auto.sh; test-hooks.sh + verify-agent-system.sh move under tests/ or src/scripts/. NOTE: record-verify.sh and verify-agent-system.sh are adapter-RENDERED (appear in tests/golden/*/.claude/hooks + .codex/hooks), so this is NOT a plain delete — it requires adapter template edits + golden regen + adapter-parity test, not cheap cleanup. From strategic-audit group A (A3), descoped from TASK-459.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/record-verify.sh
- src/core/hooks/record-verify-auto.sh
- src/adapters/claude/adapter.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
Given src/core/hooks/, When listed, Then no record-verify.sh/test-hooks.sh/verify-agent-system.sh remain (or record-verify.sh is justified + documented as distinct from -auto).
Given the adapter render, When regenerated, Then golden fixtures updated (make regen-adapter-templates / golden-capture) and tests/test_adapters.py + test_adapter_parity.py pass.
Given make verify-hooks, Then green.

## Work Log
