---
name: generated-hero-banners-miss-the-readme-bar
description: Four gpt-image-2 hero banners were all rejected; a real product screenshot is the better README hero.
metadata:
  type: project
---

2026-08-17, coding-os README: two prompt directions × two variants through the
`imagegen` skill (gpt-image-2) produced four hero banners, rated 6/10, 4/10,
6/10, 4/10 on independent review. Every one carried the same defects — broken
and doubled outlines, smeared geometry, muddy glow that the prompt explicitly
forbade, and a generic "AI/network" look. None were text-contaminated; the
failure is geometric precision, not typography.

**Decision: no generated hero.** The Hub home screenshot went to the top of the
README instead — it shows the registered projects and the agents live in each,
which is what a hero is supposed to prove, and it cannot be wrong about the
product because it *is* the product.

Do not re-run this experiment for a banner of precise linework. If a future
attempt is made, prompt for solid flat shapes over hairline vector detail — thin
lines are where this model degrades.
