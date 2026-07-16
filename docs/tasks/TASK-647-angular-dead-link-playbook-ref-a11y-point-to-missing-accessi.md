---
id: TASK-647
title: "angular dead link \u2014 playbook + REF:A11Y point to missing accessibility-web.md"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [angular, drift, wave-1, a11y, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-647: angular dead link — playbook + REF:A11Y point to missing accessibility-web.md

**Outcome (one sentence):** A fresh angular project ships docs/engineering/accessibility-web.md, so the angular playbook's Accessibility link and the REF:A11Y ref-code resolve to a real WCAG 2.2 AA Angular-specific checklist instead of a dead link.

## Read First
- src/templates/angular/stack.yaml
- src/templates/nextjs/scaffold/docs/engineering/accessibility-web.md

## Repro Steps
1. cos init --template angular; open docs/playbooks/angular-app.md line 7 — its "Read next" line links "Accessibility" to the sibling engineering doc `accessibility-web.md`.
2. ls docs/engineering/ — only angular-app/angular-rules ship; `accessibility-web.md` is absent.
Expected: the linked a11y doc exists.
Actual: dead link in the shipped playbook; the REF:A11Y ref-code in stack.yaml points to the same missing file.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a scaffolded angular project, **When** following the playbook's Accessibility link, **Then** docs/engineering/accessibility-web.md exists with a WCAG 2.2 AA, Angular-specific checklist (CDK a11y / LiveAnnouncer / forms).
- **Given** the template suite, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** green; and `uv run cos stack-lint angular` PASS.
- **Given** `make docs-lint`, **When** run, **Then** it passes.

## Work Log
- 2026-06-30 [claude]: Edit accessibility-web.md
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit angular-app.md
- 2026-06-30 [claude]: commit 18667a13a5 — fix(templates): remove go/go-fiber/svelte shipped-artifact drift
- 2026-06-30 [claude]: Renamed a11y doc accessibility-web.md→accessibility.md (avoid engineering-filename collision w/ nextjs) + repointed 3…
