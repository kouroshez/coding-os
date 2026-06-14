---
id: TASK-350
title: "Docs leveling \u2014 universal playbooks to _base + fill thin-stack docs to django baseline"
swimlane: docs
kind: docs
epic: F-docs
labels: [wave-5, onboarding-program, ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-350: Docs leveling — universal playbooks to _base + fill thin-stack docs to django baseline

**Outcome (one sentence):** security-review + research-validation playbooks move to _base with per-stack overlays (django's copies deleted, not duplicated); fastapi/go/go-fiber/react-native/python scaffold docs reach the django baseline (>=1 playbook + engineering rules each); docs-lint green.

## Read First
- src/templates/django/scaffold/docs/playbooks/security-review.md (django-only today — the file to relocate)
- src/templates/_base/scaffold/docs/playbooks/00-index.md (the shared overlay it moves into)
- src/templates/fastapi/scaffold/docs/playbooks/fastapi-service.md (thin-stack baseline shape)
- src/core/scaffold_manifest.json (derived — regen via `make manifest-regen`, never hand-edit)
- tests/test_template_scaffold.py (per-stack scaffold assertions live here)
- docs/governance/docs-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the two stack-agnostic playbooks live only under django today, **When** the move completes, **Then** src/templates/_base/scaffold/docs/playbooks/security-review.md and research-validation.md both exist, and `find src/templates -path '*scaffold/docs/playbooks/security-review.md'` returns ONLY the _base path (django copies deleted — no shadowing duplicate).
- **Given** _base now owns the universal playbooks, **When** `make manifest-regen` regenerates src/core/scaffold_manifest.json from fresh sandboxes (Rule 10), **Then** both playbooks appear under the claude_base composition and consequently under every per-stack composition (claude_fastapi / claude_go / claude_go-fiber / claude_react-native / claude_python).
- **Given** the django doc baseline (>=1 stack playbook + engineering rules), **When** each thin stack is leveled, **Then** every one of src/templates/{fastapi,go,go-fiber,react-native,python}/scaffold/docs/ holds at least one playbooks/<stack>-*.md AND at least one engineering/*-rules.md, each carrying a valid SSOT doc-header per docs/governance/docs-system.md.
- **Given** the scaffold contract is test-guarded, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** it is green and now asserts security-review.md + research-validation.md exist in at least one non-django composed project (extending the existing per-stack playbook assertions so _base inheritance is regression-locked).
- **Given** a fresh end-to-end scaffold, **When** a sandbox is composed on a thin stack (e.g. fastapi) and `make docs-lint` runs inside it, **Then** the inherited playbooks' internal links resolve against files that exist in that composed tree (no django-only path leaks through the move).
- **Given** all moved/new docs, **When** `make docs-lint` runs at repo root, **Then** it exits 0 (SSOT header + link contract intact).

## Rollback
`git restore` the moved/added scaffold docs and the thin-stack docs, restore django's two playbook copies, then re-run `make manifest-regen` to revert scaffold_manifest.json; docs + derived manifest only, so no schema or runtime change.

## Work Log
