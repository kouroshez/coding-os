<!-- domain:FRONTEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Design Review Checklist

Run when reviewing the look of an interface (any framework).

## Hierarchy & layout
- [ ] One clear primary action; secondary actions visibly quieter.
- [ ] The eye lands on the most important thing first.
- [ ] Elements aligned to a grid; related items grouped by proximity.
- [ ] Responsive, mobile-first; real breakpoints tested.

## Spacing & type
- [ ] All spacing from a scale (4/8 base) — no arbitrary values.
- [ ] One type scale, limited weights; body line-height ~1.5; measure 45–75 chars.

## Color & contrast
- [ ] Small palette: neutral ramp + 1–2 accents.
- [ ] Semantic color roles (tokens), not raw hex in components.
- [ ] Every text/background pair passes WCAG AA — `python3 scripts/check_contrast.py <fg> <bg>` → `pass`.
- [ ] Meaning not conveyed by color alone.

## Tokens & states
- [ ] Spacing/color/radius/type defined as tokens (one source of truth; themeable).
- [ ] Every interactive element has default/hover/focus(visible)/active/disabled/loading states.
- [ ] Empty + error data states designed, not just the populated happy path.

## Polish
- [ ] Doesn't read as generic "AI slop" (centered-everything, gray borders, one weight).
- [ ] Motion (if any) communicates, is fast, respects prefers-reduced-motion.
