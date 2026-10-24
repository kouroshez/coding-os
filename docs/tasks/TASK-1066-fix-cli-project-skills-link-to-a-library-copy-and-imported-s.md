---
id: TASK-1066
title: "fix(cli): project skills link to a library copy and imported skills record a deleted tmp path"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1066: fix(cli): project skills link to a library copy and imported skills record a deleted tmp path

**Outcome (one sentence):** A skill that lives inside the project is linked from its in-repo source (one copy, versioned with the project), and an imported skill's provenance records where it really came from instead of a scratchpad path that is gone.

## Read First
- docs/engineering/skill-architecture.md

## Repro Steps
1. trading-terminal: `readlink .claude/skills/redline-trading-safety` → ~/.coding-os/skills/redline-trading-safety, while the source is the tracked skills/redline-trading-safety.
2. 7 of 8 ~/.coding-os/skills/*/.provenance.json name /private/tmp/claude-501/.../scratchpad/... paths that no longer exist; none records a URL or SHA.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos skill import skills/foo` run inside a project **When** the adapter skills dir is rendered **Then** .claude/skills/foo resolves to the project's skills/foo, not ~/.coding-os/skills/foo
- **Given** an import from a git checkout **When** provenance is written **Then** it carries the remote URL and commit SHA

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
