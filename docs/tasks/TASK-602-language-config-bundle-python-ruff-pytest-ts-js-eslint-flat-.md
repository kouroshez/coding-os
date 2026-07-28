---
id: TASK-602
title: "language config bundle: python (ruff+pytest) + ts/js (eslint flat + prettier + vitest)"
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
depends_on: [TASK-598]
blocked_by: []
references: []
---
# TASK-602: language config bundle: python (ruff+pytest) + ts/js (eslint flat + prettier + vitest)

**Outcome (one sentence):** One reusable per-language toolchain-config bundle for the two biggest families — python (ruff lint+format, pytest config) and ts/js (ESLint v9 flat + Prettier/Biome + Vitest) — selected by stack.yaml `language:`. Frontend `lint` becomes `eslint . && tsc --noEmit` (keep typecheck, ADD the real linter). Config files live in scaffold/ (consumer-editable); rationale lives in the skill anatomy, never duplicated.

## Read First
- docs/playbooks/template-authoring.md
- src/templates/react-native/scaffold/src/mobile/.eslintrc.cjs
- src/templates/fastapi/stack.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a python-family stack (django/fastapi/python), **When** the bundle is applied, **Then** scaffold ships pyproject [tool.ruff] + pytest config and `make lint`/`make test` run a real configured tool, not bare defaults.
**Given** a ts/js stack (angular/astro/nestjs/node-express/nextjs/svelte/vue-nuxt/react-native/typescript-plain), **When** the bundle is applied, **Then** it ships eslint.config.js (flat v9) + a prettier/biome config + vitest.config.ts, and the `lint` script is `eslint . && tsc --noEmit`.
**Then** `uv run pytest tests/test_template_scaffold.py -q` is green.

## Work Log
- 2026-06-27 [claude]: Edit pyproject.toml
- 2026-06-27 [claude]: Edit eslint.config.js
- 2026-06-27 [claude]: Edit .prettierrc.json
- 2026-06-27 [claude]: Edit vitest.config.ts
- 2026-06-27 [claude]: Edit tsconfig.json
- 2026-06-27 [claude]: Edit main.py
- 2026-06-27 [claude]: Edit update_lint_targets.py
- 2026-06-27 [claude]: Edit stack.yaml
- 2026-06-27 [claude]: Edit stack_lint.py
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit template-authoring.md
- 2026-06-27 [claude]: Edit test_template_scaffold.py
- 2026-06-27 [claude]: Deliberation: chose ONE shared per-language bundle at _base/lang/<language>/ overlaid by _overlay_scaffold…
- 2026-06-27 [claude]: Done: shipped _base/lang/python/pyproject.toml (ruff+pytest) + typescript/{eslint.config.js flat v9,…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-27 [claude]: committed 52bc7a70 · 19 files
