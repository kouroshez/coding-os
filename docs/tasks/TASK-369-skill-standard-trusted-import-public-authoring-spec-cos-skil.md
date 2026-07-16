---
id: TASK-369
title: "Skill standard + trusted import \u2014 public authoring spec, cos skill new/lint, three trust tiers, provenance gate"
swimlane: cli
kind: feature
epic: E-skills
labels: [wave-4, onboarding-program, ready]
status: archive
priority: P1
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-352]
blocked_by: []
references: []
---
# TASK-369: Skill standard + trusted import — public authoring spec, cos skill new/lint, three trust tiers, provenance gate

**Outcome (one sentence):** Public skill authoring spec + template + `cos skill new`/`cos skill lint` (built on existing skill.schema.json); `cos skill add &lt;path|git-url&gt;` imports third-party skills through a gate: schema normalize (auto-fill tier/domain/globs), security scan (exfil/URL patterns in SKILL.md, static check on scripts/), license check, provenance record, scripts-execution consent for untrusted tier.

## Read First
- src/cli/skill_registry.py
- src/core/schemas/skill.schema.json
- src/core/skills/clean-code/SKILL.md
- src/cli/project_overrides.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos skill new my-skill`, **When** it completes, **Then** a spec-compliant scaffold (SKILL.md frontmatter + dirs) is produced that passes `cos skill lint` out of the box, and the authoring spec doc explains every field a third-party author must fill.
- **Given** a vanilla Agent-Skills-format skill (name+description only), **When** `cos skill add` imports it, **Then** normalization fills coding-os fields, the skill installs at trust tier community with provenance (source, checksum, date) recorded.
- **Given** a malicious fixture skill (exfil URL pattern in SKILL.md or dangerous scripts/), **When** import runs, **Then** the gate blocks it naming the findings; legit fixture passes; both covered by tests.
- **Given** an untrusted imported skill with scripts/, **When** an agent session loads it, **Then** scripts execution requires recorded consent (tier surfaced in skill listing).
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** green.

## Work Log
- 2026-06-11 [claude]: Edit skill-architecture.md
- 2026-06-11 [claude]: Edit skill_commands.py
- 2026-06-11 [claude]: commit d286f3615f — feat(cli): public skill standard + trusted import gate (TASK-369)
- 2026-06-11 [claude]: IMPL DONE (parked, batch 8 #2) — § Public skill standard in skill-architecture.md (three trust tiers, authoring fields,
- 2026-06-11 [claude]: CLOSED on batch-8 suite: tests/test_cli.py 134 passed (14m00s). Commit d286f361. Self-score 9/10: full authoring+import+
