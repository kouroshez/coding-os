---
id: TASK-1112
title: "fix(dispatch): with routing off, another adapter's model never rides along onto the session's adapter"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [supervision, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-115753-d372
depends_on: []
blocked_by: []
references: []
---
# TASK-1112: fix(dispatch): with routing off, another adapter's model never rides along onto the session's adapter

**Outcome (one sentence):** When supervision does not apply, a dispatch that names another adapter runs on the session's adapter as rule 6 says, but at the role's own model_pref tier resolved in that adapter's catalog instead of the other adapter's model, so it never runs at the account default (Opus), and the run is recorded under the adapter that really ran.

## Read First
- src/core/thinking_os/dispatcher.py
- docs/engineering/dispatcher-contract.md

## Repro Steps
Supervision off, Claude session: dispatch reviewer with adapter=codex, model=gpt-6.1-sol. dispatch_request skips routing, get_dispatcher logs 'adapter hint codex differs from session adapter claude — proceeding on claude', the Claude adapter maps the unknown model to its default claude-opus-5-5, and formula_dispatches row 103 records adapter=codex at $1.32.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** supervision is off in a claude session, **When** a dispatch requests adapter codex with model gpt-6.1-sol and effort high, **Then** the session runtime receives adapter claude, the role's tier resolved to claude-sonnet-5-5, no effort, and the result _meta names claude.
- **Given** supervision is off, **When** a dispatch names the session's own adapter, **Then** its model and effort pass through unchanged.
- **Given** a complexity the role's model_pref does not list (CLEAR), **When** the hint is set aside, **Then** a tier the role declares runs, not the account default.
- **Given** a codex session and a claude hint, **When** the hint is set aside, **Then** the role tier resolves to a model in the codex catalog.
- **Given** supervision is on, **When** the routed path resolves the tier sonnet, **Then** it picks the newest listed id, claude-sonnet-5-5.

## Work Log
- 2026-11-24 [claude]: commit 65991118ea — fix(dispatch): with routing off, another adapter's model and effort never ride onto the session's
- 2026-11-24 [claude]: commit a9066018b1 — fix(dispatch): the set-aside hint falls back to the role's model_pref, not the account default
- 2026-11-24 [claude]: Live: same scenario (routing off, claude session, reviewer with adapter=codex model=gpt-6.1-sol). Before: row 103 ran…
- 2026-11-24 [claude]: commit efd30ba336 — fix(dispatch): resolve the role tier in the session catalog; routed path picks the newest id
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
