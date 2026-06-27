---
id: TASK-608
title: "bootable scaffold: wordpress composer.json + phpcs.xml.dist (php runnable seed)"
swimlane: templates
kind: feature
epic: stack-factory-v2
labels: []
status: icebox
priority: P2
appetite: 1d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: [TASK-603]
blocked_by: []
references: []
---

# TASK-608: bootable scaffold: wordpress composer.json + phpcs.xml.dist (php runnable seed)

**Outcome (one sentence):** wordpress becomes a runnable seed (today no composer.json — `composer lint` is non-runnable, verified P0). Ships composer.json (require-dev squizlabs/php_codesniffer + wp-coding-standards/wpcs, lint/test scripts) + phpcs.xml.dist pulling the T5 (TASK-603) php config.

## Read First
- src/templates/wordpress/stack.yaml
- src/templates/laravel/scaffold/src/backend/composer.json

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** wordpress, **When** `cos init` then `composer install` && `composer lint`, **Then** they run on the shipped composer.json + phpcs.xml.dist (today composer.json absent → non-runnable).
**Given** the scaffold, **When** inspected, **Then** it is a runnable PHP seed, not skeletons-only.
**Then** `uv run pytest tests/test_template_scaffold.py -q` is green.

## Work Log
