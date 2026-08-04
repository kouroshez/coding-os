---
id: TASK-001
title: "fix(doctor): ID collision + broken symlink crash + new health checks C45-C48"
swimlane: cli
kind: bug
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-05-15
started: 2026-05-14
completed: 2026-05-14
agent_session: ses-claude-20260514-212614-447e
depends_on: []
blocked_by: []
references: []
---
# TASK-001: fix(doctor): ID collision + broken symlink crash + new health checks C45-C48

**Outcome (one sentence):** `cos doctor` output has unique check IDs, never crashes on broken hook symlinks, and surfaces 4 previously invisible health signals (agent identity, adapter dir symlinks, consumer project hooks, Rule-3 compliance).

## Read First
- src/cli/doctor.py — C7 adapter check, run_doctor orchestration
- src/cli/doctor_board.py — board checks currently using colliding IDs C24-C27
- src/cli/doctor_graph.py — C19 WARN without remediation hint
- src/cli/doctor_extras.py — run_extra_checks entry point

## Repro Steps
1. Run `cos doctor` and observe C24 appears twice (graph + board)
2. Create a broken symlink in .claude/hooks/ → `cos doctor` crashes in C7 (`stat()` on broken symlink)
3. `cos doctor` shows C19 WARN with no fix command
Expected: unique IDs, no crash, actionable WARNs, 4 new checks
Actual: ID collision, potential crash, silent WARN, gaps in coverage

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos doctor` runs on this meta-repo
- **When** all checks complete
- **Then** no check ID appears more than once, board uses C50-C53, C19 WARN includes `cos graph-reindex`, C45-C48 all appear and pass

## Work Log
- 2026-05-15: fixed board ID collision (C50-C53), C19 remediation hint, C7 symlink crash, added C45-C48 checks; 49 CLI tests pass
- 2026-05-15 [claude]: Status transitioned to complete via cos task-done.
- 2026-07-12 [claude]: Edit build-checklist.md
- 2026-07-12 [claude]: Edit package.json
- 2026-07-12 [claude]: Edit tsconfig.json
- 2026-07-12 [claude]: Edit postcss.config.mjs
- 2026-07-12 [claude]: Edit eslint.config.mjs
- 2026-07-12 [claude]: Edit .gitignore
- 2026-07-12 [claude]: Edit next.config.ts
- 2026-07-12 [claude]: Edit globals.css
- 2026-07-12 [claude]: Edit utils.ts
- 2026-07-12 [claude]: Edit env.ts
- 2026-07-12 [claude]: Edit layout.tsx
- 2026-07-12 [claude]: Edit theme-provider.tsx
- 2026-07-12 [claude]: Edit analytics-provider.tsx
- 2026-07-12 [claude]: Edit button.tsx
- 2026-07-12 [claude]: Edit card.tsx
- 2026-07-12 [claude]: Edit badge.tsx
- 2026-07-12 [claude]: Edit input.tsx
- 2026-07-12 [claude]: Edit textarea.tsx
- 2026-07-12 [claude]: Edit label.tsx
- 2026-07-12 [claude]: Edit dropdown-menu.tsx
- 2026-07-12 [claude]: Edit tabs.tsx
- 2026-07-12 [claude]: Edit skeleton.tsx
- 2026-07-12 [claude]: Edit copy-button.tsx
- 2026-07-12 [claude]: Edit theme-toggle.tsx
- 2026-07-12 [claude]: Edit client.ts
- 2026-07-12 [claude]: Edit admin.ts
- 2026-07-12 [claude]: Edit auth.ts
- 2026-07-12 [claude]: Edit server.ts
- 2026-07-12 [claude]: Edit header.tsx
- 2026-07-12 [claude]: Edit user-menu.tsx
- 2026-07-12 [claude]: Edit footer.tsx
- 2026-07-12 [claude]: Edit header.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit not-found.tsx
- 2026-07-12 [claude]: Edit error.tsx
- 2026-07-12 [claude]: Edit icons.tsx
- 2026-07-12 [claude]: Edit header.tsx
- 2026-07-12 [claude]: Edit header.tsx
- 2026-07-12 [claude]: Edit analytics-provider.tsx
- 2026-07-12 [claude]: Edit eslint.config.mjs
- 2026-07-12 [claude]: Edit theme-toggle.tsx
- 2026-07-12 [claude]: Edit 0001_extensions_helpers.sql
- 2026-07-12 [claude]: Edit 0002_profiles_moderators.sql
- 2026-07-12 [claude]: Edit 0003_prompts.sql
- 2026-07-12 [claude]: Edit 0004_blog.sql
- 2026-07-12 [claude]: Edit 0005_ops.sql
- 2026-07-12 [claude]: Edit seed.sql
- 2026-07-12 [claude]: Edit check-rls.sql
- 2026-07-12 [claude]: Edit check-service-role.sh
- 2026-07-12 [claude]: Edit middleware.ts
- 2026-07-12 [claude]: Edit types.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit login-form.tsx
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit account-form.tsx
- 2026-07-12 [claude]: Edit actions.ts
- 2026-07-12 [claude]: Edit landing-sections.tsx
- 2026-07-12 [claude]: Edit queries.ts
- 2026-07-12 [claude]: Edit queries.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit anon.ts
- 2026-07-12 [claude]: Edit markdown.ts
- 2026-07-12 [claude]: Edit variables.ts
- 2026-07-12 [claude]: Edit wilson.ts
- 2026-07-12 [claude]: Edit prompt-card.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit variable-fill.tsx
- 2026-07-12 [claude]: Edit vote-button.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit report-button.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit turnstile.tsx
- 2026-07-12 [claude]: Edit actions.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit submit-form.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit actions.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit actions.ts
- 2026-07-12 [claude]: Edit markdown.ts
- 2026-07-12 [claude]: Edit markdown.ts
- 2026-07-12 [claude]: Edit markdown.ts
- 2026-07-12 [claude]: Edit markdown.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit discourse.ts
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit sponsor-wall.tsx
- 2026-07-12 [claude]: Edit sync-docs.mjs
- 2026-07-12 [claude]: Edit docs.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit docs-search.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit route.ts
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit sitemap.ts
- 2026-07-12 [claude]: Edit robots.ts
- 2026-07-12 [claude]: Edit manifest.ts
- 2026-07-12 [claude]: Edit vitest.config.ts
- 2026-07-12 [claude]: Edit server-only-stub.ts
- 2026-07-12 [claude]: Edit wilson.test.ts
- 2026-07-12 [claude]: Edit variables.test.ts
- 2026-07-12 [claude]: Edit discourse-sso.test.ts
- 2026-07-12 [claude]: Edit markdown.test.ts
- 2026-07-12 [claude]: Edit sync-docs.test.ts
- 2026-07-12 [claude]: Edit markdown.test.ts
- 2026-07-12 [claude]: Edit ci.yml
- 2026-07-12 [claude]: Edit playwright.config.ts
- 2026-07-12 [claude]: Edit smoke.spec.ts
- 2026-07-12 [claude]: Edit smoke.spec.ts
- 2026-07-12 [claude]: Edit project-description.md
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit page.tsx
- 2026-07-12 [claude]: Edit docs-search.tsx
- 2026-08-04 [claude]: Edit dor_check.py
- 2026-08-04 [claude]: Edit dor_check.py
- 2026-08-04 [claude]: Edit dor_check2.py
- 2026-08-04 [claude]: Edit main.py
- 2026-08-04 [claude]: Edit main.py
- 2026-08-04 [claude]: Edit check_quickstart.py
