<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-04-24 -->
# thinking-os Formula-Agents (Phase M + N)

Source of truth: [docs/code-os-core-docs/thinkingos-formulas/formulas-en.md](code-os-core-docs/thinkingos-formulas/formulas-en.md)
Agent files: `core/thinking_os/agents/F<N>_<name>.md`
**Role registry (Phase N)**: `core/thinking_os/roles/F{1..11}_*.yaml`
**Preset registry (Phase N)**: `core/thinking_os/presets/registry.yaml`
Situation registry: `core/thinking_os/situations/registry.yaml`
~~Persona registry~~ (deprecated, removed v0.4): `core/thinking_os/personas/registry.yaml`

Phase N plan: [phase-n-role-based-routing-plan.md](phase-n-role-based-routing-plan.md)

## Overview

Phase M introduced 11 dispatchable formula-agents + a deterministic supervisor.
Phase N replaced the Phase M persona layer with **role-based routing**: the 11
formulas ARE the 11 cognitive roles, selected dynamically by task signals rather
than by static job-title labels.

```
Task prompt + memory + MCP context
          │
          ▼
   Task Analyzer  →  TaskSignals (domain, action, novelty, urgency, ...)
          │
          ▼
   Formula Composer → ComposedChain  (situation > preset > composer > fallback)
          │
          ▼
   Supervisor  →  Formula-agents (F1..F11) dispatched in order
                                F1 Researcher
                                F2 Analyst
                                F3 Architect
                                F4 Documenter
                                F5 Implementer  ← existing skills apply here
                                F6 Reviewer (Test · Review · Perf)
                                F7 Debugger
                                F8 Security Auditor (5 parallel layers)
                                F9 Deployer
                                F10 Observer
                                F11 Refactorer
```

## 11 Formula-Agents

| Formula | Agent file | Attach phases | Intensity min | Input | Output |
|---|---|---|---|---|---|
| F1 Research | `F1_research.md` | MAP | light | `F1Input` | `F1Output` |
| F2 Decompose | `F2_decompose.md` | MAP, ORIENT, PLAN | light | `F2Input` | `F2Output` |
| F3 Architect | `F3_architect.md` | PLAN | standard | `F3Input` | `F3Output` |
| F4 Document | `F4_document.md` | EXECUTE | light | `F4Input` | `F4Output` |
| F5 Implement | `F5_implement.md` | EXECUTE | light | `F5Input` | `F5Output` |
| F6 Test/Review | `F6_test_review.md` | post-EXECUTE | light | `F6Input` | `F6Output` |
| F7 Debug | `F7_debug.md` | post-EXECUTE | light | `F7Input` | `F7Output` |
| F8 Security | `F8_security.md` | post-EXECUTE | standard | `F8Input` | `F8Output` |
| F9 Deploy | `F9_deploy.md` | post-EXECUTE | full | `F9Input` | `F9Output` |
| F10 Monitor | `F10_monitor.md` | periodic | standard | `F10Input` | `F10Output` |
| F11 Refactor | `F11_refactor.md` | periodic | standard | `F11Input` | `F11Output` |

All IO contracts are Pydantic models in `core/thinking_os/cognition_schemas.py`.
The `EvidenceBundle` accumulates F1–F11 outputs across dispatches (append-only per session).

## 10 Thinking Tools × Formula Mapping

The 10 Thinking Tools from `docs/workflow-docs/thinking-os-final-edition.md` map onto
formula dispatch points as follows:

| Thinking Tool | Primary formula(s) | When triggered |
|---|---|---|
| Tool 1 — Problem Framing (PROBLEM/ACTORS/BOUNDARY) | F2 Steps 1–3 | MAP phase, first dispatch |
| Tool 2 — Constraints Enumeration | F2 Step 9, F3 Step 4 | ORIENT/PLAN |
| Tool 3 — Behavior Modeling (Given/When/Then) | F2 Step 7 (state machines, events) | ORIENT |
| Tool 4 — Rules Modeling (decision tables) | F2 Step 5 (permission matrix) | ORIENT |
| Tool 5 — Dependency Mapping | F2 Step 10, F11 Step 2 | ORIENT / periodic |
| Tool 6 — Risk Pass | F2 Step 11 (unknowns), F8 Layers 1–5 | ORIENT + post-EXECUTE |
| Tool 7 — Second-Order Effects | F3 Step 6 (trade-off analysis), F10 | PLAN + periodic |
| Tool 8 — Filter & Prioritize | F5 Step 1 (pre-impl scope check), F11 Step 4 | EXECUTE / periodic |
| Tool 9 — Convergent Build | F5 Steps 2–7, F3 Steps 1–5 (ADR) | PLAN + EXECUTE |
| Tool 10 — Record (capture) | F4 (all steps), F6 Step B (learnings) | EXECUTE + post-EXECUTE |

## Routing: Cognitive Roles (Phase N) — replaces personas

> **Phase N architectural decision**: the 11 formulas ARE the 11 cognitive roles.
> Job-title personas (`junior-dev`, `senior-backend`, ...) are **deprecated**. The
> same agent enters different roles on different tasks — debugging (F7), architecting
> (F3), documenting (F4) — driven by task signals, not job title.
>
> Full plan: [docs/phase-n-role-based-routing-plan.md](phase-n-role-based-routing-plan.md).

### 11 Roles

Stored in `core/thinking_os/roles/F{1..11}_*.yaml`. Each role has `activation` triggers,
`intensity_steps`, `tools_budget`, `backtrack_triggers`, `criteria_required` per step,
and `prompt_prefix`.

| Role | Formula | When activated (primary signals) |
|---|---|---|
| F1 Researcher | Research & Discovery | `action=research`, `novelty≥0.5`, `external_dependency=true` |
| F2 Analyst | Problem Decomposition | `complexity ∈ {COMPLICATED, COMPLEX}`, `scope_size ∈ {medium, large, recursive}` |
| F3 Architect | Architecture & Design | `breaking_change=true`, `action ∈ {create, refactor}`, `has_production_impact=true` |
| F4 Documenter | Technical Documentation | `action=document`, `domain=[docs]`, `is_takeover=true` |
| F5 Implementer | Implementation | `action ∈ {create, modify, refactor}`, any code scope |
| F6 Reviewer | Testing · Review · Perf | `action=review`, post-F5 (mandatory) |
| F7 Debugger | Debugging | `action=debug`, `urgency ∈ {elevated, incident}` |
| F8 Security Auditor | Security Audit | `action=audit`, `domain ∈ {security, auth}`, `breaking_change`, `external_dependency` |
| F9 Deployer | Deployment & DevOps | `action=deploy`, `domain ∈ {infra, devops}` |
| F10 Observer | Monitoring | `has_production_impact`, post-incident, post-deploy |
| F11 Refactorer | Tech-Debt | `action=refactor`, `is_takeover=true` |

### Task Analyzer + Composer

- `core/thinking_os/task_analyzer.py::analyze_task(prompt, complexity, dimensions)` →
  `TaskSignals` (domain, action, novelty, urgency, scope_size, external_dependency,
  breaking_change, is_takeover, has_production_impact, has_unknowns). Budget <500ms,
  flock'd cache per `task_marker`.
- `core/thinking_os/formula_composer.py::compose_chain(signals, situation?, threshold?)` →
  `ComposedChain` with provenance (source, preset_id, preset_version, effective_threshold,
  activations, parallel_roles).

### 12 Curated Presets

Stored in `core/thinking_os/presets/registry.yaml`. Each preset has a `match` block
and a `score` (0-15). `PRESET_MIN_SCORE` default 8, tunable via `.coding-os/config.yaml::cognition.preset_min_score`. Best-match wins. SHA256 version hash stamped on every dispatched chain for mid-session drift protection (N.5-C).

| Preset id | Chain | Score |
|---|---|---|
| greenfield-backend-api | F1 → F2 → F3 → F4 → F5 → F6 | 10 |
| greenfield-frontend-feature | F2 → F5 → F6 | 8 |
| schema-migration | F2 → F3 → F8 → F5 → F6 | 10 |
| production-bug-mitigate | F7 → F6 (+ mitigate/post_mortem/F10) | 12 |
| security-audit-full | F8 parallel L1..L5 | 10 |
| legacy-takeover | F2 (reverse) → F6 (characterize) → F4 → F5 → F6 → F11 → F3 | 11 |
| external-integration | F1 → F2 → F3 → F5 → F6 → F8 | 9 |
| refactor-sprint | F11 → F3 → F5 → F6 | 9 |
| docs-only-update | F4 | 9 |
| debug-standard | F7 → F6 → F4 | 8 |
| deploy-release | F8 → F9 → F10 | 9 |
| research-spike | F1 | 8 |

### Routing strategy (in priority order)

1. **Situation override** — if `.coding-os/<agent>/.situation` set, use situation's `dispatch_chain`
2. **Preset match** — scored best-match with `score ≥ effective_threshold`
3. **Composer fallback** — per-role trigger scoring, canonical F1→F11 order
4. **Hard fallback** — `{CLEAR: [F5,F6], COMPLICATED: [F2,F3,F5,F6], COMPLEX: [F1,F2,F3,F5,F6]}` (chain is never empty)

### Legacy — Phase M personas (deprecated)

The `personas/registry.yaml` file with 14 job-title personas (`junior-dev`, `senior-backend`,
...) remains on disk for 1 release. `cos_route_persona` works as a shim — internally
calls `cos_analyze_task` + `cos_compose_chain` — removed in v0.4. Doctor C28 emits WARN
while personas are present.

## 6 Situational Dispatch Chains

Stored in `core/thinking_os/situations/registry.yaml`. Situations override persona
defaults when `.coding-os/<agent>/.situation` marker is set.

| Situation id | Trigger signals | Dispatch chain |
|---|---|---|
| incident-response | production_down, pager_fired | mitigate → communicate → F7 → F6 → post_mortem → F10 |
| onboarding | new_team_member | read_f4 → read_f3 → F5 (scoped) → F6 → F2 |
| scope-change | requirements_changed | F2 (step 1) → traceability → F2 (scenarios) → F3 → F4 |
| external-integration | new_third_party_api | F1 → F2 → F3 → F5 → F6 → F8 |
| design-review | pre_implementation_review | verify_f2_scenarios → verify_adrs → approval_gate |
| existing-project-takeover | legacy_codebase, no_docs | F2 (reverse) → F6 (characterize) → F4 → F5 → F6 → F11 → F3 |

## Intensity Levels

- `light` — F2 Steps 1–5, F5 + F6 minimum; skips F8/F9/F10 unless persona primary
- `standard` — all primary formulas for chosen persona (default)
- `full` — primary + secondary formulas; ambiguity gate refuses any step skip

Resolution order: per-task frontmatter `intensity:` > `.coding-os/config.yaml` > persona default > `standard`.

## Anti-Ambiguity Gate (7 Criteria)

`cos_ambiguity_check(bundle)` fires at PLAN→EXECUTE transition. Missing criteria block
the transition until the supervisor re-dispatches the failing formula.

| Criterion | Meaning |
|---|---|
| `observable` | Behavior visible without code inspection |
| `measurable` | A number or threshold can be assigned |
| `testable` | Given/When/Then scenario writable |
| `scoped` | Boundary defined + finite |
| `owned` | Responsible party named |
| `reversible_or_justified` | Undoable, or strong written reason why not |
| `connected_to_user_value` | Solves a real user pain |

Hook: `core/hooks/enforce-anti-ambiguity.sh` (PreToolUse Write/Edit) reads
`.coding-os/<agent>/.ambiguity-cache`; BLOCKS if `FAIL:<criteria-list>`.
Bypassed for `CLEAR 1` tasks and missing cache (not yet at EXECUTE phase).

## EvidenceBundle Lifecycle

```
task-start → persona resolved → supervisor dispatches F2 → F2 appends to bundle
           → supervisor dispatches F3 → F3 reads F1+F2 slice, appends F3 output
           → ambiguity_check at PLAN→EXECUTE → passes → F5 dispatched
           → F5 appends F5 output → F6 dispatched → F6 appends
           → supervisor returns {action: "done"} → traceability sweep
```

Bundle stored at `.coding-os/<agent>/evidence_bundle_<session_id>.json` (additive,
never mutated in place — each formula appends its block via `cos_supervise_record_output`).

## MCP Tools — 13 Cognition Tools (Phase M + N)

### Phase M — Supervisor & Gates (10)

| Tool | Purpose |
|---|---|
| `cos_route_persona` | **Deprecated shim** (removed v0.4) — internally calls `cos_analyze_task` + `cos_compose_chain` |
| `cos_supervise` | Returns next action (dispatch / backtrack / done) |
| `cos_supervise_record_output` | Append formula output to evidence bundle |
| `cos_dispatch_formula` | Returns rendered prompt + input slice |
| `cos_ambiguity_check` | 7-criteria gate over the bundle |
| `cos_traceability` | Top↔bottom audit (read-only) |
| `cos_backtrack_log` | Record a backtrack event; triggers Anti-Paralysis Guard at ≥3/≥5 |
| `cos_discovery` | Record mid-work discovery (backtrack_now or record_for_later) |
| `cos_situation_detect` | Classify situation from signals |
| `cos_takeover` | Bootstrap takeover path (F2-reverse + F6-characterization + F4) |

### Phase N — Role-Based Routing (3)

| Tool | Purpose |
|---|---|
| `cos_analyze_task` | Extract `TaskSignals` from prompt + MCP context (<500ms budget) |
| `cos_compose_chain` | Return `ComposedChain` from signals (situation > preset > composer > fallback) |
| `cos_role_info` | Return role YAML metadata (prompt_prefix, tools_budget, criteria_required, intensity_steps) |

### Enterprise hooks (Phase N.5)

- **N.5-A Connection pool** (`core/thinking_os/db.py::get_pooled_conn`) — thread-local SQLite
  connections, WAL, `busy_timeout=5000`, `pool_stats()` for observability.
- **N.5-C Preset versioning** — SHA256-16 hash stamped in `ComposedChain.preset_version`;
  mid-session preset edits don't change in-flight chains.
- **N.5-E Multi-tenant override** — `.coding-os/roles.override/F{1..11}_*.yaml` and
  `.coding-os/presets.override/*.yaml` deep-merge on top of core registry at load time.
  Unknown role IDs rejected (roles sealed at F1..F11).

### New Hook (Phase N)

- `core/hooks/track-discovery.sh` (PostToolUse Write/Edit/TodoWrite) — scans output for
  discovery signal phrases; on ≥2 matches, non-blocking reminder to call `cos_discovery`.
  5-minute cooldown. Implements formulas-en.md §Navigation Protocol §4.

Total `cos_*` tools after Phase N: **42** (29 prior + 10 Phase M + 3 Phase N).

## DB Tables Added (v14)

`backtrack_events`, `persona_selections`, `ambiguity_violations`, `formula_dispatches` —
all append-only, indexed by `session_id`. See `core/thinking_os/db.py::_migrate_v14_cognition`.

## Phase N.6 — Behavioral Tracing

> Real runtime observability. Every cognition event writes a JSONL line the agent's
> path through the workflow becomes replayable end-to-end — not just "the test passed".

### Module

`core/thinking_os/tracing.py` exposes:

```python
emit(session_id, kind, data, *, role=None, phase=None)  # append one event
read_trace(session_id) -> list[dict]                     # chronological events
summarize(session_id) -> dict                            # nodes, roles, chain, counts
FLOWCHART_NODES: dict[str, str]                          # kind → flowchart node id
```

Events are flock-safe JSONL written to `.coding-os/<agent>/traces/<session_id>.jsonl`.
Files rotate at 5MB; older rotated files kept with `.<timestamp>.jsonl` suffix for forensics.

### What each event kind maps to

| Event kind | Flowchart node | Emitted by |
|---|---|---|
| `session_init`, `gate_recorded` | `n-sinit`, `n-gate` | session startup + gate recording |
| `analyze_start`, `analyze_done` | `n-analyzer` | `cos_analyze_task` |
| `preset_matched`, `situation_override`, `composer_fallback`, `hard_fallback`, `compose_done` | `n-router` | `cos_compose_chain` |
| `supervise_action`, `role_dispatch`, `role_output_recorded`, `parallel_dispatch` | `n-supervisor` | `cos_supervise`, `cos_supervise_record_output` |
| `backtrack`, `anti_paralysis_warn` | `n-supervisor` | `cos_backtrack_log` |
| `discovery` | `n-supervisor` | `cos_discovery` |
| `ambiguity_check`, `ambiguity_violation` | `n-ambi` | `cos_ambiguity_check` |
| `traceability_check` | `n-trace` | `cos_traceability` |
| `task_done`, `session_end` | `n-done`, `n-end` | lifecycle close |

### CLI surface

```bash
cos cognition trace <session_id>              # pretty timeline (default)
cos cognition trace <session_id> --raw        # raw JSONL lines
cos cognition trace <session_id> --summary    # stats block only
cos cognition trace-replay <session_id>       # CI assertion (exit 0/1)
```

### HTML replay viewer

[docs/cognition-trace-replay.html](cognition-trace-replay.html) — open in a browser,
load a JSONL file (or paste, or use the built-in Stripe-integration sample). The flowchart
nodes highlight in real time as events play; scrubber seeks any point; 0.25x..8x speed
controls. Matches flowchart V1 style verbatim for visual continuity.

### Behavioral tests

[tests/test_phase_n_behavioral.py](../tests/test_phase_n_behavioral.py) — 10 tests:

- 7 canonical scenarios: greenfield-backend, incident-override, schema-migration,
  external-integration, research-spike, legacy-takeover, docs-only. Each asserts
  "which flowchart nodes got visited, in which order, with which provenance".
- Event ordering contract (session_init < gate < analyze < compose < done < session_end).
- Concurrent multi-session isolation (each trace disjoint under flock).
- Summary shape contract (all expected keys present).

Use this pattern to prove production agent behavior rather than just unit-level correctness.

### Why this matters for enterprise

- **Production post-mortems**: load the production session's trace into the replay viewer
  to see exactly which node took a wrong turn.
- **Multi-agent forensics**: each session's trace is disjoint and flock-safe; no cross-talk.
- **Regression proofing**: behavioral tests catch routing drift that unit tests can't see.
- **Tuning feedback**: aggregate traces → "which presets hit most?", "which roles backtrack?",
  etc. (Future N.5-B metrics extractor will compute this directly from trace dir.)
