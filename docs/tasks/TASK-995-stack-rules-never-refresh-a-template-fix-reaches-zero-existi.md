---
id: TASK-995
title: "Stack rules never refresh \u2014 a template fix reaches zero existing consumers"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-16
started: 2026-08-16
completed: 2026-08-16
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-995: Stack rules never refresh — a template fix reaches zero existing consumers

**Outcome (one sentence):** A correction made to src/templates/&lt;stack&gt;/rules/*.md reaches projects that are already installed, without silently overwriting a rule the user deliberately tailored.

## Read First
- src/cli/update.py
- src/cli/_doctor_stacks.py
- src/core/scripts/install-adapter.sh
- src/core/rules/anti-overengineering.md

## Repro Steps
Proved by executing last session: replacing an installed .claude/rules/&lt;stack&gt;-*.md with a stale marker survives `cos update` untouched. Core rules are symlinks and propagate immediately; stack rules are copies and propagate never, so the corrected meta graph-first rule reached no existing install.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an installed project whose stack rule is byte-identical to the template it came from, **When** the refresh path runs after the template changes, **Then** the installed copy matches the new template.
- **Given** an installed project whose stack rule the user edited, **When** the same path runs, **Then** the edit survives and the divergence is reported rather than resolved silently.
- **Given** either case, **When** the command finishes, **Then** it names every file it changed and every file it skipped.

## Work Log
- 2026-08-16 [claude]: Edit ablation-protocol.md
- 2026-08-16 [claude]: Edit ablation-protocol.md
- 2026-08-16 [claude]: Edit ablation-protocol.md
- 2026-08-16 [claude]: Chose baseline-compare over symlinking after recon found the baseline already exists: cos init mirrors…
- 2026-08-16 [claude]: Proved all three paths on real cos init scaffolds, not just units: an untouched rule refreshes and its mirror…
- 2026-08-16 [claude]: Status transitioned to complete via cos task-done.
