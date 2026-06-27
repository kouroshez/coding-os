---
id: TASK-597
title: "repair shipped hard-breaks: dangling rules x3, go-fiber v2 to v3, mvnw, astro content-seo link"
swimlane: templates
kind: bug
epic: stack-factory-v2
labels: [ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-26
completed: null
agent_session: ses-claude-20260626-165558-a565
depends_on: []
blocked_by: []
references: []
---
# TASK-597: repair shipped hard-breaks: dangling rules x3, go-fiber v2 to v3, mvnw, astro content-seo link

---
id: TASK-597
title: "repair shipped hard-breaks: dangling rules x3, go-fiber v2 to v3, mvnw, astro content-seo link"
swimlane: templates
kind: bug
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

# TASK-597: repair shipped hard-breaks: dangling rules x3, go-fiber v2 to v3, mvnw, astro content-seo link

**Outcome (one sentence):** Four confirmed shipped breakages fixed so every stack's declared refs/commands resolve on a fresh consumer. All verified directly in source this session.

## Read First
- src/templates/laravel/stack.yaml
- src/templates/go-fiber/skills/go-fiber/scripts/new_endpoint.py
- src/templates/spring-boot/stack.yaml
- src/templates/astro/stack.yaml

## Repro Steps
grep -n rules/ src/templates/{laravel,node-express,svelte-sveltekit}/stack.yaml then ls the declared rules dir (absent); grep gofiber/fiber/v src/templates/go-fiber/skills/go-fiber/scripts/new_endpoint.py (v2) vs versions.json (v3); ls src/templates/spring-boot/scaffold mvnw (absent); ls src/templates/astro/scaffold/docs/playbooks/content-seo.md (absent).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** laravel/stack.yaml:48, node-express/stack.yaml:46, svelte-sveltekit/stack.yaml:52 each declare a rules/*.md path, **When** the file is checked on disk, **Then** it exists (all three missing today).
**Given** go-fiber new_endpoint.py:57,78 emit gofiber/fiber/v2 while versions.json:11 pins v3, **When** a handler is generated, **Then** it emits v3 and compiles.
**Given** spring-boot/stack.yaml:30,49,50,53 + java-plain reference ./mvnw, **When** verify runs on a fresh scaffold, **Then** the mvnw wrapper ships and spring-boot has a sample *Test.java.
**Given** astro/stack.yaml:40,43,48 reference content-seo.md, **When** the scaffold is created, **Then** the content-seo.md playbook ships.
**Then** `make regen-rules` runs clean and `uv run pytest tests/test_template_scaffold.py -q` is green.

## Work Log
- 2026-06-27 [claude]: Edit new_endpoint.py
- 2026-06-27 [claude]: Edit new_endpoint.py
- 2026-06-27 [claude]: Edit backend.md
- 2026-06-27 [claude]: Edit backend.md
- 2026-06-27 [claude]: Edit frontend.md
- 2026-06-27 [claude]: Edit content-seo.md
- 2026-06-27 [claude]: Edit mvnw
- 2026-06-27 [claude]: Edit maven-wrapper.properties
- 2026-06-27 [claude]: Edit HealthServiceTest.java
- 2026-06-27 [claude]: Fixed 4 shipped hard-breaks: (1) created laravel/node-express rules/backend.md + svelte-sveltekit rules/frontend.md…
