---
id: TASK-657
title: "svelte vite.config wrong import + vue-nuxt vitest/vite major skew break their lint gates"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [svelte, vue-nuxt, drift, wave-2, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-657: svelte vite.config wrong import + vue-nuxt vitest/vite major skew break their lint gates

**Outcome (one sentence):** svelte-sveltekit's vite.config.ts imports sveltekit from @sveltejs/kit/vite (not @sveltejs/vite-plugin-svelte, which only exports svelte), and vue-nuxt pins vitest to a major whose bundled vite matches nuxt's hoisted vite — so `npm run lint` (svelte-check / nuxt typecheck) reports 0 errors on a fresh init.

## Read First
- src/templates/svelte-sveltekit/scaffold/src/frontend/vite.config.ts
- src/templates/vue-nuxt/scaffold/src/frontend/package.json
- src/templates/vue-nuxt/scaffold/src/frontend/vitest.config.ts

## Repro Steps
cos init --template svelte-sveltekit; cd src/frontend; npm i; npm run lint → svelte-check: 'vite.config.ts:2 @sveltejs/vite-plugin-svelte has no exported member sveltekit (did you mean svelte?)'. cos init --template vue-nuxt; cd src/frontend; npm i; npm run lint (nuxt typecheck) → 'vitest.config.ts:5 TS2769: No overload matches this call ... two different vite Plugin types' because vitest@^1.4 bundles vite@5 while nuxt + @vitejs/plugin-vue@^5 hoist vite@6. Both pass `npm test` (vitest resolves vite at runtime) but fail the typecheck/lint gate.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fresh svelte-sveltekit scaffold, **When** npm run lint runs, **Then** 0 errors. **Given** a fresh vue-nuxt scaffold, **When** npm run lint runs, **Then** 0 errors. **Given** both scaffolds, **When** npm test runs, **Then** all tests pass.

## Work Log
- 2026-06-30 [claude]: svelte vite.config: sveltekit from @sveltejs/kit/vite; vue-nuxt vitest ^3.0.0 (dedupes vite@6); golden recaptured;…
