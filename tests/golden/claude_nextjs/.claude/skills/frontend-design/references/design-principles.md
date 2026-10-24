<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Design Principles — Hierarchy, Spacing, Type, Color, Layout

> P: The visual-design fundamentals, framework-independent, that separate "intentional" from "AI slop".
> R: Designing or reviewing any interface's look and feel.
> S: Implementation/perf of the UI — that's [frontend-fundamentals](../../frontend-fundamentals/SKILL.md).
> N: [SKILL.md](../SKILL.md), [design-checklist.md](../assets/design-checklist.md)

> Nav: [Skill](../SKILL.md)

## Hierarchy — guide the eye

The user should know where to look first without thinking. Tools, in order of
power: **size** (bigger = more important), **weight** (bold draws), **color**
(contrast/accent draws), **space** (isolation draws). Use the *fewest* tools that
work — making everything bold and big destroys hierarchy. One clear primary
action per view; secondary actions visibly quieter.

## Spacing — a scale, consistently

```
4 · 8 · 12 · 16 · 24 · 32 · 48 · 64    (a 4/8px base scale)
```

Most of "looks polished" is consistent spacing. Pick a scale and never use a
value off it (`margin: 13px` is the tell of unconsidered design). **Proximity**
groups: related elements close, unrelated elements far. Whitespace is structure,
not waste — crowding everything to "fit more" reads as cheap.

## Typography

- **One type scale** (e.g. 12, 14, 16, 20, 24, 32, 48) — not 14 arbitrary sizes.
- **Limited weights** (regular + semibold/bold) — more looks chaotic.
- **Line height** ~1.5 for body, ~1.1–1.25 for headings.
- **Measure** (line length) 45–75 characters — longer is tiring, shorter is choppy.
- **One or two typefaces** max; pair a display face with a readable body face.

## Color

- A **neutral ramp** (5–9 grays from near-white to near-black) carries most of the
  UI; **one or two accents** for action/brand. Restraint reads as confident.
- Define **semantic roles** (`surface`, `text`, `text-muted`, `primary`, `danger`,
  `border`) — components reference roles, not raw hex.
- **Contrast is non-negotiable**: body text ≥ 4.5:1, large text ≥ 3:1 (WCAG AA).
  `check_contrast.py` verifies a pair. A palette that fails contrast isn't a
  palette, it's a bug ([a11y](../../a11y/SKILL.md)).
- Don't rely on color alone to convey meaning (color-blind users) — pair with
  icon/text.

## Layout

- **Grid + alignment** — align edges; misalignment by a few px reads as sloppy
  even when the viewer can't name why.
- **Responsive, mobile-first** — design the small screen first, enhance up; test
  the real breakpoints.
- **Visual weight balance** — distribute so the composition doesn't feel lopsided;
  intentional asymmetry beats lazy centering.
- **Consistency** — the same component looks and behaves the same everywhere; a
  design system / token set enforces this.

## Motion (use sparingly)

Animate to communicate (state change, spatial relationship), not to decorate.
Fast (150–250ms), eased, and respect `prefers-reduced-motion`. Gratuitous motion
is the animated cousin of AI slop.
