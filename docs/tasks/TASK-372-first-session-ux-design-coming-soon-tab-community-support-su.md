---
id: TASK-372
title: "First-session UX + Design coming-soon tab + Community/Support surface"
swimlane: core
kind: feature
epic: I-polish
labels: [wave-5, onboarding-program, ready]
status: archive
priority: P2
appetite: 2d
created: 2026-06-11
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-364]
blocked_by: []
references: []
---
# TASK-372: First-session UX + Design coming-soon tab + Community/Support surface

**Outcome (one sentence):** A fresh project's first agent session hits no doc-anchor wall (starter anchors seeded); workspace gains a Design tab with a polished coming-soon screen + ADR for the future design module; Hub About/footer carries GitHub repo link, star/follow CTA and GitHub Sponsors/BMC/crypto support links (also in README) — outside the onboarding path.

## Read First
- src/core/web/ui/src/App.tsx
- src/core/hooks/enforce-doc-anchor.sh
- README.md
- docs/architecture/

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a freshly scaffolded project, **When** an agent performs its first legitimate code edit following AGENTS.md, **Then** no doc-anchor BLOCK fires from empty/TODO starter docs (seeded anchors verified by an end-to-end init+edit test).
- **Given** the workspace tabs, **When** Design is clicked, **Then** a polished coming-soon screen renders (consistent with hub theme, a11y-checked) and an ADR documents the design-module vision registered as a future module id.
- **Given** the Hub footer/About, **When** rendered, **Then** GitHub repo link + star CTA + Sponsors/BMC/crypto links are present, none of them appear inside the onboarding wizard, and README carries the same support section.
- **Given** the UI build + docs, **When** `make ui-build` and `make docs-lint` run, **Then** both green.

## Work Log
- 2026-06-15 [claude]: Next-session plan (handoff): 3 separable slices — (1) seed starter doc-anchors so a fresh project's FIRST code edit does
- 2026-06-15 [claude]: Edit support-links.ts
- 2026-06-15 [claude]: Edit SupportFooter.tsx
- 2026-06-15 [claude]: Edit SupportFooter.test.tsx
- 2026-06-15 [claude]: Edit AppShell.tsx
- 2026-06-15 [claude]: Edit AppShell.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-15 [claude]: Edit README.md
- 2026-06-15 [claude]: Edit DesignComingSoon.test.tsx
- 2026-06-15 [claude]: commit 46f8dc159b — feat(hub): Design coming-soon tab + ADR-0008 + support/community footer (TASK-372)
- 2026-06-15 [claude]: Edit runtime_paths.yaml
- 2026-06-15 [claude]: Edit capture_golden.py
- 2026-06-15 [claude]: Edit test_golden_parity.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit enforce-doc-anchor.sh
- 2026-06-15 [claude]: Edit test_fresh_project_anchor.py
- 2026-06-15 [claude]: commit 31a15f9cbe — feat: fresh-project first-edit grace clears the doc-anchor wall (TASK-372)
- 2026-06-15 [claude]: commit b16ee4baa4 — test(golden): recapture fixtures after _base playbooks, skill bundles + anchor grace
