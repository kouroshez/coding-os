---
id: TASK-609
title: "render_ci_workflow(world): one generated CI calling make verify (init-strip, modules.cicd-gated)"
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
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit renderer.py
- 2026-06-27 [claude]: Edit _init_helpers.py
- 2026-06-27 [claude]: Edit main.py
- 2026-06-27 [claude]: Edit main.py
- 2026-06-27 [claude]: Edit subsystems.yaml
- 2026-06-27 [claude]: Edit subsystems.yaml
- 2026-06-27 [claude]: Edit update.py
- 2026-06-27 [claude]: Edit update.py
- 2026-06-27 [claude]: Deliberation: render_ci_workflow is a string-builder twin of render_makefile_targets (line-based, not yaml.dump —…
- 2026-06-27 [claude]: Edit test_cli.py
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Done: render_ci_workflow (per-language matrix, ubuntu-only, body=make targets delegation) + materialize_ci_workflow…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
