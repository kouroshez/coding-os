---
id: TASK-195
title: "Header logo \u2192 brand iris (drop Ember signature) \u2014 unify wordmark with buttons"
swimlane: core
kind: chore
epic: ui-design-system
labels: [ui, design-system, brand, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-195: Header logo → brand iris (drop Ember signature) — unify wordmark with buttons

**Outcome (one sentence):** The 'Coding OS' wordmark uses the brand --cos-accent (iris) so the logo matches the buttons/nav instead of the Ember orange that read as a mismatch. Remove the now-unused --signature/--cos-signature token (its only consumer was the wordmark) from cos-board-tokens.css (both themes) + index.css + design-system.md §3, keeping the token system clean (no dead token). make ui-build green.

## Work Log
