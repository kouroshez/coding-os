---
id: TASK-1114
title: "feat(review): the review model follows the task's weight, up to the session's own model"
swimlane: "board_os"
kind: feature
epic: null
labels: [supervision, ready]
status: blocked
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: null
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1114: feat(review): the review model follows the task's weight, up to the session's own model

**Outcome (one sentence):** With no review model pinned, a CLEAR or COMPLICATED task is reviewed at the role's default (Sonnet), while a COMPLEX or CHAOTIC task, or a security-sensitive diff, is reviewed on the session's own model, so an important change gets the model the operator chose and a routine one stays cheap.

## Read First
- docs/engineering/agent-supervision.md
- src/core/hooks/_helpers/auto_dispatch.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** no pinned review model and a COMPLICATED gate, **When** the task enters testing, **Then** the reviewer is dispatched at complexity COMPLICATED with no model, so the role default runs.
- **Given** no pinned review model and a COMPLEX or CHAOTIC gate, **When** the task enters testing, **Then** each review role on the session's adapter is dispatched at COMPLEX with the session's model.
- **Given** a security-sensitive diff, **When** the task enters testing, **Then** the reviews are weighty as above.
- **Given** a review role pinned under supervision, **When** it is dispatched, **Then** the pin's model wins.
- **Given** an unknown session model, **When** a weighty review runs, **Then** the role's complex tier is used.

## Work Log
- 2026-11-24 [claude]: commit 400d6de21d — feat(review): the review model follows the task's weight, up to the session's own model
- 2026-11-24 [claude]: commit d6454a86fe — fix(review): type the review weighting helpers and the catalog lookup
- 2026-11-24 [claude]: commit ae93ae97ea — fix(review): a weighty review gets full intensity, twice the turns and 420 seconds
- 2026-11-24 [claude]: commit 4f000ffee6 — fix(review): honour model-only pins, validate the session model, keep a Sonnet floor
