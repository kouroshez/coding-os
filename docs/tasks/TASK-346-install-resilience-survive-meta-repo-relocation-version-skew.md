---
id: TASK-346
title: "Install resilience \u2014 survive meta-repo relocation, version skew, recovery-hint errors"
swimlane: cli
kind: bug
epic: A-install
labels: [wave-0, onboarding-program, ready]
status: complete
priority: P0
appetite: 2d
created: 2026-06-11
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---
# TASK-346: Install resilience — survive meta-repo relocation, version skew, recovery-hint errors

**Outcome (one sentence):** cos survives meta-repo relocation (resilient root resolution + auto `sync-doctor --repair` path), `cos update` warns on core-version skew, and every install/init failure path (missing extras, registry write, doc-index) prints an actionable recovery hint.

## Read First
- src/cli/main.py (CODING_OS_ROOT resolution, main.py:65)
- src/cli/update.py
- src/cli/sync_all.py
- src/cli/_init_helpers.py
- src/core/scripts/install-adapter.sh (absolute symlink creation)
- src/cli/registry.py
- docs/engineering/hub-architecture.md

## Repro Steps
1. `cos init --agent claude --template python --name t1 --yes` in a temp dir, then `mv` the coding-os meta-repo directory to a new path.
2. In the consumer project run `cos update` and any hook-firing edit.
Expected: cos detects the stale root, repairs symlinks (or prints exact `cos sync-doctor --repair` instructions), and continues.
Actual: `.claude/` symlinks dangle silently, hooks/skills/rules vanish, `cos update` resolves TEMPLATES_DIR against the dead path and fails without a recovery hint.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer project created by `cos init` and a meta-repo that has been moved to a new path, **When** the user runs any `cos` command in that project, **Then** the stale root is detected and either auto-repaired via the sync-doctor path or a single copy-pasteable repair command is printed (no silent dangling symlinks).
- **Given** a consumer project stamped with an older core version, **When** `cos update` runs, **Then** a version-skew warning names both versions and the migration doc.
- **Given** init/update failure paths (missing `--extra rag`/`graph_os`, registry write failure, doc-index failure), **When** each failure occurs, **Then** stderr contains an actionable recovery hint (verified by tests for each path).
- **Given** the existing test suite, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** new regression tests for root-resolution + skew-warning + recovery-hints pass and no existing test breaks.

## Work Log
- 2026-06-11 [claude]: Edit hub-architecture.md
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit sync_all.py
- 2026-06-11 [claude]: Edit sync_all.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: commit 7f8aae0dfc — fix(cli): install resilience — importlib roots, dangling-link nudge+prune, skew warn (TASK-346)
- 2026-06-11 [claude]: Implemented 3 resilience layers (commit 7f8aae0d): update/sync_all roots via cli._resources importlib (wheel+move safe);
- 2026-06-11 [claude]: Edit doctor-checks.md
- 2026-06-11 [claude]: Edit doctor-checks.md
- 2026-06-11 [claude]: Edit README.md
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit doctor.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: commit 7a501d8905 — feat(cli): cos doctor --bootstrap preflight checks + importlib roots in doctor (TASK-347)
- 2026-06-11 [claude]: Edit template-authoring.md
- 2026-06-11 [claude]: Edit stack.schema.json
- 2026-06-11 [claude]: Edit _data_types.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit go.mod
- 2026-06-11 [claude]: Edit main.go
- 2026-06-11 [claude]: Edit scaffold-boundary.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit tsconfig.json
- 2026-06-11 [claude]: Edit index.ts
- 2026-06-11 [claude]: Edit scaffold-boundary.yaml
- 2026-06-11 [claude]: Edit python-library.md
- 2026-06-11 [claude]: Edit python-rules.md
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: commit b22614232c — feat(templates): language layer — language/extends schema, plain stacks, grouped picker (TASK-348)
- 2026-06-11 [claude]: Edit project-anatomy.md
- 2026-06-11 [claude]: Edit stack.schema.json
- 2026-06-11 [claude]: Edit _data_types.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: Edit stack.yaml
- 2026-06-11 [claude]: commit bcded442fa — feat(core): project anatomy — structure spec per stack + multi-backend service relocation (TASK-351)
- 2026-06-11 [claude]: Edit project-anatomy.md
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit skill_primer.py
- 2026-06-11 [claude]: Edit skill_primer.py
- 2026-06-11 [claude]: Edit skill_primer.py
- 2026-06-11 [claude]: Edit t355_sanity.py
- 2026-06-11 [claude]: Edit aggregator.py
- 2026-06-11 [claude]: Edit project-anatomy.md
- 2026-06-11 [claude]: Edit project-anatomy.md
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: commit d509eb3d88 — chore(golden): recapture fixtures after hook/rule drift (test-governor, model-routing, token-diet)
- 2026-06-11 [claude]: Edit config-composition.md
- 2026-06-11 [claude]: Edit preset.schema.json
- 2026-06-11 [claude]: Edit nextjs-fastapi.yaml
- 2026-06-11 [claude]: Edit preset_registry.py
- 2026-06-11 [claude]: Edit t356_loader_sanity.py
- 2026-06-11 [claude]: Edit t356_loader_sanity.py
- 2026-06-11 [claude]: Edit config_composer.py
- 2026-06-11 [claude]: Edit config_composer.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit list_stacks.py
- 2026-06-11 [claude]: Edit list_stacks.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: commit 78e26f4578 — feat(cli): preset model — init --preset/--dry-config + merge conflict surfacing (TASK-356)
- 2026-06-11 [claude]: Edit skill-architecture.md
- 2026-06-11 [claude]: commit 8276154cc5 — docs(skills): per-stack skill-group SSOT contract for onboarding (TASK-352 groundwork)
- 2026-06-11 [claude]: Edit test-cadence-batch-heavy-suites.md
- 2026-06-11 [claude]: commit 257e6d0b2f — chore(board): DoR review sweep — fill 18 backlog acceptances, all 41 icebox tasks validated+ready
- 2026-06-11 [claude]: Edit skills_list.py
- 2026-06-11 [claude]: Edit skills_list.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit t352_fix_frontmatter.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: committed daf81ab5: src/cli/skills_list.py, src/core/web/routes/hub.py, src/templates/django/skills/python-django/SKILL.
- 2026-06-11 [claude]: Edit registry.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: Edit registry.py
- 2026-06-11 [claude]: Edit registry.py
- 2026-06-11 [claude]: Edit OnboardingWizard.tsx
- 2026-06-11 [claude]: Edit HubHome.tsx
- 2026-06-11 [claude]: Edit HubHome.tsx
- 2026-06-11 [claude]: Edit HubHome.tsx
- 2026-06-11 [claude]: Edit HubHome.tsx
- 2026-06-11 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-11 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-11 [claude]: Edit hub-architecture.md
- 2026-06-11 [claude]: committed 8a80b449: docs/engineering/hub-architecture.md, src/cli/registry.py, src/core/web/routes/hub.py, src/core/web/
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: Edit new-project.md
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: committed cce496ac: src/cli/main.py, src/core/commands/new-project.md, src/core/web/routes/hub.py, tests/test_cli.py, te
- 2026-06-11 [claude]: Edit init_jobs.py
- 2026-06-11 [claude]: Edit init_jobs.py
- 2026-06-11 [claude]: Edit init_jobs.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit hub.py
- 2026-06-11 [claude]: Edit metrics.py
- 2026-06-11 [claude]: Edit test_init_jobs.py
- 2026-06-11 [claude]: Edit test_init_jobs.py
- 2026-06-11 [claude]: Edit test_hub_init_route.py
- 2026-06-11 [claude]: Edit OnboardingWizard.tsx
- 2026-06-11 [claude]: Edit OnboardingWizard.tsx
- 2026-06-11 [claude]: Edit OnboardingWizard.tsx
- 2026-06-11 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-11 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-11 [claude]: committed 9a7f9679: docs/engineering/hub-architecture.md, src/core/web/init_jobs.py, src/core/web/routes/hub.py, src/cor
- 2026-06-11 [claude]: committed 5be36cb5: docs/engineering/hub-architecture.md, docs/engineering/hub-threat-model.md, src/core/web/routes/hub.
- 2026-06-11 [claude]: Edit setup.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit 00-index.md
- 2026-06-11 [claude]: Edit cognition.py
- 2026-06-11 [claude]: Edit cognition.py
- 2026-06-11 [claude]: Edit test_cli.py
- 2026-06-11 [claude]: committed 2f794837: src/cli/main.py, src/cli/setup.py, src/core/web/routes/cognition.py, src/templates/_base/scaffold/do
- 2026-06-11 [claude]: Edit subsystems.yaml
- 2026-06-11 [claude]: Edit subsystems.py
- 2026-06-11 [claude]: Edit state-files.md
- 2026-06-11 [claude]: committed 58dfb7f1: docs/engineering/state-files.md, src/cli/subsystems.py, src/core/subsystems.yaml, tests/test_cli.py
- 2026-06-11 [claude]: Edit _data_types.py
- 2026-06-11 [claude]: Edit stack_registry.py
- 2026-06-11 [claude]: Edit renderer.py
- 2026-06-11 [claude]: Edit tool-routing.md.tmpl
- 2026-06-11 [claude]: Edit subsystems.py
- 2026-06-11 [claude]: Edit project_overrides.py
- 2026-06-11 [claude]: committed 94d5f94c: src/cli/_data_types.py, src/cli/_init_helpers.py, src/cli/add_stack.py, src/cli/project_overrides.py
- 2026-06-11 [claude]: Edit _shared.py
- 2026-06-11 [claude]: Edit _shared.py
- 2026-06-11 [claude]: Edit _shared.py
- 2026-06-11 [claude]: Edit subsystems.yaml
- 2026-06-11 [claude]: Edit subsystems.yaml
- 2026-06-11 [claude]: Edit subsystems.yaml
- 2026-06-11 [claude]: Edit subsystems.yaml
- 2026-06-11 [claude]: Edit module_commands.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit settings.py
- 2026-06-11 [claude]: Edit settings.py
- 2026-06-11 [claude]: Edit ConfigPage.tsx
- 2026-06-11 [claude]: Edit ConfigPage.tsx
- 2026-06-11 [claude]: Edit ConfigPage.tsx
- 2026-06-11 [claude]: Edit settings.py
- 2026-06-11 [claude]: Edit ConfigPage.tsx
- 2026-06-11 [claude]: Edit mcp-error-envelope.md
- 2026-06-11 [claude]: Edit mcp-error-envelope.md
- 2026-06-11 [claude]: Edit test_module_gating.py
- 2026-06-11 [claude]: committed e5c6a50c: docs/engineering/mcp-error-envelope.md, src/cli/main.py, src/cli/module_commands.py, src/core/subsys
- 2026-06-11 [claude]: Edit update.py
- 2026-06-11 [claude]: Edit module_commands.py
- 2026-06-11 [claude]: committed 602e74c7: src/cli/module_commands.py, src/cli/update.py, tests/test_cli.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit main.py
- 2026-06-11 [claude]: Edit 00-index.md
- 2026-06-11 [claude]: committed 955b0d6c: src/cli/main.py, src/templates/_base/scaffold/docs/00-index.md, src/templates/_base/scaffold/docs/go
- 2026-06-11 [claude]: Edit template-authoring.md
- 2026-06-11 [claude]: committed b024ec32: docs/playbooks/template-authoring.md, src/cli/main.py, src/cli/stack_lint.py, tests/test_template_sc
- 2026-06-11 [claude]: committed 76ad8897: src/cli/aggregator.py, src/cli/main.py, src/cli/preset_commands.py, src/cli/preset_registry.py, src/
- 2026-06-11 [claude]: committed 08dc53b7: src/core/rules/dimension-registry.md, src/core/rules/skill-enforcement.md, src/core/scaffold_manifes
