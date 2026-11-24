---
id: TASK-1114
title: "feat(review): the review model follows the task's weight, up to the session's own model"
swimlane: "board_os"
kind: feature
epic: null
labels: [supervision, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1114: feat(review): the review model follows the task's weight, up to the session's own model

**Outcome (one sentence):** With routing off, a CLEAR or COMPLICATED task is reviewed at the role's default (Sonnet), while a COMPLEX or CHAOTIC task, or a security-sensitive diff, is reviewed on the session's own model at effort high when the adapter lists it and it is no weaker than Sonnet; with routing on the Hub's pins and orchestrator default decide; every weighty review gets full intensity, twice the turns and 420 seconds.

## Read First
- docs/engineering/agent-supervision.md
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/hooks/_helpers/review_model.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** routing off and a COMPLICATED gate, **When** the task enters testing, **Then** the reviewer runs at complexity COMPLICATED with no model, so the role default (Sonnet) runs.
- **Given** routing off and a COMPLEX or CHAOTIC gate or a sensitive diff, **When** the task enters testing, **Then** each review role on the session adapter runs on the session model at effort high, if the catalog lists it and its rank is at least Sonnet; otherwise the role's complex tier.
- **Given** routing on, **When** a weighty review is dispatched, **Then** the session model is not applied and the Hub's pins or orchestrator default decide, including a pin that names only a model.
- **Given** a weighty review, **When** it is built, **Then** it uses full intensity, twice the turn budget and 420 seconds.
- **Given** one review role errors while another passes, **When** task-done runs, **Then** the gate warns that the review was not full, ahead of any minor notes.

## Work Log
- 2026-11-24 [claude]: commit 400d6de21d — feat(review): the review model follows the task's weight, up to the session's own model
- 2026-11-24 [claude]: commit d6454a86fe — fix(review): type the review weighting helpers and the catalog lookup
- 2026-11-24 [claude]: commit ae93ae97ea — fix(review): a weighty review gets full intensity, twice the turns and 420 seconds
- 2026-11-24 [claude]: commit 4f000ffee6 — fix(review): honour model-only pins, validate the session model, keep a Sonnet floor
- 2026-11-24 [claude]: commit 0827f583d2 — fix(review): the session model weights reviews only with routing off, at effort high
- 2026-11-24 [claude]: Round 4 (after unblock) passed on Opus at effort high: $1.14/93s and $1.08/53s, against $3.10/397s at xhigh in round…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
