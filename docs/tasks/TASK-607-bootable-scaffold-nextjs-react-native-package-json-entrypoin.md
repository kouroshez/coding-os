---
id: TASK-607
title: "bootable scaffold: nextjs + react-native (package.json + entrypoint + sample test + verify block)"
swimlane: templates
kind: feature
epic: stack-factory-v2
labels: [ready]
status: archive
priority: P2
appetite: 2d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: [TASK-602]
blocked_by: []
references: []
---
# TASK-607: bootable scaffold: nextjs + react-native (package.json + entrypoint + sample test + verify block)

**Outcome (one sentence):** nextjs and react-native become runnable seeds (today docs-only/.gitkeep — verified P0, no package.json so npm/next/jest all fail). Each gets package.json + framework config + entrypoint + a sample test pulling the T4 (TASK-602) eslint/test config, plus dev/e2e make targets and the missing `verify:` block.

## Read First
- src/templates/nextjs/stack.yaml
- src/templates/react-native/stack.yaml
- src/templates/nestjs/scaffold/

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** nextjs, **When** `cos init` then `make lint-frontend`/`make build-frontend`/`make test-frontend`, **Then** they pass on package.json + next.config.ts + tsconfig.json + app/layout.tsx + app/page.tsx + a sample test.
**Given** react-native, **When** the same, **Then** package.json + App.tsx + jest.config.ts + @testing-library/react-native + a sample test run, and dev (expo) + e2e (maestro) make targets exist.
**Given** both stacks, **Then** the `verify:` per-glob block is present in stack.yaml.
**Then** `uv run pytest tests/test_template_scaffold.py -q` is green.

## Work Log
- 2026-06-27 [claude]: Edit package.json
- 2026-06-27 [claude]: Edit eslint.config.js
- 2026-06-27 [claude]: Edit tsconfig.json
- 2026-06-27 [claude]: Edit vitest.config.ts
- 2026-06-27 [claude]: Edit greeting.test.ts
- 2026-06-27 [claude]: Edit layout.tsx
- 2026-06-27 [claude]: Edit page.tsx
- 2026-06-27 [claude]: Edit greeting.ts
- 2026-06-27 [claude]: Edit package.json
- 2026-06-27 [claude]: Edit eslint.config.js
- 2026-06-27 [claude]: Edit tsconfig.json
- 2026-06-27 [claude]: Edit vitest.config.ts
- 2026-06-27 [claude]: Edit App.tsx
- 2026-06-27 [claude]: Edit greeting.ts
- 2026-06-27 [claude]: Edit greeting.test.ts
- 2026-06-27 [claude]: Edit stack.yaml
- 2026-06-27 [claude]: Edit stack.yaml
- 2026-06-27 [claude]: Edit package.json
- 2026-06-27 [claude]: Edit package.json
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit test_template_scaffold.py
- 2026-06-27 [claude]: Edit test_template_scaffold.py
- 2026-06-27 [claude]: Edit test_template_scaffold.py
- 2026-06-27 [claude]: nextjs + react-native bootable seeds, self-contained per stack-root (mirrors 605/606): nextjs src/frontend/ =…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
