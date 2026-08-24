---
id: TASK-1021
title: "Vendor humanizer skill (MIT) + wire prose de-AI enforcement for meta and consumers"
swimlane: core
kind: feature
epic: null
labels: [skills, governance, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-08-24
started: 2026-08-24
completed: null
agent_session: ses-claude-20260820-192937-ef87
depends_on: []
blocked_by: []
references: []
---
# TASK-1021: Vendor humanizer skill (MIT) + wire prose de-AI enforcement for meta and consumers

**Outcome (one sentence):** Agents writing human-facing prose (README, release notes, community posts, announcements) load a humanizer skill that names concrete AI tells, and a UserPromptSubmit nudge surfaces it on prose-writing intent. Ships to consumer projects via _base.

## Read First
- src/core/skills/technical-writing/SKILL.md
- src/templates/_base/base.yaml
- src/core/rules/skill-enforcement.md
- src/core/hooks/nudge-graph-os.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a prompt asking for a blog post, README, announcement, or community post
  **When** the turn starts
  **Then** `nudge-humanizer.sh` injects a directive naming the humanizer skill, debounced once per session.
- **Given** a Write or Edit on `README.md` or `docs/blog/**`
  **When** the humanizer skill has not been loaded this session
  **Then** `enforce-skill.sh` blocks the write and names the skill.
- **Given** `cos init` on a consumer project
  **When** the scaffold is rendered
  **Then** `humanizer` and `technical-writing` ship in the project's skills dir, sourced from `_base/base.yaml::skills`.
- **Given** the upstream skill is MIT-licensed
  **When** it is vendored
  **Then** `src/core/skills/humanizer/NOTICE` carries the upstream copyright and license text.

## Work Log
- 2026-08-24 [claude]: Edit SKILL.md
- 2026-08-24 [claude]: Edit patterns.md
- 2026-08-24 [claude]: Edit false-positives.md
- 2026-08-24 [claude]: Edit NOTICE
- 2026-08-24 [claude]: Edit nudge-humanizer.sh
- 2026-08-24 [claude]: Edit registry.yaml
- 2026-08-24 [claude]: Edit base.yaml
- 2026-08-24 [claude]: Edit adapter.yaml
- 2026-08-24 [claude]: Edit codex-userpromptsubmit-dispatch.sh
- 2026-08-24 [claude]: Edit enforce-skill.sh
- 2026-08-24 [claude]: Edit enforce-skill.sh
- 2026-08-24 [claude]: Edit enforce-skill.sh
- 2026-08-24 [claude]: Edit smoke_humanizer.sh
- 2026-08-24 [claude]: Edit subsystems.yaml
- 2026-08-24 [claude]: Wired the last two acceptance legs: _base.yaml ships humanizer + technical-writing to consumers; enforce-skill.sh…
- 2026-08-24 [claude]: Verified by execution, not reading: 10/10 hook smoke assertions (nudge fires per intent class, debounces, stays…
