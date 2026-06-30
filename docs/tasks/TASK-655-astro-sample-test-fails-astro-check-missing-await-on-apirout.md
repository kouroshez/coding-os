---
id: TASK-655
title: "astro sample test fails astro check (missing await on APIRoute) + global crypto needs Node>=20"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [astro, drift, wave-2, lint-gate, ready]
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
# TASK-655: astro sample test fails astro check (missing await on APIRoute) + global crypto needs Node>=20

**Outcome (one sentence):** A fresh astro scaffold passes its own lint gate (`npm run lint` == `astro check`, 0 errors) and `npm test` (vitest): the health-endpoint test awaits GET/ALL (APIRoute returns Response|Promise<Response>), and package.json pins node>=20.3.0 because problem.ts's global crypto.randomUUID() is unflagged only since Node 19.

## Read First
- src/templates/astro/scaffold/src/frontend/src/lib/problem.test.ts
- src/templates/astro/scaffold/src/frontend/package.json
- src/templates/astro/scaffold/src/frontend/src/lib/problem.ts

## Repro Steps
In a fresh astro scaffold run `cd src/frontend && npm i && npm run lint`: astro check reports 6 ts(2339) errors — `Property 'status'/'headers'/'json' does not exist on type 'Response | Promise<Response>'` at src/lib/problem.test.ts (GET/ALL called without await). Separately, problem.ts calls bare `crypto.randomUUID()`, which throws `crypto is not defined` on Node 18 (astro's listed minimum) where the Web Crypto global is behind --experimental-global-webcrypto until Node 19.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fresh astro scaffold, **When** `npm run lint` (astro check) runs, **Then** 0 errors/0 warnings. **Given** the same scaffold, **When** `npm test` (vitest) runs, **Then** all tests pass. **Given** a Node<20.3 environment, **When** npm install runs, **Then** the engines field warns the runtime is unsupported.

## Work Log
- 2026-06-30 [claude]: await GET/ALL in problem.test.ts (APIRoute=Response|Promise); engines node>=20.3.0 (global crypto unflagged since…
