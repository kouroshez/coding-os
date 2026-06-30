---
id: TASK-658
title: "Verify every sample-test stack through its real lint+test gate + add a CI matrix gate (scaffold-verify)"
swimlane: infra
kind: test
epic: stack-completeness-v2
labels: [ci, scaffold, wave-2, lint-gate, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: null
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-658: Verify every sample-test stack through its real lint+test gate + add a CI matrix gate (scaffold-verify)

**Outcome (one sentence):** Every stack that ships a sample test is proven to pass its real lint+test gate on a fresh cos init: the 6 locally-runnable ones (nextjs, react-native, django, fastapi, go, go-fiber) verified this session, and a .github/workflows matrix scaffolds each sample-test stack with its toolchain and runs its real gate so the rust/dotnet/flutter/spring-boot/rails stacks (no local toolchain) are gated in CI and the lint-gate bug class cannot ship again.

## Read First
- .github/workflows/ci.yml
- src/templates/nextjs/scaffold/src/frontend/package.json
- docs/architecture/meta-project.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fresh scaffold of nextjs/react-native/django/fastapi/go/go-fiber, **When** its real lint+test gate runs locally, **Then** 0 errors (bugs found are fixed). **Given** a CI matrix job per sample-test stack, **When** it scaffolds via cos init and runs that stack's real gate, **Then** the job is red on any broken sample test. **Given** the workflow yaml, **When** linted, **Then** it is valid.

## Work Log
- 2026-06-30 [claude]: Edit go.mod
- 2026-06-30 [claude]: Edit go.mod
- 2026-06-30 [claude]: Edit go.mod
- 2026-06-30 [claude]: Edit scaffold-verify.yml
- 2026-06-30 [claude]: commit 91e5d256a6 — fix(templates): ship go-fiber go.sum so go vet/test pass on a fresh init
