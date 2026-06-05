<!-- doc-header
title: Cortex Design System — Hub UI palette, tokens, typography
purpose: SSOT for the coding-os Hub UI visual language (colors, type, spacing, motion, a11y).
owner: core/web
related: hub-architecture.md, ../../src/core/skills/react-vite-hub/SKILL.md
-->

# Cortex Design System

SSOT for the coding-os Hub UI visual language. Every color, type ramp,
spacing unit, radius, elevation and motion value the SPA renders comes
from here. Components NEVER hardcode hex — they read semantic tokens
(`var(--cos-*)`). Editing a value here + the two token files it maps to
(`src/core/web/ui/public/cos-board-tokens.css`,
`src/core/web/ui/src/index.css`) re-skins the whole product.

## 1. Design language — "Cortex"

The Hub is the **control plane for autonomous AI coding agents**. The
brand promise is *trust + authority + calm at high information density* —
an instrument cluster / mission-control, not a wiki or a terminal toy.

- **Dark-first.** Dark is the default theme; light is a complete,
  first-class alternative toggled from Settings. The knowledge graph (the
  product's hero artifact) reads like a constellation on a dark canvas.
- **Deep-tech, restrained glow.** A subtle Iris radial glow on the canvas
  and on live/active elements. No heavy gradients, no skeuomorphism.
- **Information design over decoration.** Status dots, sparklines, tabular
  numerals — never walls of monospace.

Reference anchors: Linear (calm precision), Vercel/Geist (restraint,
contrast), Radix Colors (accessible scales), OKLCH (perceptually-uniform
color, the 2026 standard for predictable contrast scaling).

## 2. Token architecture — 3 layers (DTCG)

```
PRIMITIVES        SEMANTIC                COMPONENT
(raw scales)  →   (intent, theme-keyed) → (element-specific, optional)
graphite-0..12    surface/canvas|panel…   button-bg, card-border
iris-1..12        text/primary|secondary…
status hues       brand/solid|hover|tint
```

- **Primitives** = raw OKLCH-derived scales. Never referenced by
  components directly.
- **Semantic** = the only layer components read. The SAME keys exist in
  both light and dark; only their values differ. This is the contract.
- **Component** = optional element-specific overrides; added only when a
  component needs a value the semantic layer doesn't express (Rule of
  Three before promoting).

Legacy variable names (`--ink`, `--board`, `--col-bg`, `--accent`,
`--sticky-*`) are kept as aliases of the semantic layer so existing
Tailwind components follow automatically — zero component rewrites.

## 3. Semantic tokens — Light + Dark

### Neutrals — "Graphite" (cool, low-chroma blue-gray)

| Token | Dark | Light | Use |
|---|---|---|---|
| `surface/canvas` | `#0A0B0E` | `#F6F7F9` | App background |
| `surface/panel` | `#111317` | `#FFFFFF` | Card / panel |
| `surface/raised` | `#171A20` | `#F1F3F6` | Panel-on-panel |
| `surface/overlay` | `#20242C` | `#FFFFFF`+shadow | Modal / menu |
| `surface/inset` | `#0C0E12` | `#ECEEF2` | Sunken (code, input) |
| `border/subtle` | `#20242B` | `#EBEDF1` | Hairline |
| `border/default` | `#2C313A` | `#D8DCE3` | Standard divider |
| `border/strong` | `#3A4150` | `#C0C6D0` | Emphasis / focus edge |
| `text/primary` | `#E7EAF0` | `#14161B` | Headings / body |
| `text/secondary` | `#A4ABB8` | `#4A5260` | Secondary text |
| `text/muted` | `#6C7480` | `#717784` | Labels / metadata |
| `text/disabled` | `#474E59` | `#A2A9B5` | Disabled |

OKLCH anchors: canvas-dark ≈ `oklch(.16 .006 265)`; text-primary-dark ≈
`oklch(.93 .006 265)`; each surface step ≈ +0.04 L.

### Brand — "Iris" (indigo-violet = the cognition signal)

| Token | Dark | Light |
|---|---|---|
| `brand/solid` | `#7C82F2` | `#5A5FE0` |
| `brand/hover` | `#9296F6` | `#4A4FD4` |
| `brand/text` | `#A7ABF8` | `#4338CA` |
| `brand/tint` (bg) | `rgba(124,130,242,.14)` | `#EEEFFE` |
| `brand/on-solid` | `#FFFFFF` | `#FFFFFF` |
| `focus/ring` | `#7C82F2` | `#5A5FE0` |

Brand ≈ `oklch(.66 .17 277)`. No purple gradient cliché — solid fills
only; glow reserved for live/active state.

### Status (foreground / tint background)

| | Dark fg / tint | Light fg / tint |
|---|---|---|
| `success` | `#3FB950` / `rgba(63,185,80,.14)` | `#1A7F37` / `#E6F4EA` |
| `warning` | `#E0A227` / `rgba(224,162,39,.14)` | `#9A6700` / `#FBF3E0` |
| `danger` | `#F2576B` / `rgba(242,87,107,.14)` | `#CF222E` / `#FCE9EA` |
| `info` | `#4C8DFF` / `rgba(76,141,255,.14)` | `#0969DA` / `#E7F0FE` |

## 4. Domain palettes (harmonized)

**Golden rule — graph node kinds:** all hues at **equal OKLCH lightness
(~0.72) and chroma (~0.14)**; only hue distinguishes a category. (The
legacy palette mixed near-black brown with hot orange → visual chaos.)

| Category | Nodes | Dark-canvas colors |
|---|---|---|
| Structure | folder/file/module | `#8A93A6` · `#6E7686` · `#565E6C` |
| Code-defs | class/method/function/var/interface | `#8B8FF4` · `#A6A9F7` · `#6E72E8` · `#B9BBF9` · `#595DD6` |
| API-surface | route/mcp_tool/tool/contract/event | `#4C9DF0` · `#3B82F6` · `#5FB0F5` · `#2E6FE0` · `#38BDF8` |
| Docs | doc_file/heading/frontmatter/external | `#2DD4BF` · `#34D399` · `#6EE7D6` · `#14B8A6` |
| Governance | rule/skill/hook/task | `#E0A82E` · `#D98AE0` · `#F2618F` · `#B98AF0` |
| Analysis | community / unknown | `#C77DFF` / `#6B7280` |

**Swimlane / task-kind chips:** no full pastel fills. A chip = hue tint
(~10% alpha on panel) + 3px left accent border + chip text in the hue's
dark step. Keeps color-coding, kills the kindergarten look.

**Priority:** P0 `danger` · P1 `warning` · P2 `#CA8A04` · P3 `text/muted`.

## 5. Typography

- **UI:** `Inter` (LTR), `Vazirmatn` (RTL). Weights 400/500/600. Headings
  `letter-spacing: -0.01em`.
- **Mono:** `JetBrains Mono` — scoped to code blocks, IDs, and metrics
  ONLY (with `font-variant-numeric: tabular-nums`). NOT for general UI.
- **Removed:** `Outfit` (unused noise).
- **Scale (px):** 12 · 13 · 14 · 16 · 20 · 24 · 30, line-height 1.5 body /
  1.25 headings.

## 6. Spacing · radius · elevation · motion

- **Spacing:** 8pt system — 2/4/8/12/16/24/32.
- **Radius:** `6` (chip/input) · `10` (card) · `14` (modal). One scale.
- **Elevation:** shadow-based, not hot borders. `0 1px 2px rgba(0,0,0,.4)`
  (raised) · `0 8px 24px rgba(0,0,0,.45)` (overlay) in dark; lighter
  alphas in light.
- **Motion:** 120ms (micro) / 200ms (panel) ease-out; ALL motion behind
  `@media (prefers-reduced-motion: reduce)`.

## 7. Accessibility + RTL

- Every text/surface pair meets **WCAG 2.2 AA** (≥4.5:1 body, ≥3:1 large).
- Every interactive element shows `focus-visible` ring (`focus/ring`,
  2px + 2px offset).
- RTL via **CSS logical properties** (`padding-inline`, `margin-inline`,
  `inset-inline`) — never `left`/`right`. `dir="auto"` per Persian block.

## 8. Theming mechanism

`data-theme="light|dark"` on `<html>`, synced by `ThemeProvider.tsx` from
`DesignTweaks.theme`. Default = `dark` (`DEFAULT_DESIGN_TWEAKS`). User
toggles in Settings; preference persists. Not a media query (explicit
control), with an optional follow-system mode planned.

## 9. Phased rollout (epic ui-design-system / TASK-149)

| Phase | Task | Scope | Commit |
|---|---|---|---|
| 0 | TASK-150 | Token rewrite (this doc → 2 CSS files) + dark default | 1 |
| 1 | — | Typography / spacing / elevation pass | 1 |
| 2 | — | Domain palettes (node-colors, kindColors, priority) | 1 |
| 3 | — | Primitives (`HubPrimitives.tsx`: Card/Badge/Table/Button) | 1 |
| 4 | — | Page-by-page (Dashboard → Graph → Board → Diagnostics) | per page |
| 5 | — | a11y audit + RTL logical props + motion system | 1 |

## 10. File map

| Concern | File |
|---|---|
| Primitive + semantic tokens (light/dark) | `src/core/web/ui/public/cos-board-tokens.css` |
| `--cos-*` semantic aliases + global CSS | `src/core/web/ui/src/index.css` |
| Theme default + sync | `src/core/web/ui/src/design/types.ts`, `design/ThemeProvider.tsx` |
| Graph node kind colors | `src/core/web/ui/src/lib/node-colors.ts` |
| Swimlane / task-kind chips | `src/core/web/ui/src/features/cos-board/kindColors.ts` |
| Priority / event colors | `src/core/web/ui/src/features/cos-board/CosBoardPage.tsx` |
| Shared primitives | `src/core/web/ui/src/layout/HubPrimitives.tsx` |
