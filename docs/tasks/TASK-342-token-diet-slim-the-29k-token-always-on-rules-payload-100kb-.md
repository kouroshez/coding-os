---
id: TASK-342
title: "Token diet: slim the ~29k-token always-on rules payload (100KB across CLAUDE.md + 14 rule files per session)"
swimlane: docs
kind: refactor
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 2d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-342: Token diet: slim the ~29k-token always-on rules payload (100KB across CLAUDE.md + 14 rule files per session)

**Outcome (one sentence):** Per-session injected rules payload drops by at least 40% (measured bytes) by moving Why/rationale prose from always-active rules (git-workflow 12.8KB, transparency-banner 10.5KB, anti-overengineering 6.8KB, memory 5.8KB, api-contract 4.4KB) into linked docs/ pages, keeping only the operative contract in each rule — without weakening any enforced behavior.

## Read First
- src/core/rules/git-workflow.md
- src/core/rules/transparency-banner.md
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the trimmed rules, **When** summing bytes of CLAUDE.md + src/core/rules/*.md + .claude/rules/*.md loaded per session, **Then** total ≤ 60KB (baseline 100,744B measured 2026-06-10).
- **Given** each trimmed rule, **When** read, **Then** every hard contract/command/table needed at decision time is still in the rule; rationale lives in a linked doc.
- **Given** make docs-lint + make verify-hooks, **When** run, **Then** green (no enforcement regression).

## Work Log
