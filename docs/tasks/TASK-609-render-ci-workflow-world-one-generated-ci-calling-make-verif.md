---
id: TASK-609
title: "render_ci_workflow(world): one generated CI calling make verify (init-strip, modules.cicd-gated)"
swimlane: cli
kind: feature
epic: stack-factory-v2
labels: []
status: icebox
priority: P2
appetite: 2d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: [TASK-605, TASK-606, TASK-607, TASK-608]
blocked_by: []
references: []
---

# TASK-609: render_ci_workflow(world): one generated CI calling make verify (init-strip, modules.cicd-gated)

**Outcome (one sentence):** One generator emits a single .github/workflows/ci.yml at cos init whose body delegates to `make verify` — the structural twin of render_makefile_targets (renderer.py:194). Because it delegates it never rots with framework versions; because it reads AggregatedWorld, adding a stack/target auto-includes it. init-strip (consumer-owned), gated behind modules.cicd, macOS off the per-push path.

## Read First
- src/cli/renderer.py
- src/cli/_init_helpers.py
- .github/workflows/ci.yml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a multi-stack project with modules.cicd on, **When** `cos init` runs, **Then** .github/workflows/ci.yml is emitted with a job matrix driven by world.makefile_targets + verify[] keyed by language, body calling `make verify`.
**Given** a consumer adds a stack or a makefile target, **When** CI is regenerated, **Then** the new target is included automatically (no hand edit).
**Given** the emitted workflow, **Then** macOS is quarantined off the per-push path (per the repo's own ci.yml + the github-actions-cost-macos-10x lesson) and the file is init-strip, not a live symlink.
**Then** `uv run pytest tests/test_cli.py -q` is green.

## Work Log
