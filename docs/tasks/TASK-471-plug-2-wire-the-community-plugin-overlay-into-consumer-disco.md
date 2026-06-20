---
id: TASK-471
title: "PLUG-2 \u2014 wire the community-plugin overlay into consumer-discovery commands (P4-3/6)"
swimlane: infra
kind: bug
epic: null
labels: [modularity, plugins, audit-pass4, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-471: PLUG-2 — wire the community-plugin overlay into consumer-discovery commands (P4-3/6)

**Outcome (one sentence):** A community stack/adapter dropped in $COS_USER_TEMPLATES_DIR / $COS_USER_ADAPTERS_DIR is actually discovered + usable end-to-end. The overlay resolvers (overlay_template_dirs()/overlay_adapter_dirs(), one currently dead code) are threaded into the consumer-discovery call sites ONLY — regen/lint/scaffold-SSOT paths stay bundled-only (the TASK-458 leak fix must not regress).

## Read First
- docs/engineering/modularity-audit-2026-06.md
- src/cli/_resources.py
- src/cli/stack_registry.py
- src/cli/main.py
- docs/playbooks/template-authoring.md

## Repro Steps
Set $COS_USER_TEMPLATES_DIR to a dir with acme-rust/stack.yaml; `cos init --template acme-rust` and `cos add-stack acme-rust` both abort "stack 'acme-rust' not found". grep: overlay_adapter_dirs() (_resources.py:81) has zero references; every production load_stack_registry/load_adapter_registry caller passes bundled-only.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a valid stack at $COS_USER_TEMPLATES_DIR/<id>/stack.yaml **When** `cos list-stacks` / `cos init --template <id>` / `cos add-stack <id>` run **Then** the community id is discovered + usable (no "stack not found" hard-abort); AND generate_manifest.py/regen_rules.py/stack_lint.py stay bundled-only (no leak into scaffold_manifest.json / dimension-registry.md); AND a test asserts discovery under a monkeypatched $COS_USER_TEMPLATES_DIR; AND template-authoring.md §overlay matches the commands that actually surface it.

## Work Log
