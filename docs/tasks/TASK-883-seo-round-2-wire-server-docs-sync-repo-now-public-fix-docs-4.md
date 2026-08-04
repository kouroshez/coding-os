---
id: TASK-883
title: "SEO round 2: wire server docs sync (repo now public), fix docs 404s, sitemap+analytics audit"
swimlane: docs
kind: chore
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
# TASK-883: SEO round 2: wire server docs sync (repo now public), fix docs 404s, sitemap+analytics audit

## Outcome

Production serves the full synced docs set (Reference sections stop 404ing), the auto-generated sitemap grows to include them, and the analytics/search-console picture is decided and documented; full-site link/status audit passes now that real users are arriving.

## Read First

- cos-website: src/frontend/scripts/sync-docs.mjs (source resolution + wipe behavior)
- cos-website: src/frontend/Dockerfile + .dockerignore (content/docs excluded today)
- cos-website: app/sitemap.ts (docs pages feed the sitemap via loadDocsIndex)

## Acceptance

- Given the public kouroshez/coding-os repo cloned on ca-server01, when deploy.sh runs, then content/docs is host-synced into the build and a docs Reference page (e.g. /docs/playbooks/pr-workflow) returns 200 on production.
- Given the deployed site, when fetching /sitemap.xml, then it lists the synced docs routes (count >> 23).
- Given the in-container prebuild with no docs source, when pnpm build runs, then previously synced content/docs is preserved (not wiped to an empty index).

## Work Log
- 2026-08-04 [claude]: Edit sync-docs.mjs
- 2026-08-04 [claude]: Edit .dockerignore
- 2026-08-04 [claude]: Edit Dockerfile
- 2026-08-04 [claude]: Edit deploy.sh
- 2026-08-04 [claude]: Edit Dockerfile
- 2026-08-04 [claude]: Edit deploy.sh
- 2026-08-04 [claude]: Docs sync wired end-to-end now repo is public: deploy.sh clones kouroshez/coding-os + host-syncs via node container;…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
