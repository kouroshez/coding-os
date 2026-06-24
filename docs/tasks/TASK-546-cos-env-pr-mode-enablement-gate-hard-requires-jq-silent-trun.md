---
id: TASK-546
title: "cos-env pr-mode enablement gate hard-requires jq (silent trunk downgrade)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-546: cos-env pr-mode enablement gate hard-requires jq (silent trunk downgrade)

**Outcome (one sentence):** cos-env.sh reads git_settings (enabled/integration_branch/protected_branches/autonomy_level) via jq OR a python3 fallback, so a host without jq still honors an enabled pr-mode project.

## Read First
- src/core/hooks/cos-env.sh
- src/core/hooks/_helpers/json_field.py
- docs/playbooks/pr-workflow.md

## Repro Steps
1. Project with hub-settings.json git_settings.enabled=true; PATH shadowed so jq is absent.
2. Source cos-env.sh (any hook fires).
Expected: COS_GIT_WORKFLOW=pr exported via python3 fallback.
Actual: `command -v jq` precondition fails → gate skipped → enabled project silently runs trunk.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project with git_settings.enabled=true in hub-settings.json on a host where jq is NOT on PATH
- **When** any hook sources cos-env.sh
- **Then** COS_GIT_WORKFLOW=pr (+ integration/protected/autonomy) is exported via the python3 fallback (no `command -v jq` precondition), identical to the jq path; trunk projects (no git_settings) stay byte-identical

## Work Log
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: committed bd61a589 · 2 files
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
