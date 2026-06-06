---
id: TASK-200
title: "Integrate brand logo \u2014 trim/optimize logo.png (keep transparency) + logomark in header + favicon"
swimlane: core
kind: feature
epic: ui-design-system
labels: [ui, brand, logo, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-200: Integrate brand logo — trim/optimize logo.png (keep transparency) + logomark in header + favicon

**Outcome (one sentence):** Use the user's brand logo (a line-art brain + terminal >_ prompt in iris, transparent PNG at src/core/web/ui/src/assets/logo.png, currently 1024x1536 with heavy transparent padding). Trim the transparent padding to the content bbox, pad to a square with a small even margin, optimize the PNG (cap ~512px) — preserving the transparent background exactly. Render it as the logomark in the AppShell header next to a now-MONOCHROME 'Coding OS' wordmark (logomark carries the iris brand, wordmark text uses --cos-text — the enterprise pattern). Wire it as the favicon. make ui-build green.

## Read First
- src/core/web/ui/src/layout/AppShell.tsx
- src/core/web/ui/index.html
- src/core/web/ui/src/assets/logo.png

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub header and a browser tab, in light and dark mode
- **When** the app renders
- **Then** the trimmed transparent brand logomark (brain + `>_`, 512² square, alpha preserved) shows next to a monochrome `--cos-text` "Coding OS" wordmark in the AppShell header, the same logo is wired as the favicon, the transparent background is intact (no white box), and `make ui-build` is green

## Work Log
