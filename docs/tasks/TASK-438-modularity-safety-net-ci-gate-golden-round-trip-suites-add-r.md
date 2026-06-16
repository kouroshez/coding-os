---
id: TASK-438
title: "Modularity safety net: CI-gate golden+round-trip suites, add referential-integrity + all-stacks render smoke, bring logging_os/scheduled into CI"
swimlane: infra
kind: feature
epic: null
labels: [modularity, ci, tests, audit-2026-06, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: null
agent_session: ses-claude-20260615-233030-cac8
depends_on: []
blocked_by: []
references: []
---
# TASK-438: Modularity safety net: CI-gate golden+round-trip suites, add referential-integrity + all-stacks render smoke, bring logging_os/scheduled into CI

---
id: TASK-438
title: "Modularity safety net: CI-gate golden+round-trip suites, add referential-integrity + all-stacks render smoke, bring logging_os/scheduled into CI"
swimlane: infra
kind: feature
epic: null
labels: [modularity, ci, tests, audit-2026-06, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-16
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-438: Modularity safety net (CI-gate + render-smoke + referential-integrity + observability in CI)

**Outcome (one sentence):** The modularity verification layer actually runs in CI — a botched re-render, an empty required substitution, a dangling skill-name reference, or a logging_os/scheduled regression is caught by a PR gate instead of shipping silently to every consumer. Closes audit R1+R5+R9+R15 (problem-tree Branch C).

## Read First
- docs/engineering/test-governance.md
- .github/workflows/ci.yml
- docs/engineering/skill-architecture.md
- src/core/rules/skill-enforcement.md
- tests/test_template_scaffold.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** a PR that breaks rendering (a surviving `{{ }}` / `{% %}` token, or an empty required value such as `STACK_REF_CODES=''`) **When** CI runs **Then** a fast all-stacks render-smoke test fails without needing a `cos init` sandbox.

**Given** skill-enforcement.md (or any `Skill <name>` reference) names a skill with no skill dir **When** the new referential-integrity test runs in CI **Then** it fails naming the dangling skill.

**Given** the existing golden-parity + module/skill/stack round-trip tests **When** a PR is opened **Then** they gate the PR (or a nightly `make test-slow` exists and on-push runs the fast subset), with the slow mark split so pure-filesystem checks run on PR.

**Given** src/core/logging_os/** and src/core/scheduled/** change **When** CI runs **Then** a Verification-Matrix row + ci.yml step exercises them; all new tests are green locally before the CI wiring lands.

## Work Log
- 2026-06-16 [claude]: Edit test_skill_ref_integrity.py
- 2026-06-16 [claude]: commit 84230fe4c2 — test(modularity): guard skill-enforcement.md skill-name referential integrity
- 2026-06-16 [claude]: R5 landed (84230fe4): added tests/test_skill_ref_integrity.py — harvests core + per-stack skill universe, asserts every
- 2026-06-16 [claude]: Edit test_all_stacks_render_smoke.py
- 2026-06-16 [claude]: commit 34654b0ef3 — test(modularity): all-stacks AGENTS.md render smoke (no surviving Jinja delimiters)
- 2026-06-16 [claude]: commit 542c625135 — test(golden): regenerate fixtures drifted from cae258bc + d4e2d042
- 2026-06-16 [claude]: Edit ci.yml
- 2026-06-16 [claude]: Edit ci.yml
- 2026-06-16 [claude]: Edit ci.yml
- 2026-06-16 [claude]: commit 78e803d34d — ci: gate modularity safety net (golden parity + render smokes) + nightly slow suite
- 2026-06-16 [claude]: Edit conftest.py
- 2026-06-16 [claude]: Edit ci.yml
- 2026-06-16 [claude]: commit ab06f39685 — ci: run logging_os + scheduled suites in CI; fix migration import in logging_os tests
