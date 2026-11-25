---
name: frontend-design
tier: quality
domain: [frontend]
description: Create distinctive, production-grade visual interfaces — design principles that apply to ANY frontend (React, Next.js, Vue, Svelte, plain HTML/CSS, React Native). Use when the aesthetic direction matters — building a component, page, landing site, or app where it must look intentional, not generic "AI slop". Covers visual hierarchy, spacing/rhythm, typography, color + contrast, layout, and design tokens — independent of framework. Triggers — "make this look good", "design", "UI", "landing page", "the spacing feels off", "color palette", "it looks generic/AI". Pairs with frontend-fundamentals (implementation patterns), a11y (accessibility — aesthetic without it is a lawsuit), state-management.
globs: ""
paths: []
last_reviewed: "2026-06-04"
---

# Frontend Design

Good design looks *intentional* — every spacing value, type size, and color is a decision, not a default. This skill is the aesthetic direction, and it is **framework-independent**: the same principles apply whether you write React, Vue, Svelte, React Native, or hand-written HTML/CSS. The implementation patterns are owned by [frontend-fundamentals](../frontend-fundamentals/SKILL.md); accessibility by [a11y](../a11y/SKILL.md) — load all three for real UI work (aesthetic without a11y is a lawsuit; aesthetic without patterns is tech debt).

> Check a color pair against WCAG contrast (design + a11y in one):
> `python3 scripts/check_contrast.py "#1a1a1a" "#ffffff"`

## Avoid "AI slop" — the generic look

The default generic interface: even gray borders everywhere, centered everything,
one font weight, purple-to-blue gradients, emoji as iconography, no hierarchy. It
reads as "no decisions were made". Distinctive design makes deliberate choices: a
real type scale, intentional asymmetry, a restrained palette with one accent,
generous or deliberately tight spacing — consistently applied.

## The principles (framework-agnostic)

1. **Hierarchy** — the eye should land on the most important thing first. Achieve
   it with size, weight, color, and space — not by making everything bold.
2. **Spacing rhythm** — use a scale (4/8px base: 4, 8, 12, 16, 24, 32, 48, 64),
   never arbitrary values. Consistent spacing is most of what "looks polished" is.
3. **Typography** — a type scale (not 14 random sizes); limited weights; line-height
   ~1.5 for body, tighter for headings; measure (line length) ~45–75 characters.
4. **Color** — a small palette: a neutral ramp + one or two accents. Define
   semantic roles (surface, text, primary, danger), not raw hex scattered in code.
   Every text/background pair must pass contrast — `check_contrast.py`.
5. **Layout** — align to a grid; respect proximity (related things close, unrelated
   apart); use whitespace as a tool, not filler.

Full treatment → [references/design-principles.md](references/design-principles.md).

## Design tokens — one source of truth

```
// tokens (CSS vars / a theme object) — the SSOT for the look
--space-1: 4px; --space-2: 8px; ... --radius: 8px;
--color-surface: #fff; --color-text: #1a1a1a; --color-primary: #2563eb;
```

Define spacing, color, radius, type as **tokens**, reference them everywhere —
never hardcode `margin: 13px` or `#3b82f6` inline. Tokens make the design
consistent and themeable (dark mode = swap the token values). This is the
api-contract-discipline principle applied to visual values.

## Responsive + state, by default

Design mobile-first and scale up; test the real breakpoints, not just a desktop
width. Every interactive element needs its full state set: default, hover, focus
(visible — a11y), active, disabled, loading, and the empty/error data states.
A design that only shows the happy, populated, desktop view is half-designed.

## Anti-patterns (reject on sight)

- Arbitrary spacing (`margin: 13px`, `gap: 7px`) instead of a scale.
- Raw hex/px scattered in components instead of tokens.
- One font size/weight for everything → no hierarchy.
- Centered everything, gray borders, generic gradient → AI slop.
- Color pairs that fail contrast (looks fine to you, invisible to many).
- Missing focus styles (removed `outline` with no replacement) → inaccessible.
- Only the happy/populated/desktop state designed.

## See also

- [references/design-principles.md](references/design-principles.md) — hierarchy, spacing, type, color, layout in depth.
- [assets/design-checklist.md](assets/design-checklist.md) — the review gate.
- [frontend-fundamentals](../frontend-fundamentals/SKILL.md) — implementation patterns · [a11y](../a11y/SKILL.md) — accessibility · [performance](../performance/SKILL.md).
