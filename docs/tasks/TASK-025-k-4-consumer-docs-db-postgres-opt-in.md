---
id: TASK-025
title: "K.4  Consumer docs: --db postgres:// opt-in"
swimlane: docs
kind: docs
epic: phase-k
labels: [db-abstraction, consumer-docs]
status: icebox
priority: P3
appetite: "30m"
created: 2026-04-20
started: null
completed: null
agent_session: null
depends_on: [TASK-023, TASK-024]
blocked_by: []
references: []
---

# TASK-025: K.4 — Consumer docs for Postgres opt-in

**Outcome (one sentence):** Consumer-project docs (README, getting-started, and `cos init --help` text) add a short "Postgres is opt-in and gated" section that references `docs/phase-k-db-abstraction-plan.md` as the SSOT and makes absolutely clear that SQLite remains the default forever.

## Read First

- [docs/phase-k-db-abstraction-plan.md §K.4](../phase-k-db-abstraction-plan.md) — SSOT (K.4 row in the roadmap table, plus R-K-2: "Postgres never becomes the default; `cos init` keeps SQLite as default forever; Postgres is opt-in").
- [templates/_base/README.md](../../templates/_base/README.md) — base template readme consumer projects inherit.
- [cli/main.py](../../cli/main.py) — `init` click command; `--db` flag help string lives here.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a fresh consumer project scaffolded from `cos init`
  **When** a developer reads its README
  **Then** a short section titled "Database backend (SQLite default; Postgres opt-in)" references the gate conditions with a link to the plan, and clearly states the default.
- **Given** `cos init --help`
  **When** a user reads it
  **Then** the `--db` flag's help text mentions the gate + points to the plan doc.
- **Given** the stack-specific templates (`templates/django/`, `templates/nextjs/`, `templates/fastapi/`, `templates/go/`, `templates/go-fiber/`)
  **When** they render
  **Then** they inherit the same section from `_base/` — no duplicated text per stack.
- **Given** the consumer project's `cos doctor`
  **When** run against a Postgres-backed project
  **Then** it reports the backend and mentions "See `docs/phase-k-db-abstraction-plan.md` for gate conditions".
- **Tests:** `tests/test_consumer_docs.py` asserts the section exists in rendered templates; `tests/test_cli.py` asserts the `--help` text contains the required phrases.

## Implementation Notes

- Do NOT re-state the gate conditions inline (Rule 14 — task / doc SSOT hygiene). Link to the plan only.
- The `--db` flag was already referenced in K.2/K.3 tasks; make sure the help text here is the definitive wording.
- Keep the section short (≤ 15 lines in README).

## Dependencies

- **Depends on:** TASK-023 + TASK-024 (no point documenting opt-in for a path that doesn't exist yet).
- **Unblocks:** officially closes Phase K.

## Work Log
