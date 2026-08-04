---
id: TASK-876
title: "cos update deletes adapter-specific hooks (P0) + skips disabled_skills/module filters and settings re-render (P1)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-876: cos update deletes adapter-specific hooks (P0) + skips disabled_skills/module filters and settings re-render (P1)

## Outcome
`cos update` no longer deletes adapter-specific hooks, honors `disabled_skills`/module-disabled rules, skips the two catalog rules install.sh deliberately excludes, and re-renders (or delegates to install.sh for) hook registration. Verified by `cos update --dry-run` on the dogfood repo showing an empty removal diff for adapter hooks.

## Read First
- src/cli/update.py (_build_target_assets :153-254, _scan_project_assets :257-297, _apply_diff :322-364)
- src/adapters/*/install.sh (adapter hook linking :122-135; exclusions :149-166; disabled filters :154-232)
- Audit evidence: TASK-874 work log (session 632-5fca)

## Acceptance
- **Given** a project with claude+codex adapters, **When** `cos update` runs, **Then** codex-*-dispatch.sh and agent-memory hooks survive and newly shipped adapter hooks are added.
- **Given** `.coding-os.yaml::disabled_skills` entries, **When** `cos update` runs, **Then** disabled skills/rules stay unlinked.
- **Given** the install.sh exclusion of dimension-registry.md/skill-enforcement.md, **When** `cos update` runs, **Then** they are not re-linked.
- Secondary (same area, may split): wheel omits core/scripts/extract_disabled_*.py (pyproject package-data); per-agent manifest overwrite; dead --yes flag; site-packages/src legacy paths in 14 CLI files.

## Work Log
