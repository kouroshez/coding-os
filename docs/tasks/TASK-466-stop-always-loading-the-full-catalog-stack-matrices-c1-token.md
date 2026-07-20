---
id: TASK-466
title: "Stop always-loading the full-catalog stack matrices (C1 token floor)"
swimlane: infra
kind: refactor
epic: audit-remediation-2026-06
labels: [audit-remediation, token-economics, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-466: Stop always-loading the full-catalog stack matrices (C1 token floor)

**Outcome (one sentence):** install-adapter.sh no longer symlinks the two DERIVED full-stack-catalog matrices (dimension-registry.md, skill-enforcement.md) into a project's always-active rules dir — they were ~4.5K tokens/session of stacks a project does not use. The agent already gets the per-consumer, installed-stack-only view via SessionStart's skill_primer card, and enforce-skill.sh carries its enforcement inline (never reads the .md), so nothing is lost; the files remain on-demand reference at src/core/rules/.

## Read First
- src/core/scripts/install-adapter.sh
- src/core/hooks/_helpers/skill_primer.py
- src/core/hooks/enforce-skill.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project installed/updated via install-adapter.sh, **When** the rules dir is populated, **Then** dimension-registry.md and skill-enforcement.md are NOT symlinked there (the other core rules still are).
**Given** the SessionStart card + enforce-skill.sh, **When** an agent classifies/edits, **Then** it still sees the installed-stack dimensions + per-glob enforcement and the BLOCK still fires (no behavioral loss).
**Given** make verify-hooks + test_adapters + test_adapter_parity + test_golden_parity + test_template_scaffold, **When** run after golden regen, **Then** all green.

## Work Log
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-20 [claude]: install-adapter.sh step 5 excludes dimension-registry.md + skill-enforcement.md; removed meta-repo .claude/.codex…
