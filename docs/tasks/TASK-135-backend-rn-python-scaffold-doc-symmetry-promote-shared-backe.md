---
id: TASK-135
title: "Backend/RN/python scaffold doc symmetry — promote shared backend docs, RN design tokens, python/meta minimal docs"
swimlane: templates
kind: docs
epic: doc-system
labels: [docs-system, templates, scaffold-richness, audit-d2-f5, ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-135: Backend/RN/python scaffold doc symmetry — promote shared backend docs, RN design tokens, python/meta minimal docs

**Outcome (one sentence):** No stack persona starts from a blank doc tree: stack-agnostic backend docs (naming-conventions, logging-standards, glossary, secrets-rotation-runbook) are promoted so fastapi/go/go-fiber match django (D2-F5); react-native gets a design/ tokens + screens-content-spec mirror like nextjs (D2-F6); python + meta stacks get a minimal scaffold/docs (python-rules: typing/packaging/public-API) instead of empty (D2-F8).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/templates/django/scaffold/docs/
- src/templates/nextjs/scaffold/docs/design/
- src/templates/python/

## Work Log
- 2026-06-07 [claude]: Archived (premature/bloat). Triage verified: django's backend docs (naming/logging/glossary/secrets) are ExampleApp-spec
