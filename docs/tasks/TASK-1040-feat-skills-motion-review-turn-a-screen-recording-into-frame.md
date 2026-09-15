---
id: TASK-1040
title: "feat(skills): motion-review \u2014 turn a screen recording into frames an agent can judge"
swimlane: core
kind: feature
epic: null
labels: [skills, video, visual-verification, user-scope, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-09-15
started: 2026-09-15
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1040: feat(skills): motion-review — turn a screen recording into frames an agent can judge

**Outcome (one sentence):** A self-contained motion-review skill in src/core/skills/ that converts any screen recording into a settled-state + transition frame set plus a timing profile, and installs user-scope for Claude and Codex with zero coding-os runtime dependency.

## Read First
- src/core/skills/codebase-explorer/SKILL.md
- src/core/rules/anti-overengineering.md
- docs/architecture/raptor-consolidation.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a screen recording from a simulator, emulator, browser, local file or URL, **When** the engine runs, **Then** it emits exactly one frame per settled state (taken at the END of the run) plus 3-8 frames per transition, and a timing profile per transition.
- **Given** a recording whose screen never changed (a 1-frame file), **When** the engine runs, **Then** it fails with a diagnosis naming the frame count — never a silent empty directory.
- **Given** the skill is installed at ~/.claude/skills or ~/.codex/skills on a machine with no coding-os checkout, **When** its scripts run, **Then** they work with no $COS_* env var, no cos-env.sh and no wrapper dir.
- **Given** two frames differing only in colour (an enabled vs a luminance-matched disabled control), **When** dedup runs, **Then** both survive.
- **Given** make lint, the golden-parity suite and the file-size budget, **When** they run, **Then** all pass.

## Work Log
- 2026-09-15 [claude]: Verified by execution: engine run on a real 243-frame capture, static-recording failure path, colour-only state…
