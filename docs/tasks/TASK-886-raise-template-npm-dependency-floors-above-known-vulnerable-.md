---
id: TASK-886
title: "Raise template npm dependency floors above known-vulnerable ranges"
swimlane: templates
kind: security
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-04
completed: 2026-08-04
agent_session: ses-claude-20260804-151316-9ae7
depends_on: []
blocked_by: []
references: []
---
# TASK-886: Raise template npm dependency floors above known-vulnerable ranges


**Outcome (one sentence):** Every shipped template package.json declares a dependency floor that excludes known-critical versions, so a fresh `npm install` in a scaffolded project cannot resolve a vulnerable release.

## Read First
- `src/templates/*/scaffold/src/*/package.json` — the shipped floors
- `docs/playbooks/template-authoring.md` — template contract
- `docs/engineering/stack-maturity.md` — per-stack verification bar

## Threat Model
- **Attacker:** any site a developer visits while a scaffolded project's dev/test server is listening on localhost.
- **Asset:** the developer's workstation — source tree, environment, credentials reachable from the dev process.
- **Vector:** GHSA-9crc-q9x8-hgqq / GHSA-5xrq-8626-4rwp — Vitest's API/UI server accepts cross-origin requests, allowing arbitrary file read and remote code execution on every vitest below 3.2.6; the Next.js advisories in the same alert set cover SSRF, cache poisoning and middleware auth bypass below 15.5.21.
- **Mitigation:** raise each template's declared floor above the patched version. A floor — not a pin — keeps the "always latest" template contract while making the vulnerable range unresolvable.
- **Residual risk:** an existing project with a stale lockfile is unaffected by a template change; that is a `cos update` concern, out of scope here.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project scaffolded from each touched template,
- **When** `npm install` and the template's own `npm test` / `npm run lint` run against the new floors,
- **Then** both succeed and no declared range admits a version listed in the repo's open Dependabot alerts.

## Work Log
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit verify_floors.sh
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit package.json
- 2026-08-04 [claude]: Edit .gitignore
- 2026-08-04 [claude]: Edit test_golden_parity.py
- 2026-08-04 [claude]: Edit scaffold-verify.yml
- 2026-08-04 [claude]: commit 5143d3aee1 — fix(templates): npm floors above known-vulnerable ranges + repair the SvelteKit toolchain
- 2026-08-04 [claude]: commit d07bdc526d — ci(scaffold-verify): drop the svelte-kit sync workaround now the template self-prepares
- 2026-08-04 [claude]: Raised vitest floors to >=3.2.6 across nextjs/react-native/nestjs/vue-nuxt and next to >=15.5.21. Found the SvelteKit…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
