<!-- domain:DESIGN | layer:index | ssot:true | updated:{{DATE}} -->
# Design System — Index

Purpose: Navigation hub for the design system — colors, typography, spacing, components, and motion.
Read when: Implementing or restyling UI components, or onboarding to the visual system.
Skip when: The task is purely backend or doesn't touch visual presentation.
Read next: The specific design doc relevant to your task.

> Nav: [Docs Index](../00-index.md)

## Files

- [Colors & Tokens](./colors-tokens.md) — Color palette, semantic tokens, dark mode
- [Typography & Spacing](./typography-spacing.md) — Font scale, spacing scale, layout grid
- [Components & Patterns](./components-patterns.md) — Reusable component recipes
- [Motion & Accessibility](./motion-accessibility.md) — Animations, transitions, a11y rules

## Authoring Rules

- Design tokens are SSOT. Tailwind config / CSS variables import from these docs.
- Components defined here have a single canonical implementation in `src/frontend/src/components/`.
- Accessibility is non-negotiable. See `../engineering/accessibility-checklist.md`.
- When the design system evolves, update the doc and components in the same PR.
