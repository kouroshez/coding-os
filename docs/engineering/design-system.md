<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-05 -->
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
| `text/muted` | `#7D8593` | `#646A77` | Labels / metadata (AA-bumped) |
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

**Iris ramp (primitive scale, theme-independent — `cos-board-tokens.css`):**
`--iris-50` `#EEF0FE` · `100` `#E0E3FC` · `200` `#C6CBF9` · `300` `#A3ABF4`
· `400` `#7C82F2` · `500` `#5A5FE0` · `600` **`#4F46E5`** (logo / brand-mark
weight) · `700` `#4138C4` · `800` `#352DA0` · `900` `#2A2480`. Custom icons
and the logomark reference this single scale; the semantic `brand/*` tokens
above are picks from it (dark accent = 400, light accent = 500).

### Status (foreground / tint background)

| | Dark fg / tint | Light fg / tint |
|---|---|---|
| `success` | `#3FB950` / `rgba(63,185,80,.14)` | `#1A7F37` / `#E6F4EA` |
| `warning` | `#E0A227` / `rgba(224,162,39,.14)` | `#9A6700` / `#FBF3E0` |
| `danger` | `#F2576B` / `rgba(242,87,107,.14)` | `#CF222E` / `#FCE9EA` |
| `info` | `#4C8DFF` / `rgba(76,141,255,.14)` | `#0969DA` / `#E7F0FE` |

### Live · Signature · Focus (adopted from external review)

| Token | Dark | Light | Use |
|---|---|---|---|
| `live` | `#45D6E8` | `#0E7490` | SSE / agent-live / connection — distinct from `info` |
| `focus-ring` | `#A78BFA` | `#7C3AED` | violet — distinct from brand so focus pops on brand elements |

Consumers: `*:focus-visible` → `--cos-focus`; agent `working` presence → `--cos-live`. The "Coding OS" wordmark uses the brand `--cos-accent` (iris) for a unified logo (the Ember signature idea was dropped — the brand owner wanted the logo to match the buttons).

## 4. Domain palettes (harmonized)

**Golden rule — graph node kinds (v3, THEME-AWARE):** across families = a
**distinct hue region**; within a family = **bold lightness steps**. Two
palettes — v2's single mid-lightness set read washed/lifeless on the white
canvas:

- **DARK** (`NODE_COLORS`) — bright-saturated, pops on near-black.
- **LIGHT** (`NODE_COLORS_LIGHT`) — deep-saturated (ink-on-paper), pops on white.

Both with **warm structure** (amber/bronze/tan, not grey) so the canvas
reads alive. `kindColor(kind, theme)` picks the palette (defaults to the
live theme-store theme so DOM legends follow); `useSigma` recolors nodes in
place on a theme toggle (positions preserved). Families: structure=amber ·
code-defs=indigo→violet · refs=warm-slate · api=azure/cyan · docs=green/teal
· governance=magenta/pink · analysis=orange. **Verified:** every
common-vs-common kind pair ≥18 ΔE76 in BOTH palettes + every node separable
from its canvas — `src/core/web/ui/scripts/palette_dual.py`. Values SSOT:
`src/core/web/ui/src/lib/node-colors.ts`.

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

- Every text/surface pair meets **WCAG 2.2 AA** (≥4.5:1 body, ≥3:1 large) — **programmatically verified** in both themes (card text, kind badges, status, priority → 0 failures). Board cards must use `--cos-*` tokens, never sticky-era hardcoded hex.
- A persisted dark/light toggle lives in the **global AppShell header** (zustand `theme-store` → `data-theme` on `<html>`, applied before first paint; default dark).
- Every interactive element shows `focus-visible` ring (`focus/ring`,
  2px + 2px offset).
- RTL via **CSS logical properties** (`padding-inline`, `margin-inline`,
  `inset-inline`) — never `left`/`right`. `dir="auto"` per Persian block.

## 8. Theming mechanism

`data-theme="light|dark"` on `<html>`. **Single source of truth = the
zustand `theme-store`** (`src/store/theme-store.ts`): persists to
`localStorage` (guarded for absent/blocked storage) and applies
`data-theme` before first paint (default `dark`). Both the global header
toggle (`ThemeToggle`) and the board's Theme tweak write the store;
`DesignThemeProvider` / `BoardThemeProvider` **subscribe** to it so
`tweaks.theme` never goes stale (no multi-source race). Not a media query
(explicit control), with an optional follow-system mode planned.

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
| Theme single source + toggle | `src/core/web/ui/src/store/theme-store.ts` (+ `.test.ts`), `layout/ThemeToggle.tsx`, `design/ThemeProvider.tsx` |
| Color codemod + verification | `src/core/web/ui/scripts/{color_codemod,contrast_check,deltae_check}.py` |
| Graph node kind colors | `src/core/web/ui/src/lib/node-colors.ts` |
| Swimlane / task-kind chips | `src/core/web/ui/src/features/cos-board/kindColors.ts` |
| Priority / event colors | `src/core/web/ui/src/features/cos-board/CosBoardPage.tsx` |
| Shared primitives | `src/core/web/ui/src/layout/HubPrimitives.tsx` |

## 11. External review — validated rules + roadmap (2026-06-05)

A source-blind external product/design review independently converged on
this system's direction (Indigo/Iris primary, orange→signature-only, kill
handwritten fonts, near-identical neutral+brand palette). The binding
cross-cutting rules it confirmed:

### Color-namespace separation (BINDING)

Status, domain (swimlane), priority and agent MUST use **disjoint** color
namespaces — never the same hue scale. A color that means "domain" must
never also read as "success/warning". Current mapping:

| Axis | Source |
|---|---|
| status | `--st-*` / `--cos-ok\|warn\|err\|info` |
| domain (swimlane) | lane color — rail + ≤16% body tint + chip ONLY |
| task-kind | `--kind-*` chip |
| priority | `priorityColor` (P0 danger … P3 muted) |
| agent presence | `AGENT_PRESENCE_VISUALS` |

### Domain = rail/tint, never full fill (BINDING)

Domain identity = a 3–5px left rail + ≤16% tint + badge. The Phase-4
follow-up reduced the board card body from 0.55/0.32 → 0.16/0.07
lane-color alpha and removed the last handwritten fonts (Permanent
Marker / Caveat / Kalam → Inter).

### Lifecycle vocabularies (TARGET)

- **Task**: Backlog → Ready → Running → Verifying → Review → Done.
  Priority / Blocker / Risk / SLA are SEPARATE axes (today's columns
  conflate state + priority + condition).
- **Memory pattern**: Candidate → Observed → Validated → Trusted →
  Decaying → Deprecated (today most rows are `volatile`).

### Roadmap (DEFERRED — backlog under epic `ui-design-system`)

Multi-phase product/IA efforts, NOT token tweaks; built incrementally on
this foundation, tracked as tasks:

1. IA restructure → app shell (Mission / Work / Agents / Graph /
   Knowledge / System) + global ContextBar.
2. Mission Control → attention-first (approvals, failed verification,
   policy violations, budget risk), not a widget grid.
3. Chat/Trace split → conversation vs execution-trace; collapsed tool
   calls; sticky run-context; virtualized lists.
4. Doctor → finding-oriented triage (severity / owner / remediation /
   release-blocking); fix `Doctor OK` vs `attention` contradiction;
   human-readable DB size + redacted path.
5. Memory → lifecycle + evidence drill-down + actions (validate / pin /
   merge / quarantine / forget).
6. Graph → semantic zoom / LOD / saved views / query-scoped (never
   whole-repo default); React Flow for the role/workflow composer,
   Sigma for large read graphs.
7. Component system → tokens → headless a11y primitives (Radix behavior,
   own visual) → base → patterns → domain components.
8. Board state axes → split lifecycle state from priority / blocker /
   risk / SLA.

**Honest scope note:** the external review's "10–20 layers per scenario"
is itself over-engineering for low-risk flows (Rule 22). Apply deep
analysis **risk-based** — permissions, destructive/irreversible actions,
autonomous execution — not uniformly.

## 12. Color-token enforcement — no hardcoded UI colors

**Rule:** no component hardcodes a palette color. Every UI color resolves
from a `--cos-*` token, so a rebrand = editing `cos-board-tokens.css`
alone. Enforced by a repeatable codemod committed at
`src/core/web/ui/scripts/color_codemod.py` (run from repo root;
`contrast_check.py` / `deltae_check.py` verify WCAG contrast + ΔE
distinctness) — the mapping IS the rule:

| Tailwind named family | Token |
|---|---|
| `rose` `red` `pink` | `--cos-err` (bg → `--cos-err-tint`) |
| `emerald` `green` `lime` | `--cos-ok` / `--cos-ok-tint` |
| `amber` `yellow` `orange` | `--cos-warn` / `--cos-warn-tint` |
| `sky` `blue` | `--cos-info` / `--cos-info-tint` |
| `violet` `fuchsia` `indigo` `purple` | `--cos-brand-text` (border → `--cos-accent`, bg → `--cos-brand-tint`) |
| `cyan` `teal` | `--cos-live` |
| `slate` `gray` `zinc` `neutral` `stone` | text→`--cos-text`/`muted`/`faint` by shade; bg→`--cos-panel`/`inset`; border→`--cos-border` |

**Legitimately hex (NOT violations) — centralized single-source maps:**

| Map | Why hex |
|---|---|
| `lib/node-colors.ts`, `graph/graph-adapter.ts`, `graph/useSigma.ts` | Sigma/WebGL canvas cannot read CSS vars |
| `cos-board/agentPresenceVisuals.ts`, `AGENTS` map, `EVENT_COLOR`, `LiveStatus` presence, `LEVEL_COLORS` | external-agent identity / categorical data — change in one place |
| `#fff` / `#000` on solid accents | theme-neutral contrast anchors, not palette hues |

Sweep (must stay 0 outside the maps above): `grep -rE '(text\|bg\|border\|ring)-(rose\|emerald\|amber\|sky\|violet\|zinc\|gray\|slate\|...)-[0-9]' src/core/web/ui/src --include='*.tsx'`.
