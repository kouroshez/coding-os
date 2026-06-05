---
id: TASK-163
title: "Cortex token enrich (Live/Ember/focus) + Roles page color+display alignment"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, design-system, cognition, roles, ready]
status: testing
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-163: Cortex token enrich (Live/Ember/focus) + Roles page color+display alignment

**Outcome (one sentence):** Adopt the 3 genuinely-better token ideas from the external review into the base palette: --live (Pulse Cyan, for SSE/agent-live) distinct from info, --signature (Ember orange, reserved for logo/brand mark), and a --focus-ring (violet) distinct from the brand so focus stands out on brand-colored elements; wire *:focus-visible to it and expose --cos-live/--cos-signature/--cos-focus aliases. Then fix the Roles page (RolesPage.tsx): replace every hardcoded emerald/amber/rose Tailwind class with the new --cos-ok/warn/err status tokens, and rebuild the flat formula-id "Composed Chain" list into a real visual numbered pipeline (connector line + step number + prettified role name + active-step highlight). Harmonize TraceTimeline event colors + agent live presence onto the new tokens. make ui-build green.

## Read First
- src/core/web/ui/src/pages/RolesPage.tsx
- src/core/web/ui/src/features/cognition/TraceTimeline.tsx
- src/core/web/ui/public/cos-board-tokens.css
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub renders in dark mode (default)
- **When** any page shows a live/connection state, a focus ring, or the Roles page
- **Then** the palette exposes `--cos-live` (cyan), `--cos-signature` (ember), `--cos-focus` (violet) tokens with real consumers (focus-visible → violet, agent-live → cyan, logo → ember), the Roles page uses only `--cos-*` status tokens (no hardcoded emerald/amber/rose), the Composed Chain renders as a visual numbered pipeline (connector + step number + role name + active highlight), TraceTimeline event colors are harmonized onto the Cortex palette, and `make ui-build` is green

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
