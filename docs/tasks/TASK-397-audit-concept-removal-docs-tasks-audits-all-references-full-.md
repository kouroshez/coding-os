---
id: TASK-397
title: "Audit-concept removal (docs/tasks/audits + all references) + full task-system analysis (board_os, DB, UI, hooks, docs)"
swimlane: "board_os"
kind: docs
epic: null
labels: [docs-update, governance, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-397: Audit-concept removal (docs/tasks/audits + all references) + full task-system analysis (board_os, DB, UI, hooks, docs)

**Outcome (one sentence):** docs/tasks/audits folder deleted with every link/mention to its files removed across docs/; a comprehensive findings report of the task system (board_os core, SQLite tasks table vs docs/tasks frontmatter duplication, web UI board routes/components, task hooks, playbooks, agent instructions) listing bugs, duplications, and wrong logic with concrete follow-up recommendations.

## Read First
- docs/governance/task-lifecycle.md
- src/core/board_os/
- src/core/thinking_os/database.py
- src/core/web/routes/
- src/core/hooks/registry.yaml

## Work Log
- 2026-06-11 [claude]: Edit audit_sweep.py
- 2026-06-11 [claude]: Edit graph-os-deep-audit-findings-2026-05-25.md
- 2026-06-11 [claude]: Edit graph-os-deep-audit-findings-2026-05-25.md
- 2026-06-11 [claude]: Edit graph-os-deep-audit-findings-2026-05-25.md
- 2026-06-11 [claude]: Edit graph-os-round3-audit-findings-2026-05-26.md
- 2026-06-11 [claude]: Edit graph-os-round3-audit-findings-2026-05-26.md
- 2026-06-11 [claude]: Edit graph-os-round4-audit-findings-2026-05-27.md
- 2026-06-11 [claude]: Edit graph-os-round4-audit-findings-2026-05-27.md
- 2026-06-11 [claude]: Edit graph-os-round4-audit-findings-2026-05-27.md
- 2026-06-11 [claude]: Edit historical-task-ids.md
- 2026-06-11 [claude]: Edit critical-rules.md
- 2026-06-11 [claude]: Edit critical-rules.md
- 2026-06-11 [claude]: Edit critical-rules.md
- 2026-06-11 [claude]: Edit critical-rules.md
- 2026-06-11 [claude]: Edit critical-rules.md
- 2026-06-11 [claude]: Edit critical-rules.md
- 2026-06-11 [claude]: Edit transparency-banner.md
- 2026-06-11 [claude]: Edit transparency-banner.md
- 2026-06-11 [claude]: Edit transparency-banner.md
- 2026-06-11 [claude]: Edit transparency-banner.md
- 2026-06-11 [claude]: Edit transparency-banner.md
- 2026-06-11 [claude]: Edit TASK-199-fix-hub-audits-page-crash-coerce-list-typed-audit-fields-to-.md
- 2026-06-11 [claude]: Edit agent-workflow-flowchart.html
- 2026-06-11 [claude]: Edit AGENTS.md
- 2026-06-11 [claude]: Edit enforce-task-transition.sh
- 2026-06-11 [claude]: Edit enforce-task-transition.sh
- 2026-06-11 [claude]: Edit enforce-wip-limit.sh
- 2026-06-11 [claude]: Edit validate-task-frontmatter.sh
- 2026-06-11 [claude]: Edit detect_status_transition.py
- 2026-06-11 [claude]: Edit detect_status_transition.py
- 2026-06-11 [claude]: Edit _rules_primer_card.txt
- 2026-06-11 [claude]: Edit registry.yaml
- 2026-06-11 [claude]: Edit registry.yaml
- 2026-06-11 [claude]: Edit registry.yaml
- 2026-06-11 [claude]: Edit reviewer.md
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit test_reindex_dispatch.py
- 2026-06-11 [claude]: Edit test_reindex_dispatch.py
- 2026-06-11 [claude]: Edit mcp_tools.py
- 2026-06-11 [claude]: Edit NeedProjectPage.tsx
- 2026-06-11 [claude]: Edit test_hooks_workflow_integrity.py
- 2026-06-11 [claude]: Edit test_hooks_workflow_integrity.py
- 2026-06-11 [claude]: Edit test_hooks_workflow_integrity.py
- 2026-06-11 [claude]: Edit test_hooks_phase_f.py
- 2026-06-11 [claude]: Edit test_hooks_phase_f.py
- 2026-06-11 [claude]: Edit 0003-intent-enforcement-layer.md
- 2026-06-11 [claude]: Edit test_centrality_ranking_doctor.py
- 2026-06-11 [claude]: commit 9a67789fd5 — refactor(governance): retire task-audit subsystem — folder, refs, hooks, prompts (TASK-397)
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
