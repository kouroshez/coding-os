---
id: TASK-056
title: "graph_os recall+health round 2: attribute-call resolution, md-links target gates, contracts kind-bucket"
swimlane: core
kind: bug
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: 2026-06-01
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-056: graph_os recall+health round 2: attribute-call resolution, md-links target gates, contracts kind-bucket

**Outcome (one sentence):** Graph recall+health round 2 — attribute-aliased calls (`g.func()`) resolve to real functions, `cos graph-reindex --path <subdir>` writes the repo-root DB (no stray), `contracts` stops mis-bucketing hooks, and md-links stops minting `#L`/placeholder phantom nodes.

## Read First
- [graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md) — references/impact recall contract
- [graph-explorer SKILL.md](../../src/core/skills/graph-explorer/SKILL.md) — `result_truncated` coverage contract (F3)

## Repro Steps
1. `cos_graph_rename_plan("…::cos_graph_doctor")` → `call_sites=1` (misses every `g.cos_graph_doctor()` attribute call).
2. `cos graph-reindex --path src/core/web/routes --force` → creates a stray `src/core/web/routes/.coding-os/coding-os.db`, main DB untouched.
3. `cos_graph_contracts(kinds=http)` → 12 `cos:hook:*` nodes mis-bucketed as http routes.
4. DB has 28 `code:file:…#L<n>` phantom nodes + placeholder `doc:file:…/relative/path` garbage.

Expected: rename finds all ~17 sites; subdir reindex hits the repo DB; no hooks in http_routes; no `#L`/placeholder nodes.
Actual (pre-fix): as above.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `g.cos_graph_doctor()` attribute calls, **When** `cos_graph_rename_plan` runs after reindex, **Then** `call_sites` ≈ 17 (was 1).
- **Given** `cos graph-reindex --path <subdir>`, **When** it runs, **Then** no `<subdir>/.coding-os/` DB is created and the global link targets the repo-root DB.
- **Given** `cos_graph_contracts(kinds=http)`, **Then** zero `cos:hook:*` nodes appear.
- **Given** a full reindex + `doctor(fix=True)`, **Then** `#L` and placeholder phantom nodes = 0.
- **Given** the graph_os + CLI matrices, **When** run, **Then** green (712 + 49 pass).

## Work Log
- 2026-06-01 [claude]: Shipped A1/B1/B2/C1/D1 + /code-review. Proven via full reindex (1105 files): A1 rename_plan(cos_graph_doctor) 1→17 call-
