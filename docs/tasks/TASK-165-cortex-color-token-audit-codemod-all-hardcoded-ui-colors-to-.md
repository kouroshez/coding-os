---
id: TASK-165
title: "Cortex color-token audit — codemod all hardcoded UI colors to --cos-* tokens (exhaustive)"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, design-system, tokens, audit, exhaustive, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-165: Cortex color-token audit — codemod all hardcoded UI colors to --cos-* tokens (exhaustive)

**Outcome (one sentence):** Exhaustive sweep: NO UI color is hardcoded anywhere — every Tailwind named-color utility (237: rose/red→cos-err, emerald/green→cos-ok, amber/orange→cos-warn, sky/blue→cos-info, violet/fuchsia/indigo/purple→cos-brand, cyan/teal→cos-live, zinc/gray/slate→cos surface/text/border by shade) and every mappable inline component hex (69, excluding canonical canvas maps) is replaced with a --cos-* token so the whole palette is changeable from one place (cos-board-tokens.css). Done via a documented, repeatable codemod (the mapping IS the enterprise rule), then build + grep verified to 0 violations across all *.tsx, with the canonical canvas/Sigma color maps (node-colors.ts, graph-adapter.ts, useSigma.ts, agentPresenceVisuals.ts) explicitly exempted (WebGL cannot read CSS vars; they are already centralized single-source maps). make ui-build green.

## Read First
- src/core/web/ui/src/index.css
- src/core/web/ui/public/cos-board-tokens.css
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub SPA after the codemod
- **When** grepping every `*.tsx`/`*.ts` for Tailwind named-color utilities and mappable inline component hex
- **Then** the violation count is 0 (every UI color resolves from a `--cos-*` token, so the whole palette changes from cos-board-tokens.css alone), the ONLY remaining hex are the documented canonical canvas/Sigma maps (node-colors.ts, graph-adapter.ts, useSigma.ts, agentPresenceVisuals.ts — WebGL can't read CSS vars), `make ui-build` is green, and the codemod + mapping are recorded as the repeatable enterprise rule

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
- 2026-06-05 [claude]: Shipped (commit 29c565c, 32 files): repeatable codemod (/tmp/color_codemod.py) converted 236 Tailwind named-color utilit
