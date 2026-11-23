---
id: TASK-1091
title: "feat(templates): brand-design stack \u2014 non-code scaffold for brand and design projects (template-update)"
swimlane: templates
kind: feature
epic: stacks
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-23
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261107-135839-5342
depends_on: []
blocked_by: []
references: []
---
# TASK-1091: feat(templates): brand-design stack — non-code scaffold for brand and design projects (template-update)

**Outcome (one sentence):** cos init -t brand-design gives a compact brand/design project: no software-only docs, brand AGENTS.md sections, brand swimlanes, docs/brand.md SSOT, assets/ dirs, and cos doctor 0 FAIL.

## Read First
- docs/playbooks/template-authoring.md
- docs/engineering/config-composition.md
- src/core/schemas/stack.schema.json

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the brand-design stack, **When** `cos stack-lint brand-design` runs, **Then** it exits 0
- **Given** an empty dir, **When** `cos init -t brand-design` runs, **Then** no software-only base docs (api-contracts, architecture, engineering, ops, insights, src/shared, ...) are written and `cos doctor` reports 0 FAIL
- **Given** a fresh brand-design project, **When** the board loads, **Then** the swimlanes are brand/design/channels/tooling only and `.coding-os.yaml` verify holds docs only
- **Given** the template, doctor and aggregator suites, **When** run, **Then** they pass

## Work Log
- 2026-11-23T07:30:00Z — Plan: three stack-declared levers (scaffold_excludes with every-stack semantics, same-id AGENTS.md section override, composer replace_keys) instead of a new module or base-doc markers; the base stays the single source and existing stacks render byte-identically (anti-overengineering, SSOT-first).
- 2026-11-23T07:30:00Z — Governance auto-index excluded without replacement: the block-protected-files scaffold/docs/governance guard reads only the bare-id .task-current marker; consumer auto-regen-doc-index rebuilds it.
- 2026-11-23T07:30:00Z — Verified: cos stack-lint brand-design PASS (soft GAP: golden); init --dry-run 33 files, no software docs; scratch init cos doctor 0 FAIL; manifest-regen adds only the 2 brand sections; make lint, docs-lint, file-size gate green; golden parity 5 FAIL pre-existing from 12a641bb (settings.json CLAUDE_PROJECT_DIR), not this change.
- 2026-11-23T07:55:00Z — Close suites: test_template_scaffold_* + doctor + module tags 133 passed; test_cli + stack_rule_refresh 303 passed; aggregator/composer/stack_registry/size gate 74 passed.
- 2026-11-23 [claude]: Status transitioned to complete via cos task-done.
