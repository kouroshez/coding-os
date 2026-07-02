---
name: sample-test-lint-gate-blindspot
description: "Scaffold sample tests must be run through the stack's REAL lint+test gate, not just checked for existence"
metadata: 
  node_type: memory
  type: project
  originSessionId: d19e577b-5df3-4679-9f38-6c88a7f58fcd
---

`cos stack-lint` only verifies a sample-test **file exists** under `scaffold/` — it does NOT run the stack's real lint/test gate. That blind spot let three "passes-its-test-runner-but-fails-the-lint-gate" bugs ship undetected (TASK-655/656/657, 2026-06-30):

- astro `problem.test.ts` called an `APIRoute` (`Response | Promise<Response>`) without `await` → `astro check` errored, `vitest` passed.
- svelte `vite.config.ts` imported `sveltekit` from `@sveltejs/vite-plugin-svelte` (only exports `svelte`; it lives in `@sveltejs/kit/vite`) → `svelte-check` errored, `vitest` passed.
- vue-nuxt `vitest@^1` bundled vite@5 vs nuxt's vite@6 → `nuxt typecheck` TS2769, `vitest` passed.

**Why:** stacks have TWO gates (`npm run lint` = tsc/astro-check/svelte-check/nuxt-typecheck, and `npm test` = the runner). A test can pass the runner while breaking the typecheck gate, which is what a real `cos init` consumer hits first.

**How to apply:** to trust a scaffold sample test, actually run it — `cos init` into a sandbox, `npm install`, then BOTH `npm run lint` and `npm test`. Parallelize across stacks with a Workflow (one agent per stack in an isolated sandbox; see the `frontend-sample-test-gate-sweep` run). Also grep the rendered project for leftover `{{PROJECT_NAME}}`/`{{DATE}}` — the renderer (`src/cli/main.py::_overlay_scaffold`, TASK-656) now substitutes any UTF-8 text file instead of a fixed extension allowlist, but a new binary type or encoding edge could regress it.
