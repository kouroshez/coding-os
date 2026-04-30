<!-- domain:THINKING_OS | layer:plan | ssot:true | updated:2026-04-24 -->
# Phase N — Role-Based Cognitive Routing

> P: Plan for replacing F1..F11 formula dispatch with semantic role chains (researcher · architect · …) addressed via cos_compose_chain.
> R: Working on thinking_os routing, role yaml, dispatcher, or the agents/roles surface.
> S: Looking for the executed implementation — read AGENTS.md § Cognition & Tracing.
> N: [phase-m-thinking_os-new-formula.md](phase-m-thinking_os-new-formula.md), [thinking_os-formulas.md](thinking_os-formulas.md), [code-os-core-docs/thinkingos-formulas/formulas-en.md](code-os-core-docs/thinkingos-formulas/formulas-en.md)

> Nav: [AGENTS.md](../AGENTS.md) › [roadmap](development-roadmap.md) › **Phase N**
> Predecessor: [Phase M — Hybrid thinking_os v0.3](phase-m-thinking_os-new-formula.md) (implemented but architecturally incorrect on the routing layer)
> Reference: [formulas-en.md](code-os-core-docs/thinkingos-formulas/formulas-en.md), [thinking_os-formulas.md](thinking_os-formulas.md)
> Flowchart (target state): [agent-workflow-flowchart-V1.html](agent-workflow-flowchart-V1.html)

## 1. Context — Why Phase N

Phase M shipped 11 formula-agents (F1..F11), a supervisor state machine, DB v14, 10 MCP tools, and 2 hooks. The **cognitive machinery is correct**. What is wrong is the **routing layer**: Phase M inherited the draft design's idea that *personas = job titles* (`junior-dev`, `senior-backend`, `frontend-dev`, …) with statically assigned `primary_formulas` lists.

### The user's correction (2026-04-20)

> «. !  mcp .. . … .»

Translated: job titles are not cognitive primitives. The **11 formulas are the 11 roles**. An agent that needs to debug enters the Debugging role (F7). An agent that needs to architect enters the Architect role (F3). The same human or AI agent inhabits different roles on different tasks. Routing must be driven by **task signals** (extracted from prompt + memory + MCP context + complexity), not by a static label.

### Architectural mapping (locked in)

```
Old (Phase M):  task → persona-by-job-title → fixed primary_formulas
New (Phase N):  task → TaskSignals → Role Router → {Preset | Composer | Situation} → Formula chain
```

**The 11 roles = the 11 formulas.** One YAML file per role under `core/thinking_os/roles/`. Each role IS a formula; the formula prompt lives in `agents/F<N>_name.md` (unchanged from Phase M).

### Validated gaps carried from Phase M audit

| # | Gap | Phase M state | Phase N fix |
|---|---|---|---|
| 1 | Job-title personas | `personas/registry.yaml` (14 files) | Replace with `roles/` (11 files) |
| 2 | No signal extraction | `cos_route_persona` keyword-match on domain | `task_analyzer.py` + `cos_analyze_task` |
| 3 | No dynamic chain | Fixed `primary_formulas` per persona | `formula_composer.py` + `cos_compose_chain` |
| 4 | No preset cache | — | `presets/registry.yaml` |
| 5 | Anti-Ambiguity bucket-level | `cos_ambiguity_check` returns single bool | Per-step iteration over `criteria_required` |
| 6 | Discovery auto-trigger missing | `cos_discovery` exists but manual | `track-discovery.sh` PostToolUse hook |
| 7 | Anti-Paralysis without progress metric | Counter ≥3 emits warning only | Add `forward_progress` check (bundle delta since last backtrack) |
| 8 | Intensity not enforced in dispatch | `intensity_steps` present in agent files, ignored at dispatch | `cos_dispatch_formula` filters prompt by intensity |
| 9 | Backtrack triggers not deterministic | Agent must self-report via `cos_backtrack_log` | `cos_supervise_record_output` pattern-matches `backtrack_triggers` from role file |
| 10 | Recursion (component too large → F1) | Not wired | `cos_supervise` spawns sub-session on F2 Step 12 signal |
| 11 | Traceability auto-call | `cos_traceability` manual | Auto on PLAN→EXECUTE and SessionEnd |
| 12 | F8/F6 parallel dispatch untested | Supervisor supports `dispatch_parallel` action | Explicit end-to-end test |

---

## 2. Design

### 2.1 — Task Analyzer (new)

Location: [core/thinking_os/task_analyzer.py](core/thinking_os/task_analyzer.py) (new)

**Single public function:**

```python
def analyze_task(
    prompt: str,
    task_marker: str | None,
    session_id: str,
    complexity: str,        # from .thinking_os-gate
    dimensions: int,        # from .thinking_os-gate
) -> TaskSignals
```

**`TaskSignals` (Pydantic, in `cognition_schemas.py`):**

```python
class TaskSignals(BaseModel):
    domain: list[str]                    # backend | frontend | infra | docs | db | ai-ml | security | mobile
    action: Literal["create","modify","debug","research","review","deploy","refactor","document","audit"]
    novelty: float                       # 0..1 (0=seen many times in memory, 1=unprecedented)
    breaking_change: bool                # derived from cos_graph_impact on the target symbol
    has_production_impact: bool          # derived from task swimlane + file paths
    has_unknowns: bool                   # prompt contains "not sure", "maybe", "??", "TBD"
    urgency: Literal["normal","elevated","incident"]
    scope_size: Literal["trivial","small","medium","large","recursive"]   # recursive = F2.12 sub-decompose
    external_dependency: bool            # mentions stripe, twilio, auth0, oauth, api key, sdk, …
    is_takeover: bool                    # repo has low doc density AND recent commits by others
    evidence: dict                       # backing signal sources, for debugging
```

**How signals are extracted:**

| Signal | Source | Technique |
|---|---|---|
| `domain` | prompt text + file paths from task frontmatter | Keyword match on `core/rules/dimension-registry.md` terms |
| `action` | first verb in prompt | Verb classifier (static map: "add/build/create"→create, "fix/debug"→debug, "why/explain"→research, …) |
| `novelty` | `cos_search(prompt_topic, limit=10)` | 1.0 − (count of similar past patterns / 10), floored at 0 |
| `breaking_change` | `cos_graph_impact(target_uid, depth=3)` when target is grep-able | Presence of ≥5 reverse-deps OR touches public API contract |
| `urgency` | prompt tokens: "incident", "down", "pager", "asap", "S0", "S1" | Literal match |
| `scope_size` | prompt length + dimension count + "recursive" hint from F2 | Dimensions 1→trivial, 2-3→small, 4-6→medium, 7-8→large, 9+→recursive |
| `external_dependency` | token match: stripe, twilio, sendgrid, oauth, jwt, kms, sns, sqs, api key, token, sdk | Literal match with allow-list |
| `is_takeover` | `git log --since=30d --format='%ae' <paths>` + `cos_doc_search` density | Commits by >1 author AND doc-density ratio <0.3 |

**Performance budget:** <500ms total (1 grep pass, 1 `cos_search`, 1 optional `cos_graph_impact`, 1 optional `git log`).

**Cached:** `.coding-os/<agent>/.signals` keyed by `task_marker`; re-extracted if task_marker changes.

### 2.2 — Role registry (replaces personas/)

Location: `core/thinking_os/roles/` (11 files, one per formula)

**Shape of `roles/architect.yaml`:**

```yaml
id: architect
role_name: "Architect"
formula_ref: architect
agent_file: agents/architect.md

# when this role should be activated (fed by TaskSignals)
activation:
  primary_triggers:
    - signal: breaking_change
      weight: 3
    - signal: action
      equals: create
      weight: 2
    - signal: scope_size
      in: [medium, large]
      weight: 2
  secondary_triggers:
    - signal: action
      equals: modify
      weight: 1
  deactivators:
    - signal: action
      equals: research        # F1 role handles research, not F3
  min_score: 3                # role activated only if total weight ≥ 3

# dispatch contract
intensity_steps:
  light:    [1, 2]            # NFRs + pattern only
  standard: [1, 2, 3, 4, 5, 6]
  full:     [1, 2, 3, 4, 5, 6]
tools_budget: [cos_graph_query, cos_graph_impact, cos_doc_search, cos_search, Read, Grep]
max_tokens_in: 8000
max_tokens_out: 4000
timeout_s: 120
model_pref:
  complicated: sonnet
  complex: opus

# downstream wiring
output_schema: cognition_schemas.ArchitectOutput
backtrack_triggers:
  - signal_phrase_regex: "(missing|unknown) actor"
    target: F2
    reason_template: "F3 encountered missing actor — backtrack to F2 actor map"
  - signal_phrase_regex: "undefined (capability|requirement)"
    target: F2
  - signal_phrase_regex: "(no|missing) (research|landscape|prior art)"
    target: F1
criteria_required:
  step_1: [scoped, measurable, testable]
  step_2: [scoped, reversible_or_justified, owned]
  step_3: [scoped, testable, observable]
  step_4: [observable, testable, scoped]
  step_5: [scoped, owned, reversible_or_justified]
  step_6: [scoped, observable, owned]

# prompt augmentation
prompt_prefix: |
  You are in the F3 Architect role. Your job is to produce NFRs, pattern,
  DB design, API contracts, infrastructure decisions, and ADRs. You are
  NOT implementing. You are NOT researching options (that was F1). You
  are NOT defining scenarios (that was F2). Output strict ArchitectOutput JSON.
```

All 11 role files follow this shape. The `role_name` is the human-readable noun (Researcher, Analyst, Architect, Documenter, Implementer, Reviewer, Debugger, Security Auditor, Deployer, Observer, Refactorer).

### 2.3 — Formula Composer (new)

Location: [core/thinking_os/formula_composer.py](core/thinking_os/formula_composer.py) (new)

**Algorithm (deterministic):**

```python
def compose_chain(signals: TaskSignals, complexity: str, situation: str | None) -> list[str]:
    # 1. Situation override (highest priority)
    if situation:
        return load_situation(situation).dispatch_chain    # e.g. incident-response

    # 2. Preset lookup (scored best-match)
    best_preset = match_preset(signals)
    if best_preset and best_preset.score >= PRESET_MIN_SCORE:
        return best_preset.chain

    # 3. Composer fallback — score each role
    scored = []
    for role in load_all_roles():
        score = score_role(role, signals, complexity)
        if score >= role.activation.min_score:
            scored.append((role.id, score))

    # 4. Order by canonical phase sequence: F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9 → F10 → F11
    scored.sort(key=lambda x: canonical_phase_order(x[0]))
    chain = [role_id for role_id, _ in scored]

    # 5. Apply intensity filter
    if complexity == "CLEAR":
        chain = [r for r in chain if r in {"implementer","reviewer"}]   # Light default
    return chain
```

**`score_role(role, signals, complexity)`** sums the weights of matching `primary_triggers` and `secondary_triggers`, subtracts any `deactivators`, and returns the total. A role with score ≥ `min_score` joins the chain.

### 2.4 — Presets registry

Location: [core/thinking_os/presets/registry.yaml](core/thinking_os/presets/registry.yaml) (new)

Curated chains for high-frequency signal combinations — validated via dogfood:

```yaml
presets:
  - id: greenfield-backend-api
    match:
      action: create
      domain: [backend, api]
      novelty_gte: 0.4
      scope_size: [medium, large]
    chain: [F1, F2, F3, F4, F5, F6]
    rationale: "Standard bootstrap for a new backend service — research, analysis, architecture, docs, implement, verify."
    score: 10

  - id: schema-migration
    match:
      action: modify
      breaking_change: true
      domain: [db, backend]
    chain: [F2, F3, F8, F5, F6]
    rationale: "Schema changes need decision table update + architecture review + security audit (data protection) before implementation."
    score: 10

  - id: production-bug-mitigate
    match:
      urgency: incident
    chain_before_formulas: ["mitigate", "communicate"]
    chain: [F7, F6]
    chain_after_formulas: ["post_mortem", "update_F10"]
    rationale: "formulas-en.md §Incident Response — restore service BEFORE root-cause."
    score: 12

  - id: security-audit-full
    match:
      action: audit
      domain: [security, auth]
    chain: [F8]              # supervisor dispatches F8's 5 layers in parallel
    parallel: true
    score: 10

  - id: legacy-takeover
    match:
      is_takeover: true
    chain: [analyst_reverse, reviewer_characterization, documenter, implementer, reviewer, refactorer, architect]
    rationale: "formulas-en.md §Existing Project Takeover — reverse-engineer, stabilize, then evolve."
    score: 11

  - id: frontend-feature-standard
    match:
      action: create
      domain: [frontend]
      novelty_gte: 0.2
    chain: [F2, F5, F6]
    score: 8

  - id: docs-only-update
    match:
      action: document
      domain: [docs]
    chain: [F4]
    score: 9

  - id: refactor-sprint
    match:
      action: refactor
    chain: [F11, F3, F5, F6]
    score: 9
```

`match_preset(signals)` returns the preset with highest `score` among those whose `match` block is fully satisfied. `PRESET_MIN_SCORE = 8`.

### 2.5 — Supervisor changes (Phase M keeps working)

The supervisor state machine in `cognition.py` is unchanged. Only the **ROUTING** state gets new inputs:

```python
# Before (Phase M):
def route(state):
    persona = cos_route_persona(state.task)
    return persona.primary_formulas

# After (Phase N):
def route(state):
    signals = analyze_task(prompt=state.prompt, task_marker=state.task_marker, ...)
    situation = read_marker(".situation")
    chain = compose_chain(signals, complexity=state.complexity, situation=situation)
    return chain
```

All downstream states (`DISPATCHING`, `AWAITING_AGENT`, `INTEGRATING`, backtracking) remain identical. Agent files (`agents/F*.md`) remain identical. DB v14 remains identical. Hooks from Phase M remain active.

### 2.6 — New MCP tools (3)

| Tool | Purpose | Latency budget |
|---|---|---|
| `cos_analyze_task(prompt, complexity)` | Run task analyzer, return TaskSignals | <500ms |
| `cos_compose_chain(signals, situation?)` | Return the composed formula chain | <30ms |
| `cos_role_info(role_id)` | Return role metadata (prompt_prefix, tools_budget, criteria_required) | <10ms |

**Deprecated / repurposed:** `cos_route_persona` remains as a backward-compat wrapper for 1 release — internally calls `cos_analyze_task` → `cos_compose_chain` → returns a synthetic "persona" record so old code doesn't break. Scheduled for removal in v0.4.

**Existing tools updated:**
- `cos_dispatch_formula` — now filters the rendered prompt by `intensity_steps[current_intensity]` before returning it (gap #8 fixed).
- `cos_ambiguity_check` — now iterates per-step using `criteria_required` from the role file and returns `list[AmbiguityViolation]` instead of `bool` (gap #5 fixed).
- `cos_supervise_record_output` — now pattern-matches the output against the role's `backtrack_triggers` regex list and auto-emits backtrack actions (gap #9 fixed).
- `cos_supervise` — on INTEGRATING state, if any formula output contains an F2.12 "sub-component too large" marker, spawn sub-session with new `task_marker` (gap #10 fixed).

### 2.7 — New hook

`core/hooks/track-discovery.sh` (PostToolUse on Write/Edit/TodoWrite outputs):
- Scans agent output for discovery signal phrases: "I notice", "found a new", "discovered that", "missing", "undocumented", "hidden dependency".
- Writes the match to `observations` table with `kind='discovery'` and fires a non-blocking reminder asking the agent to call `cos_discovery` explicitly with an impact assessment.

### 2.8 — Backward compatibility

- `personas/registry.yaml` — **deleted** in Phase N.5 (after role cutover verified). Not kept as deprecated to avoid parallel SSOT (violates P1).
- `.persona` marker — renamed to `.role` / `.roles` (plural, since chain has multiple). `task-start.sh` writes both until v0.4.
- Rule 16 in AGENTS.md — rewritten (see §4.5 below).

### 2.9 — Failure modes (explicit policy, same shape as Phase M)

| Failure | Detection | Policy |
|---|---|---|
| **TaskSignals extraction throws** | `analyze_task` wrapped in try/except | Return `TaskSignals(evidence={"error": ...})` with all fields at default; composer falls back to canonical chain by complexity (`CLEAR→[F5,F6]`, `COMPLICATED→[F2,F3,F5,F6]`, `COMPLEX→[F1,F2,F3,F5,F6]`) |
| **No preset matches & composer yields empty chain** | Empty list after scoring | Fallback to `[F2, F5, F6]` minimum and log a warning; never return empty chain (supervisor would deadlock) |
| **Signal source unavailable** (MCP down, git absent) | Each extractor returns `None` on error | Signal recorded as `None` in `evidence`; composer treats `None` as "no signal" (lowest weight) |
| **Role file malformed YAML** | `load_role(id)` raises | Doctor C29 catches at startup; agent-side fails loud with `fail("internal", "role_file_invalid")` |

---

## 3. Rollout — 4 vertical slices

**N.1 — Schemas + role registry + presets + task analyzer (foundation)**
- New: `core/thinking_os/roles/F{1..11}_<name>.yaml` (11 files)
- New: `core/thinking_os/presets/registry.yaml`
- New: `core/thinking_os/task_analyzer.py`
- New: `core/thinking_os/formula_composer.py`
- Edit: `core/thinking_os/cognition_schemas.py` — add `TaskSignals` model
- New tests: `tests/test_task_analyzer.py` (synthetic prompts → expected signals), `tests/test_formula_composer.py` (signal scenarios → expected chain)
- Verify: `uv run pytest tests/test_task_analyzer.py tests/test_formula_composer.py -q`

**N.2 — Supervisor rewire + 3 new MCP tools + 3 updated tools**
- Edit: `core/thinking_os/cognition.py` — ROUTING state uses new analyzer + composer
- New: `core/thinking_os/tools/cognition.py` — add `cos_analyze_task`, `cos_compose_chain`, `cos_role_info`
- Edit same file — rewrite `cos_ambiguity_check` (per-step), `cos_dispatch_formula` (intensity filter), `cos_supervise_record_output` (auto-backtrack on trigger pattern match), `cos_supervise` (recursion spawn on F2.12 signal)
- Edit: `core/thinking_os/server.py` — register 3 new tools
- Keep: `cos_route_persona` as backward-compat wrapper (1 release)
- Tests: add cases in `core/thinking_os/tests/test_cognition_tools.py`
- Verify: `uv run --extra rag pytest core/thinking_os/tests/test_cognition_tools.py -q && python core/thinking_os/server.py --test`

**N.3 — Hooks + auto-traceability + discovery hook**
- New: `core/hooks/track-discovery.sh` (PostToolUse)
- Edit: `core/hooks/registry.yaml` — declare track-discovery
- Edit: `core/thinking_os/session_summary.py` — auto-call `cos_traceability` at SessionEnd (gap #11)
- Edit: `core/hooks/enforce-anti-ambiguity.sh` — read per-step violations from `ambiguity_violations` v14 table instead of bucket bool
- Run: `make regen-adapter-templates`
- Tests: extend `tests/test_hooks_phase_m.py` + new `tests/test_phase_n_hooks.py`
- Verify: `make verify-hooks && uv run pytest tests/test_hooks_phase_m.py tests/test_phase_n_hooks.py -q`

**N.4 — Cutover + cleanup + docs**
- Edit: `core/scripts/task-start.sh` — call `cos_analyze_task` + `cos_compose_chain`, write `.role` (primary role) and `.roles` (full chain) markers
- Edit: `core/thinking_os/task_parser.py` — parse `roles:` list frontmatter field (alongside existing `persona:` for compat)
- Edit: `core/hooks/enforce-task-start.sh` — require `.role` marker for COMPLICATED+ (replaces `.persona`)
- **Delete:** `core/thinking_os/personas/registry.yaml` + all references
- Edit: `cli/doctor.py` — rename C28 to check `roles/` not `personas/`; add C29 for preset registry + composer reachability
- Edit: [AGENTS.md](../AGENTS.md) Rule 16 — rewrite "Persona" → "Role" (see §4.5)
- Edit: [docs/thinking_os-formulas.md](thinking_os-formulas.md) — swap persona section for role section
- New: `docs/phase-n-role-based-routing-plan.md` (this file)
- Edit: `cli/cognition.py` — add `cos cognition roles` subcommand (list active role chain, signals, preset match)
- Edit: `tests/test_persona_integration.py` — rename to `tests/test_role_integration.py`, rewrite scenarios
- Run: `make safe-test && make verify && make dogfood`
- Verify: `cos doctor` (C1..C29 PASS), flowchart V1 updated if routing model drifted

---

## 4. Critical files (create / edit / delete)

| Action | Path | Why |
|---|---|---|
| New | `core/thinking_os/roles/researcher.yaml` | F1 role metadata |
| New | `core/thinking_os/roles/analyst.yaml` | F2 role |
| New | `core/thinking_os/roles/architect.yaml` | F3 role |
| New | `core/thinking_os/roles/documenter.yaml` | F4 role |
| New | `core/thinking_os/roles/implementer.yaml` | F5 role |
| New | `core/thinking_os/roles/reviewer.yaml` | F6 role |
| New | `core/thinking_os/roles/debugger.yaml` | F7 role |
| New | `core/thinking_os/roles/security_auditor.yaml` | F8 role |
| New | `core/thinking_os/roles/deployer.yaml` | F9 role |
| New | `core/thinking_os/roles/observer.yaml` | F10 role |
| New | `core/thinking_os/roles/refactorer.yaml` | F11 role |
| New | `core/thinking_os/presets/registry.yaml` | Validated chain combinations |
| New | `core/thinking_os/task_analyzer.py` | Signal extractor |
| New | `core/thinking_os/formula_composer.py` | Dynamic chain builder |
| New | `core/hooks/track-discovery.sh` | Auto-trigger for Discovery Protocol |
| Edit | `core/thinking_os/cognition.py` | ROUTING state rewire, recursion spawn |
| Edit | `core/thinking_os/cognition_schemas.py` | Add `TaskSignals` model |
| Edit | `core/thinking_os/tools/cognition.py` | 3 new tools + 4 updated tools |
| Edit | `core/thinking_os/server.py` | Register 3 new tools |
| Edit | `core/thinking_os/task_parser.py` | Parse `roles:` list |
| Edit | `core/thinking_os/session_summary.py` | Auto-call `cos_traceability` |
| Edit | `core/hooks/enforce-anti-ambiguity.sh` | Per-step violations |
| Edit | `core/hooks/enforce-task-start.sh` | Require `.role`, not `.persona` |
| Edit | `core/hooks/registry.yaml` | Declare track-discovery |
| Edit | `core/scripts/task-start.sh` | Write `.role` + `.roles` |
| Edit | [AGENTS.md](../AGENTS.md) | Rewrite Rule 16, update Phase M → Phase N status |
| Edit | [docs/thinking_os-formulas.md](thinking_os-formulas.md) | Replace persona section with role section |
| Edit | [docs/agent-workflow-flowchart-V1.html](agent-workflow-flowchart-V1.html) | Remove Phase N "target" badges (promote to implemented) |
| Edit | `cli/doctor.py` | C28 roles, C29 presets/composer |
| Edit | `cli/cognition.py` | `cos cognition roles` subcommand |
| **Delete** | `core/thinking_os/personas/registry.yaml` | SSOT violation (replaced by roles/) |
| Edit | `tests/test_persona_integration.py` → `tests/test_role_integration.py` | Rename + rewrite |
| New | `tests/test_task_analyzer.py` | Signal extraction tests |
| New | `tests/test_formula_composer.py` | Chain composition tests |
| New | `tests/test_phase_n_hooks.py` | track-discovery + auto-traceability |

### 4.5 — AGENTS.md Rule 16 rewrite

Current (Phase M, to be replaced):

> 16. **Persona must be set for COMPLICATED+ tasks (Phase M)** — Any task classified as COMPLICATED or COMPLEX MUST have a persona marker (`.coding-os/<agent>/.persona`) populated before code writing begins. …

New (Phase N):

> 16. **Role chain must be composed for COMPLICATED+ tasks (Phase N)** — Any task classified as COMPLICATED or COMPLEX MUST have a role chain composed before code writing begins. The chain is the output of `cos_compose_chain(signals)` and is written to `.coding-os/<agent>/.roles` (chain) and `.coding-os/<agent>/.role` (currently active role). `task-start.sh` auto-populates both via `cos_analyze_task` + `cos_compose_chain`; `enforce-task-start.sh` emits a non-blocking advisory if missing. **Roles are the 11 formulas themselves** — F1 Researcher, F2 Analyst, F3 Architect, F4 Documenter, F5 Implementer, F6 Reviewer, F7 Debugger, F8 Security Auditor, F9 Deployer, F10 Observer, F11 Refactorer. Registry: `core/thinking_os/roles/F{1..11}_*.yaml`. Rationale: routing by cognitive role (what kind of thinking is happening right now) is a more stable primitive than routing by job title — the same agent debugs (F7), architects (F3), and documents (F4) on different tasks; a job-title persona obscures that.

---

## 5. Verification (end-to-end)

```bash
# 1. New unit tests (task analyzer + composer + hooks)
uv run pytest tests/test_task_analyzer.py tests/test_formula_composer.py tests/test_phase_n_hooks.py -q

# 2. Rewired integration tests
uv run pytest tests/test_role_integration.py -q

# 3. Full safe-test (≤30s)
make safe-test

# 4. Existing full suite
make verify

# 5. Dogfood — coding-os uses itself
make dogfood

# 6. MCP server self-test
python core/thinking_os/server.py --test

# 7. Doctor (C1..C29)
cos doctor

# 8. Manual signal → chain smoke
cos cognition analyze "add Stripe webhook for subscription renewal"
# expected signals: domain=[backend], action=create, external_dependency=true
# expected preset: "external-integration-style" fallback or composer → [F1, F2, F3, F5, F6, F8]

# 9. Situational override still wins
echo "CHAOTIC 1" > .coding-os/claude/.thinking_os-gate
echo "incident-response" > .coding-os/claude/.situation
cos cognition chain
# expected: [mitigate, communicate, F7, F6, post_mortem, update_F10]

# 10. Backward compat (1 release)
# cos_route_persona still callable — returns synthetic record warning "deprecated, use cos_compose_chain"
```

### 5.1 — Dogfood checks

Three synthetic tasks run through the full pipeline to prove routing works end-to-end:

| Task | Expected signals | Expected preset / chain |
|---|---|---|
| "Add pagination to /users endpoint" | action=modify, domain=[backend,api], novelty≈0.2 | `frontend-feature-standard`-like composer chain `[F2, F5, F6]` |
| "Payment webhook from Stripe" | action=create, external_dependency=true, domain=[backend] | `external-integration` preset → `[F1, F2, F3, F5, F6, F8]` |
| "Users report slow dashboard at 10:15 AM" | urgency=incident | situation override `incident-response` → `[mitigate, F7, F6, post_mortem, F10]` |

Each run must produce a non-empty chain, record a `formula_dispatches` row per dispatched role, and complete with a traceability sweep at SessionEnd.

---

## 6. Non-goals (explicit)

- **Do NOT keep personas/ as deprecated SSOT.** Hard delete — P1 forbids parallel truths. Backward compat is the `cos_route_persona` shim tool, not file duplication.
- **Do NOT extend role registry beyond F1..F11.** If a role is needed that doesn't map to a formula, that's a signal the formula file is incomplete — edit the formula (and `formulas-en.md`), not the role registry.
- **Do NOT build a web UI for role inspection in this phase.** CLI (`cos cognition roles`, `cos cognition analyze`) + flowchart V1 are sufficient. UI is Phase O if ever.
- **Do NOT implement dynamic learning of new presets.** Presets are hand-curated. `cos_learn_validate` feedback may surface preset candidates in `cos cognition suggest-preset`, but promotion to `presets/registry.yaml` is a human edit.
- **Do NOT let the composer produce chains outside canonical F1→F11 phase order.** If a signal suggests F8 before F3, fail with a warning — reorder signals or edit presets.
- **Do NOT add a "custom role" escape hatch** where users define ad-hoc roles per project. That re-introduces the persona anti-pattern. Roles = formulas, end of discussion.
- **Do NOT auto-promote discoveries to tasks without agent opt-in.** `track-discovery.sh` reminds, it does not call `cos_task_create` on behalf of the agent.
- **Do NOT parallelize TaskAnalyzer across multiple signal sources.** 500ms budget is plenty sequential; parallel introduces ordering bugs in signal merging.

---

## 7. Locked decisions (user-approved 2026-04-20)

All five open questions were reviewed under the enterprise-grade, multi-agent concurrency lens. Decisions:

1. **`cos_route_persona` deprecation window** — **LOCKED: 1 minor release shim with loud deprecation.** Shim lives as a thin wrapper that internally calls `cos_analyze_task` + `cos_compose_chain` and returns a synthetic record. Every call emits a `metrics` row `deprecated_tool_called{name=cos_route_persona}` and the envelope carries `meta.deprecated=true`. Doctor C29 reports usage count over the last 7 days; when count reaches zero, v0.4 removes the shim. *Rationale:* coding-os is a meta-project — removing tools without migration window breaks every downstream project that upgraded mid-session.
2. **`PRESET_MIN_SCORE`** — **LOCKED: tunable via `.coding-os/config.yaml::cognition.preset_min_score`, default 8, range 0-15.** Every `formula_dispatches` row stamps the effective threshold + match source (`preset | composer | situation | fallback`) so tuning is data-driven. *Rationale:* different teams need different strictness; observability + validation prevents brittle misconfiguration.
3. **`is_takeover` git cost** — **LOCKED: time-box 200ms + 24h cache + path-cap + flock.**
   1. First check `.coding-os/.takeover-verdict` (flock, 24h TTL) — all concurrent sessions share it.
   2. On miss, run `timeout 200 git log --since=30d <source_paths>` where `<source_paths>` comes from `stack.yaml::source_paths` (fallback: top-level non-hidden dirs).
   3. On timeout, fall back to doc-density heuristic only.
   *Rationale:* with 10+ concurrent agents, naive git log on a large repo is an IO storm; layered caching eliminates thrash.
4. **Role `prompt_prefix` vs `agent_file`** — **LOCKED: keep both separate; this is SoC, not duplication.** Prefix = routing-time role voice (1-2 sentences); agent file = cognitive procedure (the formula's 12 steps). Different edit lifecycles, different reviewers, different observability signals (`prompt_prefix_hash` stamped on every dispatch). No N.5 merge scheduled. *Rationale:* DRY is a code principle; prompts are content — controlled duplication is acceptable when the two lifecycles are independent.
5. **`/cos-analyze` slash command** — **LOCKED: yes, add to both adapters as a thin wrapper over `cos_analyze_task`.** `adapters/claude/commands/cos-analyze.md` + `adapters/codex/commands/cos-analyze.md`, each <30 lines. *Rationale:* dry-run "what would this route to?" is a high-value affordance for enterprise dev teams and multi-agent coordination. SSOT stays in the MCP tool.

---

## 7a. N.5 — Enterprise Hardening (MANDATORY before production rollout)

These six items were added to the plan after the enterprise/multi-agent concurrency review. Without them the system is not safe for concurrent multi-agent load.

| # | Item | Location | Implementation sketch |
|---|---|---|---|
| A | **Connection pool for SQLite** | `core/thinking_os/db.py` | `threading.local` pool, max 20 connections, WAL mode (already on), `PRAGMA busy_timeout=5000` per connection. Replace per-call `sqlite3.connect` with `get_pooled_conn()`. |
| B | **Observability metrics** | `core/thinking_os/tools/cognition.py` + `metrics` table | Emit on every dispatch/analyze/compose: `cognition_chain_latency_ms` (p50/p99 via `cos_metric_trend`), `preset_match_rate`, `empty_chain_fallback_count`, `role_backtrack_rate`, `ambiguity_violation_rate`, `composer_vs_preset_ratio`. Grafana-compatible labels. |
| C | **Preset versioning + stamping** | `core/thinking_os/presets/registry.yaml` + `evidence_bundle.json` | Add `version: <sha256-of-yaml-content>` auto-computed at load; stamp bundle at ROUTING state; session continues with stamped version even if file changes mid-session. Prevents chain-drift. |
| D | **Circuit breaker per role** | `core/thinking_os/cognition.py` | Per-role counter in `.coding-os/<agent>/.role-health.json`. 3 consecutive invalid outputs → mark `degraded`, supervisor skips to next role or backtracks. New hook `warn-role-degraded.sh` alerts on SessionStart if any role degraded in last 24h. |
| E | **Multi-tenant role override** | File system | Supervisor loads `core/thinking_os/roles/*.yaml` then merges `.coding-os/roles.override/*.yaml` on top. Org can override metadata but cannot add roles outside F1..F11 (schema rejects unknown role IDs). Same mechanism for presets (`.coding-os/presets.override/`). |
| F | **Rate limit expensive signals** | `core/thinking_os/task_analyzer.py` | Semaphore around `cos_graph_impact` (max 5 concurrent); queued calls wait up to 1s then fall back to "no signal". Prevents IO storm from 10+ simultaneous `task-start`. |

### N.5 tests

- `tests/test_connection_pool.py` — 20 parallel threads hammering `cos_search`; no `database is locked` errors.
- `tests/test_preset_versioning.py` — modify registry mid-session, assert stamped version still used.
- `tests/test_circuit_breaker.py` — inject 3 consecutive role failures, assert `degraded` marker written + next call skips role.
- `tests/test_role_override.py` — place override YAML, assert merged metadata wins; attempt to add new role ID, assert rejection.
- `tests/test_rate_limit_graph.py` — fire 20 concurrent `cos_graph_impact`, assert max 5 in flight + queued callers get "no signal" fallback after 1s.
- `tests/test_observability_metrics.py` — run a full synthetic session, assert 6 expected metric keys appear in `metrics` table.

### N.5 verification

```bash
# Concurrent stress: 10 agents, 20 task-starts, full chain
scripts/bench_concurrent_cognition.py --agents 10 --tasks-per-agent 20

# Expected outcomes (pass criteria):
#   - zero "database is locked" errors
#   - p99 chain-composition latency < 1500ms
#   - zero empty-chain fallbacks
#   - all metrics populated
```

---

## 7b. Open questions (genuinely open — require user input before N.1)

None. All items above are locked. Proceed to N.1.

---

## 8. Timeline estimate

| Slice | Scope | Estimate |
|---|---|---|
| N.1 ✅ | Schemas + role files + preset registry + analyzer + composer + unit tests | 2 days |
| N.2 ✅ | Supervisor rewire + 3 new tools + 4 updated tools + tests + connection pool (A) | 1.5 days |
| N.3 ✅ | Hooks + auto-traceability + discovery trigger + tests | 1 day |
| N.4 ✅ | Cutover + docs + dogfood + verification | 1.5 days |
| N.5 ⚠️ partial | Enterprise hardening: A (pool) + C (versioning) + E (override) shipped; B (metrics) + D (circuit breaker) + F (rate limit) deferred post-usage-data | 2 days |
| N.6 ✅ | Behavioral tracing: tracing.py + FLOWCHART_NODES map + instrumented 5 MCP tools + `cos cognition trace` CLI + HTML replay viewer + 10 behavioral tests | 1 day |
| **Total shipped** | | **~8 days** |

Gate between slices: all tests green + `make verify` + `cos doctor` PASS. Slice N.4 cannot start until N.1-N.3 are merged because the `.persona` → `.role` cutover has no middle ground.

### What N.6 added post-plan

The original plan ended at N.5. During dogfood review the user requested proper behavioral
verification — not just "did the function return the right chain", but "did the agent
actually traverse the correct path on the flowchart in the correct order". This became N.6:

- `core/thinking_os/tracing.py` — JSONL trace emitter with `FLOWCHART_NODES` mapping.
- 5 MCP tools instrumented (`cos_analyze_task`, `cos_compose_chain`, `cos_supervise`,
  `cos_supervise_record_output`, `cos_backtrack_log`) emit trace events on every call.
- `cos cognition trace <session_id>` CLI — pretty timeline + `--raw` + `--summary` +
  `cos cognition trace-replay` CI assertion.
- [docs/cognition-trace-replay.html](cognition-trace-replay.html) — HTML replay viewer
  that animates the flowchart nodes as events play, with file/paste input, timeline
  scrubber, 0.25x..8x playback speed, and a built-in Stripe-integration sample trace.
- [tests/test_phase_n_behavioral.py](../tests/test_phase_n_behavioral.py) — 10 tests
  asserting real agent paths across 7 canonical scenarios + event ordering + concurrent
  session isolation + summary shape contract.

Enterprise use-cases unlocked: production post-mortems ("which role backtracked, why?"),
multi-agent forensics (disjoint flock-safe per-session files), behavioral regression
testing, and future aggregate tuning (feeds into N.5-B metrics extractor).

---

## 9. Risk log

| Risk | Mitigation |
|---|---|
| Signal extractor false positives (e.g. "incident" token in a documentation task) | Weight combinations — urgency=incident requires ≥2 matching tokens, not 1 |
| Empty chain from composer (regression vs Phase M fixed chains) | Hard fallback `[F2, F5, F6]` + warning log |
| Role cutover breaks session in flight | N.4 rename writes both `.persona` (synthetic) and `.role` for 1 release |
| `cos_graph_impact` latency blocks task-start | Timeout 200ms on signal extraction, degrade gracefully |
| Dogfood shows composer chain is wrong for a common case | Add a preset — that's literally what the preset layer exists for |
| Doctor C28/C29 flake on CI | Registries loaded once at startup, cached; unit test load path |

---

## 10. Success criteria

- [ ] `cos cognition analyze "<prompt>"` returns a TaskSignals JSON for every synthetic prompt in §5.1
- [ ] `cos cognition chain` returns a non-empty chain for every classified task
- [ ] `personas/` directory deleted, no references remain (grep `personas/` in core/ returns zero)
- [ ] Rule 16 in AGENTS.md reads "Role chain must be composed", not "Persona must be set"
- [ ] Doctor C28 passes (roles registry valid, presets valid, composer reachable, analyzer reachable)
- [ ] `make safe-test` passes in ≤30s
- [ ] `make dogfood` exercises all 3 synthetic scenarios in §5.1 with correct chains
- [ ] EvidenceBundle contains per-role outputs for at least 3 roles in a COMPLICATED task
- [ ] `ambiguity_violations` table records per-step violations (not bucket-level) on a deliberately ambiguous task
- [ ] `backtrack_events` table has ≥1 auto-recorded backtrack from a role's `backtrack_triggers` regex match
- [ ] Flowchart V1 updated — "Phase N target" badges removed, "implemented" status shown

---

## 11. After N ships

- **Phase O (maybe)** — Role dashboards: web view of active chain per session, historical chain performance (which chains led to fewer backtracks / faster close), preset suggestions from warm history.
- **Phase P (maybe)** — Cross-session role pattern learning: `cos_learn_extract` surfaces emergent role chains that human-curated presets missed. Promote via `cos cognition suggest-preset` review queue.
