---
id: TASK-204
title: "Brand finish \u2014 iris-50..900 primitive scale + drop dead handwriting fonts from index.html"
swimlane: core
kind: chore
epic: ui-design-system
labels: [ui, design-system, brand, tokens, ready]
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
# TASK-204: Brand finish — iris-50..900 primitive scale + drop dead handwriting fonts from index.html

**Outcome (one sentence):** Add the full Iris brand ramp --iris-50..900 as theme-independent primitive tokens in cos-board-tokens.css :root (so custom icons/logo reference one canonical scale; --iris-600 = the logo weight) and document the ramp in design-system.md §3. Remove the now-dead handwriting fonts (Caveat, Kalam, Permanent Marker) from the index.html Google Fonts link — they were de-stickified out of every component, so loading them is wasted payload. make ui-build green.

## Work Log
