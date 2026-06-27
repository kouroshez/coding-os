---
id: TASK-610
title: "render_dockerfile(world): backend-only multi-stage Dockerfile skeleton + security-scan stub"
swimlane: cli
kind: feature
epic: stack-factory-v2
labels: [ready]
status: complete
priority: P2
appetite: 2d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260626-165558-a565
depends_on: [TASK-605, TASK-606, TASK-607, TASK-608]
blocked_by: []
references: []
---
# TASK-610: render_dockerfile(world): backend-only multi-stage Dockerfile skeleton + security-scan stub

**Outcome (one sentence):** One generator emits a multi-stage, non-root, healthcheck Dockerfile skeleton ONLY for category=backend stacks (~11), keyed by language base image; frontend stacks get a static-build CI job, mobile (flutter/react-native) get build-only and NO Dockerfile (respecting flutter's NA). The CI carries a commented `# security-scan:` job stub as the documented seam — the scanner itself stays an agent skill (Rule 22, no speculative machinery).

## Read First
- src/cli/renderer.py
- src/templates/go-fiber/scaffold-boundary.yaml
- src/core/skills/docker/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a category=backend stack, **When** `cos init` runs, **Then** a multi-stage non-root Dockerfile skeleton (EXPOSE + CMD to run target) + .dockerignore is emitted keyed by language base image.
**Given** a frontend or mobile stack, **When** the same, **Then** no server Dockerfile is emitted (frontend to static build, mobile to build-only), respecting flutter's NA.
**Given** the emitted CI, **Then** it carries a commented `# security-scan:` job stub as the seam with no scanner inlined.
**Then** `uv run pytest tests/test_cli.py -q` is green.

## Work Log
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit _init_helpers.py
- 2026-06-27 [claude]: Edit main.py
- 2026-06-27 [claude]: Edit main.py
- 2026-06-27 [claude]: Edit update.py
- 2026-06-27 [claude]: Edit update.py
- 2026-06-27 [claude]: Edit test_cli.py
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit stack-factory-v2-epic.md
- 2026-06-27 [claude]: Done: render_dockerfile (8 backend-language multi-stage non-root healthchecked skeletons) + render_dockerignore +…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
