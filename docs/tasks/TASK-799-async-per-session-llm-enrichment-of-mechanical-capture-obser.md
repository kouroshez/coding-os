---
id: TASK-799
title: "Async per-session LLM enrichment of mechanical capture observations (root fix, default-OFF)"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-05
completed: 2026-07-05
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-799: Async per-session LLM enrichment of mechanical capture observations (root fix, default-OFF)

**Outcome (one sentence):** Signal-bearing mechanical `changelog` observations gain a real distilled narrative + concepts and get promoted off `changelog` via one detached, budget-capped LLM dispatch per session — the root fix for the memory corpus, shipped default-OFF behind an owner-enabled budget gate.

## Read First
- src/core/thinking_os/distill.py (P8 dispatch pattern to mirror — `enabled`/`_run_dispatch`/`model_validate`)
- src/core/thinking_os/session_enrich.py (Stop-time host; `apply_session_facts` from item D)
- src/core/thinking_os/agents/distiller.md (agent-prompt shape to mirror)
- src/core/thinking_os/cognition_schemas.py (`SessionSummaryFacts`; add the two new models here)

## Design
1. **Schemas** (cognition_schemas.py): `ObservationEnrichment{observation_id:int, narrative, concepts:list[str], has_signal}`; `SessionEnrichment{observations:list[ObservationEnrichment], summary:SessionSummaryFacts}`.
2. **Dispatch** (distill.py): `enrich_enabled()` (env `COS_ENRICH_LLM`, default OFF); `observe_session(evidence)->SessionEnrichment|None` reusing distill's `_run_dispatch`/dispatcher-resolution/budget helpers (no duplication).
3. **Prompt** (agents/session_observer.md, NEW): mirrors distiller.md; output_schema `cognition.SessionEnrichment`; sees only tool metadata + paths, never file bodies.
4. **Worker** (session_observe_worker.py, NEW): collects this session's top-N `changelog` rows, ONE `observe_session` dispatch, promotes signal rows off changelog with sanitized narrative/concepts (`redact_secrets`+`scrub_username`), then `apply_session_facts` for the summary. Fire-and-forget, exit 0 always.
5. **Spawn** (session_enrich.py): when `enrich_enabled()` AND gate is COMPLICATED/COMPLEX, `subprocess.Popen(..., start_new_session=True)` the worker so the slow LLM call outlives the hook's 2s bound.
6. **Idempotency**: intrinsic — an enriched row leaves `memory_type='changelog'`, so a re-run finds nothing (no migration, no marker).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a seeded session with `changelog` observations and a mocked dispatcher returning a `SessionEnrichment` (no real LLM),
- **When** the worker's `enrich_session(conn, session_id)` runs,
- **Then** signal rows are promoted to `discovery` with the distilled narrative/concepts (secrets redacted), no-signal rows stay `changelog`, `apply_session_facts` fills the summary, a hallucinated observation_id is ignored, `enrich_enabled()` OFF ⇒ zero dispatch, and the thinking_os matrix + `server.py --test` stay green. P8: `src/core/**` never imports an adapter SDK (dispatch goes through distill→dispatcher).

## Work Log
- 2026-07-05 [claude]: Edit cognition_schemas.py
- 2026-07-05 [claude]: Edit distill.py
- 2026-07-05 [claude]: Edit distill.py
- 2026-07-05 [claude]: Edit distill.py
- 2026-07-05 [claude]: Edit session_observer.md
- 2026-07-05 [claude]: Edit session_observe_worker.py
- 2026-07-05 [claude]: Edit session_enrich.py
- 2026-07-05 [claude]: Edit session_enrich.py
- 2026-07-05 [claude]: Edit session_enrich.py
- 2026-07-05 [claude]: Edit test_session.py
- 2026-07-05 [claude]: Implemented default-OFF: observe_session() reuses distill.py's dispatcher-resolution/budget/_run_dispatch helpers (no…
- 2026-07-05 [claude]: Edit session_enrich.py
- 2026-07-05 [claude]: Edit test_cognition_supervisor.py
- 2026-07-05 [claude]: Edit distill.py
- 2026-07-05 [claude]: Edit test_cognition_supervisor.py
- 2026-07-05 [claude]: commit c63c52c050 — feat(memory): async per-session LLM enrichment of changelog observations (default-OFF)
- 2026-07-05 [claude]: Verification caught a blast-radius: placing the prompt in agents/ made it a registered agent card → +1 to…
- 2026-07-05 [claude]: Status transitioned to complete via cos task-done.
