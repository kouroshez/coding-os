---
id: TASK-621
title: "backfill scaffolding scripts + versions.json for the 13 anatomy-completed stack skills"
swimlane: templates
kind: feature
epic: stack-factory-v2
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-621: backfill scaffolding scripts + versions.json for the 13 anatomy-completed stack skills

**Outcome (one sentence):** The 13 stack skills that now ship references/anatomy.md (TASK-599) also get a scaffolding generator script + a versions.json with ACCURATE current pins, reaching full go-fiber parity (the last two completeness-bar artifacts).

## Read First
- src/templates/go-fiber/skills/go-fiber/versions.json
- src/templates/go-fiber/skills/go-fiber/scripts/new_endpoint.py
- src/templates/angular/skills/angular/references/anatomy.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** each of the 13 skills (angular/aspnet-core/astro/flutter/laravel/nestjs/node-express/rails/react-native/rust/spring-boot/svelte/vue-nuxt) now has references/anatomy.md, **When** this task runs, **Then** each ships a scripts/<new_entity>.py generator matching its anatomy's primary recipe AND a versions.json whose framework+language pins are verified against the upstream release page (firecrawl, no hallucinated versions) with a `checked:` date.
**Given** versions.json must not carry invented version numbers, **When** a pin can't be web-verified, **Then** it is omitted with a note rather than guessed.
**Then** `make skills-check-versions` and `uv run pytest tests/test_template_scaffold.py -q` are green.

## Work Log
