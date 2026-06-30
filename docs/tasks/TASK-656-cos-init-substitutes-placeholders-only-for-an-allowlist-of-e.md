---
id: TASK-656
title: "cos init substitutes placeholders only for an allowlist of extensions \u2014 literal {{PROJECT_NAME}} ships in 12 stacks"
swimlane: cli
kind: bug
epic: stack-completeness-v2
labels: [renderer, cli, drift, wave-2, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-656: cos init substitutes placeholders only for an allowlist of extensions — literal {{PROJECT_NAME}} ships in 12 stacks

**Outcome (one sentence):** cos init substitutes {{PROJECT_NAME}}/{{DATE}}/{{PROJECT_DESCRIPTION}} in every UTF-8-decodable scaffold text file (binary copied verbatim), replacing the fragile _PLACEHOLDER_SUFFIXES allowlist that omitted .cs/.svelte/.dart/.rs/.php/.java/.rb/.html/.toml/.js — so no consumer of any stack ships a literal {{PROJECT_NAME}}.

## Read First
- src/cli/main.py
- docs/architecture/meta-project.md

## Repro Steps
grep -rlE '\{\{(PROJECT_NAME|DATE)\}\}' src/templates for .svelte/.cs/.dart/.rs/.php/.java/.rb/.html/.toml/.js lists 26 scaffold files across 12 stacks (svelte/aspnet-core/flutter/rust-axum/rust-plain/wordpress/spring-boot/angular/java-plain/ruby-plain/csharp-plain). After `cos init --template svelte-sveltekit && cd src/frontend && npm i && npm run lint`, svelte-check fails: '+layout.svelte:9 Cannot find name PROJECT_NAME' because the literal {{PROJECT_NAME}} survived. Root cause: src/cli/main.py:566 _PLACEHOLDER_SUFFIXES = {.md,.go,.mod,.ts,.tsx,.json,.vue}; the renderer at main.py:880 only substitutes those suffixes and shutil.copy2's every other file verbatim.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fresh scaffold of any stack, **When** cos init renders it, **Then** no shipped source/config file contains a literal {{PROJECT_NAME}}/{{DATE}}/{{PROJECT_DESCRIPTION}}. **Given** a binary asset (image/font), **When** rendered, **Then** it is copied byte-for-byte without a decode error. **Given** test_cli + test_template_scaffold + golden parity, **When** run, **Then** all pass.

## Work Log
- 2026-06-30 [claude]: Edit main.py
- 2026-06-30 [claude]: Edit main.py
- 2026-06-30 [claude]: Edit vite.config.ts
- 2026-06-30 [claude]: Edit package.json
- 2026-06-30 [claude]: main.py _overlay_scaffold: allowlist->UTF-8 text-detection (binary copied verbatim); dead _PLACEHOLDER_SUFFIXES…
- 2026-06-30 [claude]: committed f1fe3930 · 1 file
