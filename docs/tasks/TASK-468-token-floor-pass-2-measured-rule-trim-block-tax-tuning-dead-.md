---
id: TASK-468
title: "Token-floor pass 2: measured rule-trim + block-tax tuning + dead-hook prune (C2-C5)"
swimlane: infra
kind: refactor
epic: audit-remediation-2026-06
labels: [audit-remediation, token-economics, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-468: Token-floor pass 2: measured rule-trim + block-tax tuning + dead-hook prune (C2-C5)

**Outcome (one sentence):** The risky remainder of the token-economics audit after C1 (TASK-466) shipped the big mechanical win: C2 measured per-rule trim of the ~13K always-active rule floor (NOT mechanical — each rule is load-bearing; trim only proven-redundant prose, keep enforcement contracts); C3 retune block-tax (enforce-verify blocked twice in this very session even after docs-lint ran — investigate the ledger dedup/tree-invalidation friction, not just the count); C4 prune provably-dead hooks (needs a longer hook-firing telemetry window than the rolling .hooks.log to avoid removing rare-fire safety hooks like block-migration-conflict); C5 collapse session-state gate hooks where redundant. Each sub-item is measured (before/after token or block-rate) and verified (verify-hooks + golden + adapter parity), never a blind trim of a guardrail.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/enforce-verify.sh
- src/core/rules/transparency-banner.md
- docs/engineering/modularity-audit-2026-06.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the always-active rule floor, **When** a rule is trimmed, **Then** the diff removes only redundant prose (no enforcement contract / remediation text lost), token delta is measured, and verify-hooks + test_golden_parity + test_adapter_parity stay green.
**Given** the enforce-verify/test-governor block friction, **When** retuned, **Then** a documented repro shows the false/duplicate block and the fix keeps the guardrail's true-positive behavior (a real unverified close still BLOCKs).
**Given** a hook proposed for removal, **When** assessed, **Then** telemetry over a sufficient window (not the rolling log) confirms zero legitimate fires AND its registry entry + adapter render are cleaned with golden regen.

## Work Log
