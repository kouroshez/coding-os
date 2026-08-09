---
id: TASK-888
title: "Clear remaining Dependabot alerts \u2014 Hub UI lockfile + nestjs/laravel/rails template floors"
swimlane: core
kind: security
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-04
completed: 2026-08-04
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---
# TASK-888: Clear remaining Dependabot alerts — Hub UI lockfile + nestjs/laravel/rails template floors


**Outcome (one sentence):** Zero open Dependabot alerts — the Hub UI lockfile's 25 transitive advisories are resolved and every advisory-flagged template floor is raised past its patched version.

## Read First
- `src/core/web/ui/package-lock.json` — 25 open transitive alerts (brace-expansion, js-yaml, postcss, react-router, undici)
- `src/templates/{nestjs,laravel,rails}/scaffold/src/backend/` — the three flagged manifests
- `docs/engineering/hub-architecture.md` — what the UI bundle ships into

## Threat Model
- **Attacker:** a crafted input reaching a vulnerable transitive parser, or a malicious page against a running dev server.
- **Asset:** the Hub process (serves every registered project's board, graph and cognition data) and any project scaffolded from the flagged templates.
- **Vector:** `undici`/`react-router`/`postcss`/`js-yaml`/`brace-expansion` advisories in the Hub's own lockfile; `laravel/framework < 12.61.1`, `puma < 7.2.1`, `@nestjs/core <= 11.1.17` in shipped scaffolds.
- **Mitigation:** update the lockfile transitives and raise the declared template floors past each patched version.
- **Residual risk:** template floors do not retro-fix an already-scaffolded project with a committed lockfile; that is the consumer's own dependency-update duty.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub UI and each touched template,
- **When** the real toolchain runs (`npm ci` + UI build/test; `npm install` + test/lint for nestjs; `composer validate/update` for laravel; `bundle lock` for rails),
- **Then** each succeeds and `gh api .../dependabot/alerts?state=open` returns zero.

## Work Log
- 2026-08-05 [claude]: Hub UI: npm audit fix cleared 23 of 25 lockfile advisories; react-router-dom raised to the patched ^7.18.0 (installed…
- 2026-08-05 [claude]: Status transitioned to complete via cos task-done.
