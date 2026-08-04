---
id: TASK-872
title: "Seed Discourse community content + correct adapter-parity claims (forum + site)"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-153956-0acf
depends_on: []
blocked_by: []
references: []
---
# TASK-872: Seed Discourse community content + correct adapter-parity claims (forum + site)

## Outcome

community.coding-os.dev launches non-empty and truthful: ≥20 substantive staff-authored topics (KB-style Q&A, RFCs, open calls, founder Show & Tell — no staged dialogues), categories matching the site's /community hub slugs, Solved + topic-voting plugins enabled, sitemap live; outdated "Codex Bash-only" claims corrected on the forum AND on coding-os.dev (installation, concepts, llms.txt).

## Read First

- cos-website repo: docs/ops/runbooks/community-seeding.md (spec + launch gate)
- ca-server01 repo: scripts/discourse-seed.rb (idempotent seeder, SSOT for forum content)
- docs/adapters/codex.md § Capability Matrix (current parity truth)

## Acceptance

- Given a logged-out browser, when visiting community.coding-os.dev, then ≥20 substantive topics render across Announcements / Q&A / Ideas / Show & Tell / Prompt requests / Docs & Feedback with the exact hub slugs (q-a, ideas, show-and-tell, prompt-requests).
- Given the seeded content, when reading any adapter claim, then it matches docs/adapters/codex.md (Claude Code + Codex both full parity) and no staged founder-asks-team dialogues exist.
- Given coding-os.dev/docs/installation, /docs/concepts and /llms.txt, when deployed via CI, then no "Bash-event hooks only" claim remains.

## Work Log
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit route.ts
- 2026-08-04 [claude]: Edit adapter-support.ts
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit community-seeding.md
- 2026-08-04 [claude]: Edit community-seeding.md
- 2026-08-04 [claude]: Edit build-checklist.md
- 2026-08-04 [claude]: Seeded production Discourse (26 content topics, 6 categories matching hub slugs, Solved+voting enabled, @codingos…
- 2026-08-04 [claude]: Verified live after manual deploy (GitHub Actions billing-blocked — operator must fix billing): /docs/adapters matrix…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
