---
id: TASK-478
title: "Apply confirmed adversarial-review fixes for the audit-pass4 batch (cascade stack-guard, flock dep-validation, update+skills_list overlay)"
swimlane: infra
kind: bug
epic: null
labels: [modularity, audit-pass4, review-fix, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-478: Apply confirmed adversarial-review fixes for the audit-pass4 batch (cascade stack-guard, flock dep-validation, update+skills_list overlay)

**Outcome (one sentence):** Four confirmed defects from the multi-agent review of TASK-475/474/471 are fixed: the module→skill cascade enable-path no longer force-links a meta-stack-only skill (graph-os-authoring) into a non-meta consumer; the flock RMW re-runs the dependency-refusal validation under the lock so concurrent toggles cannot orphan a dependency; and cos update + skills_list (Hub skills preview) thread the community overlay like the other consumer-discovery sites.

## Read First
- docs/engineering/modularity-audit-2026-06.md
- src/cli/skill_commands.py
- src/cli/subsystems.py
- src/cli/update.py
- src/cli/skills_list.py

## Repro Steps
1. (#1) On a `templates: [python]` project run `cascade_module_skills(project, "graph", enabled=True)` → `graph-os-authoring` (a meta-stack-only skill) is force-linked into `.claude/skills/`, bypassing the installed-stack guard `set_project_skill:508` enforces. doctor PASSes (skill_drift only flags DISABLED modules).
2. (#2) Two processes race `enable tasks` and `disable docs` from a shared start; both pass refusal against the pre-lock snapshot → tasks ends enabled while docs is disabled (orphaned dependency the refusal logic forbids).
3. (#6) `cos update` on a project carrying a community stack loads bundled-only registries → the community stack is dropped/breaks on recompose.
4. (#7) `skills_list.collect_stack_skill_groups` / Hub skills preview loads bundled-only → KeyError / missing rows for a community stack id.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the 4 confirmed review findings **When** the fixes land **Then** cascade_module_skills enable skips stack-provenance skills not in the project's installed stacks (graph-os-authoring NOT linked on a templates:[python] project, graph-explorer still is) — **And** set_module_enabled re-runs kernel/dependents/missing-dependency validation against the re-read disabled set inside the flock block (a concurrent enable-dependent + disable-dependency race refuses, no orphan) — **And** update.py + skills_list.py pass overlay_template_dirs()/overlay_adapter_dirs() — **And** regression tests cover the cascade non-meta-skip + the under-lock validation — **And** test_modularity_toggle + test_cli + thinking_os-subsystems suites pass.

## Work Log
- 2026-06-20 [claude]: Edit skill_commands.py
- 2026-06-20 [claude]: Edit skill_commands.py
- 2026-06-20 [claude]: Edit subsystems.py
- 2026-06-20 [claude]: Edit skills_list.py
- 2026-06-20 [claude]: Edit update.py
- 2026-06-20 [claude]: Edit update.py
- 2026-06-20 [claude]: Edit update.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: commit 6c62524899 — fix(modularity): apply confirmed adversarial-review fixes for the audit-pass4 batch (TASK-478)
- 2026-06-20 [claude]: Applied 4 of 7 confirmed review findings. #1 (475): cascade_module_skills enable now skips stack-provenance skills…
