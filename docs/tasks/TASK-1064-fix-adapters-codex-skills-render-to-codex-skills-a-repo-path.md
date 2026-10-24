---
id: TASK-1064
title: "fix(adapters): Codex skills render to .codex/skills, a repo path current Codex does not scan"
swimlane: adapters
kind: bug
epic: null
labels: [ready]
status: complete
priority: P0
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1064: fix(adapters): Codex skills render to .codex/skills, a repo path current Codex does not scan

**Outcome (one sentence):** Codex sessions in coding-os and every consumer see the enabled skills, because the codex adapter renders them where Codex 0.164+ discovers repo skills (.agents/skills).

## Read First
- docs/engineering/adapter-parity.md
- docs/engineering/skill-architecture.md

## Repro Steps
1. src/adapters/codex/adapter.yaml:83 → `skills_dir: ".codex/skills"`.
2. developers.openai.com/codex/skills: REPO scope is `$CWD/.agents/skills` … `$REPO_ROOT/.agents/skills`; `.codex/skills` is not listed.
3. `strings codex 0.164` names only codex-home-skills, .agents/skills, user-agent-skills, system-skills.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer project after `cos update` **When** Codex lists skills **Then** the core and stack skills appear
- **Given** the codex adapter descriptor **When** it is rendered **Then** skills_dir is .agents/skills and no skill is listed twice

## Work Log
- 2026-10-24 [claude]: Premise refuted, no code change: in a scratch git repo with .codex/skills/probe-codexdir and…
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
