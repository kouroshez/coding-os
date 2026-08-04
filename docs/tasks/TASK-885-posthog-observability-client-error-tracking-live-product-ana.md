---
id: TASK-885
title: "PostHog observability: client error tracking live + product-analytics dashboard via API"
swimlane: docs
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-04
completed: 2026-08-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-885: PostHog observability: client error tracking live + product-analytics dashboard via API

## Outcome

Unhandled browser exceptions from coding-os.dev flow into PostHog Error tracking (capture_exceptions in the existing init), deployed and verified with a real captured $exception event; product-analytics dashboard created in PostHog (API if operator provides a personal key, else documented in-app steps).

## Read First

- cos-website: src/frontend/components/analytics-provider.tsx (single PostHog init — extend, don't duplicate)
- ca-server01 runbook Addendum 9 (PostHog wiring + US-cloud note)

## Acceptance

- Given the deployed site, when an uncaught exception is thrown in the browser, then a POST to us.i.posthog.com containing a $exception event returns 200.
- Given the change, when running typecheck and lint, then both pass.
- Given the PostHog project, when the operator opens Error tracking, then the verification exception is listed.

## Work Log
- 2026-08-04 [claude]: Edit analytics-provider.tsx
- 2026-08-04 [claude]: Error tracking live: capture_exceptions added to the single PostHog init (cos-website f1ce966), typecheck+lint PASS,…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
