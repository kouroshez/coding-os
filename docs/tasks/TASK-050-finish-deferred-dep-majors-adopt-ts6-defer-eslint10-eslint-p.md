---
id: TASK-050
title: "Finish deferred dep majors: adopt TS6, defer ESLint10 (eslint-plugin-react peer block)"
swimlane: infra
kind: chore
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-05-31
started: 2026-05-31
completed: 2026-05-31
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: ["TASK-049"]
---
# TASK-050: Finish deferred dep majors: adopt TS6, defer ESLint10 (eslint-plugin-react peer block)

**Outcome (one sentence):** Hub UI TypeScript bumped to 6.0.3 (tsc/build/vitest/lint all exit 0); ESLint 10 deferred until `eslint-plugin-react` ships a `^10` peer; Python deps confirmed already-latest via `>=` floors → no manifest change.

Continuation of [TASK-049](TASK-049-dependency-upgrade-sweep-all-python-js-deps-to-latest-incl-r.md), whose acceptance line "JS dev-tooling majors (TS6, ESLint10) green" was left unchecked at close.

## Read First
- src/core/web/ui/package.json — JS deps (the only edited manifest)
- pyproject.toml — Python floors + intentional caps (all non-binding as of 2026-05-30)

## Acceptance
- [x] `typescript ^6.0.3` in package.json + lock; tsc --noEmit, vite build, vitest (30/30), eslint (--max-warnings=200) all exit 0
- [x] ESLint 10 deferral evidence-backed: `eslint-plugin-react@7.37.5` peer caps at `^9.7`; `npm install eslint@10` → ERESOLVE
- [x] Python confirmed already-latest: every `>=` floor admits PyPI latest; caps (tree-sitter<0.26, claude-agent-sdk<0.3, numpy<3.0, tree-sitter-yaml<0.8) all sit above current latest → non-binding, no change
- [x] No other outdated direct deps: `npm outdated` = only the 3 majors; no Go/Rust/requirements/template manifests in repo

## Work Log
- 2026-05-31 [claude]: Status transitioned to complete via cos task-done.
