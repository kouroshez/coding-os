---
id: TASK-1096
title: "fix(cli): cos update reports symlinked project skills as removed although it never removes them"
swimlane: cli
kind: bug
epic: workflow-enforcement
labels: [ready]
status: complete
priority: P2
appetite: 2h
created: 2026-11-23
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1096: fix(cli): cos update reports symlinked project skills as removed although it never removes them

**Outcome (one sentence):** cos update and cos update --dry-run list only the skills they actually add or remove; symlinked project skills (cos skill new/enable) never appear as removed.

## Read First
- docs/architecture/meta-project.md
- src/cli/_update_manifest.py

## Repro Steps
In a project with a cos skill new skill (Streaming-Channels: .claude/skills/brand-image -> ../../.agents/skills/brand-image), cos update --dry-run prints "Removed skills: platform-export, brand-image, figma-brand" for claude and codex, while _apply_diff skips symlinked skill dirs and removes nothing.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project whose adapter skills dir holds a symlinked skill dir that is not in the manifest, **When** cos update --dry-run runs, **Then** that skill is not listed as removed
- **Given** the same project, **When** cos update runs, **Then** the symlinked skill and its source stay untouched
- **Given** the CLI suites, **When** uv run pytest tests/test_cli.py tests/test_stack_rule_refresh.py -q runs, **Then** they pass

## Work Log
- 2026-11-23 [claude]: Plan: fix ownership at the single scan (_scan_project_assets) instead of filtering the report — a skill dir counts as…
- 2026-11-23 [claude]: Done: _scan_project_assets counts a skill dir as cos's only when its SKILL.md is a symlink or it is in…
- 2026-11-23 [claude]: Status transitioned to complete via cos task-done.
