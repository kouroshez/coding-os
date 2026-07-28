---
id: TASK-635
title: "Enforcement hygiene: risk-register expiry lint, block-hook exit-2 lint, diff-size warn hook"
swimlane: core
kind: chore
epic: cognitive-kernel-hardening
labels: [governance, hooks, docs-lint, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-635: Enforcement hygiene: risk-register expiry lint, block-hook exit-2 lint, diff-size warn hook

**Outcome (one sentence):** Three small reuse-first guardrails that close real gaps: an enforced expiry+tracking discipline on the risk-register via docs-lint (so tolerated risk is re-triaged, not silently accumulated), a verify-hooks assertion that every block-* hook actually contains `exit 2` (so enforcement can't be accidentally disarmed), and a fail-open diff-size warn hook nudging diff-minimal commits.

## Work Log
- 2026-06-28 [claude]: Edit Makefile.base
- 2026-06-28 [claude]: Edit risk-register.md
- 2026-06-28 [claude]: Edit risk-register.md
- 2026-06-28 [claude]: Edit docs-lint.sh
- 2026-06-28 [claude]: Edit docs-lint.sh
- 2026-06-28 [claude]: Edit commit635a.txt
- 2026-06-28 [claude]: Edit warn-diff-size.sh
- 2026-06-28 [claude]: Edit registry.yaml
- 2026-06-28 [claude]: commit fc3f810c4f — chore(governance): risk-register expiry lint + block-hook exit-2 verify
- 2026-06-28 [claude]: Edit test_warn_diff_size.py
- 2026-06-28 [claude]: Edit commit635b.txt
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit adapter.yaml
- 2026-06-28 [claude]: Edit codex-pretool-dispatch.sh
- 2026-06-28 [claude]: Edit commit635c.txt
- 2026-06-28 [claude]: Shipped 3 guardrails. (1) docs-lint Check 5: each active RISK-NNN must carry review-by:YYYY-MM-DD + tracking:<ref>;…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
