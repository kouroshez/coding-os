---
id: TASK-879
title: "Wire GitHub Sponsors: FUNDING.yml in coding-os + donate-page embeds on site"
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
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-879: Wire GitHub Sponsors: FUNDING.yml in coding-os + donate-page embeds on site

## Outcome

Sponsor button lives on the PUBLIC product repo (coding-os, not the private cos-website), and coding-os.dev/donate embeds the official GitHub Sponsors button + profile card iframes; FUNDING.yml removed from the private site repo; deployed and verified live.

## Read First

- cos-website: docs/ops/runbooks/go-live-checklist.md item 17 (funding rails, env-driven)
- cos-website: src/frontend/app/donate/page.tsx + components/sponsor-wall.tsx + lib/env.ts
- ca-server01: docs/runbooks/2026-08-02-phase2-stacks.md Addendum 8

## Acceptance

- Given the coding-os repo, when it is published on GitHub, then .github/FUNDING.yml points the Sponsor button at kouroshez.
- Given https://coding-os.dev/donate deployed, when loaded logged-out, then the GitHub Sponsors rail shows the official /button iframe and a "Sponsor via GitHub" section shows the /card iframe with no horizontal page scroll.
- Given the private cos-website repo, when listing tracked files, then no FUNDING.yml remains.

## Work Log
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: commit f7a4a50e21 — chore(repo): FUNDING.yml — GitHub Sponsors button for the public repo
- 2026-08-04 [claude]: FUNDING.yml moved to the public product repo (coding-os f7a4a50e) and removed from private cos-website; donate page…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
