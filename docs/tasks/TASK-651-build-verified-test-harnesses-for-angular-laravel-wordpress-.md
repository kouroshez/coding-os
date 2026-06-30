---
id: TASK-651
title: "Build verified test harnesses for angular/laravel/wordpress scaffolds + promote sample-test gate to HARD"
swimlane: templates
kind: test
epic: stack-completeness-v2
labels: [sample-tests, stack-completeness, wave-2, ready]
status: icebox
priority: P2
appetite: 3d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-651: Build verified test harnesses for angular/laravel/wordpress scaffolds + promote sample-test gate to HARD

**Outcome (one sentence):** angular (Karma), laravel (bootable app skeleton ~8 files), and wordpress (PHPUnit) scaffolds each ship a verified runnable sample test, then stack_lint's sample-test check is promoted from soft GAP to HARD with all 30 stacks green.

## Read First
- src/cli/stack_lint.py
- docs/playbooks/template-authoring.md
- src/templates/laravel/skills/laravel/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fresh scaffold of angular/laravel/wordpress, **When** the stack's documented test command runs in its real toolchain (CI, not inspection), **Then** the sample test passes.
**When** all three ship verified tests, **Then** the stack_lint sample-test check is flipped report.soft→report.hard and `cos stack-lint` stays green for all 30 stacks.
**Given** the workflow drafts already produced (wf_6c9cf2f2), **When** building each harness, **Then** the verifier-flagged blockers are resolved: angular legacy Karma bootstrap + double initTestEnvironment, laravel missing base Controller/bootstrap, wordpress {{PROJECT_NAME}}-in-.php namespace + PSR-12.

## Work Log
