---
id: TASK-370
title: "Per-project extra-skills \u2014 extra-skills.yaml, cos skill add/remove/list, Config-tab management"
swimlane: cli
kind: feature
epic: E-skills
labels: [wave-4, onboarding-program, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-352]
blocked_by: []
references: []
---
# TASK-370: Per-project extra-skills — extra-skills.yaml, cos skill add/remove/list, Config-tab management

**Outcome (one sentence):** .coding-os/extra-skills.yaml lets a consumer add skills beyond the stack list; `cos skill add/remove/list` manages it and re-renders adapter skill links; the existing Hub Config tab lists and manages extra skills (no new UI section).

## Read First
- src/core/scripts/link-stack-skills.sh
- src/cli/skill_registry.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/routes/config.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos skill add redis` in a consumer project, **When** it completes, **Then** extra-skills.yaml lists redis and the skill symlink appears in every installed adapter's skills dir; remove reverses both; list shows stack-provided vs extra provenance.
- **Given** `cos update`, **When** assets re-link, **Then** extra skills survive (not clobbered by stack re-link) — regression test.
- **Given** the Config tab, **When** the skills panel renders, **Then** extra skills are manageable there via the config API and changes round-trip to the YAML.
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py -q` + web-route test run, **Then** green.

## Work Log
- 2026-06-11 [claude]: Edit config.py
- 2026-06-11 [claude]: Edit config.py
- 2026-06-11 [claude]: Edit ConfigPage.tsx
- 2026-06-11 [claude]: Edit skill-architecture.md
- 2026-06-11 [claude]: Edit ConfigPage.tsx
